# Calendar Scheduling Rules

**Read this before creating or moving any calendar event.**

## Calendars in scope

Always operate against exactly these two when reading availability or writing events:

| Calendar | ID | Use for |
|---|---|---|
| Primary (`your.email@example.com`) | `primary` | Read availability, write personal events / focus picks / course study |
| Work | `<your-work-calendar-id>@group.calendar.google.com` | Read availability only — never write |

**Excluded — do NOT read for conflicts and do NOT write to:**

| Calendar | ID | Why excluded |
|---|---|---|
| Example Shared Calendar 1 | `<example-shared-calendar-id-1>@group.calendar.google.com` | example shared informational calendar — informational only, not a personal blocker |
| Example Shared Calendar 2 | `<example-shared-calendar-id-2>@group.calendar.google.com` | example shared informational calendar — opt-in, not a personal blocker |

**Context-only (read for awareness, never blocks):** US Holidays calendar.

If a user request touches a calendar not in the table above (a new shared calendar, a vendor invite), ask before treating it as a blocker or a write target.

## Personal-task time windows (where events may land)

These are the only windows on which any personal task — focus picks, course study, course-series batches, errands, anything not work-related — may be scheduled on the primary calendar:

| Day type | Allowed personal-task windows (your local timezone) |
|---|---|
| Weekdays (Mon–Fri) | 8:00–9:00 AM · 12:00–1:00 PM (lunch) · 5:00–9:00 PM (default — edit to match your schedule) |
| Weekends (Sat/Sun) | 8:00 AM – 9:00 PM |

Work hours (Mon–Fri 9 AM – noon, 1 PM – 5 PM) are excluded — personal tasks must not land there. Note that **other blockers may further restrict these windows** (family commitments, appointments, recurring meetings, all-day blocks). Read `0-me/schedule-patterns.md` for the fixed-pattern blockers, then run the per-day conflict check below.

These windows apply equally to:
- `pfc-schedule-focus` (the focus-task slot finder enforces them via `find_focus_slots.py`)
- Course-series batch scheduling (any multi-event series)
- Any ad-hoc personal event the assistant places on the calendar

If a window collides with an existing event on a given day, pick a different window from the table above for that day. If all windows on a day are blocked, push to the next available day rather than overlapping.

## The rule: never schedule over an existing event

Before creating/moving an event on date `D` at time `[T_start, T_end]`, you MUST:

1. Pull the **full day** of events on calendar `D` from both the primary calendar AND the work calendar (`<your-work-calendar-id>@group.calendar.google.com`).
2. Compute overlap: an existing event `[E_start, E_end]` conflicts with the target slot iff `E_start < T_end AND E_end > T_start`.
3. Treat all-day events as "blocked context only" — they don't block timed slots, but note them (e.g., "In Office").
4. Treat events marked `transparency: "transparent"` as non-blocking (free/available).
5. If there's any conflict, pick a different slot. Do not schedule on top.

## Reading event titles

Read calendar titles **literally**. When a title is ambiguous (`Appointment`, `Block`, `Meeting`), report it as-is — do NOT guess who or what it is for, since the same title can mean many different things. Only treat a title as a specific commitment when the wording is explicit. When in doubt, ask.

## Embedding task/project IDs in event titles

When creating a calendar event for work that corresponds to a tracked task or project, embed the identifier in brackets at the end of the title so "I did the thing on my calendar today" resolves mechanically via regex (`\[task-\d{8}-\d{3}\]` or `\[proj-\d{8}-\d{3}\]`):

- `Course: Module Lesson - D2 [task-YYYYMMDD-NNN]`
- `Project: Session Block (example) [proj-YYYYMMDD-NNN]`
- `⭐ [AA-S] Complete important task [task-YYYYMMDD-NNN]` (focus-task format)

Prefer the task ID when the event maps to one specific task. Project ID is acceptable for umbrella practice blocks where each session maps loosely to 1–2 tasks. The `✅` completion-sync section below relies on this convention.

## Common failure modes (don't repeat these)

- **Filtering `list_events` by `fullText` and trusting the result for conflict checks.** A `fullText: "course-name"` query returns only matching events. It will NOT show the All-Day Event, Appointment, Pickup appointment, In-Office work blocks, or any other event on the same day. `fullText` is for *finding events to update or delete*, never for *finding conflicts*. For conflict checks, re-pull the day with NO `fullText` filter.
- **Only checking the target hour.** A 9 AM–2 PM field trip blocks 11 AM. Check the whole day.
- **Assuming "10 AM free" means "11 AM free".** A 10–11 AM meeting might be followed by a 11 AM–12 PM travel block. Check both.
- **Ignoring travel/prep blocks.** Travel to/from an appointment is a real event; don't overlap.
- **Ignoring recurring events on work calendar.** recurring planning, team meetings, and 1:1s live on the work calendar.
- **Ignoring schedule-pattern blocks.** `0-me/schedule-patterns.md` lists fixed weekly blockers (e.g. Friday noon – 1 PM "Standing meeting" weekly). These ARE on the calendar, but read the patterns doc first so you know what to expect — it's faster than discovering them mid-conflict.

### Scar reference: a real batch-scheduling incident

Symptoms: scheduled 17 new lunch/weekend events without per-day conflict checks. 6 of 17 landed on top of existing events (All-Day Event 9–14, Recurring Friday blocker 11:45–12:45 ×3, In Office 9–14 ×2). Root cause: used `fullText: "course-name"` filters to plan and assumed those results were exhaustive — they were not. Lesson: when batch-creating events, the conflict pull is **per-target-date, no filter, both calendars**, even if it's slow.

## Algorithm for finding a slot

Given a target duration (e.g., 1 hour) on date `D`, and a preferred time (e.g., 10 AM):

1. Fetch the full day from both calendars.
2. Build a list of `[start, end]` blocks from all **non-transparent, non-all-day** events.
3. Try the preferred time first. If it overlaps any block, try:
   - The earliest free 1-hour window starting ≥ 8 AM
   - If nothing fits between 8 AM and 5 PM, push to the next weekday and retry.
4. If the whole day is blocked, skip it entirely and shift the series.

## For batch scheduling (e.g., course series, multi-week reschedules)

This is the **mandatory** sequence when creating more than ~3 events at once. Skipping any step is what produces the scar above.

1. **Read `0-me/schedule-patterns.md`** to know fixed blockers (office days, recurring weekday blockers, all-day events).
2. **Pull both calendars for the full date range, with NO `fullText` filter.** Primary + work (`<your-work-calendar-id>@group.calendar.google.com`). If the response is truncated, pull per-day or per-week.
3. **Build a proposed schedule offline** — date, start, end, task ID — and run the per-day conflict check (`E_start < T_end AND E_end > T_start`) for every proposed event against every existing event on that date from BOTH calendars.
4. **Show the user the full proposed schedule** (table: date · time · summary · "free" or "conflict with X") BEFORE creating any events. Wait for confirmation. This is the single most important step — once events are created, fixing them is several times more work than running the check.
5. Only after confirmation: create the events.
6. **Verify after creation:** re-pull each target date with NO `fullText` filter and confirm zero overlaps. If any, fix before reporting "done."

If a slot has no clean window the same day, push the task to the next available day rather than scheduling on top.

## Verification after creation

After batch-creating events, re-pull every target date (no `fullText` filter, both calendars) and confirm no overlaps. If any exist, fix them before reporting "done." Spot-checking 3 random days is not enough for batches > 10 — check all of them.

## Focus-task scheduling (pfc-schedule-focus)

Daily 2+1 focus picks are auto-scheduled onto the primary calendar by the `pfc-schedule-focus` skill. The slot-finder (`automations/scripts/find_focus_slots.py`) enforces:

**Allowed windows (your local timezone — defaults shown):**
- Weekdays (Mon–Fri): 8–9 AM, 12–1 PM, 5–9 PM
- Weekends (Sat/Sun): 8 AM – 9 PM

Work hours (default 9 AM – noon, 1–5 PM — edit to match your schedule) are excluded on weekdays — personal tasks should not land during work, except at lunch.

**Durations by task size (calendar block):** XS = 15 min · S = 15 min · M = 30 min · L = 60 min · XL = 120 min · null → M.

A 15-minute floor applies to every placement (`MIN_SLOT_MINUTES` in `find_focus_slots.py`). XS tasks represent ~5 minutes of effort but still get a 15-minute calendar block — tiny events are hard to see and easy to miss.

**Title format:** `⭐ [AA-S] {description} [task-id]` (critical) or `Bonus: [AA-S] ...` (bonus). `AA-S` encodes impact + urgency + size, with impact/urgency mapped high→A, medium→B, low→C (same scheme as Gmail priority labels).

**Color:** all PFC-scheduled events use banana (`colorId: "5"`). One color is the visual signature that an event came from the PFC system — never vary by tier. The title prefix (`⭐ ` for critical, `Bonus: ` for bonus) carries the tier distinction.

**Event IDs** are persisted in `5-actions/_data/daily-focus.ndjson` under `calendar_events`, so carry-forwards can move the same event rather than duplicate it.

When in doubt, re-run `pfc-schedule-focus` — it's idempotent: updates existing events, creates missing ones, deletes orphans of swapped-out tasks.

## Completion sync — ✅ convention

`✅ ` (U+2705 + a single space) at the start of a calendar event's title means "this task is done." The marker flows both ways:

- **Calendar → system (read):** Evening check-in reconciles today's primary calendar; morning daily-focus reconciles yesterday's. Events whose title starts with `✅ ` and contains a `[task-...]` ID cause the matching task in `5-actions/_data/tasks.ndjson` to be marked done silently.
- **System → calendar (write):** When `pfc-complete-task` marks a task done, it prepends `✅ ` to every event on today's primary calendar whose title contains `[<that-task-id>]`.

Only `✅` is recognized. The earlier `✓` convention is retired — no backward-compat reading.

### Reconciliation algorithm

Both reading skills (`pfc-evening-checkin` for today, `pfc-morning-checkin` for yesterday) run this procedure:

1. Set `TARGET_DATE` (today or yesterday, derived via `TZ="${LOCAL_TZ:-America/Denver}" date ...`).
2. Call `mcp__claude_ai_Google_Calendar__list_events` with:
   - `timeMin`: `${TARGET_DATE}T00:00:00`
   - `timeMax`: `${NEXT_DATE}T00:00:00`, where `NEXT_DATE` is derived as `NEXT_DATE=$(TZ="${LOCAL_TZ:-America/Denver}" date -d "$TARGET_DATE +1 day" '+%Y-%m-%d')`
   - `timeZone`: your local timezone (defaults to `America/Denver`; read from `$LOCAL_TZ`)
   - `orderBy`: `startTime`
   - Calendar: omit `calendarId` (defaults to primary; the work calendar is NOT scanned).

   (Naive-ISO + `timeZone` matches the idiom used by `pfc-schedule-focus` — the MCP connector handles DST offsets internally.)
3. For each returned event, apply the regex `\[task-\d{8}-\d{3}\]` to `summary`. Use the **first** match (events with multiple IDs count as one task). Events with no match are dropped.
4. For each match, compute `done = summary.startswith("✅ ")`. Pairs with `done=false` are ignored.
5. For each `(task_id, true)` pair, check `5-actions/_data/tasks.ndjson`. If the task is absent or `status != "open"`, skip. Otherwise:
   a. Update `tasks.ndjson` in place:
      ```bash
      jq -c --arg id "$TASK_ID" --arg d "$TARGET_DATE" \
        'if .id == $id then . + {status:"done", completed:$d} else . end' \
        5-actions/_data/tasks.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 5-actions/_data/tasks.ndjson
      ```
   b. Append a completion record to `5-actions/_data/task_events.ndjson`:
      ```bash
      jq -cn --arg id "$TASK_ID" --arg d "$TARGET_DATE" \
        '{task_id:$id, event:"completed", timestamp:$d, source:"calendar-sync"}' \
        >> 5-actions/_data/task_events.ndjson
      ```
   c. If `5-actions/_data/daily-focus.ndjson` has a record for `$TARGET_DATE` that references this task: update `completed[]` (de-duplicated) if it's in `critical`; set `bonus_completed:true` if it's the `bonus`:
      ```bash
      jq -c --arg d "$TARGET_DATE" --arg id "$TASK_ID" '
        if .date == $d then
          if (.critical // [] | index($id)) then .completed = ((.completed // []) + [$id] | unique)
          elif .bonus == $id then .bonus_completed = true
          else . end
        else . end' 5-actions/_data/daily-focus.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 5-actions/_data/daily-focus.ndjson
      ```
6. Print a one-line summary of what was reconciled (e.g., `✅ synced 2 tasks from calendar: task-...`, or `calendar sync: nothing to reconcile`).
7. If any MCP call fails, print `⚠️ calendar sync skipped: <error>` and continue — do not block the host skill.

### Write-path rules (pfc-complete-task)

When marking `task_id` done:

1. Call `list_events` for today's primary calendar (same params as step 2 above, with `TARGET_DATE = today`).
2. Find every event whose `summary` contains `[<task_id>]` literally. For each:
   - If `summary` already starts with `✅ `: skip.
   - Else call `mcp__claude_ai_Google_Calendar__update_event` with `summary = "✅ " + current_summary`. Leave `startTime`, `endTime`, `description`, and `colorId` unchanged.
3. Events on past or future days are not touched — scope is today only.
4. MCP failure: print `⚠️ calendar update skipped: <error>` and continue. The task remains `done` in `tasks.ndjson`.
