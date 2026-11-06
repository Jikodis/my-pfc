---
name: pfc-list-tasks
description: Show all open tasks. Use when the user says "show my tasks", "task list", "list tasks", "open tasks", "what's on my list", "what am I working on", or wants to review the full task backlog without the rest of the status view.
---

# List Open Tasks

Show every open task in `6-tasks/_data/tasks.ndjson`, nothing else. No life wheel, no habits, no hypotheses, no trend tables. Just the task list.

## Step 1: Pull open tasks

```bash
jq -c 'select(.status == "open")' 6-tasks/_data/tasks.ndjson
```

## Step 2: Render — two subsections, never duplicate a task across them

### 2a. Standalone tasks (`project == "none"`)

One flat list, sorted by (in order):
1. impact: high → medium → low
2. urgency: high → medium → low
3. size: XS → S → M → L → XL
4. deadline: earliest first (null deadlines last)

One compact line per task, no blank lines between rows. **Impact and urgency use A/B/C letters, not H/M/L.** This matches the `pfc-add-task` shorthand: A=high, B=medium, C=low. First letter is impact, second is urgency. Format:

```
XY (size) - description  (due YYYY-MM-DD)
```

Example: `AB (M) - Submit expense report  (due 2026-05-01)` → high impact, medium urgency, size M.

- Do NOT show task IDs in the rendered list — they muddy the output. The user can reference tasks by description when completing; `pfc-complete-task` does keyword search.
- Do NOT use H/M/L letters anywhere. Only A/B/C.
- Omit `(due …)` when deadline is null.
- Prefix overdue tasks with `[OVERDUE]`.
- Prefix stale tasks (created 2+ weeks ago and no deadline) with `[STALE]`.

### 2b. Project tasks — one subsection per active project with open tasks

For each such project, render a heading `**<project name>** (<N> open)` then:

- Overdue tasks for this project — always shown individually, above today's. Never collapse overdue.
- Today's task for this project (deadline == today), if any.
- Next 1–2 near-term tasks (deadline > today, soonest first).
- If more remain: a single summary line `+N more through YYYY-MM-DD` (latest deadline across the project's remaining open tasks).

Do NOT enumerate 20–30 course-series tasks. Collapsing is mandatory once a project has >3 future-dated open tasks.

Project names come from `5-projects/_data/projects.ndjson`:
```bash
jq -c 'select(.active == true) | {id, name}' 5-projects/_data/projects.ndjson
```

## Step 3: Footer

One line: total open count. Example: `105 open tasks.`

## Rules

- Never emit a group header more than once.
- Never list the same task in both 2a and 2b.
- Never render task IDs. Descriptions + impact/urgency/size are enough.
- Always A/B/C for impact and urgency. Never H/M/L.
- Use `jq` for all reads — never `grep` on structured NDJSON.
- Date math uses `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'`.
- Read-only — this skill never commits, never writes.
- No prose, no commentary, no "want me to...?" trailing prompt. Just the list.

## Parked tasks (`deferred: true`)

`/pfc-list-tasks` is the ONE place a parked task stays visible — it's hidden from pick pools, the Trello `✅ Tasks` list, and `pfc-revive`'s slippage signals, so without this section it would vanish from the system entirely.

List them in a separate section **after** the live tasks, headed `⏸️ Parked (not in rotation)`, showing the description and `deferred_reason` so the why is visible at un-park time:

```bash
jq -c 'select(.status == "open" and .deferred == true) | {id, description, deferred_reason, area}' \
  6-tasks/_data/tasks.ndjson
```

Never mix parked tasks into the main list or the counts — they are not on deck. Don't nudge about them; the user parked them deliberately. To un-park, set `deferred` to `false`.
