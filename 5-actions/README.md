# Actions

The "do" layer of VAVPAH. Concrete next steps — tasks, daily focus picks, and an event log of what actually happened.

## What lives here

- **Tasks** (`_data/tasks.ndjson`) — every open and recently-completed task. New tasks are appended; the `pfc-add-task` skill walks you through capture. The `pfc-pick-tasks` skill surfaces what to work on next, prioritized by impact, urgency, and size.
- **Archive** (`_data/tasks-archive.ndjson`) — completed tasks rolled out of the working set during weekly check-in, so the live file stays readable.
- **Event log** (`_data/task_events.ndjson`) — append-only history: every task creation, completion, deferral. Lets the weekly review answer "what actually moved this week?"
- **Daily focus** (`_data/daily-focus.ndjson`) — the 2+1 picks for each day (2 critical + 1 bonus, optionally + 1 project task). Driven by `pfc-morning-checkin`.

## Key skills

| Skill | What it does |
|---|---|
| `/pfc-add-task` | Capture a new task — interactive walk-through for size, location, impact, urgency |
| `/pfc-complete-task` | Mark a task done |
| `/pfc-pick-tasks` | Suggest what to work on next |
| `/pfc-list-tasks` | Show all open tasks |
| `/pfc-morning-checkin` | Pick today's 2+1 |
| `/pfc-schedule-focus` | Drop today's focus picks onto your calendar |

## Why an event log

Tasks are mutable (status changes from open → done; deadlines slip). The event log is append-only — once something is recorded, it's never rewritten. That gives you a real history to look back on without losing fidelity when the live state changes.

## Agent operations

If you're an agent working with this folder, see [`AGENTS.md`](AGENTS.md) at this level for the operational rules (jq patterns, ID format, never-read-entire-file).
