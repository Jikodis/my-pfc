"""End-to-end tests for web_write.py, the one program that writes the repo for the web UI.

Every test builds its own git repo in a temporary folder (fixture data, a habit
schema, a stub pre-commit hook standing in for the repo's validator hook, one
commit, no remote unless the test adds a bare one) and points the script at it
through PFC_REPO_ROOT. Nothing here touches the worktree's own data files.
"""

from __future__ import annotations

import fcntl
import json
import importlib
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "web_write.py"
sys.path.insert(0, str(SCRIPT.parent))

from trmnl_push import today_local  # noqa: E402
from web_data import habit_title  # noqa: E402

TZ = "America/Denver"
TODAY = today_local({"LOCAL_TZ": TZ})

YESTERDAY = (date.fromisoformat(TODAY) - timedelta(days=1)).isoformat()
TOMORROW = (date.fromisoformat(TODAY) + timedelta(days=1)).isoformat()

TASKS = [
    {"id": "task-20250901-001", "status": "open", "description": "Call the dentist",
     "created": "2025-09-01", "area": "health"},
    {"id": "task-20250901-002", "status": "open", "description": "Reply to the landlord's email",
     "created": "2025-09-01", "area": "family", "source_email_thread_id": "abc123"},
    {"id": "task-20250901-003", "status": "done", "description": "Already finished",
     "created": "2025-09-01", "completed": "2025-09-02", "area": "health"},
    {"id": "task-20250901-004", "status": "open", "description": "Fill the form", "created": "2025-09-01",
     "area": "health", "agent_doable": "yes"},
    {"id": "task-20250901-005", "status": "open", "description": "Write the letter", "created": "2025-09-01",
     "area": "health", "agent_doable": "no"},
]
FOCUS = [
    {"id": "focus-20250706-001", "tier": "pursuit", "area": "recreation", "title": "Learn an instrument",
     "status": "red", "retired_date": None, "parked": False},
    {"id": "focus-20250706-002", "tier": "pursuit", "area": "recreation", "title": "Write short stories",
     "status": "red", "retired_date": None},
    {"id": "focus-20250706-003", "tier": "pursuit", "area": "health", "title": "Old thing",
     "status": "red", "retired_date": "2025-08-01", "parked": False},
]
LIFE_WHEEL_OLD = {"date": "2025-03-01", "ratings": {"career": "red", "health": "red"}, "notes": {},
                  "logged_at": "2025-03-01T09:00:00-0700"}
LIFE_WHEEL = {"date": "2025-06-03", "ratings": {"career": "green", "health": "red", "learning": "red"},
              "notes": {"health": "Not enough sleep.", "learning": "Stalled."},
              "logged_at": "2025-06-03T09:00:00-0600"}
HOUSEHOLD = {"date": "2025-04-19", "ratings": {"kitchen": "yellow", "garage": "red"}, "notes": {},
             "logged_at": "2025-04-19T09:00:00-06:00"}
GROUNDING = [
    {"id": "ground-20250812-001", "title": "Protect focus time", "body": "b", "area": "career", "status": "active",
     "created": "2025-08-12", "retired_date": None, "notes": "n"},
    {"id": "ground-20250905-001", "title": "One thing at a time", "body": "b", "area": "career", "status": "active",
     "created": "2025-09-05", "retired_date": None, "notes": "n"},
]
PROJECTS = [
    {"id": "proj-20250801-001", "name": "Closet cleanup", "active": False, "status": "on-deck", "area": "household",
     "total_parts": 3, "completed_parts": 0, "created": "2025-08-01"},
    {"id": "proj-20250802-001", "name": "Online course", "active": True, "status": "active", "area": "career",
     "total_parts": 40, "completed_parts": 10, "created": "2025-08-02"},
    {"id": "proj-20250803-001", "name": "Finished thing", "active": False, "status": "done", "area": "career",
     "total_parts": 1, "completed_parts": 1, "created": "2025-08-03"},
    {"id": "proj-20250804-001", "name": "Dropped thing", "active": False, "status": "dropped", "area": "career",
     "total_parts": 1, "completed_parts": 0, "created": "2025-08-04"},
]
SCHEMA = """\
daily_habits:
  - id: morning-walk
    description: "20+ minute walk"
    frequency: 5
    area: health
    values: [Health]
  - id: sleep-on-time
    description: "Asleep by the target bedtime (measured by the watch)"
    frequency: 7
    area: health
    values: [Health]
    auto_derived: true
  - id: old-habit
    description: "Switched off"
    frequency: 3
    area: health
    values: [Health]
    active: false

monthly_habits:
  - id: social-time
    description: "Time with friends"
    frequency: 2
    area: social
    values: [Connection]

deprecated_habits:
  - id: old-reading-habit
    replaced_by: null
    retired: "2025-08-01"
"""
# The repo's real pre-commit hook runs scripts/validate.sh; these stand in for it.
HOOK_OK = "#!/bin/bash\necho '  ✓ fine'\necho '✅ All checks passed.'\nexit 0\n"
HOOK_FAIL = (
    "#!/bin/bash\necho '  ✗ tasks.ndjson — record task-x violates schema' >&2\n"
    "echo '❌ Validation failed. Fix issues above before committing.'\nexit 1\n"
)
# The writer no longer runs the validator itself; if it did, this would fail every write.
VALIDATE_NEVER = "#!/bin/bash\necho '  ✗ the writer ran validate.sh itself' >&2\nexit 1\n"
TRAILER = "Co-Authored-By: PFC web UI <noreply@localhost>"


def _write_ndjson(path: Path, rows: list[dict], raw_lines: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = list(raw_lines or []) + [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows]
    path.write_text("".join(line + "\n" for line in lines))


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "AGENTS.md").write_text("# test repo\n")
    (root / ".gitignore").write_text("data/.web-write.lock\n")
    (root / "data").mkdir()
    (root / "data" / "keep.txt").write_text("keep\n")
    # A spaced line in the task file proves untouched lines keep their exact bytes.
    _write_ndjson(root / "6-tasks/_data/tasks.ndjson", TASKS[1:],
                  raw_lines=['{"id": "task-20250901-001", "status": "open", "description": "Call the dentist", '
                             '"created": "2025-09-01", "area": "health"}'])
    _write_ndjson(root / "6-tasks/_data/task_events.ndjson",
                  [{"task_id": "task-20250901-001", "event": "created", "timestamp": "2025-09-01", "source": "chat"}])
    _write_ndjson(root / "6-tasks/_data/daily-focus.ndjson",
                  [{"date": TODAY, "critical": ["task-20250901-001"], "bonus": None,
                    "completed": [], "bonus_completed": False}])
    _write_ndjson(root / "7-habits/_data/habits-daily.ndjson",
                  [{"habit_id": "morning-walk", "date": "2025-09-01", "completed": True, "source": "chat"}])
    _write_ndjson(root / "7-habits/_data/habits-monthly.ndjson", [])
    _write_ndjson(root / "4-focus/_data/focus.ndjson", FOCUS)
    _write_ndjson(root / "data/day-tracking.ndjson", [
        {"date": YESTERDAY, "health": {"sleep_hours": 7.0}},
        {"date": "2025-09-04", "rating": 3, "energy": 3, "mood": 3, "focus": 3, "health": {}}])
    _write_ndjson(root / "data/review-ledger.ndjson", [
        {"id": "stale-task-triage", "label": "Stale-task triage", "tier": "weekly", "cadence_days": 7,
         "weekday_hint": None, "last_done": "2025-07-29"}])
    _write_ndjson(root / "2-areas/_data/life-wheel.ndjson", [LIFE_WHEEL_OLD, LIFE_WHEEL])
    _write_ndjson(root / "2-areas/_data/household-status.ndjson", [HOUSEHOLD])
    _write_ndjson(root / "data/grounding.ndjson", GROUNDING)
    _write_ndjson(root / "5-projects/_data/projects.ndjson", PROJECTS)
    (root / "config").mkdir()
    (root / "config/habit_schema.yaml").write_text(SCHEMA)
    (root / "scripts").mkdir()
    validate = root / "scripts/validate.sh"
    validate.write_text(VALIDATE_NEVER)
    validate.chmod(0o755)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@localhost")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "config", "core.hooksPath", str(root / ".git/hooks"))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--no-verify", "-m", "initial")
    _pre_commit(root, HOOK_OK)
    return root


def _pre_commit(repo: Path, script: str) -> None:
    """Install `script` as the repo's pre-commit hook (the real one runs validate.sh)."""
    hook = repo / ".git/hooks/pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(script)
    hook.chmod(0o755)


FAKE_RENDER = """\
import os, sys, time
from pathlib import Path
out = Path(os.environ["FAKE_RENDER_OUT"])
out.write_text("started\\n")
time.sleep(float(os.environ.get("FAKE_RENDER_SLEEP", "0")))
out.write_text("started\\nfinished\\n")
print("fake render ran")
"""


def run(repo: Path, *args: str, extra_env: dict | None = None) -> tuple[int, dict]:
    # Never the real Trello render from a test: a fake that records it was started.
    fake = repo.parent / "fake_render.py"
    if not fake.exists():
        fake.write_text(FAKE_RENDER)
    env = {**os.environ, "PFC_REPO_ROOT": str(repo), "LOCAL_TZ": TZ, "GIT_TERMINAL_PROMPT": "0",
           "PFC_TRELLO_RENDER": str(fake), "FAKE_RENDER_OUT": str(repo.parent / "render-out"),
           "PFC_WEB_LOG": str(repo.parent / "web.log")}
    env.update(extra_env or {})
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=60)
    assert proc.stdout.strip(), f"no stdout; stderr: {proc.stderr}"
    return proc.returncode, json.loads(proc.stdout)


def head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()


def message(repo: Path) -> str:
    """The commit message exactly as stored in the commit object."""
    raw = _git(repo, "cat-file", "commit", "HEAD")
    return raw.split("\n\n", 1)[1]


def rows(repo: Path, rel: str) -> list[dict]:
    return [json.loads(line) for line in (repo / rel).read_text().splitlines() if line.strip()]


def status(repo: Path) -> str:
    return _git(repo, "status", "--short")


# ---------------------------------------------------------------- complete-task

def test_complete_task_commits_and_reports(repo):
    code, out = run(repo, "complete-task", "task-20250901-001")
    assert code == 0
    assert out["ok"] is True and out["changed"] is True
    assert out["action"] == "complete-task" and out["id"] == "task-20250901-001"
    assert out["title"] == "Call the dentist"
    assert out["email_linked"] is False
    assert out["commit"] == _git(repo, "rev-parse", "--short", "HEAD").strip()
    assert message(repo) == f"task: complete Call the dentist\n\nWritten by the web UI.\n\n{TRAILER}\n"
    task = rows(repo, "6-tasks/_data/tasks.ndjson")[0]
    assert task["status"] == "done" and task["completed"] == TODAY
    assert rows(repo, "6-tasks/_data/task_events.ndjson")[-1] == {
        "task_id": "task-20250901-001", "event": "completed", "timestamp": TODAY, "source": "web"}
    assert rows(repo, "6-tasks/_data/daily-focus.ndjson")[0]["completed"] == ["task-20250901-001"]
    assert status(repo) == ""


def test_drop_task_removes_the_task_and_logs_the_event(repo):
    before = rows(repo, "6-tasks/_data/tasks.ndjson")
    code, out = run(repo, "drop-task", "task-20250901-002")
    assert code == 0
    assert out["ok"] is True and out["changed"] is True and out["action"] == "drop-task"
    assert message(repo).startswith("task: drop ")
    after = rows(repo, "6-tasks/_data/tasks.ndjson")
    assert [t["id"] for t in after] == [t["id"] for t in before if t["id"] != "task-20250901-002"]
    last = rows(repo, "6-tasks/_data/task_events.ndjson")[-1]
    assert last["task_id"] == "task-20250901-002" and last["event"] == "deleted" and last["source"] == "web"
    changed = _git(repo, "show", "--name-only", "--format=", "HEAD").split()
    # Never a 2+1 pick, so it is removed outright and the archive is untouched.
    assert changed == ["6-tasks/_data/task_events.ndjson", "6-tasks/_data/tasks.ndjson"]
    assert status(repo) == ""


def test_drop_task_named_in_a_2_plus_1_moves_to_the_archive(repo):
    # task-20250901-001 is a critical pick in the fixture's daily-focus record, and
    # the validator requires every pick to resolve, so it is archived, not deleted.
    code, out = run(repo, "drop-task", "task-20250901-001")
    assert code == 0 and out["changed"] is True
    assert "task-20250901-001" not in [t["id"] for t in rows(repo, "6-tasks/_data/tasks.ndjson")]
    archived = rows(repo, "6-tasks/_data/tasks-archive.ndjson")[-1]
    assert archived["id"] == "task-20250901-001" and archived["status"] == "open" and archived["dropped"] == TODAY
    changed = _git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert "6-tasks/_data/tasks-archive.ndjson" in changed
    assert rows(repo, "6-tasks/_data/daily-focus.ndjson")[0]["critical"] == ["task-20250901-001"]


def test_drop_task_keeps_the_other_lines_byte_for_byte(repo):
    before = (repo / "6-tasks/_data/tasks.ndjson").read_text().splitlines()
    run(repo, "drop-task", "task-20250901-002")
    after = (repo / "6-tasks/_data/tasks.ndjson").read_text().splitlines()
    assert after == [before[0], *before[2:]]


def test_drop_task_refuses_a_done_task(repo):
    before = head(repo)
    code, out = run(repo, "drop-task", "task-20250901-003")
    assert code == 2 and out["reason"] == "refused"
    assert head(repo) == before and status(repo) == ""


def test_drop_task_unknown_id(repo):
    code, out = run(repo, "drop-task", "task-20990101-001")
    assert code == 2 and out["reason"] == "not_found"


def test_complete_task_keeps_untouched_lines_byte_for_byte(repo):
    before = (repo / "6-tasks/_data/tasks.ndjson").read_text().splitlines()
    run(repo, "complete-task", "task-20250901-002")
    after = (repo / "6-tasks/_data/tasks.ndjson").read_text().splitlines()
    assert after[0] == before[0]  # the spaced line nobody changed
    assert after[2] == before[2]
    assert after[1] != before[1]
    events_before = 1
    assert len(rows(repo, "6-tasks/_data/task_events.ndjson")) == events_before + 1


def test_complete_task_email_linked(repo):
    code, out = run(repo, "complete-task", "task-20250901-002")
    assert code == 0 and out["email_linked"] is True
    # Not a 2+1 pick, so the daily-focus file is not part of the commit.
    changed = _git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert changed == ["6-tasks/_data/task_events.ndjson", "6-tasks/_data/tasks.ndjson"]


def test_complete_task_unknown_id_exits_2_without_commit(repo):
    before = head(repo)
    code, out = run(repo, "complete-task", "task-20990101-001")
    assert code == 2
    assert out == {"ok": False, "reason": "not_found", "error": "No open task with that id."}
    assert head(repo) == before and status(repo) == ""


def test_complete_task_already_done_is_a_no_op(repo):
    before = head(repo)
    code, out = run(repo, "complete-task", "task-20250901-003")
    assert code == 0
    assert out["ok"] is True and out["changed"] is False and out["commit"] is None
    assert out["message"] == "Already done."
    assert head(repo) == before


@pytest.mark.parametrize("args", [
    ["complete-task", "task-1"],
    ["complete-task", "task-20250901-001; rm -rf /"],
    ["log-habit", "Morning_Walk"],
    ["log-habit", "x" * 65],
    ["park-focus", "focus-20250706-001", "maybe"],
    ["park-focus", "focus-1", "on"],
    ["delete-everything", "task-20250901-001"],
    ["complete-task"],
    [],
])
def test_bad_arguments_exit_2(repo, args):
    before = head(repo)
    code, out = run(repo, *args)
    assert code == 2
    assert out["ok"] is False and out["reason"] == "bad_request"
    assert head(repo) == before


@pytest.mark.parametrize("bad", ["--dry-run", "-x", "-", "-row"])
def test_a_habit_id_may_not_start_with_a_dash(repo, bad):
    import web_write
    assert web_write.HABIT_ID.fullmatch(bad) is None
    before = head(repo)
    code, out = run(repo, "log-habit", bad)
    assert code == 2 and out["reason"] == "bad_request"
    assert head(repo) == before


def test_every_real_habit_id_matches_the_shape():
    import yaml
    import web_write
    schema = yaml.safe_load((SCRIPT.parents[2] / "config/habit_schema.yaml").read_text())
    ids = [h["id"] for key in ("daily_habits", "monthly_habits", "deprecated_habits")
           for h in (schema.get(key) or []) if isinstance(h, dict) and "id" in h]
    assert ids
    assert [i for i in ids if not web_write.HABIT_ID.fullmatch(i)] == []


# ---------------------------------------------------------------- log-habit

def test_log_daily_habit(repo):
    code, out = run(repo, "log-habit", "morning-walk")
    assert code == 0 and out["changed"] is True
    assert out["title"] == habit_title("morning-walk")
    assert rows(repo, "7-habits/_data/habits-daily.ndjson")[-1] == {
        "habit_id": "morning-walk", "date": TODAY, "completed": True, "source": "web"}
    assert message(repo) == f"habit: log {TODAY}\n\nWritten by the web UI.\n\n{TRAILER}\n"


def test_log_monthly_habit_goes_to_monthly_file(repo):
    code, _ = run(repo, "log-habit", "social-time")
    assert code == 0
    assert rows(repo, "7-habits/_data/habits-monthly.ndjson") == [
        {"habit_id": "social-time", "date": TODAY, "completed": True, "source": "web"}]
    assert len(rows(repo, "7-habits/_data/habits-daily.ndjson")) == 1


def test_log_habit_already_logged(repo):
    run(repo, "log-habit", "morning-walk")
    before = head(repo)
    code, out = run(repo, "log-habit", "morning-walk")
    assert code == 0
    assert out == {**out, "ok": True, "changed": False, "message": "Already logged today."}
    assert head(repo) == before
    assert len(rows(repo, "7-habits/_data/habits-daily.ndjson")) == 2


def test_log_habit_flips_a_missed_row_in_place(repo):
    _write_ndjson(repo / "7-habits/_data/habits-daily.ndjson",
                  [{"habit_id": "morning-walk", "date": TODAY, "completed": False, "source": "evening-checkin"}])
    _git(repo, "commit", "-qam", "missed row")
    code, out = run(repo, "log-habit", "morning-walk")
    assert code == 0 and out["changed"] is True
    assert out["message"] == "Saved. Not pushed yet."  # no remote in this repo
    assert rows(repo, "7-habits/_data/habits-daily.ndjson") == [
        {"habit_id": "morning-walk", "date": TODAY, "completed": True, "source": "web"}]
    assert message(repo).startswith(f"habit: log {TODAY}\n")


def test_log_habit_missed_row_message_when_pushed(repo, tmp_path):
    _write_ndjson(repo / "7-habits/_data/habits-daily.ndjson",
                  [{"habit_id": "morning-walk", "date": TODAY, "completed": False, "source": "evening-checkin"}])
    _git(repo, "commit", "-qam", "missed row")
    _add_remote(repo, tmp_path)
    code, out = run(repo, "log-habit", "morning-walk")
    assert code == 0 and out["pushed"] is True
    assert out["message"] == "Marked done (it was logged as missed)."


def test_log_habit_refuses_auto_derived(repo):
    before = head(repo)
    code, out = run(repo, "log-habit", "sleep-on-time")
    assert code == 2
    assert out == {"ok": False, "reason": "refused",
                   "error": "That habit is logged automatically (from the watch or the calendar); there is nothing to click."}
    assert head(repo) == before


@pytest.mark.parametrize("habit", ["no-such-habit", "old-habit", "old-reading-habit"])
def test_log_habit_unknown_or_inactive(repo, habit):
    code, out = run(repo, "log-habit", habit)
    assert code == 2
    assert out == {"ok": False, "reason": "not_found", "error": "No active habit with that id."}


def _days_ago(n: int) -> str:
    return (date.fromisoformat(TODAY) - timedelta(days=n)).isoformat()


def test_log_habit_for_yesterday_writes_that_date(repo):
    yesterday = _days_ago(1)
    code, out = run(repo, "log-habit", "morning-walk", yesterday)
    assert code == 0 and out["changed"] is True
    assert rows(repo, "7-habits/_data/habits-daily.ndjson")[-1] == {
        "habit_id": "morning-walk", "date": yesterday, "completed": True, "source": "web"}
    assert message(repo).startswith(f"habit: log {yesterday}\n")


def test_log_habit_for_the_oldest_day_allowed(repo):
    code, out = run(repo, "log-habit", "social-time", _days_ago(7))
    assert code == 0 and out["changed"] is True
    assert rows(repo, "7-habits/_data/habits-monthly.ndjson")[-1]["date"] == _days_ago(7)


def test_log_habit_already_logged_on_a_past_day_names_the_day(repo):
    run(repo, "log-habit", "morning-walk", _days_ago(2))
    before = head(repo)
    code, out = run(repo, "log-habit", "morning-walk", _days_ago(2))
    assert code == 0 and out["changed"] is False
    assert out["message"] == "Already logged for that day."
    assert head(repo) == before


@pytest.mark.parametrize("when,error", [
    (-1, "That day has not happened yet."),
    (8, "That day is more than 7 days back; log it in chat."),
])
def test_log_habit_refuses_a_day_outside_the_window(repo, when, error):
    before = head(repo)
    code, out = run(repo, "log-habit", "morning-walk", _days_ago(when))
    assert code == 2
    assert out == {"ok": False, "reason": "refused", "error": error}
    assert head(repo) == before


@pytest.mark.parametrize("bad", ["yesterday", "2025-02-30", "--dry-run-x", "20251013", ""])
def test_log_habit_refuses_a_date_that_is_not_one(repo, bad):
    code, out = run(repo, "log-habit", "morning-walk", bad)
    assert code == 2
    assert out == {"ok": False, "reason": "bad_request", "error": "That is not a valid date."}


# ---------------------------------------------------------------- park-focus

def test_park_and_unpark_focus(repo):
    code, out = run(repo, "park-focus", "focus-20250706-001", "on")
    assert code == 0 and out["changed"] is True and out["title"] == "Learn an instrument"
    assert rows(repo, "4-focus/_data/focus.ndjson")[0]["parked"] is True
    assert message(repo) == f"focus: park Learn an instrument\n\nWritten by the web UI.\n\n{TRAILER}\n"

    code, out = run(repo, "park-focus", "focus-20250706-001", "off")
    assert code == 0 and out["changed"] is True
    assert rows(repo, "4-focus/_data/focus.ndjson")[0]["parked"] is False
    assert message(repo).startswith("focus: unpark Learn an instrument\n")


def test_park_focus_unchanged_is_a_no_op(repo):
    before = head(repo)
    code, out = run(repo, "park-focus", "focus-20250706-002", "off")  # no parked field = not parked
    assert code == 0 and out["changed"] is False and out["message"] == "Already active."
    assert head(repo) == before


def test_park_focus_retired(repo):
    code, out = run(repo, "park-focus", "focus-20250706-003", "on")
    assert code == 2
    assert out == {"ok": False, "reason": "refused", "error": "That focus is retired."}


def test_park_focus_unknown(repo):
    code, out = run(repo, "park-focus", "focus-20990101-001", "on")
    assert code == 2 and out["reason"] == "not_found" and out["error"] == "No focus with that id."


# ---------------------------------------------------------------- lock, validator, dirty files

def test_lock_held_exits_3(repo):
    lock_path = repo / "data/.web-write.lock"
    with open(lock_path, "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = head(repo)
        code, out = run(repo, "complete-task", "task-20250901-001")
    assert code == 3
    assert out == {"ok": False, "reason": "busy", "error": "Another change is still being saved."}
    assert head(repo) == before
    assert rows(repo, "6-tasks/_data/tasks.ndjson")[0]["status"] == "open"


def test_the_writer_leaves_validation_to_the_pre_commit_hook(repo):
    # scripts/validate.sh fails here; the hook passes, so the write goes through.
    code, out = run(repo, "--no-render", "complete-task", "task-20250901-001")
    assert code == 0 and out["changed"] is True


def test_validator_failure_restores_files_and_exits_4(repo):
    _pre_commit(repo, HOOK_FAIL)
    before = head(repo)
    code, out = run(repo, "complete-task", "task-20250901-001")
    assert code == 4
    assert out == {"ok": False, "reason": "invalid",
                   "error": "tasks.ndjson: record task-x violates schema"}
    assert head(repo) == before
    assert status(repo) == ""
    assert rows(repo, "6-tasks/_data/tasks.ndjson")[0]["status"] == "open"


def test_uncommitted_edit_in_a_target_file_is_refused(repo):
    path = repo / "6-tasks/_data/task_events.ndjson"
    path.write_text(path.read_text() + '{"task_id":"x","event":"created","timestamp":"2025-09-01"}\n')
    before_text = path.read_text()
    before = head(repo)
    code, out = run(repo, "complete-task", "task-20250901-001")
    assert code == 3 and out["reason"] == "dirty"
    assert out["error"] == "A file this change needs has edits that are not committed yet."
    assert path.read_text() == before_text  # the person's edit is untouched
    assert head(repo) == before
    assert rows(repo, "6-tasks/_data/tasks.ndjson")[0]["status"] == "open"


def test_other_staged_files_stay_out_of_the_commit(repo):
    (repo / "data/keep.txt").write_text("staged elsewhere\n")
    _git(repo, "add", "data/keep.txt")
    code, _ = run(repo, "complete-task", "task-20250901-001")
    assert code == 0
    assert "data/keep.txt" not in _git(repo, "show", "--name-only", "--format=", "HEAD")
    assert _git(repo, "diff", "--cached", "--name-only").split() == ["data/keep.txt"]


# ---------------------------------------------------------------- dry run, push, render flag

def test_dry_run_changes_nothing(repo):
    before = head(repo)
    code, out = run(repo, "--dry-run", "complete-task", "task-20250901-001")
    assert code == 0
    assert out["ok"] is True and out["dry_run"] is True and out["changed"] is True
    assert out["files"] == ["6-tasks/_data/daily-focus.ndjson", "6-tasks/_data/task_events.ndjson",
                            "6-tasks/_data/tasks.ndjson"]
    assert head(repo) == before and status(repo) == ""


def test_dry_run_unknown_id_exits_2(repo):
    code, out = run(repo, "--dry-run", "complete-task", "task-00000000-000")
    assert code == 2 and out["reason"] == "not_found"
    assert status(repo) == ""


def test_push_failure_still_reports_the_commit(repo):
    code, out = run(repo, "log-habit", "morning-walk")
    assert code == 0
    assert out["pushed"] is False
    assert isinstance(out["push_error"], str) and out["push_error"]
    assert "\n" not in out["push_error"]
    assert out["message"] == "Saved. Not pushed yet."


def _add_remote(repo: Path, tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "-u", "origin", "main")
    return remote


def test_push_success(repo, tmp_path):
    remote = _add_remote(repo, tmp_path)
    code, out = run(repo, "log-habit", "morning-walk")
    assert code == 0
    assert out["pushed"] is True and out["push_error"] is None and out["message"] == "Saved."
    assert subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "main"], check=True,
                          capture_output=True, text=True).stdout.strip() == head(repo)


# Another clone of the same origin (a second machine). It pushes between this repo's
# last sync and its next write.
def _other_machine(tmp_path: Path, remote: Path) -> Path:
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", "-b", "main", str(remote), str(other)], check=True, capture_output=True)
    _git(other, "config", "user.name", "Other")
    _git(other, "config", "user.email", "other@localhost")
    _git(other, "config", "commit.gpgsign", "false")
    return other


def _remote_git(remote: Path, *args: str) -> str:
    return subprocess.run(["git", "--git-dir", str(remote), *args], check=True,
                          capture_output=True, text=True).stdout


def test_push_lands_on_top_of_what_the_other_machine_pushed(repo, tmp_path):
    remote = _add_remote(repo, tmp_path)
    other = _other_machine(tmp_path, remote)
    (other / "AGENTS.md").write_text("# edited on the other machine\n")
    _git(other, "commit", "-q", "-am", "other: edit AGENTS")
    _git(other, "push", "-q")
    code, out = run(repo, "log-habit", "morning-walk")
    assert code == 0
    assert out["pushed"] is True and out["push_error"] is None, out
    assert _remote_git(remote, "log", "--format=%s", "main").splitlines()[:2] == [f"habit: log {TODAY}", "other: edit AGENTS"]
    # The rebase rewrote the commit; the page gets the sha that is actually on origin.
    assert out["commit"] == _remote_git(remote, "rev-parse", "--short", "main").strip()
    assert (repo / "AGENTS.md").read_text() == "# edited on the other machine\n"
    assert status(repo) == ""


def test_write_edits_the_newest_copy_of_the_file(repo, tmp_path):
    remote = _add_remote(repo, tmp_path)
    other = _other_machine(tmp_path, remote)
    theirs = {"habit_id": "morning-walk", "date": "2025-09-02", "completed": True, "source": "trello"}
    with open(other / "7-habits/_data/habits-daily.ndjson", "a") as fh:
        fh.write(json.dumps(theirs, separators=(",", ":")) + "\n")
    _git(other, "commit", "-q", "-am", "habit: log 2025-09-02")
    _git(other, "push", "-q")
    code, out = run(repo, "log-habit", "morning-walk")
    assert code == 0
    assert out["pushed"] is True and out["push_error"] is None, out
    logged = rows(repo, "7-habits/_data/habits-daily.ndjson")
    assert theirs in logged
    assert {"habit_id": "morning-walk", "date": TODAY, "completed": True, "source": "web"} in logged


def test_a_conflict_keeps_the_commit_local_and_the_repo_clean(repo, tmp_path):
    remote = _add_remote(repo, tmp_path)
    other = _other_machine(tmp_path, remote)
    (other / "AGENTS.md").write_text("# other\n")
    _git(other, "commit", "-q", "-am", "other: AGENTS")
    _git(other, "push", "-q")
    # A commit stranded here earlier, touching the same line.
    (repo / "AGENTS.md").write_text("# local\n")
    _git(repo, "commit", "-q", "-am", "local: AGENTS")
    code, out = run(repo, "log-habit", "morning-walk")
    assert code == 0
    assert out["pushed"] is False and out["push_error"].startswith("Not pushed:"), out
    assert out["message"] == "Saved. Not pushed yet."
    assert _git(repo, "log", "--format=%s").splitlines()[:2] == [f"habit: log {TODAY}", "local: AGENTS"]
    assert (repo / "AGENTS.md").read_text() == "# local\n"
    assert status(repo) == ""
    assert not (repo / ".git/rebase-merge").exists() and not (repo / ".git/rebase-apply").exists()


def test_a_rebase_in_progress_refuses_the_write(repo, tmp_path):
    remote = _add_remote(repo, tmp_path)
    other = _other_machine(tmp_path, remote)
    (other / "AGENTS.md").write_text("# other\n")
    _git(other, "commit", "-q", "-am", "other: AGENTS")
    _git(other, "push", "-q")
    (repo / "AGENTS.md").write_text("# local\n")
    _git(repo, "commit", "-q", "-am", "local: AGENTS")
    stopped = subprocess.run(["git", "pull", "--rebase", "--quiet"], cwd=repo, capture_output=True, text=True)
    assert stopped.returncode != 0 and (repo / ".git/rebase-merge").exists()
    code, out = run(repo, "log-habit", "morning-walk")
    assert code == 3 and out["reason"] == "rebase_in_progress"
    assert (repo / ".git/rebase-merge").exists()  # someone's rebase is not aborted for them
    _git(repo, "rebase", "--abort")


# A pre-push hook sees the environment git gives the push. It records what the
# writer passed and asks the askpass helper for both answers, the way git would
# for an https remote; a local bare remote never asks on its own.
RECORD_PRE_PUSH = """#!/bin/bash
out="$PUSH_RECORD"
{
  echo "askpass=$GIT_ASKPASS"
  echo "prompt=$GIT_TERMINAL_PROMPT"
  echo "config=$GIT_CONFIG_PARAMETERS"
  echo "user=$("$GIT_ASKPASS" "Username for 'https://github.com': ")"
  echo "pass=$("$GIT_ASKPASS" "Password for 'https://example-user@github.com': ")"
  echo "refs=$(cat)"
} > "$out"
exit 0
"""

FAKE_GH = """#!/bin/bash
if [ "$1 $2 $3 $4" = "auth token --user example-user" ]; then echo "tok-123"; exit 0; fi
echo "unexpected gh call: $*" >&2
exit 1
"""


def _bin_dir(tmp_path: Path, with_gh: bool) -> Path:
    """A PATH folder holding git (and a fake gh when asked), used alone with /usr/bin:/bin."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "git").symlink_to(shutil.which("git"))
    if with_gh:
        gh = bindir / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
    return bindir


def _system_bin_without_gh(tmp_path: Path) -> Path:
    """A PATH folder linking every command in /usr/bin and /bin except gh. The server
    installs gh in /usr/bin (apt), so `/usr/bin:/bin` alone would still find it."""
    bindir = tmp_path / "bin-no-gh"
    bindir.mkdir()
    for d in ("/usr/bin", "/bin"):
        for f in Path(d).iterdir():
            link = bindir / f.name
            if f.name != "gh" and not link.exists():
                link.symlink_to(f)
    return bindir


def test_push_with_gh_user_uses_a_one_shot_askpass(repo, tmp_path):
    remote = _add_remote(repo, tmp_path)
    hook = repo / ".git/hooks/pre-push"
    hook.write_text(RECORD_PRE_PUSH)
    hook.chmod(0o755)
    record = tmp_path / "push-record"
    bindir = _bin_dir(tmp_path, with_gh=True)
    code, out = run(repo, "log-habit", "morning-walk",
                    extra_env={"PFC_PUSH_GH_USER": "example-user", "PUSH_RECORD": str(record),
                               "PATH": f"{bindir}:/usr/bin:/bin"})
    assert code == 0
    assert out["pushed"] is True and out["push_error"] is None and out["message"] == "Saved."
    lines = dict(line.split("=", 1) for line in record.read_text().splitlines() if "=" in line)
    askpass = Path(lines["askpass"])
    assert lines["prompt"] == "0"
    assert "'credential.helper'=''" in lines["config"]  # git's quoting of -c credential.helper=
    assert lines["user"] == "example-user"
    assert lines["pass"] == "tok-123"
    assert "refs/heads/main" in lines["refs"]
    assert not askpass.exists(), "the askpass helper must be removed after the push"
    assert subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "main"], check=True,
                          capture_output=True, text=True).stdout.strip() == head(repo)


def test_push_without_gh_user_passes_no_askpass(repo, tmp_path):
    _add_remote(repo, tmp_path)
    hook = repo / ".git/hooks/pre-push"
    hook.write_text("#!/bin/bash\necho \"askpass=$GIT_ASKPASS\" > \"$PUSH_RECORD\"\n")
    hook.chmod(0o755)
    record = tmp_path / "push-record"
    env = {"PUSH_RECORD": str(record), "PFC_PUSH_GH_USER": "", "GIT_ASKPASS": ""}
    code, out = run(repo, "log-habit", "morning-walk", extra_env=env)
    assert code == 0 and out["pushed"] is True
    assert record.read_text().strip() == "askpass="


def test_push_with_gh_user_but_no_gh_reports_it(repo, tmp_path):
    remote = _add_remote(repo, tmp_path)
    before = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "main"], check=True,
                            capture_output=True, text=True).stdout.strip()
    code, out = run(repo, "log-habit", "morning-walk",
                    extra_env={"PFC_PUSH_GH_USER": "example-user", "PATH": str(_system_bin_without_gh(tmp_path))})
    assert code == 0
    assert out["commit"] and out["pushed"] is False
    assert out["push_error"] == "gh is not on PATH; cannot read the push token."
    assert out["message"] == "Saved. Not pushed yet."
    assert subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "main"], check=True,
                          capture_output=True, text=True).stdout.strip() == before


def _hook_repo(repo: Path) -> Path:
    hooks = repo / ".hooks"
    hooks.mkdir()
    hook = hooks / "post-commit"
    hook.write_text('#!/bin/bash\necho "render=${PFC_SKIP_TRELLO_RENDER:-unset}" > "$(git rev-parse --show-toplevel)/data/.hook-out"\n'
                    'echo noise on stdout\n')
    hook.chmod(0o755)
    pre_commit = hooks / "pre-commit"
    pre_commit.write_text(HOOK_OK)
    pre_commit.chmod(0o755)
    (repo / ".gitignore").write_text("data/.web-write.lock\ndata/.hook-out\n.hooks/\n")
    _git(repo, "commit", "-qam", "ignore hook output")
    _git(repo, "config", "core.hooksPath", str(hooks))
    return repo / "data/.hook-out"


def _wait_for(path: Path, text: str, seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists() and text in path.read_text():
            return True
        time.sleep(0.05)
    return False


def test_commit_never_renders_inline(repo):
    out_file = _hook_repo(repo)
    code, out = run(repo, "log-habit", "morning-walk")  # hook stdout must not reach ours
    assert code == 0 and out["ok"] is True
    assert out_file.read_text().strip() == "render=1"


def test_render_is_started_detached_after_the_commit(repo):
    marker = repo.parent / "render-out"
    started = time.monotonic()
    code, out = run(repo, "log-habit", "morning-walk", extra_env={"FAKE_RENDER_SLEEP": "4"})
    elapsed = time.monotonic() - started
    assert code == 0 and out["changed"] is True
    # The writer returned without waiting for the four-second render.
    assert elapsed < 3.5, elapsed
    assert _wait_for(marker, "started")
    assert "finished" not in marker.read_text()
    assert _wait_for(marker, "finished")
    assert "fake render ran" in (repo.parent / "web.log").read_text()


def test_no_render_starts_no_render(repo):
    out_file = _hook_repo(repo)
    code, _ = run(repo, "--no-render", "log-habit", "morning-walk")
    assert code == 0
    assert out_file.read_text().strip() == "render=1"
    time.sleep(0.5)
    assert not (repo.parent / "render-out").exists()


def test_nothing_changed_starts_no_render(repo):
    run(repo, "--no-render", "log-habit", "morning-walk")
    code, out = run(repo, "log-habit", "morning-walk")
    assert code == 0 and out["changed"] is False
    time.sleep(0.5)
    assert not (repo.parent / "render-out").exists()


# ---------------------------------------------------------------- jq -c spacing

def _compact(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def test_changed_line_is_compact_even_when_the_file_ends_spaced(repo):
    path = repo / "6-tasks/_data/tasks.ndjson"
    lines = path.read_text().splitlines()
    spaced_last = json.dumps(json.loads(lines[-1]), ensure_ascii=False)
    path.write_text("".join(line + "\n" for line in [*lines[:-1], spaced_last]))
    _git(repo, "commit", "-qam", "spaced last line")
    before = path.read_text().splitlines()
    code, _ = run(repo, "--no-render", "complete-task", "task-20250901-002")
    assert code == 0
    after = path.read_text().splitlines()
    assert after[0] == before[0] and after[2] == before[2]
    assert after[1] == _compact(json.loads(after[1]))


def test_appended_event_line_is_compact(repo):
    code, _ = run(repo, "--no-render", "complete-task", "task-20250901-001")
    assert code == 0
    last = (repo / "6-tasks/_data/task_events.ndjson").read_text().splitlines()[-1]
    assert last == _compact(json.loads(last))


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq is not installed")
def test_changed_line_matches_real_jq_c(repo):
    code, _ = run(repo, "--no-render", "complete-task", "task-20250901-002")
    assert code == 0
    line = (repo / "6-tasks/_data/tasks.ndjson").read_text().splitlines()[1]
    jq = subprocess.run(["jq", "-c", "."], input=line, capture_output=True, text=True, check=True).stdout.strip()
    assert line == jq


# ---------------------------------------------------------------- anything else exits 1

def test_a_bad_data_line_exits_1_with_fixed_text(repo):
    path = repo / "6-tasks/_data/tasks.ndjson"
    path.write_text(path.read_text() + "{not json\n")
    _git(repo, "commit", "-qam", "broken line")
    code, out = run(repo, "complete-task", "task-20250901-001")
    assert code == 1
    assert out == {"ok": False, "reason": "error", "error": "The change could not be saved."}


def test_a_refused_commit_without_a_failure_line_reports_its_last_line(repo):
    _pre_commit(repo, "#!/bin/bash\necho refused >&2\nexit 1\n")
    before = head(repo)
    code, out = run(repo, "complete-task", "task-20250901-001")
    assert code == 4
    assert out == {"ok": False, "reason": "invalid", "error": "refused"}
    assert head(repo) == before
    assert status(repo) == ""
    assert rows(repo, "6-tasks/_data/tasks.ndjson")[0]["status"] == "open"


# ---------------------------------------------------------------- branch guard

def test_feature_branch_is_refused_and_nothing_changes(repo):
    _git(repo, "switch", "-q", "-c", "feature")
    before = head(repo)
    code, out = run(repo, "complete-task", "task-20250901-001")
    assert code == 3
    assert out == {"ok": False, "reason": "wrong_branch",
                   "error": "The repo is on branch feature, not main; nothing was changed."}
    assert head(repo) == before and status(repo) == ""


def test_detached_head_is_refused_and_nothing_changes(repo):
    _git(repo, "checkout", "-q", "--detach")
    before = head(repo)
    code, out = run(repo, "complete-task", "task-20250901-001")
    assert code == 3
    assert out == {"ok": False, "reason": "wrong_branch", "error": "The repo has no branch checked out."}
    assert head(repo) == before and status(repo) == ""


@pytest.mark.parametrize("breakage", ["missing", "not_executable"])
def test_missing_pre_commit_hook_is_refused_and_nothing_changes(repo, breakage):
    hook = repo / ".git/hooks/pre-commit"
    if breakage == "missing":
        hook.unlink()
    else:
        hook.chmod(0o644)
    before = head(repo)
    code, out = run(repo, "complete-task", "task-20250901-001")
    assert code == 3
    assert out == {"ok": False, "reason": "no_precommit_hook",
                   "error": "The repo's pre-commit hook is not installed; see docs/install/web-ui.md."}
    assert head(repo) == before and status(repo) == ""
    assert not (repo / "data/.web-write.lock").exists()


def test_missing_pre_commit_hook_does_not_block_a_dry_run(repo):
    (repo / ".git/hooks/pre-commit").unlink()
    code, out = run(repo, "--dry-run", "complete-task", "task-20250901-001")
    assert code == 0 and out["dry_run"] is True


def test_write_branch_can_be_named(repo):
    _git(repo, "switch", "-q", "-c", "feature")
    code, out = run(repo, "--no-render", "complete-task", "task-20250901-001",
                    extra_env={"PFC_WRITE_BRANCH": "feature"})
    assert code == 0 and out["changed"] is True


# ---------------------------------------------------------------- timeouts and stopping

# Writes the pid of its sleep to the marker, so a test can check the sleep was stopped.
SLOW_HOOK = ("#!/bin/bash\nsleep 20 &\necho $! > \"$(git rev-parse --show-toplevel)/validator-started\"\n"
             "wait\nexit 0\n")


def _slow_validator(repo: Path) -> None:
    _pre_commit(repo, SLOW_HOOK)
    (repo / ".gitignore").write_text("data/.web-write.lock\nvalidator-started\n")
    _git(repo, "commit", "-q", "--no-verify", "-am", "slow validator")


def _no_git_locks(repo: Path) -> bool:
    return not list((repo / ".git").glob("*.lock"))


def _gone(pid: int, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def _lock_is_free(repo: Path) -> bool:
    with open(repo / "data/.web-write.lock", "a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(fh, fcntl.LOCK_UN)
        return True


def test_a_validator_past_its_timeout_restores_and_exits_4(repo):
    _slow_validator(repo)
    before = head(repo)
    started = time.monotonic()
    code, out = run(repo, "--no-render", "complete-task", "task-20250901-001",
                    extra_env={"PFC_WRITE_COMMIT_TIMEOUT": "1"})
    assert time.monotonic() - started < 10
    assert code == 4
    assert out == {"ok": False, "reason": "invalid",
                   "error": "The commit and its validator did not finish in 1 seconds."}
    assert head(repo) == before and status(repo) == ""
    assert _no_git_locks(repo)
    assert _lock_is_free(repo)


def test_sigterm_during_validation_restores_and_frees_the_lock(repo):
    _slow_validator(repo)
    before = head(repo)
    env = {**os.environ, "PFC_REPO_ROOT": str(repo), "LOCAL_TZ": TZ, "GIT_TERMINAL_PROMPT": "0",
           "PFC_WEB_LOG": str(repo.parent / "web.log")}
    proc = subprocess.Popen([sys.executable, str(SCRIPT), "--no-render", "complete-task", "task-20250901-001"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    marker = repo / "validator-started"
    assert _wait_for(marker, "\n")
    sleeper = int(marker.read_text().strip())
    assert status(repo) != ""  # the files are written and being validated
    proc.send_signal(signal.SIGTERM)
    stdout, _ = proc.communicate(timeout=10)
    assert _gone(sleeper)  # the hook's child did not outlive the writer
    assert proc.returncode == 1
    assert json.loads(stdout) == {"ok": False, "reason": "stopped",
                                  "error": "The change was stopped before it was saved."}
    assert head(repo) == before and status(repo) == ""
    assert _no_git_locks(repo)
    assert _lock_is_free(repo)


def test_a_commit_killed_mid_way_leaves_no_index_lock(repo):
    # The hook kills git itself, the way a crash would: git leaves index.lock behind.
    _pre_commit(repo, "#!/bin/bash\nkill -9 $PPID\n")
    before = head(repo)
    code, out = run(repo, "--no-render", "complete-task", "task-20250901-001")
    assert code == 4 and out["reason"] == "invalid"
    assert head(repo) == before and status(repo) == ""
    assert _no_git_locks(repo)
    assert rows(repo, "6-tasks/_data/tasks.ndjson")[0]["status"] == "open"


def test_an_older_index_lock_is_left_alone(repo):
    # A lock that was there before this run belongs to someone else.
    lock = repo / ".git/index.lock"
    lock.write_text("")
    old = time.time() - 60
    os.utime(lock, (old, old))
    code, out = run(repo, "--no-render", "complete-task", "task-20250901-001")
    assert code == 1 and out["reason"] == "error"
    assert lock.exists()
    lock.unlink()


SLOW_PRE_PUSH = "#!/bin/bash\ntouch \"$(git rev-parse --show-toplevel)/push-started\"\nsleep 20\nexit 0\n"


def test_sigterm_after_the_commit_reports_the_saved_commit(repo, tmp_path):
    remote = _add_remote(repo, tmp_path)
    remote_before = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "main"], check=True,
                                   capture_output=True, text=True).stdout.strip()
    # A push that hangs: the pre-push hook sleeps, the way a stalled network does.
    (repo / ".gitignore").write_text("data/.web-write.lock\npush-started\n")
    _git(repo, "commit", "-q", "--no-verify", "-am", "ignore push marker")
    hook = repo / ".git/hooks/pre-push"
    hook.write_text(SLOW_PRE_PUSH)
    hook.chmod(0o755)
    env = {**os.environ, "PFC_REPO_ROOT": str(repo), "LOCAL_TZ": TZ, "GIT_TERMINAL_PROMPT": "0",
           "PFC_WEB_LOG": str(repo.parent / "web.log")}
    proc = subprocess.Popen([sys.executable, str(SCRIPT), "--no-render", "complete-task", "task-20250901-001"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    assert _wait_for_file(repo / "push-started")
    proc.send_signal(signal.SIGTERM)
    stdout, _ = proc.communicate(timeout=10)
    assert proc.returncode == 0
    out = json.loads(stdout)
    assert out == {"ok": True, "action": "complete-task", "id": "task-20250901-001", "title": "Call the dentist",
                   "email_linked": False, "changed": True,
                   "commit": _git(repo, "rev-parse", "--short", "HEAD").strip(), "pushed": False,
                   "push_error": "The push timed out; the commit is saved and will push next time.",
                   "message": "Saved. Not pushed yet."}
    assert message(repo).startswith("task: complete Call the dentist\n")
    assert rows(repo, "6-tasks/_data/tasks.ndjson")[0]["status"] == "done"
    assert status(repo) == ""
    assert _lock_is_free(repo)
    assert subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "main"], check=True,
                          capture_output=True, text=True).stdout.strip() == remote_before


def _wait_for_file(path: Path, seconds: float = 30.0) -> bool:
    # 30 s, not 10: on a loaded machine the writer's sync and commit can take past
    # 10 s before the push starts (2025-11-15: two full-suite runs at 3-4x normal
    # duration failed here; the same suite unloaded passed with this test at 1.8 s).
    # The wait returns as soon as the file appears, so a passing run is not slower.
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return False


# ---------------------------------------------------------------- changed underneath

def test_a_file_committed_between_plan_and_write_is_refused(repo, monkeypatch, capsys):
    monkeypatch.setenv("LOCAL_TZ", TZ)
    import web_write
    importlib.reload(web_write)
    monkeypatch.setattr(web_write, "REPO", repo)
    real_plan = web_write.plan_complete_task

    def plan_then_a_skill_commits(task_id, today):
        planned = real_plan(task_id, today)
        path = repo / "6-tasks/_data/tasks.ndjson"
        path.write_text(path.read_text() + json.dumps({"id": "task-20250902-001", "status": "open",
                                                       "description": "Added by a skill"}) + "\n")
        _git(repo, "commit", "-qam", "task: add Added by a skill")
        return planned

    monkeypatch.setattr(web_write, "plan_complete_task", plan_then_a_skill_commits)
    previous = signal.getsignal(signal.SIGTERM)
    try:
        code = web_write.main(["--no-render", "complete-task", "task-20250901-001"])
    finally:
        signal.signal(signal.SIGTERM, previous)

    out = json.loads(capsys.readouterr().out)
    assert code == 3
    assert out["reason"] == "changed_underneath"
    # The skill's commit is the last one, and the writer left nothing behind.
    assert message(repo).startswith("task: add Added by a skill") and status(repo) == ""
    assert rows(repo, "6-tasks/_data/tasks.ndjson")[-1]["description"] == "Added by a skill"
    assert rows(repo, "6-tasks/_data/tasks.ndjson")[0]["status"] == "open"


# ---------------------------------------------------------------- rate-day, set-picks, stamp-review

def test_rate_day_fills_an_unrated_row_in_place(repo):
    code, out = run(repo, "rate-day", YESTERDAY, "4", "3", "5")
    assert code == 0 and out["changed"] is True
    row = next(r for r in rows(repo, "data/day-tracking.ndjson") if r["date"] == YESTERDAY)
    assert row["rating"] == 4 and row["energy"] == 4 and row["mood"] == 3 and row["focus"] == 5
    assert "hyperfocused" not in row and row["health"] == {"sleep_hours": 7.0}
    assert _git(repo, "log", "-1", "--format=%s").strip() == f"track: log day {YESTERDAY}"
    assert "Written by the web UI." in message(repo) and TRAILER in message(repo)


def test_rate_day_appends_a_row_when_none_exists(repo):
    code, out = run(repo, "rate-day", TODAY, "3", "3", "3", "hyper:yes")
    assert code == 0
    row = rows(repo, "data/day-tracking.ndjson")[-1]
    assert row["date"] == TODAY and row["rating"] == 3 and row["hyperfocused"] is True
    assert row["sick"] is None and row["exercised"] is None and row["notes"] is None


def test_rate_day_refuses_a_rated_day_outside_the_window_and_bad_ratings(repo):
    code, out = run(repo, "rate-day", YESTERDAY, "4", "3", "5")
    assert code == 0
    before = head(repo)
    code, out = run(repo, "rate-day", YESTERDAY, "1", "1", "1")
    assert code == 0 and out["changed"] is False and head(repo) == before
    code, out = run(repo, "rate-day", "2025-09-04", "1", "1", "1")
    assert code == 2 and out["reason"] == "refused"
    code, out = run(repo, "rate-day", TOMORROW, "1", "1", "1")
    assert code == 2 and out["reason"] == "refused"
    for bad in (["6", "3", "3"], ["0", "3", "3"], ["3", "3"], ["3", "3", "3", "sick:yes"], ["3", "3", "3", "hyper:maybe"], ["3", "3", "3", "hyper:yes", "hyper:no"]):
        code, out = run(repo, "rate-day", TODAY, *bad)
        assert code == 2 and out["reason"] == "bad_request", bad
    assert head(repo) == before


def test_set_picks_adds_a_day_and_keeps_the_project_slot(repo):
    code, out = run(repo, "set-picks", TOMORROW, "task-20250901-001", "task-20250901-005", "bonus:task-20250901-002")
    assert code == 0
    assert rows(repo, "6-tasks/_data/daily-focus.ndjson")[-1] == {
        "date": TOMORROW, "critical": ["task-20250901-001", "task-20250901-005"], "bonus": "task-20250901-002",
        "completed": [], "bonus_completed": False}
    assert _git(repo, "log", "-1", "--format=%s").strip() == f"focus: set {TOMORROW}"
    code, out = run(repo, "set-picks", TODAY, "task-20250901-005")
    assert code == 0
    today = next(r for r in rows(repo, "6-tasks/_data/daily-focus.ndjson") if r["date"] == TODAY)
    assert today["critical"] == ["task-20250901-005"] and today["bonus"] is None


def test_set_picks_same_picks_is_a_no_op(repo):
    before = head(repo)
    code, out = run(repo, "set-picks", TODAY, "task-20250901-001")
    assert code == 0 and out["changed"] is False and head(repo) == before


@pytest.mark.parametrize("args,code,reason", [
    (["task-20250901-004"], 2, "refused"),
    (["task-20250901-001", "bonus:task-20250901-004"], 2, "refused"),
    (["task-20250901-003"], 2, "not_found"),
    (["task-20259999-999"], 2, "not_found"),
    (["task-20250901-001", "task-20250901-002", "task-20250901-005"], 2, "refused"),
    (["task-20250901-001", "task-20250901-001"], 2, "bad_request"),
    ([], 2, "bad_request"),
])
def test_set_picks_refusals(repo, args, code, reason):
    before = head(repo)
    got, out = run(repo, "set-picks", TODAY, *args)
    assert (got, out["reason"]) == (code, reason) and head(repo) == before


def test_set_picks_pull_with_one_done_pick(repo):
    # The fixture's one pick for today is done; two more open tasks can be pulled in.
    code, out = run(repo, "complete-task", "task-20250901-001")
    assert code == 0
    code, out = run(repo, "set-picks", TODAY, "task-20250901-001", "task-20250901-002", "task-20250901-005")
    assert code == 0 and out["changed"] is True, out
    today = next(r for r in rows(repo, "6-tasks/_data/daily-focus.ndjson") if r["date"] == TODAY)
    assert today["critical"] == ["task-20250901-001", "task-20250901-002", "task-20250901-005"]
    assert today["completed"] == ["task-20250901-001"]


def test_set_picks_with_two_done_and_one_new(repo):
    assert run(repo, "set-picks", TODAY, "task-20250901-001", "task-20250901-005")[0] == 0
    assert run(repo, "complete-task", "task-20250901-001")[0] == 0
    assert run(repo, "complete-task", "task-20250901-005")[0] == 0
    code, out = run(repo, "set-picks", TODAY, "task-20250901-001", "task-20250901-005", "task-20250901-002")
    assert code == 0 and out["changed"] is True, out
    today = next(r for r in rows(repo, "6-tasks/_data/daily-focus.ndjson") if r["date"] == TODAY)
    assert today["critical"] == ["task-20250901-001", "task-20250901-005", "task-20250901-002"]
    assert today["completed"] == ["task-20250901-001", "task-20250901-005"]


def test_set_picks_refuses_a_done_task_that_is_not_done_on_that_day(repo):
    # task-20250901-003 is done, but not in today's `completed`, so it is not a pick of today.
    before = head(repo)
    code, out = run(repo, "set-picks", TODAY, "task-20250901-001", "task-20250901-003")
    assert (code, out["reason"]) == (2, "not_found") and head(repo) == before


def test_set_picks_refuses_a_third_undone_pick_after_a_done_one(repo):
    assert run(repo, "set-picks", TODAY, "task-20250901-001", "task-20250901-005")[0] == 0
    before = head(repo)
    code, out = run(repo, "set-picks", TODAY, "task-20250901-001", "task-20250901-005", "task-20250901-002")
    assert (code, out["reason"]) == (2, "refused") and "still open" in out["error"] and head(repo) == before


def test_set_picks_refuses_a_deferred_task(repo):
    tasks = rows(repo, "6-tasks/_data/tasks.ndjson")
    for t in tasks:
        if t["id"] == "task-20250901-005":
            t["deferred"] = True
    (repo / "6-tasks/_data/tasks.ndjson").write_text("".join(json.dumps(t) + "\n" for t in tasks))
    _git(repo, "commit", "-qam", "defer one")
    before = head(repo)
    for args in (["task-20250901-005"], ["task-20250901-001", "bonus:task-20250901-005"]):
        code, out = run(repo, "set-picks", TODAY, *args)
        assert (code, out["reason"]) == (2, "refused") and "parked" in out["error"], args
    assert head(repo) == before


def test_set_picks_refuses_a_day_outside_today_and_tomorrow(repo):
    code, out = run(repo, "set-picks", YESTERDAY, "task-20250901-001")
    assert code == 2 and out["reason"] == "refused"


def test_stamp_review_sets_last_done_to_today(repo):
    code, out = run(repo, "stamp-review", "stale-task-triage")
    assert code == 0 and out["changed"] is True
    assert rows(repo, "data/review-ledger.ndjson")[0]["last_done"] == TODAY
    assert _git(repo, "log", "-1", "--format=%s").strip() == "review: stamp Stale-task triage"
    code, out = run(repo, "stamp-review", "stale-task-triage")
    assert code == 0 and out["changed"] is False
    code, out = run(repo, "stamp-review", "nope")
    assert code == 2 and out["reason"] == "not_found"


def test_drop_pick_takes_a_task_out_of_the_days_picks(repo):
    code, out = run(repo, "drop-pick", TODAY, "task-20250901-001")
    assert code == 0 and out["changed"] is True
    today = next(r for r in rows(repo, "6-tasks/_data/daily-focus.ndjson") if r["date"] == TODAY)
    assert "task-20250901-001" not in today["critical"] and today["dropped"] == ["task-20250901-001"]
    assert _git(repo, "log", "-1", "--format=%s").strip().startswith("focus: drop pick ")
    code, out = run(repo, "drop-pick", TODAY, "task-20250901-002")
    assert (code, out["reason"]) == (2, "not_found")


def test_review_seen_keeps_a_long_review_due_and_a_stamp_clears_it(repo):
    code, out = run(repo, "review-seen", "stale-task-triage", "task-20250901-001", "task-20250901-002")
    assert code == 0 and out["changed"] is True
    row = rows(repo, "data/review-ledger.ndjson")[0]
    assert row["seen"] == ["task-20250901-001", "task-20250901-002"] and row["last_done"] != TODAY
    code, out = run(repo, "review-seen", "stale-task-triage", "task-20250901-001")
    assert code == 0 and out["changed"] is False
    code, out = run(repo, "stamp-review", "stale-task-triage")
    row = rows(repo, "data/review-ledger.ndjson")[0]
    assert code == 0 and row["last_done"] == TODAY and "seen" not in row


# ---------------------------------------------------------------- one-tap writes: skips, areas, rooms, anchors, projects

def test_skip_suggestion_adds_to_an_existing_day(repo):
    code, out = run(repo, "skip-suggestion", TODAY, "task-20250901-002")
    assert code == 0 and out["changed"] is True and out["title"] == "Reply to the landlord's email"
    today = next(r for r in rows(repo, "6-tasks/_data/daily-focus.ndjson") if r["date"] == TODAY)
    assert today["skipped"] == ["task-20250901-002"] and today["critical"] == ["task-20250901-001"]
    assert _git(repo, "log", "-1", "--format=%s").strip() == "focus: skip Reply to the landlord's email"
    before = head(repo)
    code, out = run(repo, "skip-suggestion", TODAY, "task-20250901-002")
    assert code == 0 and out["changed"] is False and head(repo) == before


def test_skip_suggestion_for_tomorrow_creates_a_record(repo):
    code, out = run(repo, "skip-suggestion", TOMORROW, "task-20250901-002")
    assert code == 0
    assert rows(repo, "6-tasks/_data/daily-focus.ndjson")[-1] == {
        "date": TOMORROW, "critical": [], "bonus": None, "completed": [], "bonus_completed": False,
        "skipped": ["task-20250901-002"]}


@pytest.mark.parametrize("args,reason", [
    ([YESTERDAY, "task-20250901-002"], "refused"),
    ([TODAY, "task-20250901-003"], "not_found"),
    ([TODAY, "task-20259999-999"], "not_found"),
    ([TODAY], "bad_request"),
    ([TODAY, "task-20250901-002", "task-20250901-001"], "bad_request"),
    ([TODAY, "--dry-run"], "bad_request"),
    (["2025-02-30", "task-20250901-002"], "bad_request"),
])
def test_skip_suggestion_refusals(repo, args, reason):
    before = head(repo)
    code, out = run(repo, "skip-suggestion", *args)
    assert (code, out["reason"]) == (2, reason) and head(repo) == before


def test_set_area_appends_a_snapshot_copying_the_latest_row(repo):
    code, out = run(repo, "set-area", "career", "yellow")
    assert code == 0 and out["changed"] is True
    snapshots = rows(repo, "2-areas/_data/life-wheel.ndjson")
    assert snapshots[:2] == [LIFE_WHEEL_OLD, LIFE_WHEEL]
    new = snapshots[-1]
    assert new["date"] == TODAY
    assert new["ratings"] == {"career": "yellow", "health": "red", "learning": "red"}
    assert new["notes"] == LIFE_WHEEL["notes"]
    assert re.fullmatch(rf"{TODAY}T\d\d:\d\d:\d\d-0[67]:00", new["logged_at"]), new["logged_at"]
    assert _git(repo, "log", "-1", "--format=%s").strip() == "review: area Career yellow"


def test_set_area_note_forms(repo):
    code, out = run(repo, "set-area", "health", "yellow", "note:Sleeping better: 7 hours, twice.")
    assert code == 0
    assert rows(repo, "2-areas/_data/life-wheel.ndjson")[-1]["notes"] == {
        "health": "Sleeping better: 7 hours, twice.", "learning": "Stalled."}
    code, out = run(repo, "set-area", "health", "yellow", "note:")
    assert code == 0
    assert rows(repo, "2-areas/_data/life-wheel.ndjson")[-1]["notes"] == {"learning": "Stalled."}
    # No note argument leaves the note alone.
    code, out = run(repo, "set-area", "learning", "yellow")
    assert code == 0
    assert rows(repo, "2-areas/_data/life-wheel.ndjson")[-1]["notes"] == {"learning": "Stalled."}


def test_set_area_same_light_is_a_no_op(repo):
    before = head(repo)
    code, out = run(repo, "set-area", "career", "green")
    assert code == 0 and out["changed"] is False and head(repo) == before


@pytest.mark.parametrize("args,reason", [
    (["pets", "green"], "not_found"),
    (["career", "purple"], "bad_request"),
    (["Career", "green"], "bad_request"),
    (["--dry-run", "green"], "bad_request"),
    (["career"], "bad_request"),
    (["career", "green", "just text"], "bad_request"),
    (["career", "green", "note:two\nlines"], "bad_request"),
    (["career", "green", "note:a\u0085b"], "bad_request"),
    (["career", "green", "note:a\u2028b"], "bad_request"),
    (["career", "green", "note:a\u2029b"], "bad_request"),
    (["career", "green", "note:" + "x" * 301], "bad_request"),
    (["career", "green", "note:a", "note:b"], "bad_request"),
])
def test_set_area_refusals(repo, args, reason):
    before = head(repo)
    code, out = run(repo, "set-area", *args)
    assert (code, out["reason"]) == (2, reason) and head(repo) == before


def test_set_area_accepts_a_note_of_exactly_300_characters(repo):
    code, out = run(repo, "set-area", "career", "yellow", "note:" + "x" * 300)
    assert code == 0 and len(rows(repo, "2-areas/_data/life-wheel.ndjson")[-1]["notes"]["career"]) == 300


def test_set_room_changes_household_status(repo):
    code, out = run(repo, "set-room", "garage", "green", "note:Cleared the shelves.")
    assert code == 0
    new = rows(repo, "2-areas/_data/household-status.ndjson")[-1]
    assert new["date"] == TODAY and new["ratings"] == {"kitchen": "yellow", "garage": "green"}
    assert new["notes"] == {"garage": "Cleared the shelves."}
    assert _git(repo, "log", "-1", "--format=%s").strip() == "review: room Garage green"
    code, out = run(repo, "set-room", "career", "green")
    assert (code, out["reason"]) == (2, "not_found")


def test_retire_anchor(repo):
    code, out = run(repo, "retire-anchor", "ground-20250812-001")
    assert code == 0 and out["changed"] is True and out["title"] == "Protect focus time"
    first, second = rows(repo, "data/grounding.ndjson")
    assert first["status"] == "retired" and first["retired_date"] == TODAY
    assert second == GROUNDING[1]
    assert _git(repo, "log", "-1", "--format=%s").strip() == "grounding: retire Protect focus time"
    before = head(repo)
    code, out = run(repo, "retire-anchor", "ground-20250812-001")
    assert code == 0 and out["changed"] is False and head(repo) == before


@pytest.mark.parametrize("arg,reason", [
    ("ground-20259999-999", "not_found"), ("proj-20250801-001", "bad_request"), ("--dry-run", "bad_request"),
])
def test_retire_anchor_refusals(repo, arg, reason):
    code, out = run(repo, "retire-anchor", arg)
    assert (code, out["reason"]) == (2, reason)


def test_set_project_activates_and_parks(repo):
    code, out = run(repo, "set-project", "proj-20250801-001", "active")
    assert code == 0 and out["changed"] is True
    row = rows(repo, "5-projects/_data/projects.ndjson")[0]
    assert row["active"] is True and row["status"] == "active"
    assert _git(repo, "log", "-1", "--format=%s").strip() == "project: activate Closet cleanup"
    code, out = run(repo, "set-project", "proj-20250802-001", "parked")
    assert code == 0
    row = rows(repo, "5-projects/_data/projects.ndjson")[1]
    assert row["active"] is False and row["status"] == "parked"
    assert _git(repo, "log", "-1", "--format=%s").strip() == "project: park Online course"
    before = head(repo)
    code, out = run(repo, "set-project", "proj-20250802-001", "parked")
    assert code == 0 and out["changed"] is False and head(repo) == before


@pytest.mark.parametrize("args,reason", [
    (["proj-20250803-001", "active"], "refused"),
    (["proj-20250804-001", "parked"], "refused"),
    (["proj-20259999-999", "active"], "not_found"),
    (["proj-20250801-001", "paused"], "bad_request"),
    (["proj-20250801-001"], "bad_request"),
    (["ground-20250812-001", "active"], "bad_request"),
])
def test_set_project_refusals(repo, args, reason):
    before = head(repo)
    code, out = run(repo, "set-project", *args)
    assert (code, out["reason"]) == (2, reason) and head(repo) == before
