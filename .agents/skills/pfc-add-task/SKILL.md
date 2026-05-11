---
name: pfc-add-task
description: Add a new task to the productivity system. Use when the user says "add task", "new task", "todo", or similar.
---

# Add Task

All tasks live in `5-actions/_data/tasks.ndjson` — strategic and operational alike. See [task_schema.yaml](../../../config/task_schema.yaml).

## Required fields

Every task needs all four — never skip or omit any:
- **size**: `XS`, `S`, `M`, `L`, `XL`
- **location**: `Home`, `PC`, `Errand`, `Phone`, `Anywhere`
- **impact**: `high`, `medium`, `low`
- **urgency**: `high`, `medium`, `low`

For operational items without clear strategic weight, default to `impact: medium`, `urgency: low`. Infer from context — only ask if truly ambiguous.

## Shorthand input

The user often prefixes task input with a compact code like `BC S Install <software> ...`:

- **1st letter** = impact: `A`=high, `B`=medium, `C`=low
- **2nd letter** = urgency: `A`=high, `B`=medium, `C`=low
- **Following token** = size: `XS`, `S`, `M`, `L`, `XL`

Example: `BC S Install <software> on <device>` → impact=medium, urgency=low, size=S, description="Install <software> on <device>". Strip the codes from the description before saving. If the leading letters aren't valid A/B/C, treat them as part of the description.

## Steps

1. Parse description, notes, size, location, impact, urgency, project, and deadline from user input. Infer any missing required fields. `notes` is optional — include any links, extended context, or details the user provides beyond the short title.
2. **Breakdown check — ALWAYS apply.** Before appending, evaluate whether the task decomposes into 2+ distinct steps. If it does, either (a) split into separate tasks with an explicit dependency note (e.g. "Depends on task-YYYYMMDD-NNN"), or (b) capture the sub-steps inside `notes`. Apply this by default — **do not wait for the user to request it.**

   Common split patterns:
   - **"Pick X + do X with X"** → two tasks, second depends on first (e.g. pick doctor → schedule appointment)
   - **"Research + decide + act"** → two tasks OR one task with phased sub-steps in notes
   - **Any `size: M` or larger** → probe: can this be 15-minute chunks instead?
   - **Task phrased as a multi-stage project** (contact A, then B, then C) → split each stage or list them in notes

   Why: if the user's profile indicates severe Initiation/Execution deficits (see [`0-me/profile.md`](../../../0-me/profile.md), or [`0-me/core-psychology.md`](../../../0-me/core-psychology.md) if present), un-broken-down tasks go un-done regardless of intent or motivation. This is accommodation, not style.

   Exception: genuinely atomic actions (one phone call, one form submission, one button press) stay as-is.

   When splitting, increment task IDs sequentially and populate the dependent task's `depends_on` field with the prior task's ID (e.g. `"depends_on": ["task-20260422-004"]`). Do NOT stuff the dependency into notes — `depends_on` is the schema field and is validated. `pfc-pick-tasks` hides a task from suggestions until all its `depends_on` entries are `done`, so the picker automatically enforces the order. Commit all resulting tasks together.
3. **Duplicate check — ALWAYS run before appending.** Search existing open tasks for similar descriptions:
   ```bash
   # Extract 2-3 keywords from the description; use case-insensitive substring match.
   jq -c --arg kw "KEYWORD" 'select(.status == "open" and (.description | test($kw; "i")))' 5-actions/_data/tasks.ndjson
   ```
   Try each significant noun/verb from the user's input. If any existing open task looks like a match:
   - Show the existing record(s) to the user.
   - Ask: "This looks like a duplicate of `task-YYYYMMDD-NNN` — use the existing task / add a new one / cancel?"
   - Only proceed if the user confirms the new task is genuinely distinct.
4. If the task has no `project`, ask which area of life it serves and which value(s) from `1-values/values.md`. If it can't be tied to any area or value, flag it: "This task doesn't connect to an area or value — do you still want to add it, or reconsider?"
5. Get today's date: `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'`
6. Generate ID: `task-YYYYMMDD-NNN` (count existing `task-YYYYMMDD-` entries + 1)
7. Append via jq (never raw echo):
   ```bash
   jq -cn \
     --arg id "task-YYYYMMDD-NNN" \
     --arg desc "..." \
     --argjson notes '"NOTES_STRING_OR_NULL"' \
     --argjson depends_on 'null' \
     --arg created "YYYY-MM-DD" \
     '{id:$id, status:"open", description:$desc, notes:$notes, size:"M", location:"PC", impact:"high", urgency:"low", project:"none", depends_on:$depends_on, deadline:null, created:$created, completed:null, source:"chat"}' \
     >> 5-actions/_data/tasks.ndjson
   ```
   - Pass `--argjson notes 'null'` when no notes, or `--argjson notes '"the notes text"'` when notes are present.
   - Pass `--argjson depends_on 'null'` when no dependencies, or `--argjson depends_on '["task-20260422-004"]'` (JSON array) when the task is blocked by one or more prior tasks.
8. Append event to `5-actions/_data/task_events.ndjson`:
   ```bash
   jq -cn --arg id "task-YYYYMMDD-NNN" --arg ts "YYYY-MM-DD" \
     '{task_id:$id, event:"created", timestamp:$ts, source:"chat"}' \
     >> 5-actions/_data/task_events.ndjson
   ```
9. Commit and push: `git add 5-actions/_data/ && git commit -m "task: add [short description]" && git push`

10. **Refresh Trello dashboard** (fail-safe)

    If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, refresh the board so the new task shows up on `✅ Actions` immediately.

    ```bash
    python3 automations/scripts/trello_render.py 2>&1
    ```

    On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step.

IMPORTANT: All NDJSON writes must use `jq` — never raw string appends, `echo >>`, or `sed` on structured data.
