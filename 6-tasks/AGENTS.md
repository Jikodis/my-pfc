# Agents — actions folder

Folder-scoped operational rules for any agent reading or writing in `6-tasks/`. Cross-cutting rules live in the repo-root `AGENTS.md` and take precedence when they overlap.

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
     6-tasks/_data/tasks.ndjson > data/.jq_update.tmp \
     && mv data/.jq_update.tmp 6-tasks/_data/tasks.ndjson
   ```
5. **Always log lifecycle events to `task_events.ndjson`** when changing task status — creation, completion, deferral, archive. The rolling reviews and trend analysis depend on it.
6. **Date stamps are derived in `$LOCAL_TZ`.** Never trust the system-injected `currentDate`. See repo-root `AGENTS.md` § Dates and time.

## Canonical query patterns

```bash
# All open tasks, high urgency
jq -c 'select(.status == "open" and .urgency == "high")' 6-tasks/_data/tasks.ndjson

# One task by id
jq -c 'select(.id == "task-20260412-001")' 6-tasks/_data/tasks.ndjson

# Today's daily-focus record
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
jq -c --arg d "$TODAY" 'select(.date == $d)' 6-tasks/_data/daily-focus.ndjson
```

## Archival policy

Audits and health checks **never** archive tasks. Archival happens in exactly two places: during the `stale-task-triage` rolling review, and when the live `tasks.ndjson` grows past roughly 200 lines. If you notice the live file is getting long during any other run, report it informationally — do not move records into the archive.

Archiving means moving `status: "done"` records out of `_data/tasks.ndjson` and appending them to `_data/tasks-archive.ndjson`. Completed tasks are never deleted: `pfc-add-task`'s duplicate check and `pfc-email-triage`'s thread dedup both query the archive, so dropping records there would let handled items respawn.

## Daily focus — 2+1 (+ optional project slot)

Each day carries 3 deliberate tasks plus an optional 4th:

- **2 critical items** — most important things to accomplish
- **1 bonus task** — stretch item if time and energy allow
- **(optional) 1 project task** — a 4th slot reserved for a pre-planned active-project task

Logged in `_data/daily-focus.ndjson` under `critical` (2 ids), `bonus` (1 id), and optionally `project` (1 id).

### Picked the night before, not the morning of

The 2+1 is **staged the evening before** by the evening check-in, not chosen the morning it applies to. The record for tomorrow's date is written tonight.

Why the night before rather than the morning: picking is a planning act, and planning at the moment you're supposed to *start* puts a decision in front of the thing you were already having trouble starting. Deciding the night before means the morning has no decision in it — the picks are already made and waiting. It also means the picks bend out of a running state (the check-in you're already in) instead of needing to be summoned cold.

**Ceiling: exactly one day ahead. Never stage a 2+1 for a date beyond tomorrow.** Writing `daily-focus` records two or three days out produces a plan that's already wrong by the time it arrives — an overdue task lands, a meeting moves, energy is different — and then the stale picks either get silently ignored (teaching you the 2+1 doesn't mean anything) or get re-picked anyway, which made the advance work waste. One day is far enough to remove the morning decision and near enough that tomorrow's conditions are still knowable.

Consequences to hold:

- **At most two open focus records at any moment:** today's (in flight) and tomorrow's (staged). Anything further out is a bug.
- **A same-day re-pick is legitimate** and mutates today's existing record in place — it does not append a second row for the same date. One row per date, always.
- **When the 2+1 for a date changes, anything mirroring it must change in the same breath** — the calendar anchor annotation and the Trello board both. A focus write that leaves a mirror showing stale picks is a bug, not a lag.

**Project tasks live outside the 2+1.** A task with `project != "none"` is pre-planned work; it should NOT compete with standalone tasks for the 2 critical slots. Reserving the 4th slot for an active-project task makes that work visible in the daily flow without crowding the standalone 2+1. Project work runs on its own deadline cadence and is surfaced via the project status block (see `../5-projects/AGENTS.md` § Daily project status), not via 2+1 prioritization.

## Task breakdown

Any time a task feels too big, offer to break it down into 15-minute chunks. ADHD context: overwhelm often prevents starting — the problem is usually the task definition, not motivation. See `pfc-pick-tasks` skill for stale task triage during reviews.

**The first sub-step must be doable in two minutes.** When a task gets broken down, size the *first* step so starting it costs almost nothing — "open the file", "put the case by the door", "open the course" — not "draft the section" or "review the doc". If the first step would take longer than two minutes, break it down again.

Why the first step specifically: the effort-cost calculation prices the *first* action, not the average one. A 15-minute task whose first step is 15 minutes reads as "not worth it"; the same task whose first step is 30 seconds fires. See [`docs/habit-mechanics.md`](../docs/habit-mechanics.md) § The two-minute first step.

## Agent delegation — the `agent_doable` field

Starting is often the hardest part of a task, not the ability to do it. So the cheapest route through a stalled task is often **not being the one who does it**. Every open task carries `agent_doable` (definition in `config/task_schema.yaml`):

| Value | Meaning | Example tasks |
|---|---|---|
| `yes` | A browser agent drives it start to finish; the user approves the result | Research a product and summarize the reviews, fill out an online form, reorder a household item |
| `partly` | Agent does the setup or research; the user does the one irreducibly human step (a call, a signature, being somewhere, talking to a person) | Plan a trip (agent drafts options, user picks and pays), sort a cluttered inbox folder |
| `no` | Only the user: their learning, their body, their relationships, their creative voice | Practice an instrument, work through a course, write a letter to a friend |

Rules:

1. **Set it at capture time.** `pfc-add-task` asks or infers. Unclassified (`null`) is only for older records.
2. **A `no` must be defensible.** "Only I can do it" means the *doing* is the point (learning, presence, voice) or it needs the user's body in a place. "It'd be faster if I did it" is not a `no`.
3. **Never mark a relationship or parenting conversation `yes`.** An agent may prepare the material; the conversation is the user's.
4. **`yes` tasks batch.** They are meant to be run several at once in separate browser tabs and supervised, not picked one at a time into the 2+1. Pull the batch with:
   ```bash
   jq -r 'select(.status == "open" and .agent_doable == "yes") | .id + " — " + .description' \
     6-tasks/_data/tasks.ndjson
   ```

## Slippage / pfc-revive

See `../5-projects/AGENTS.md` § Slippage — the skill spans tasks + projects, and projects are higher-stakes (vision/values aligned). Task-side triggers are: open task ≥30 days, high-impact open task ≥7 days, same task carried in 2+1 ≥3 days without completion.

## See also

- Repo-root [`AGENTS.md`](../AGENTS.md) § Task operations — the canonical reference for query/update patterns.
- [`docs/data-model.md`](../docs/data-model.md) — full schemas for tasks, events, daily-focus.
