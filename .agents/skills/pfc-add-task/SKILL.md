---
name: pfc-add-task
description: Add a new task to the productivity system. Use when the user says "add task", "new task", "todo", or similar.
---

# Add Task

All tasks live in `6-tasks/_data/tasks.ndjson` — strategic and operational alike. See [task_schema.yaml](../../../config/task_schema.yaml).

## Required fields

Every task needs all five — never skip or omit any:
- **size**: `XS`, `S`, `M`, `L`, `XL`
- **location**: `Home`, `PC`, `Errand`, `Phone`, `Anywhere`
- **impact**: `high`, `medium`, `low`
- **urgency**: `high`, `medium`, `low`
- **agent_doable**: `yes`, `partly`, `no` — who can actually do the work. Infer it; only ask when it's genuinely unclear. Full rules: [`../../../6-tasks/AGENTS.md`](../../../6-tasks/AGENTS.md) § Agent delegation.
  - **`yes`**: an agent with a browser can drive it start to finish and the user only approves the result. Infer it for online research, comparing and picking, web forms, portals, registrations, warranties, returns, purchases, account changes, drafting a reply, and code in this repo.
  - **`partly`**: an agent does the setup or research, and the user does one step only a person can do. Infer it for anything that ends in a phone call, a signature, a physical object, or being somewhere in person.
  - **`no`**: only the user can do it. Infer it for learning and practice, workouts, creative work in the user's own voice, and any conversation with another person.
  - **The bar for `no` is "the doing is the point."** "It would be faster to just do it myself" is not a reason for `no`; a task an agent can finish should not take one of the user's 2+1 slots.

For operational items without clear strategic weight, default to `impact: medium`, `urgency: low`. Infer from context — only ask if truly ambiguous.

## Parking a task (`deferred`)

When the user says "take X off the rotation", "park it", "stop offering it", or "not until I'm ready", set `deferred: true` on the task plus a `deferred_reason` in their own words. Do NOT delete it and do NOT mark it done — it's still open work.

```bash
tmp=6-tasks/_data/.jq_update.tmp
jq -c --arg id "task-YYYYMMDD-NNN" --arg why "..." \
  'if .id==$id then .deferred=true | .deferred_reason=$why else . end' \
  6-tasks/_data/tasks.ndjson > "$tmp" && mv "$tmp" 6-tasks/_data/tasks.ndjson
```

Deferred tasks drop out of `pfc-pick-tasks`, the evening check-in's 2+1 pool, the Trello `✅ Tasks` list, and `pfc-revive`'s slippage signals. They stay visible in `/pfc-list-tasks`. Un-park by setting `deferred` to `false`.

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

   **The first sub-step must be doable in two minutes.** When a task gets broken down, size the *first* step so starting it costs almost nothing — "open the file", "put the case by the door", "open the course" — not "draft the section" or "review the doc". If the first step would take longer than two minutes, break it down again.

   Why the first step specifically: the effort-cost calculation prices the *first* action, not the average one. A 15-minute task whose first step is 15 minutes reads as "not worth it"; the same task whose first step is 30 seconds fires. This sharpens the 15-minute chunk rule at the point where launch actually fails. See [`docs/habit-mechanics.md`](../../../docs/habit-mechanics.md) § The two-minute first step.

   When splitting, increment task IDs sequentially and populate the dependent task's `depends_on` field with the prior task's ID (e.g. `"depends_on": ["task-20260422-004"]`). Do NOT stuff the dependency into notes — `depends_on` is the schema field and is validated. `pfc-pick-tasks` hides a task from suggestions until all its `depends_on` entries are `done`, so the picker automatically enforces the order. Commit all resulting tasks together.

2a. **Trigger-plan prompt for initiation-heavy items (optional, one line).** If the task looks initiation-heavy — size L/XL, OR the description hints at re-entering a stalled thread ("get back into", "start again", "finally", "course", "practice", "resume"), OR it's explicitly low-interest-but-important — ask once, in one line:

    > "Want to attach a trigger plan? (anchor-to: <running state> / person-at-start: <who and when, if available> / scheduled live / action-alarm / skip)"

    Default to **anchor-to-running-state** in your suggestion: it needs no other person and is always available. Chaining a stalled chunk onto something already in motion (a meeting ending, a meal finishing, music starting) closes the decision gap that object-based reminders — sticky notes, calendar squares, progress bars — cannot, because those go invisible within a couple of days.

    If the user picks anything other than `skip`, write it into `notes` with a `trigger:` prefix, the same format `pfc-revive` uses (e.g. `"trigger: anchor-to end of morning standup"`). Both `pfc-pick-tasks` and `pfc-revive` read this field. One-line ask — do not interview; if they skip, move on.

3. **Duplicate check — ALWAYS run before appending.** Run the layers below in order; stop at the first hit.

   **Layer 1 — email thread ID (exact; only when `source='email-triage'`).** When the caller passes an email thread ID, query both open AND archived tasks for an exact match:
   ```bash
   jq -c --arg tid "GMAIL_THREAD_ID" 'select(.source_email_thread_id == $tid)' \
     6-tasks/_data/tasks.ndjson 6-tasks/_data/tasks-archive.ndjson
   ```
   Match against the archive too — a previously-completed task on the same thread usually means the email should be unlabeled, not re-tasked.

   **Layer 2 — normalized email subject (fallback when there's no thread ID, or Layer 1 missed).** Strip any `Re:` / `Fwd:` prefix, lowercase, then exact-match against existing `source_email_subject` values:
   ```bash
   NORM=$(printf '%s' "EMAIL_SUBJECT" | sed -E 's/^([Rr][Ee]|[Ff][Ww][Dd]):[[:space:]]*//' | tr '[:upper:]' '[:lower:]')
   jq -c --arg sub "$NORM" 'select((.source_email_subject // "") | ascii_downcase | sub("^(re|fwd):[[:space:]]*"; "") == $sub)' \
     6-tasks/_data/tasks.ndjson 6-tasks/_data/tasks-archive.ndjson
   ```

   **Layer 3 — keyword substring (always; catches non-email duplicates and same-topic-different-phrasing).** Try each significant noun/verb from the description:
   ```bash
   jq -c --arg kw "KEYWORD" 'select(.status == "open" and (.description | test($kw; "i")))' 6-tasks/_data/tasks.ndjson
   ```

   If any layer finds a match:
   - Show the existing record(s) to the user.
   - Ask: "This looks like a duplicate of `task-YYYYMMDD-NNN` — use the existing task / add a new one / cancel?"
   - Only proceed if the user confirms the new task is genuinely distinct.
4. **Area and values are only for clearly strategic standalone tasks — quick captures skip them.** Asking "which area? which value?" on every errand turns capture into a chore, and a capture system with friction stops getting used. If the task has no `project`:
   - **Quick capture, errand, or chore** (most tasks) → **don't ask.** Leave `area` null (the schema allows it) and just add it.
   - **Significant strategic standalone task** (tied to a direction, not a one-off) → softly ask which area and which value(s) from `1-values/values.md` it serves. Only when it's clearly meant to be strategic yet ties to no area or value, flag it: "This one doesn't tie to an area or value — still want it, or reconsider?"
   - **Project-linked tasks inherit the project's area** — never ask.
5. Get today's date: `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'`
6. Generate ID: `task-YYYYMMDD-NNN` (count existing `task-YYYYMMDD-` entries + 1)
7. Append via jq (never raw echo):
   ```bash
   jq -cn \
     --arg id "task-YYYYMMDD-NNN" \
     --arg desc "..." \
     --argjson notes '"NOTES_STRING_OR_NULL"' \
     --argjson depends_on 'null' \
     --argjson tid 'null' \
     --argjson esub 'null' \
     --arg created "YYYY-MM-DD" \
     '{id:$id, status:"open", description:$desc, notes:$notes, size:"M", location:"PC", impact:"high", urgency:"low", agent_doable:"no", project:"none", depends_on:$depends_on, deadline:null, created:$created, completed:null, source:"chat", source_email_thread_id:$tid, source_email_subject:$esub}' \
     >> 6-tasks/_data/tasks.ndjson
   ```
   - Pass `--argjson notes 'null'` when no notes, or `--argjson notes '"the notes text"'` when notes are present.
   - Pass `--argjson depends_on 'null'` when no dependencies, or `--argjson depends_on '["task-20260422-004"]'` (JSON array) when the task is blocked by one or more prior tasks.
   - Pass `--argjson tid 'null'` and `--argjson esub 'null'` for non-email tasks. For email-sourced tasks (`source: "email-triage"`), pass `--argjson tid '"<gmail-thread-id>"'` and `--argjson esub '"<email subject>"'`.
8. Append event to `6-tasks/_data/task_events.ndjson`:
   ```bash
   jq -cn --arg id "task-YYYYMMDD-NNN" --arg ts "YYYY-MM-DD" \
     '{task_id:$id, event:"created", timestamp:$ts, source:"chat"}' \
     >> 6-tasks/_data/task_events.ndjson
   ```
9. Commit and push: `git add 6-tasks/_data/ && git commit -m "task: add [short description]" && git push`

10. **Refresh Trello dashboard** (fail-safe)

    If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, refresh the board so the new task shows up on `✅ Tasks` immediately.

    ```bash
    python3 automations/scripts/trello_render.py 2>&1
    ```

    On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step.

IMPORTANT: All NDJSON writes must use `jq` — never raw string appends, `echo >>`, or `sed` on structured data.
