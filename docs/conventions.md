# Conventions

## File naming

- Use lowercase with hyphens: `my-project-name.md`
- Dates in filenames: ISO 8601 (`YYYY-MM-DD`) for single days, `YYYY-WNN` for weeks, `YYYY-qN` for quarters
- Daily notes: `notes/daily/YYYY-MM-DD.md` (generated reports)

## Task IDs

Format: `task-YYYYMMDD-NNN`

- `YYYYMMDD` = creation date
- `NNN` = sequential number for that day (001, 002, etc.)
- Determined by counting existing tasks for that day in `6-tasks/_data/tasks.ndjson`

## NDJSON files

- One JSON object per line, no trailing commas
- Append-only for event logs (`task_events.ndjson`, `day-tracking.ndjson`, `daily-focus.ndjson`, habit logs)
- Mutable in place for state stores (`tasks.ndjson`, `projects.ndjson`, `supplements.ndjson`, `hypotheses.ndjson`)
- All writes go through `jq` — never raw string concatenation, `echo >>` of raw JSON, or `sed` for structured edits. See CLAUDE.md "Task operations" for the canonical jq patterns.
- Never read entire NDJSON files into Claude's context — query with `jq`.

## Markdown frontmatter

Skills use YAML frontmatter with `name` and `description` fields. Project and area files use markdown headers, not frontmatter.

## Commit messages

See CLAUDE.md "Commit message conventions" for the canonical list. Summary:

- `task: add [description]`
- `task: complete [description]`
- `focus: set [date]`
- `habit: log [date]`
- `track: log day [date]`
- `track: trello sync [date]`
- `track: refresh calendar cache`
- `review: stamp [label]`
- `project: [add|update|archive] [name]`
- `report: generate yearly check-in`
- `system: [description of structural change]`

## Dates

- Always use ISO 8601: `YYYY-MM-DD`
- Timestamps in NDJSON event logs use ISO 8601 with timezone: `YYYY-MM-DDTHH:MM:SSZ`
- Derive the current local date from server UTC with `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'` (set `LOCAL_TZ` in `.env` to your IANA zone) — do not trust injected `currentDate` if it conflicts

## Bash permission hook

Claude Code's allow rules never match a command that contains `$(...)` or backticks, so the `TODAY=$(TZ=... date ...)` lines in the `pfc-*` skills are refused in headless runs (`claude -p --permission-prompts none`, which the web UI's chat drawer uses). `scripts/hook-allow-known-commands.py`, registered as a `PreToolUse` hook on `Bash` in `.claude/settings.json`, parses each command for zsh (the macOS default shell) and bash, and allows it only when all of these hold:
- every command word, at the top level and inside every substitution, is covered by a `Bash(...)` allow rule in `.claude/settings.json`;
- no deny or ask rule matches, read from `.claude/settings.json`, `.claude/settings.local.json`, and the user-level `settings.json` (`$CLAUDE_CONFIG_DIR`, else `~/.claude`); a Bash deny or ask rule the hook cannot read, or a settings file that exists but cannot be parsed, turns the hook off for every command;
- every redirect writes to `/dev/null`, a file descriptor, or a relative path inside the repo with no `..`, `~`, glob, or `$`, and not into `.claude/`, `.git/`, or `.githooks/`; a command that also runs `cd` may redirect only to `/dev/null` or a descriptor, because after `cd` a relative path may point outside the repo;
- the session's working directory is inside the repo, and the command is under 64 KB.

Anything it cannot fully parse, including zsh-only forms such as `${(e)V}` or `$~V`, is handed back to the normal permission flow, and deny rules still win over its allow. The allow list stays the boundary. The one deliberate widening: a leading `NAME=value` assignment is accepted when the name is listed as `Bash(NAME=*)` or is all caps and not on the hook's list of names that change how later commands run (`PATH`, `IFS`, `LD_*`, `DYLD_*`, `GIT_*`, `PYTHON*`, `NODE_*`, `EDITOR`, `PAGER`, `SHELL`, and similar), because the listed rules (`TODAY`, `TS`, `NOW`) show that shell-local assignments are intended. Tests: `pytest scripts/tests -q`.
