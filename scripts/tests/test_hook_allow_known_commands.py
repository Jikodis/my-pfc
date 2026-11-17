"""Tests for scripts/hook-allow-known-commands.py (the PreToolUse Bash hook).

Each case runs the hook as a subprocess, the way Claude Code does, and
asserts the exact stdout: the allow JSON, or nothing (fall through).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "scripts" / "hook-allow-known-commands.py"


def allow(*words: str) -> str:
    reason = "Every command word is on the allow list: " + ", ".join(sorted(words))
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": reason,
    }}) + "\n"


# A synthetic allow list, shaped like the rules a project grants its skills.
# The tests use their own list so they do not depend on the repo's settings.
ALLOW = [
    "Bash(date *)", "Bash(echo *)", "Bash(jq *)", "Bash(mv *)", "Bash(cat *)",
    "Bash(git *)", "Bash(bash *)", "Bash(cd *)", "Bash(python3 *)",
    "Bash(systemctl --user *)", "Bash(mktemp)",
    "Bash(tmp=*)", "Bash(TODAY=*)", "Bash(TZ=*)",
]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A fixture project with the synthetic allow list."""
    settings = {"permissions": {"allow": ALLOW, "deny": []}}
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps(settings))
    (tmp_path / "user-config").mkdir()
    return tmp_path


def set_rules(path: Path, **rules) -> None:
    """Write deny/ask rules into a settings file, creating it if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text()) if path.exists() else {}
    data.setdefault("permissions", {}).update(rules)
    path.write_text(json.dumps(data))


def run(project: Path, stdin: str, python: str = sys.executable) -> subprocess.CompletedProcess:
    # CLAUDE_CONFIG_DIR points at an empty user-level folder inside the fixture,
    # so the real ~/.claude settings never leak into a test.
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project),
               CLAUDE_CONFIG_DIR=str(project / "user-config"))
    return subprocess.run([python, str(HOOK)], input=stdin, capture_output=True,
                          text=True, env=env, timeout=10)


def bash(project: Path, command: str, **extra) -> str:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, **extra}
    proc = run(project, json.dumps(payload))
    assert proc.returncode == 0
    return proc.stdout


# ---- the three original probe commands -----------------------------------

def test_probe_1_today_substitution_allowed(project):
    cmd = 'TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date \'+%Y-%m-%d\'); echo "$TODAY"'
    assert bash(project, cmd) == allow("date", "echo")


def test_probe_2_redirect_to_tmp_falls_through(project):
    assert bash(project, "jq -c '.' 6-tasks/_data/tasks.ndjson > /tmp/x && echo ok") == ""


def test_probe_3_substitution_then_jq_allowed(project):
    cmd = 'TODAY=$(date +%F) && jq -cn --arg d "$TODAY" \'{date: $d}\''
    assert bash(project, cmd) == allow("date", "jq")


# ---- real skill shapes ---------------------------------------------------

def test_jq_write_pattern_allowed(project):
    cmd = ("jq -c --arg id \"task-1\" 'if .id == $id then .status = \"done\" else . end' "
           "6-tasks/_data/tasks.ndjson > data/.jq_update.tmp "
           "&& mv data/.jq_update.tmp 6-tasks/_data/tasks.ndjson")
    assert bash(project, cmd) == allow("jq", "mv")


def test_quoted_heredoc_body_is_literal(project):
    cmd = "cat <<'EOF'\nnot run: $(rm -rf /)\nEOF"
    assert bash(project, cmd) == allow("cat")


def test_unquoted_heredoc_body_substitution_is_checked(project):
    # With an unquoted delimiter bash expands the body, so $(rm ...) would run.
    cmd = "cat <<EOF\nrun: $(rm -rf /)\nEOF"
    assert bash(project, cmd) == ""


def test_commit_message_heredoc_in_substitution(project):
    cmd = "git commit -m \"$(cat <<'EOF'\nsystem: x\n\nbody $(not run)\nEOF\n)\""
    assert bash(project, cmd) == allow("cat", "git")


# ---- boundary cases ------------------------------------------------------

def test_disallowed_word_in_substitution(project):
    assert bash(project, "echo $(rm -rf /)") == ""


def test_disallowed_top_level_word(project):
    assert bash(project, "curl http://x") == ""


def test_bash_c_allowed_because_list_allows_bash(project):
    # Bash(bash *) is on the allow list, so Claude Code itself already allows
    # this without the hook. The hook is not wider than the list: it only
    # repeats the list's own verdict for commands the list cannot parse.
    assert bash(project, "bash -c 'anything at all'") == allow("bash")


def test_sudo_falls_through(project):
    assert bash(project, "sudo jq . x") == ""


def test_redirect_to_home_falls_through(project):
    assert bash(project, "jq . x > ~/x") == ""


def test_redirect_to_parent_falls_through(project):
    assert bash(project, "jq . x > ../x") == ""


def test_backtick_allowed_word(project):
    assert bash(project, "echo `date +%F`") == allow("date", "echo")


def test_backtick_disallowed_word(project):
    assert bash(project, "echo `curl http://x`") == ""


def test_nested_substitution(project):
    assert bash(project, "echo $(echo $(date))") == allow("date", "echo")


def test_parameter_expansion_in_string(project):
    assert bash(project, 'echo "${LOCAL_TZ:-America/Denver}"') == allow("echo")


def test_deny_rule_wins(project):
    path = project / ".claude" / "settings.json"
    settings = json.loads(path.read_text())
    settings["permissions"]["deny"] = ["Bash(git push *)"]
    path.write_text(json.dumps(settings))
    assert bash(project, "git status && git push origin main") == ""
    assert bash(project, "git status") == allow("git")


def test_multiword_prefix_rule_is_matched_word_by_word(project):
    assert bash(project, "X=$(systemctl --user is-active foo)") == allow("systemctl")
    assert bash(project, "X=$(systemctl stop foo)") == ""


def test_exact_rule_takes_no_arguments(project):
    assert bash(project, "tmp=$(mktemp)") == allow("mktemp")
    assert bash(project, "tmp=$(mktemp -d /tmp/x)") == ""


def test_path_changing_assignment_falls_through(project):
    assert bash(project, "PATH=/tmp/evil jq . x") == ""


def test_cd_then_redirect_falls_through(project):
    assert bash(project, "cd /tmp && echo hi > x") == ""


def test_process_substitution_falls_through(project):
    assert bash(project, "cat <(date)") == ""


def test_arithmetic_falls_through(project):
    assert bash(project, "echo $((1+2))") == ""


# ---- inputs the hook ignores ---------------------------------------------

def test_non_bash_tool_is_ignored(project):
    proc = run(project, json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "x"}}))
    assert (proc.returncode, proc.stdout) == (0, "")


def test_malformed_stdin(project):
    proc = run(project, "{not json")
    assert (proc.returncode, proc.stdout) == (0, "")


def test_unbalanced_quote(project):
    assert bash(project, "echo 'oops") == ""


@pytest.mark.skipif(not shutil.which("/usr/bin/python3"), reason="no system python")
def test_runs_under_system_python(project):
    stdin = json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo $(date)"}})
    proc = run(project, stdin, python="/usr/bin/python3")
    assert (proc.returncode, proc.stdout) == (0, allow("date", "echo"))


# ---- fix round 1 ----------------------------------------------------------

# 1. backtick inside double quotes: \" becomes " before the body is parsed
def test_backtick_in_dquote_hides_command_falls_through(project):
    # Inside double quotes the shell turns \" into " before parsing the body,
    # so it runs: echo "'"; rm y; "'"   (rm is a real command). Reading the
    # body without that step hides "; rm y; " inside single quotes.
    assert bash(project, r'''echo "`echo \"'\"; rm y; \"'\"`"''') == ""


def test_backtick_in_dquote_allowed_word_still_allowed(project):
    assert bash(project, 'echo "`date \\"+%F\\"`"') == allow("date", "echo")


# 2. zsh forms
@pytest.mark.parametrize("cmd", [
    'echo ${(e)V}',
    'echo ${~V}',
    'echo $~V',
    'echo $=V',
    'echo $^V',
    'echo "${(e)V}"',
    'echo ${V:-$(date)}',
    'echo hi >! /tmp/x',
    'echo hi >>! /tmp/x',
])
def test_zsh_forms_fall_through(project, cmd):
    assert bash(project, cmd) == ""


def test_zsh_clobber_redirect_inside_repo_allowed(project):
    assert bash(project, "echo hi >! data/x.tmp") == allow("echo")


def test_plain_parameter_expansion_still_allowed(project):
    assert bash(project, 'TZ="${LOCAL_TZ:-America/Denver}" date') == allow("date")
    assert bash(project, 'echo ${#V} ${V}') == allow("echo")


# 3. deny and ask rules from every settings source
def test_colon_star_deny_rule_is_honored(project):
    set_rules(project / ".claude" / "settings.json", deny=["Bash(git push:*)"])
    assert bash(project, "X=$(date) && git push") == ""
    assert bash(project, "X=$(date) && git status") == allow("date", "git")


@pytest.mark.parametrize("rule", ["Bash", "Bash(git * main)", "Bash(*)"])
def test_unparseable_deny_rule_disables_hook(project, rule):
    set_rules(project / ".claude" / "settings.json", deny=[rule])
    assert bash(project, "echo $(date)") == ""


def test_unparseable_ask_rule_disables_hook(project):
    set_rules(project / ".claude" / "settings.json", ask=["Bash(git * main)"])
    assert bash(project, "echo $(date)") == ""


def test_ask_rule_match_falls_through(project):
    set_rules(project / ".claude" / "settings.json", ask=["Bash(git commit *)"])
    assert bash(project, "git commit -m \"$(date)\"") == ""
    assert bash(project, "git log -1 \"$(date)\"") == allow("date", "git")


def test_local_settings_deny_is_honored(project):
    set_rules(project / ".claude" / "settings.local.json", deny=["Bash(date *)"])
    assert bash(project, "echo $(date)") == ""


def test_user_settings_deny_is_honored(project):
    set_rules(project / "user-config" / "settings.json", deny=["Bash(date:*)"])
    assert bash(project, "echo $(date)") == ""


def test_user_settings_ask_is_honored(project):
    set_rules(project / "user-config" / "settings.json", ask=["Bash(echo *)"])
    assert bash(project, "echo $(date)") == ""


def test_allow_rules_only_from_project_settings(project):
    set_rules(project / ".claude" / "settings.local.json", allow=["Bash(curl *)"])
    set_rules(project / "user-config" / "settings.json", allow=["Bash(curl *)"])
    assert bash(project, "echo $(curl -s x)") == ""


# 4. cwd must be inside the project
def test_cwd_outside_project_falls_through(project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    assert bash(project, "echo $(date)", cwd=str(outside)) == ""


def test_cwd_inside_project_allowed(project):
    sub = project / "data"
    sub.mkdir()
    assert bash(project, "echo $(date)", cwd=str(sub)) == allow("date", "echo")
    assert bash(project, "echo $(date)", cwd=str(project)) == allow("date", "echo")


def test_cwd_absent_means_project_root(project):
    assert bash(project, "echo $(date)") == allow("date", "echo")


# 5. size cap and linear parsing
def test_command_over_64kb_falls_through(project):
    assert bash(project, "echo " + "a" * (64 * 1024)) == ""


def test_large_word_under_cap_is_fast(project):
    import time
    start = time.monotonic()
    assert bash(project, "echo " + "a" * 60000) == allow("echo")
    assert time.monotonic() - start < 3


# 6. redirects into the harness folders
@pytest.mark.parametrize("target", [".claude/settings.json", ".git/hooks/pre-commit",
                                    ".githooks/post-commit", "./.git/config"])
def test_redirect_into_harness_folders_falls_through(project, target):
    assert bash(project, f"echo $(date) > {target}") == ""


# 7. ANSI-C quoted words count as a possible deny match
def test_ansi_c_word_counts_as_deny_match(project):
    set_rules(project / ".claude" / "settings.json", deny=["Bash(git push *)"])
    assert bash(project, "X=$(date); git $'push' origin") == ""


# 8. assignment names
@pytest.mark.parametrize("cmd,expected", [
    ("TODAY=$(date +%F); echo $TODAY", allow("date", "echo")),
    ("WEEK_START=$(date +%F); echo $WEEK_START", allow("date", "echo")),
    ("tmp=$(mktemp)", allow("mktemp")),
    ("GIT_SSH_COMMAND=x git fetch $(date)", ""),
    ("EDITOR=x git commit $(date)", ""),
    ("today=$(date +%F)", ""),
    ("PYTHONPATH=x python3 $(date)", ""),
])
def test_assignment_names(project, cmd, expected):
    assert bash(project, cmd) == expected


# 9. zsh >&! and >&| (and &>! / &>|) write stdout and stderr to a file
CLOBBER_DUP_FORMS = [">&! {}", "1>&! {}", ">&!{}", ">&| {}", "&>! {}", "&>| {}"]


@pytest.mark.parametrize("form", CLOBBER_DUP_FORMS)
@pytest.mark.parametrize("target", ["/tmp/x", ".git/hooks/pre-commit"])
def test_clobber_dup_redirect_outside_or_protected_falls_through(project, form, target):
    assert bash(project, "jq . " + form.format(target)) == ""


@pytest.mark.parametrize("form", CLOBBER_DUP_FORMS)
def test_clobber_dup_redirect_inside_repo_allowed(project, form):
    assert bash(project, "jq . " + form.format("data/.jq_update.tmp")) == allow("jq")


@pytest.mark.parametrize("cmd", ["jq . 2>&1", "jq . >&2", "jq . 2>&-"])
def test_real_descriptor_dups_still_allowed(project, cmd):
    assert bash(project, cmd) == allow("jq")


# 10. protected folders are matched without regard to letter case
@pytest.mark.parametrize("target", [".GIT/config", ".Claude/settings.json", ".GitHooks/pre-commit"])
def test_protected_folders_case_insensitive(project, target):
    assert bash(project, f"echo hi > {target}") == ""


# 11. XDG_CONFIG_HOME changes where git reads its config
def test_xdg_config_home_assignment_falls_through(project):
    assert bash(project, "XDG_CONFIG_HOME=x git status $(date)") == ""
