---
name: pfc-morning-checkin
description: Run the morning check-in workflow. Use when the user says "morning checkin", "morning check-in", "morning planning", "start my day", "plan my day", "daily focus", "set my focus", "pick my tasks for today", or "good morning".
---

# Morning Check-in

Sets up the day: health data, schedule overview, and 2+1 focus picks. No questions asked — show data and set priorities.

---

## Step 0 — Derive today's date (CRITICAL)

The server clock is UTC. The injected `currentDate` in your context may be wrong. Always derive the date explicitly:

```bash
TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'
```

Use that output as `YYYY-MM-DD` in every step below.

---

## Step 1 — Fetch health data

```bash
python3 automations/scripts/google_health_fetch.py
```

Parse JSON for sleep (hours + stages), resting HR, active zone minutes.
If it errors or returns nulls, continue without health data.

---

## Step 2 — Show schedule and email

Pull calendar from BOTH in parallel:
- `primary` (your.email@example.com)
- Work calendar (`<your-work-calendar-id>@group.calendar.google.com`)

**Email summary** — queried by the AA–CC priority labels (manually applied, priority grid where first letter = tier 1 and second letter = tier 2; A > B > C on both axes). **Every query must include `in:inbox`** — archived emails are out of scope.

- `in:inbox label:AA` — top priority → list sender + subject for each
- `in:inbox (label:AB OR label:BA)` — high → list sender + subject for each
- `in:inbox (label:AC OR label:BB OR label:CA)` — medium → count only
- `in:inbox (label:BC OR label:CB OR label:CC)` — low → count only
- Unprocessed (`in:inbox is:unread -label:AA -label:AB -label:AC -label:BA -label:BB -label:BC -label:CA -label:CB -label:CC`) — numbered list: sender + subject

Do NOT use `is:starred` or star-color queries — the inbox has migrated to the AA–CC grid. Keep it brief — this is a summary, not a full triage.

---

## Step 3 — Append morning record

```bash
jq -c 'select(.date == "YYYY-MM-DD")' data/day-tracking.ndjson
```

If no record exists yet, append one:

```bash
jq -cn \
  --arg date "YYYY-MM-DD" \
  --argjson health '{...}' \
  '{
    date: $date,
    rating: null,
    energy: null,
    focus: null,
    mood: null,
    caffeine_mg: null,
    sick: null,
    hyperfocused: null,
    notes: null,
    evening_notes: null,
    health: $health
  }' >> data/day-tracking.ndjson
```

Write daily note to `notes/daily/YYYY-MM-DD.md` with health summary (sleep hours + stages, resting HR, AZM).

---

## Step 3b — Pull Trello completions into repo (fail-safe)

Run **before** Step 4 so any cards the user checked off via the phone widget land in `tasks.ndjson` and `habits-daily.ndjson` first. Without this, Step 4 may prompt about habits already done on the widget (e.g. last night's `<bedtime-habit>`), and Step 4b's calendar reconcile won't see task completions that arrived through Trello.

```bash
python3 automations/scripts/trello_writeback.py sync 2>&1
```

Output is a JSON counters block (`tasks_completed`, `habits_logged`, etc.). On error: print `🟡 Trello sync failed (non-blocking): <error>` and continue — every later step reads from local NDJSON, so a missed sync only means widget state isn't reflected; the check-in still completes.

If `TRELLO_DASHBOARD_BOARD_ID` is not set in `.env`, skip this step.

---

## Step 4 — Yesterday's habits

Some habits (e.g. `<bedtime-habit>`) get logged the morning after. Before picking today's focus, check which manual (non-auto-logged) daily habits from `config/habit_schema.yaml` have NO entry for yesterday in `6-habits/_data/habits-daily.ndjson`.

**Ask only what the user DID do, not yes/no for each habit.** List the unlogged manual habits as a single prompt: "Which of these did you do yesterday? [list]". Log positives as `completed: true`; log everything else (unmentioned) as `completed: false` with `source: "morning-checkin"`.

**Structural skips.** If yesterday was structurally unavailable for a given habit (e.g. a family-time habit on a night when family is unavailable), log it via the skip branch in `pfc-log-habit` — `{completed:false, skipped:true, skip_reason:"..."}` — not as a miss. Infer the skip from context when unambiguous; ask the user when it's not.

Skip habits that have `auto_log:` in their schema entry (those write themselves via systemd).

---

## Step 4b — Reconcile yesterday's calendar completions (`✅`)

Before picking today's focus, sync any `✅`-ticked events from **yesterday's** primary calendar into `tasks.ndjson`. This matters because yesterday's unfinished focus tasks carry forward (Step 5) — if one was ticked `✅` on the calendar, the reconcile ensures it drops out of the carry-forward pool rather than being re-presented.

```bash
YESTERDAY=$(TZ="${LOCAL_TZ:-America/Denver}" date -d 'yesterday' '+%Y-%m-%d')
```

Run the reconciliation algorithm from `docs/calendar-scheduling.md` §Completion sync with `TARGET_DATE = $YESTERDAY`.

Summary of what this does:

1. Fetch yesterday's primary-calendar events via `mcp__claude_ai_Google_Calendar__list_events` (primary only; work calendar is NOT scanned).
2. For each event whose `summary` starts with `✅ ` and contains `[task-YYYYMMDD-NNN]` (first match wins): if the task is open in `tasks.ndjson`, mark it `done` with `completed = YESTERDAY`, append a `source:"calendar-sync"` record to `task_events.ndjson`. **Only if a daily-focus record exists for `$YESTERDAY`** (check with `jq -c --arg d "$YESTERDAY" 'select(.date == $d)' 5-actions/_data/daily-focus.ndjson | head -1`), also update that record's `completed[]` / `bonus_completed`. If no focus record exists for yesterday (morning planning was skipped), skip the daily-focus update — the task-level update still applies.
3. Print a one-line summary (e.g. `✅ synced 1 task from yesterday's calendar` or `calendar sync: nothing to reconcile`).
4. On MCP error: print `⚠️ calendar sync skipped: <error>` and continue with Step 5 — do not block morning planning.

Do NOT run this for today's calendar; that's the evening check-in's job.

The exact jq one-liners are in `docs/calendar-scheduling.md`. Use them verbatim; do not improvise.

---

## Step 5 — Active project status

Before picking the 2+1, surface every active project so the user can see where things stand and decide whether to add a 4th project slot today (Step 5b).

```bash
jq -c 'select(.active == true)' 4-projects/_data/projects.ndjson
```

For each active project, render one line:

```
<name>  [====------] 40%  velocity X.X parts/wk → est <YYYY-MM-DD>  vs deadline <YYYY-MM-DD>  🟢|🟡|🔴
```

Velocity calc:
- `days_elapsed = today - started` (use ISO date math)
- `parts_per_day = completed_parts / max(1, days_elapsed)`
- `est_completion = today + ceil((total_parts - completed_parts) / parts_per_day)` if `parts_per_day > 0`; else `est_completion = "—"`
- Compare `est_completion` to `deadline`: 🟢 on or before · 🟡 ≤7 days late · 🔴 >7 days late

Also list today's project tasks (deadline == today) per project, if any. The user uses this to decide whether one of those project tasks belongs in the optional 4th slot below.

---

## Step 5b — 2+1 focus picks (+ optional project slot)

Check if focus is already set today:

```bash
jq -c 'select(.date == "YYYY-MM-DD")' 5-actions/_data/daily-focus.ndjson
```

If already set, show it and skip to Step 6.

If not set, check yesterday for carry-forwards:

```bash
jq -c 'select(.date == "YESTERDAY")' 5-actions/_data/daily-focus.ndjson
```

**Carry-forward rule:** Unfinished tasks from yesterday auto-carry to today. Show them pre-selected and ask to confirm or swap. Only prompt for fresh picks if no carry-forwards exist.

Pull candidates for the 2+1, **excluding project tasks** (they're handled separately in the optional 4th slot):

```bash
jq -c 'select(.status == "open" and (.project // "none") == "none")' 5-actions/_data/tasks.ndjson | head -15
```

Project tasks (`project != "none"`) are pre-planned work and do NOT compete with standalone tasks for the 2 critical slots. Surface them only via Step 5's project status block + the optional 4th slot below.

**Exclude tasks already on the calendar today or later.** Tasks that already have a calendar event at `DATE` or any future date are already committed to a time — don't re-surface them. Tasks with a calendar event dated *before* `DATE` that weren't completed (overdue) DO stay in the pool. See `pfc-pick-tasks` Step 1b for the fetch + filter recipe.

Suggest based on impact/urgency. User picks 2 critical + 1 bonus from the standalone pool.

**Optional 4th slot — project task.** After the 2+1 is set, ask: "Add a project task as a 4th focus slot today? (yes/no/which project)". If yes, pull the **next-up** open task per project (lowest `sequence`, treating null as last):

```bash
jq -cs '
  map(select(.status == "open" and .project != "none"))
  | group_by(.project)
  | map(sort_by(.sequence // 999999) | .[0])
  | .[]
' 5-actions/_data/tasks.ndjson
```

This surfaces one task per project — the one that's actually next given dependency order — never a higher-sequenced sibling. Skip the prompt if the result is empty.

**Respect work hours when suggesting.** Personal tasks land in your configured windows (see docs/calendar-scheduling.md) (all-day on weekends) — see `docs/calendar-scheduling.md` §Focus-task scheduling. If today's personal windows are mostly blocked, flag it and prefer smaller-size tasks; don't pick an XL personal task on a day with only 30 free personal minutes.

Log focus (omit `project` field if no 4th slot was chosen):

```bash
jq -cn \
  --arg date "YYYY-MM-DD" \
  --arg c1 "TASK-ID-1" \
  --arg c2 "TASK-ID-2" \
  --arg bonus "TASK-ID-3" \
  --arg proj "TASK-ID-4-or-empty" \
  '{date: $date, critical: [$c1, $c2], bonus: $bonus, completed: [], bonus_completed: false}
   + (if $proj == "" then {} else {project: $proj, project_completed: false} end)' \
  >> 5-actions/_data/daily-focus.ndjson
```

Never pull tasks from the calendar — calendar events are already built into the day.

---

## Step 5b1 — Sync Trello dashboard (fail-safe)

If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, sync Trello to reflect the new 2+1.

**This step is fail-safe:** any error here is logged but does not block the rest of morning-checkin. If Trello is down, your routine still completes normally.

1. Pre-emptively clean up yesterday's leftover 2+1 cards (in case evening-checkin didn't fire):
   ```bash
   python3 automations/scripts/trello_writeback.py move-back-uncompleted 2>&1
   ```
   On error: print `🟡 Trello cleanup failed (non-blocking): <error>` and continue.

2. Move today's 2+1 cards from Actions to ✅ 2+1:
   ```bash
   python3 automations/scripts/trello_writeback.py move-2plus1 <task-id-1> <task-id-2> [<bonus-task-id>] [<project-task-id>]
   ```
   Pass the actual task ids picked in step 5b. On error: print `🟡 Trello move failed (non-blocking): <error>` and continue.

3. If TRELLO_DASHBOARD_BOARD_ID is NOT set, skip this step entirely.

---

## Step 5b2 — Revive watchlist (fail-safe)

After 2+1 is set, surface any slipped items.

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
python3 automations/scripts/revive_watchlist.py --today "$TODAY"
```

If the array is empty: skip — say nothing in chat. If non-empty, print:

```
🔁 Revive watchlist (N items)
  1. <item description> — <signal detail>
  2. ...
Walk any of these now? (1, 2, …, all, none)
```

If the user picks one or more: invoke the `pfc-revive` skill walk-flow on the selected items only (don't re-fetch the watchlist; pass the indices). If `none` or no answer in 30 seconds of typing: leave them for the standalone `/pfc-revive` or weekly walk.

Any error from the helper logs 🟡 (`🟡 Revive watchlist failed: <stderr>. Skipping.`) and the morning check-in continues — never blocks.

---

## Step 5c — Auto-schedule to calendar

Once the focus record is written (2+1 or 2+1+project), first migrate any carry-forward calendar events from yesterday, then invoke the `pfc-schedule-focus` skill inline.

**Carry-forward migration (do this BEFORE invoking pfc-schedule-focus):** if yesterday's `daily-focus.ndjson` has a `calendar_events` map and any of today's tasks also appeared in yesterday's critical/bonus set, copy those entries into today's record. The standalone skill will then treat them as updates (move in place) rather than creates.

```bash
YESTERDAY=$(TZ="${LOCAL_TZ:-America/Denver}" date -d 'yesterday' '+%Y-%m-%d')
# Pull yesterday's calendar_events for any task that's also in today's focus.
prev_events=$(jq -c --arg d "$YESTERDAY" --argjson today_ids "$TODAY_IDS_JSON" '
  select(.date == $d)
  | .calendar_events // {}
  | with_entries(select(.key as $k | $today_ids | index($k)))
' 5-actions/_data/daily-focus.ndjson)

# Merge into today's record (replacing any existing calendar_events field).
jq -c --arg d "$DATE" --argjson prev "$prev_events" \
  'if .date == $d then .calendar_events = $prev else . end' \
  5-actions/_data/daily-focus.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 5-actions/_data/daily-focus.ndjson
```

Where `$TODAY_IDS_JSON` is a JSON array of today's 3 task IDs, e.g. `["task-...","task-...","task-..."]`.

**Then invoke pfc-schedule-focus** to fetch events, run the slot-finder, show the proposal, confirm, write events, and persist IDs. See `.claude/skills/pfc-schedule-focus/SKILL.md` for the full sequence.

---

## Step 6 — Commit

```bash
git add data/day-tracking.ndjson 5-actions/_data/daily-focus.ndjson notes/daily/
git commit -m "checkin: record YYYY-MM-DD"
git push
```

---

## Step 7 — Refresh Trello dashboard (fail-safe)

If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, refresh the full board so `✅ 2+1`, `✅ Actions`, `⬅ Last 7 Days`, project velocity, calendar, and email priorities all reflect the new morning state. Step 5b1's writeback already moved the 2+1 cards between lists — this render also picks up everything else (day-tracking row, project status, calendar refresh).

```bash
python3 automations/scripts/trello_render.py 2>&1
```

On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step.
