# Conventions

## File naming

- Use lowercase with hyphens: `my-project-name.md`
- Dates in filenames: ISO 8601 (`YYYY-MM-DD`) for single days, `YYYY-WNN` for weeks, `YYYY-qN` for quarters
- Daily notes: `notes/daily/YYYY-MM-DD.md` (written by `pfc-morning-checkin`)
- Weekly summaries: `notes/weekly/YYYY-WNN.md` (written by `pfc-weekly-checkin`)

## Task IDs

Format: `task-YYYYMMDD-NNN`

- `YYYYMMDD` = creation date
- `NNN` = sequential number for that day (001, 002, etc.)
- Determined by counting existing tasks for that day in `5-actions/_data/tasks.ndjson`

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
- `checkin: record [date]`
- `project: [add|update|archive] [name]`
- `report: generate weekly check-in`
- `report: generate monthly check-in`
- `report: generate yearly check-in`
- `system: [description of structural change]`
- `personal: [description]` — for structural changes that intentionally stay maintainer-only and must NOT propagate to the public template. `/pfc-update-template` skips these commits entirely (no diff inspection, no PR proposal). Use when a change touches template-eligible files (skills, automations, schemas, docs) but is bespoke to this fork.

## Dates

- Always use ISO 8601: `YYYY-MM-DD`
- Timestamps in NDJSON event logs use ISO 8601 with timezone: `YYYY-MM-DDTHH:MM:SSZ`
- Derive the current local date from server UTC with `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'` (set `LOCAL_TZ` in `.env` to your IANA zone) — do not trust injected `currentDate` if it conflicts
