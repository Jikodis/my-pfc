---
name: pfc-schedule-focus
description: Schedule (or re-schedule) today's 2+1 focus tasks onto the primary calendar. Use when the user says "schedule my focus", "put focus on calendar", "reschedule focus", or when carry-forward focus tasks need to move to today's slots.
---

# Schedule Focus

Places each of today's 2+1 focus tasks into a free slot on the primary calendar, creating new events or moving existing ones. Runs the slot-finder script; user confirms before any writes.

## Allowed personal-task windows (local time)

Personal focus tasks may ONLY land in these windows — work hours are reserved for work. Edit the windows below to match your own schedule:

- **Weekdays (Mon–Fri):** 8–9 AM, 12–1 PM, 5–9 PM (example — edit these)
- **Weekends (Sat/Sun):** 8 AM – 9 PM (example — edit these)

The slot-finder (`automations/scripts/find_focus_slots.py`) enforces this automatically. Surface it to the user if all 2+1 slots can't fit the available windows — never widen the window silently.

**Durations by size (calendar block):** XS = 15 min · S = 15 min · M = 30 min · L = 60 min · XL = 120 min · null → M. Calendar events have a 15-minute floor — XS effort (~5 min) still gets a 15-min block so it's visible on the calendar.

See `docs/calendar-scheduling.md` §Focus-task scheduling for the canonical spec.

---

## Step 0 — Derive today's date (CRITICAL)

```bash
TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'
```

Use the output as `DATE` in every step below. Never trust `currentDate`.

---

## Step 0.5 — Verify Calendar MCP available (precondition)

This skill requires the Google Calendar MCP server. If the `mcp__claude_ai_Google_Calendar__*` tools aren't available in this session:

> 🟡 Calendar not configured — focus scheduling skipped. See `docs/install/connectors.md` to enable.

Then exit cleanly. The calling skill (typically `pfc-morning-checkin`) treats this as a non-blocking skip, same as the Trello sync step.

If the tools ARE available, proceed.

---

## Step 1 — Read today's focus record

```bash
jq -c --arg d "$DATE" 'select(.date == $d)' 5-actions/_data/daily-focus.ndjson
```

If no record exists, stop and tell the user to run `pfc-morning-checkin` first.

Capture:
- `critical` — array of 2 task IDs
- `bonus` — 1 task ID (or null)
- `calendar_events` — existing `{task_id → {event_id, start, end}}` map (may be absent)

---

## Step 2 — Resolve task sizes, titles, and project

For each of the 3 task IDs, pull the full task record:

```bash
jq -c --arg id "$TASK_ID" 'select(.id == $id)' 5-actions/_data/tasks.ndjson
```

Collect per task: `id`, `description`, `notes`, `size`, `impact`, `urgency`, `project`.

---

## Step 3 — Fetch today's calendar events

Use the Google Calendar MCP `list_events` tool for BOTH calendars:

- Primary: `your.email@example.com`
- Work: `<your-work-calendar-id>@group.calendar.google.com`

Time range: `${DATE}T00:00:00` to `${next_day}T00:00:00`, `timeZone: "${LOCAL_TZ:-America/Denver}"`, `orderBy: startTime`.

Normalize the result: drop events that are all-day (no `start.dateTime`), drop `transparency: "transparent"` events. Keep `{start, end}` as ISO strings.

---

## Step 4 — Run the slot-finder

Always pass the current local time as `now` so the scheduler never picks slots in the past. Derive it with the same TZ as `$DATE`:

```bash
NOW=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%dT%H:%M:%S%:z')
```

Build the payload:

```bash
cat > /tmp/focus-payload.json <<EOF
{
  "date": "$DATE",
  "now":  "$NOW",
  "busy_events": [ ... normalized events ... ],
  "tasks": [
    {"id": "$CRITICAL1_ID", "size": "$CRITICAL1_SIZE"},
    {"id": "$CRITICAL2_ID", "size": "$CRITICAL2_SIZE"},
    {"id": "$BONUS_ID",     "size": "$BONUS_SIZE"}
  ]
}
EOF
python3 automations/scripts/find_focus_slots.py < /tmp/focus-payload.json
```

Parse `placements` and `unscheduled` from the output. The scheduler drops any free window ending before `now` and rounds `now` up to the next quarter-hour for the starting slot — so placements are always in the future.

---

## Step 5 — Show the proposal and confirm

Show the user a human-readable summary:

```
Proposed schedule for 2026-04-20:
  ⭐ Critical 1 — 8:00–8:15 AM — Process inbox backlog
  ⭐ Critical 2 — 12:00–12:30 PM — Update <document>
  Bonus       — 5:00–5:15 PM — Set up email labels
```

If any tasks are in `unscheduled`, list them with a warning:
```
⚠️ Couldn't schedule:
  - task-20260412-018 — Update <document> (no 30-min slot free today)
```

Ask the user to confirm or swap any slot.

---

## Step 6 — Compute event deltas

For each placement, classify:

- **Update in place:** task has an entry in `calendar_events` with an `event_id`. Use MCP `update_event` with the new start/end. Refresh the title (impact/urgency/size may have changed).
- **Create:** task has no `calendar_events` entry. Use MCP `create_event`.

For any task ID in the existing `calendar_events` map but NOT in today's focus set (user swapped a task mid-day): use MCP `delete_event` to remove the orphan.

---

## Step 7 — Build the event payload

For each placement, construct:

**Title:**
- Critical: `⭐ [{AA-S}] {description} [{task-id}]`
- Bonus:    `Bonus: [{AA-S}] {description} [{task-id}]`

Letter code: impact + urgency + size, each mapped high→A, medium→B, low→C, and size verbatim (S/M/L). Example: high impact + high urgency + small → `AA-S`.

**Body (event description):**
```
{task.notes if set, else task.description}

task-id: {task.id}
project: {task.project}       ← line only included if task.project != "none"
```

**Color ID:** all PFC-scheduled events use `"5"` (banana). One color is the visual signature that an event came from the PFC system — never vary it by tier (critical vs bonus). Title prefix (`⭐` vs `Bonus:`) carries the tier distinction.

**Calendar:** primary (omit the `calendarId` argument on MCP calls to target primary).

**Start/End:** the `start`/`end` ISO strings from the placement.

**MCP parameter mapping (reference when calling `create_event` / `update_event`):**

| Spec field | MCP parameter |
|---|---|
| Title | `summary` |
| Body | `description` |
| Start | `startTime` |
| End | `endTime` |
| Color ID | `colorId` |
| Event ID (for update/delete) | `eventId` |
| Calendar | (omit; defaults to primary) |

---

## Step 8 — Write events via MCP (fail-safe)

**This step is fail-safe per call:** any individual MCP call error is logged but does not block the rest of the step or the calling skill.

For creates: call `mcp__claude_ai_Google_Calendar__create_event`. Capture the returned event `id`. On error: print `🟡 Calendar create failed for <task-id> (non-blocking): <error>` and continue with the remaining events.

For updates: call `mcp__claude_ai_Google_Calendar__update_event` with the stored `event_id`. On error: print `🟡 Calendar update failed for <task-id> (non-blocking): <error>` and continue.

For deletes: call `mcp__claude_ai_Google_Calendar__delete_event`. On error: print `🟡 Calendar delete failed for <event-id> (non-blocking): <error>` and continue.

If a partial set of events landed and others failed, persist what succeeded into `daily-focus.ndjson` (Step 9) — partial state beats no state.

---

## Step 9 — Persist event IDs into daily-focus.ndjson

Build the new `calendar_events` map: one entry per scheduled task, dropping any deleted orphans. Write it in place:

```bash
jq -c --arg d "$DATE" --argjson evs "$NEW_MAP" \
  'if .date == $d then .calendar_events = $evs else . end' \
  5-actions/_data/daily-focus.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 5-actions/_data/daily-focus.ndjson
```

Where `$NEW_MAP` is the JSON object:
```json
{
  "task-20260412-001": {"event_id": "abc123", "start": "...", "end": "..."},
  ...
}
```

---

## Step 10 — Commit

```bash
git add 5-actions/_data/daily-focus.ndjson
git commit -m "focus: schedule $DATE"
git push
```

If events failed to create (MCP error), skip the NDJSON write. Surface the failure to the user — the focus picks themselves remain unchanged.
