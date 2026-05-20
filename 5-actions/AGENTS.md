# Agents — actions folder

Folder-scoped operational rules for any agent reading or writing in `5-actions/`. Cross-cutting rules live in the repo-root `AGENTS.md` and take precedence when they overlap.

## File summary

| Path | Shape | Mutability |
|---|---|---|
| `_data/tasks.ndjson` | One task per line | Mutable in place (status, completed date, etc.) |
| `_data/tasks-archive.ndjson` | One archived task per line | Append-only at archive time |
| `_data/task_events.ndjson` | One event per line | **Append-only — never rewrite** |
| `_data/daily-focus.ndjson` | One day per line | Append for new day, mutate in place during the day |

## Schema

- Task records: `config/task_schema.yaml`
- ID format: `task-YYYYMMDD-NNN` where `YYYYMMDD` is the creation date in `$LOCAL_TZ` and `NNN` is a per-day sequence number starting at `001`.
- Daily-focus records: see [`../docs/data-model.md`](../docs/data-model.md) § daily-focus.

## Hard rules

1. **Never read the entire `tasks.ndjson` into context.** Always query with `jq`. Active files can be hundreds of records.
2. **All structured writes go through `jq`.** Never use raw `echo >>`, `sed`, or string concatenation on NDJSON — escaping and type handling will eventually bite you.
3. **Task events are append-only.** Even when correcting a mistake, append a corrective event (e.g. `reverted`); do not edit prior events in place.
4. **Mutating updates require the atomic temp-file pattern** to avoid clobbering the file on a partial write:
   ```bash
   jq -c 'if .id == "TASK-ID" then . + {status:"done", completed:"YYYY-MM-DD"} else . end' \
     5-actions/_data/tasks.ndjson > data/.jq_update.tmp \
     && mv data/.jq_update.tmp 5-actions/_data/tasks.ndjson
   ```
5. **Always log lifecycle events to `task_events.ndjson`** when changing task status — creation, completion, deferral, archive. The weekly review depends on it.
6. **Date stamps are derived in `$LOCAL_TZ`.** Never trust the system-injected `currentDate`. See repo-root `AGENTS.md` § Dates and time.

## Canonical query patterns

```bash
# All open tasks, high urgency
jq -c 'select(.status == "open" and .urgency == "high")' 5-actions/_data/tasks.ndjson

# One task by id
jq -c 'select(.id == "task-20260412-001")' 5-actions/_data/tasks.ndjson

# Today's daily-focus record
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
jq -c --arg d "$TODAY" 'select(.date == $d)' 5-actions/_data/daily-focus.ndjson
```

## Archival policy

Audits and health checks **never** archive tasks. Archival happens exclusively during weekly check-in. If you notice the live `tasks.ndjson` is getting long during a non-checkin run, report it informationally — do not move records into the archive.

## Daily focus — 2+1 (+ optional project slot)

Each morning, pick 3 deliberate tasks plus an optional 4th:

- **2 critical items** — most important things to accomplish
- **1 bonus task** — stretch item if time and energy allow
- **(optional) 1 project task** — a 4th slot reserved for a pre-planned active-project task

Logged in `_data/daily-focus.ndjson` under `critical` (2 ids), `bonus` (1 id), and optionally `project` (1 id).

**Project tasks live outside the 2+1.** A task with `project != "none"` is pre-planned work; it should NOT compete with standalone tasks for the 2 critical slots. Reserving the 4th slot for an active-project task makes that work visible in the daily flow without crowding the standalone 2+1. Project work runs on its own deadline cadence and is surfaced via the project status block (see `../4-projects/AGENTS.md` § Daily project status), not via 2+1 prioritization.

## Task breakdown

Any time a task feels too big, offer to break it down into 15-minute chunks. ADHD context: overwhelm often prevents starting — the problem is usually the task definition, not motivation. See `pfc-pick-tasks` skill for stale task triage during reviews.

## Slippage / pfc-revive

See `../4-projects/AGENTS.md` § Slippage — the skill spans tasks + projects, and projects are higher-stakes (vision/values aligned). Task-side triggers are: open task ≥30 days, high-impact open task ≥7 days, same task carried in 2+1 ≥3 days without completion.

## See also

- Repo-root [`AGENTS.md`](../AGENTS.md) § Task operations — the canonical reference for query/update patterns.
- [`docs/data-model.md`](../docs/data-model.md) — full schemas for tasks, events, daily-focus.
