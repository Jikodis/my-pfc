#!/usr/bin/env python3
"""PreToolUse hook: allow a Bash command when every command word in it is
already allowed by `.claude/settings.json`.

Why: Claude Code's allow rules never match a command that contains `$(...)`
or backticks, so a headless run (`claude -p --permission-prompts none`)
refuses the `TODAY=$(TZ=... date ...)` lines the pfc-* skills use. This hook
parses the command, finds every command word (top level and inside every
substitution), and allows the command only when each one is covered by an
existing `Bash(...)` allow rule. It never allows more than the list does.

Target shells: zsh (the macOS default shell) and bash. The
parser accepts only the syntax the two shells read the same way; any
shell-specific form beyond that (zsh `${(flags)...}`, `$~V`, `$=V`, `$^V`,
glob qualifiers, subshells, arithmetic, process substitution) falls through.

Boundary kept:
  * every command word must match a `Bash(word *)` or `Bash(word)` allow rule
    from `.claude/settings.json` (multi-word prefixes such as
    `Bash(systemctl --user *)` are matched word by word);
  * deny and ask rules are read from `.claude/settings.json`,
    `.claude/settings.local.json`, and the user-level `settings.json`
    (`$CLAUDE_CONFIG_DIR`, else `~/.claude`); any matching one, any Bash
    deny/ask rule the hook cannot read, or a settings file that exists but
    cannot be parsed, falls through;
  * eval, exec, source, `.` and sudo always fall through;
  * redirect targets must be relative paths with no `..`, `~`, glob, or `$`,
    not inside `.claude`, `.git`, or `.githooks`, or /dev/null, or a file
    descriptor; a command that also runs `cd` may only redirect to /dev/null
    or a descriptor, since after `cd` a relative path may leave the repo;
  * the payload's `cwd` must be inside the project root;
  * commands over 64 KB fall through unparsed.

The one widening: a leading `NAME=value` assignment is accepted when NAME is
listed as `Bash(NAME=*)`, or is all caps (`^[A-Z][A-Z0-9_]*$`) and not on the
dangerous list (PATH, IFS, LD_*, DYLD_*, GIT_*, PYTHON*, NODE_*, EDITOR, ...).
Those rules (TODAY, TS, NOW, ...) show the intent: assignments are
shell-local steps. Lowercase names need their own rule.

Output: the allow JSON on stdout when allowed; nothing otherwise, which hands
the command back to the normal permission flow. Always exits 0.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\+?=")
FORBIDDEN_WORDS = {"eval", "exec", "source", ".", "sudo"}
UPPER_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
DANGEROUS_VARS = {
    "PATH", "IFS", "BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS", "PS1", "PS2",
    "PS3", "PS4", "PROMPT", "PROMPT2", "PROMPT3", "PROMPT4", "RPROMPT",
    "PROMPT_COMMAND", "CDPATH", "GLOBIGNORE", "HOME", "FPATH", "ZDOTDIR",
    "NULLCMD", "READNULLCMD", "MODULE_PATH", "TMPPREFIX",
    "EDITOR", "VISUAL", "PAGER", "SHELL", "XDG_CONFIG_HOME",
}
DANGEROUS_PREFIXES = ("LD_", "DYLD_", "BASH_FUNC_", "GIT_", "PYTHON", "NODE_",
                      "PERL", "RUBY", "SYSTEMD_", "LESS", "JAVA_")
PARAM_RE = re.compile(r"\$\{#?[A-Za-z_][A-Za-z0-9_]*(:?[-=+?][^(){}~]*)?\}")
PROTECTED_DIRS = {".claude", ".git", ".githooks"}
MAX_COMMAND_BYTES = 64 * 1024
WORD_STOP = set(" \t\n;&|<>()")


class Unsafe(Exception):
    """Any construct the parser does not fully understand."""


class Word:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.expanded = False  # contains a variable or command substitution
        self.quoted = False    # contains a quote or backslash
        self.ansi = False      # contains $'...' (escapes left undecoded)
        self.lead_parts: list[str] = []  # unquoted literal prefix, for NAME=
        self.lead_open = True

    @property
    def text(self) -> str:
        return "".join(self.parts)

    @property
    def lead(self) -> str:
        return "".join(self.lead_parts)

    def add(self, piece: str) -> None:
        self.parts.append(piece)

    def plain(self, ch: str) -> None:
        self.parts.append(ch)
        if self.lead_open:
            self.lead_parts.append(ch)

    def close_lead(self) -> None:
        self.lead_open = False


class Segment:
    def __init__(self) -> None:
        self.words: list[Word] = []
        self.redirects = 0

    def empty(self) -> bool:
        return not self.words and not self.redirects


class Parser:
    def __init__(self, s: str, segments=None, redirects=None) -> None:
        self.s = s
        self.n = len(s)
        self.i = 0
        self.segments: list[Segment] = segments if segments is not None else []
        self.redirects: list[tuple[str, Word]] = redirects if redirects is not None else []
        self.pending: list[tuple[str, bool, bool]] = []

    # ---- helpers -------------------------------------------------------
    def peek(self, k: int = 0) -> str:
        j = self.i + k
        return self.s[j] if j < self.n else ""

    def skip_blanks(self) -> None:
        while self.i < self.n:
            c = self.s[self.i]
            if c in " \t":
                self.i += 1
            elif c == "\\" and self.peek(1) == "\n":
                self.i += 2
            else:
                break

    def parse_all(self) -> None:
        self.parse_sequence(None)
        if self.pending:
            raise Unsafe("unterminated here-doc")

    # ---- sequences -----------------------------------------------------
    def parse_sequence(self, term: str | None) -> None:
        seg = Segment()
        last_op = None
        while True:
            self.skip_blanks()
            if self.i >= self.n:
                if term is not None:
                    raise Unsafe("unterminated substitution")
                if seg.empty() and last_op in ("|", "&&", "||", "|&"):
                    raise Unsafe("dangling operator")
                self.segments.append(seg)
                return
            c = self.s[self.i]
            if term == ")" and c == ")":
                if seg.empty() and last_op in ("|", "&&", "||", "|&"):
                    raise Unsafe("dangling operator")
                self.i += 1
                self.segments.append(seg)
                return
            if c == "\n":
                self.i += 1
                if seg.empty() and last_op in ("|", "&&", "||", "|&"):
                    # a pipeline may continue on the next line
                    self.read_heredocs()
                    continue
                self.segments.append(seg)
                seg = Segment()
                last_op = None
                self.read_heredocs()
                continue
            if c == "#":
                while self.i < self.n and self.s[self.i] != "\n":
                    self.i += 1
                continue
            if c == "&" and self.peek(1) == ">":
                self.parse_redirect(seg)
                continue
            if c in ";&|":
                two = self.s[self.i:self.i + 2]
                if two in ("&&", "||", "|&"):
                    op = two
                elif two == ";;" or two == ";&":
                    raise Unsafe("case syntax")
                else:
                    op = c
                if seg.empty():
                    raise Unsafe("empty segment before operator")
                self.i += len(op)
                self.segments.append(seg)
                seg = Segment()
                last_op = op
                continue
            if c in "<>":
                self.parse_redirect(seg)
                continue
            if c in "()":
                raise Unsafe("subshell or grouping")
            word, fd = self.read_word(term)
            if fd:
                self.parse_redirect(seg)
                continue
            seg.words.append(word)
            last_op = None

    # ---- here-docs -----------------------------------------------------
    def read_heredocs(self) -> None:
        while self.pending:
            delim, strip, quoted = self.pending.pop(0)
            while True:
                if self.i >= self.n:
                    raise Unsafe("unterminated here-doc")
                end = self.s.find("\n", self.i)
                line = self.s[self.i:] if end == -1 else self.s[self.i:end]
                check = line.lstrip("\t") if strip else line
                if check == delim:
                    self.i = self.n if end == -1 else end + 1
                    break
                if quoted:
                    if end == -1:
                        raise Unsafe("unterminated here-doc")
                    self.i = end + 1
                    continue
                # Unquoted delimiter: the body is expanded, so its
                # substitutions run and must be checked too.
                while self.i < self.n and self.s[self.i] != "\n":
                    ch = self.s[self.i]
                    if ch == "\\":
                        self.i += 2
                    elif ch == "$":
                        self.read_dollar(Word(), in_dq=True)
                    elif ch == "`":
                        self.read_backtick(Word())
                    else:
                        self.i += 1
                if self.i >= self.n:
                    raise Unsafe("unterminated here-doc")
                self.i += 1

    # ---- redirects -----------------------------------------------------
    def parse_redirect(self, seg: Segment) -> None:
        s, i = self.s, self.i
        kind = "path"
        if s.startswith("<<<", i):
            self.i += 3
            kind = "herestring"
        elif s.startswith("<<-", i) or s.startswith("<<", i):
            strip = s.startswith("<<-", i)
            self.i += 3 if strip else 2
            self.skip_blanks()
            if self.i >= self.n or self.s[self.i] in WORD_STOP:
                raise Unsafe("missing here-doc delimiter")
            w, _ = self.read_word(None, allow_fd=False)
            if w.expanded or not w.text:
                raise Unsafe("odd here-doc delimiter")
            self.pending.append((w.text, strip, w.quoted))
            seg.redirects += 1
            return
        elif s.startswith("<(", i) or s.startswith(">(", i):
            raise Unsafe("process substitution")
        elif s.startswith("&>>", i):
            self.i += 3
        elif s.startswith("&>", i) or s.startswith(">>", i) or s.startswith("<>", i):
            self.i += 2
        elif s.startswith(">&", i) and s[i + 2:i + 3] in ("!", "|"):
            # zsh >&! and >&| send stdout and stderr to a file, clobbering it
            self.i += 3
        elif s.startswith(">&", i) or s.startswith("<&", i):
            self.i += 2
            kind = "dup"
        elif s[i] in "<>":
            self.i += 1
        else:
            raise Unsafe("unknown redirect")
        # zsh and bash clobber forms: >|, >>|, >!, >>!, &>|, &>! (the ! is zsh);
        # >&! and >&| are consumed above, so a dup is never followed by one
        if s[self.i - 1] == ">" and self.peek() in ("|", "!"):
            self.i += 1
        if s.startswith("(", self.i):
            raise Unsafe("process substitution")
        self.skip_blanks()
        if self.i >= self.n or self.s[self.i] in WORD_STOP:
            raise Unsafe("missing redirect target")
        w, _ = self.read_word(None, allow_fd=False)
        seg.redirects += 1
        self.redirects.append((kind, w))

    # ---- words ---------------------------------------------------------
    def read_word(self, term: str | None, allow_fd: bool = True) -> tuple[Word, bool]:
        w = Word()
        start = self.i
        while self.i < self.n:
            c = self.s[self.i]
            if c in WORD_STOP:
                if c in "<>" and allow_fd and w.text.isdigit() and not w.quoted \
                        and not w.expanded and self.s[start:self.i] == w.text:
                    return w, True
                if c == "(":
                    raise Unsafe("parenthesis inside a word")
                if c == ")" and term != ")":
                    raise Unsafe("stray parenthesis")
                break
            if c == "\\":
                w.quoted = True
                w.close_lead()
                if self.peek(1) == "\n":
                    self.i += 2
                    continue
                if self.i + 1 >= self.n:
                    raise Unsafe("trailing backslash")
                w.add(self.s[self.i + 1])
                self.i += 2
            elif c == "'":
                w.quoted = True
                w.close_lead()
                end = self.s.find("'", self.i + 1)
                if end == -1:
                    raise Unsafe("unbalanced single quote")
                w.add(self.s[self.i + 1:end])
                self.i = end + 1
            elif c == '"':
                w.quoted = True
                w.close_lead()
                self.read_dquote(w)
            elif c == "$":
                w.close_lead()
                self.read_dollar(w, in_dq=False)
            elif c == "`":
                w.close_lead()
                self.read_backtick(w)
            else:
                w.plain(c)
                self.i += 1
        return w, False

    def read_dquote(self, w: Word) -> None:
        self.i += 1
        while True:
            if self.i >= self.n:
                raise Unsafe("unbalanced double quote")
            c = self.s[self.i]
            if c == '"':
                self.i += 1
                return
            if c == "\\":
                nxt = self.peek(1)
                if nxt == "":
                    raise Unsafe("unbalanced double quote")
                if nxt in '$`"\\':
                    w.add(nxt)
                elif nxt != "\n":
                    w.add("\\" + nxt)
                self.i += 2
            elif c == "$":
                self.read_dollar(w, in_dq=True)
            elif c == "`":
                self.read_backtick(w, in_dq=True)
            else:
                if c == "\n" and self.pending:
                    raise Unsafe("newline in quotes with a pending here-doc")
                w.add(c)
                self.i += 1

    def read_dollar(self, w: Word, in_dq: bool) -> None:
        nxt = self.peek(1)
        if nxt == "(":
            if self.peek(2) == "(":
                raise Unsafe("arithmetic expansion")
            self.i += 2
            self.parse_sequence(")")
            w.expanded = True
        elif nxt == "{":
            # Only plain ${NAME}, ${#NAME} and ${NAME:-word} style forms; zsh
            # flags such as ${(e)V} or ${~V} and anything nested fall through.
            j = self.s.find("}", self.i)
            if j == -1:
                raise Unsafe("unterminated parameter expansion")
            body = self.s[self.i:j + 1]
            if not PARAM_RE.fullmatch(body) or any(ch in body[2:] for ch in "$`'\"\\"):
                raise Unsafe("parameter expansion form not supported")
            w.add(body)
            w.expanded = True
            self.i = j + 1
        elif nxt and nxt in "~=^":
            raise Unsafe("zsh expansion flag")
        elif nxt == "[":
            raise Unsafe("arithmetic expansion")
        elif nxt == "'" and not in_dq:
            j = self.i + 2
            while j < self.n and self.s[j] != "'":
                j += 2 if self.s[j] == "\\" else 1
            if j >= self.n:
                raise Unsafe("unbalanced ANSI-C quote")
            w.add(self.s[self.i + 2:j])
            w.quoted = True
            w.ansi = True
            self.i = j + 1
        elif nxt == '"' and not in_dq:
            self.i += 1  # $"..." locale string: read as a double quote
            w.quoted = True
            self.read_dquote(w)
        elif nxt and (nxt.isalnum() or nxt == "_"):
            j = self.i + 1
            if nxt.isdigit():
                j += 1
            else:
                while j < self.n and (self.s[j].isalnum() or self.s[j] == "_"):
                    j += 1
            w.add(self.s[self.i:j])
            w.expanded = True
            self.i = j
        elif nxt and nxt in "@*#?$!-":
            w.add(self.s[self.i:self.i + 2])
            w.expanded = True
            self.i += 2
        else:
            w.add("$")
            self.i += 1

    def read_backtick(self, w: Word, in_dq: bool = False) -> None:
        # Inside double quotes the shell also turns \" into " before it
        # parses the body, so the body must be read the same way.
        j = self.i + 1
        buf = []
        while True:
            if j >= self.n:
                raise Unsafe("unbalanced backtick")
            ch = self.s[j]
            if ch == "\\" and j + 1 < self.n:
                nxt = self.s[j + 1]
                keep = "$`\\\"" if in_dq else "$`\\"
                buf.append(nxt if nxt in keep else "\\" + nxt)
                j += 2
                continue
            if ch == "`":
                break
            buf.append(ch)
            j += 1
        sub = Parser("".join(buf), self.segments, self.redirects)
        sub.parse_all()
        w.expanded = True
        self.i = j + 1


# ---- rules ---------------------------------------------------------------
class RuleError(Exception):
    """A Bash rule the hook cannot read, or a settings file it cannot parse."""


def parse_bash_rule(rule: str):
    """Return ("prefix", words, exact) or ("assign", name), or None for a
    non-Bash rule. Raise RuleError for a Bash rule in any other form."""
    rule = rule.strip()
    if rule == "Bash":
        raise RuleError(rule)
    if not rule.startswith("Bash("):
        return None
    m = re.fullmatch(r"Bash\((.*)\)", rule)
    if not m:
        raise RuleError(rule)
    inner = m.group(1).strip()
    am = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=\*", inner)
    if am:
        return ("assign", am.group(1))
    if inner.endswith(":*"):
        inner = inner[:-2] + " *"
    if inner.endswith(" *"):
        head = inner[:-2]
        if head.strip() and "*" not in head:
            return ("prefix", head.split(), False)
        raise RuleError(rule)
    if inner and "*" not in inner:
        return ("prefix", inner.split(), True)
    raise RuleError(rule)


class Rules:
    def __init__(self) -> None:
        self.allow: list[tuple[list[str], bool]] = []
        self.allow_assign: set[str] = set()
        self.block: list[tuple[list[str], bool]] = []  # deny + ask
        self.block_assign: set[str] = set()


def read_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())  # unreadable file: caller falls through
    if not isinstance(data, dict):
        raise RuleError(str(path))
    perms = data.get("permissions") or {}
    if not isinstance(perms, dict):
        raise RuleError(str(path))
    return perms


def user_config_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".claude"


def load_rules(root: Path) -> Rules:
    rules = Rules()
    project = read_settings(root / ".claude" / "settings.json")
    for rule in project.get("allow") or []:
        if not isinstance(rule, str):
            continue
        try:
            parsed = parse_bash_rule(rule)
        except RuleError:
            continue  # an allow rule the hook cannot read only narrows it
        if parsed is None:
            continue
        if parsed[0] == "assign":
            rules.allow_assign.add(parsed[1])
        else:
            rules.allow.append((parsed[1], parsed[2]))
    sources = [project,
               read_settings(root / ".claude" / "settings.local.json"),
               read_settings(user_config_dir() / "settings.json")]
    for perms in sources:
        for key in ("deny", "ask"):
            for rule in perms.get(key) or []:
                if not isinstance(rule, str):
                    raise RuleError(repr(rule))
                parsed = parse_bash_rule(rule)  # RuleError: fall through
                if parsed is None:
                    continue
                if parsed[0] == "assign":
                    rules.block_assign.add(parsed[1])
                else:
                    rules.block.append((parsed[1], parsed[2]))
    return rules


def rule_matches(words: list[Word], rule_words: list[str], exact: bool, lenient: bool) -> bool:
    """lenient=True (deny and ask rules): a word whose final text the hook
    cannot know (an expansion, or $'...' with undecoded escapes) matches."""
    if exact and len(words) != len(rule_words):
        return False
    if len(words) < len(rule_words):
        return False
    for w, r in zip(words, rule_words):
        if w.expanded or w.ansi:
            if not lenient:
                return False
            continue
        if w.text != r:
            return False
    return True


def safe_path(w: Word) -> bool:
    t = w.text
    if w.expanded or w.ansi or not t or "$" in t:
        return False
    if t == "/dev/null":
        return True
    if t.startswith("/") or t.startswith("~"):
        return False
    if any(ch in t for ch in "*?[]{}"):
        return False
    segments = [part for part in t.split("/") if part not in ("", ".")]
    if not segments or ".." in segments or segments[0].lower() in PROTECTED_DIRS:
        return False
    return True


def assignment_ok(name: str, rules: Rules) -> bool:
    if name in rules.block_assign:
        return False
    if name in rules.allow_assign:
        return True
    if not UPPER_NAME_RE.match(name):
        return False
    return name not in DANGEROUS_VARS and not name.startswith(DANGEROUS_PREFIXES)


def decide(command: str, root: Path, cwd: str | None = None) -> str | None:
    """Return the allow reason, or None to fall through."""
    if len(command.encode("utf-8")) > MAX_COMMAND_BYTES:
        return None
    root_real = os.path.realpath(root)
    if cwd is not None:
        cwd_real = os.path.realpath(cwd)
        if cwd_real != root_real and not cwd_real.startswith(root_real + os.sep):
            return None
    rules = load_rules(root)
    p = Parser(command)
    p.parse_all()

    checked: list[str] = []
    runs_cd = False
    for seg in p.segments:
        words = list(seg.words)
        while words:
            m = ASSIGN_RE.match(words[0].lead)
            if not m:
                break
            if not assignment_ok(m.group(1), rules):
                return None
            words.pop(0)
        if not words:
            continue
        cmd = words[0]
        if cmd.expanded or not cmd.text:
            return None
        name = cmd.text
        if name in FORBIDDEN_WORDS:
            return None
        if any(rule_matches(words, rw, ex, lenient=True) for rw, ex in rules.block):
            return None
        if not any(rule_matches(words, rw, ex, lenient=False) for rw, ex in rules.allow):
            return None
        if name in ("cd", "pushd", "popd"):
            runs_cd = True
        if name not in checked:
            checked.append(name)

    for kind, w in p.redirects:
        if kind == "herestring":
            continue
        if kind == "dup" and not w.expanded and re.fullmatch(r"\d+-?|-", w.text or ""):
            continue
        if not safe_path(w):
            return None
        if runs_cd and w.text != "/dev/null":
            return None

    if not checked:
        return None
    return "Every command word is on the allow list: " + ", ".join(sorted(checked))


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    for d in (here, *here.parents):
        if (d / ".claude" / "settings.json").is_file():
            return d
    return here.parent


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
            return 0
        command = (payload.get("tool_input") or {}).get("command")
        if not isinstance(command, str) or not command.strip():
            return 0
        cwd = payload.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            return 0
        reason = decide(command, project_root(), cwd)
    except Exception:
        return 0
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": reason,
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
