---
name: pfc-evening-checkin
description: Run the evening check-in workflow. Use when the user says "evening check-in", "end of day", "rate my day", "log my day", or "day review".
---

# Evening Check-in

Closes out the day: review focus + habits, log supplements, and score the day.

---

## Step 0 — Derive the target date (CRITICAL)

The server clock is UTC. After your local evening crosses UTC midnight, the injected `currentDate` in your context is already tomorrow's date. Using it for evening check-in writes records to the WRONG day. Always derive the local date explicitly first:

```bash
TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'
```

**Default:** use that output as `YYYY-MM-DD` in every step below. Do NOT substitute in the `currentDate` from context. Before writing any record, verify the date still matches the TZ-derived value.

**Past-midnight handling (00:00–04:59 local time):** if the local hour is < 5, the user is almost certainly closing out the *prior* calendar day, not the current one. Auto-shift the target date to yesterday and announce it in one line before proceeding (e.g. "Past midnight — targeting 2026-05-08, closing out yesterday."). The user can override by naming today or a specific other date.

```bash
HOUR=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%H')
if [ "$HOUR" -lt 5 ]; then
  TARGET_DATE=$(TZ="${LOCAL_TZ:-America/Denver}" date -d 'yesterday' '+%Y-%m-%d')
else
  TARGET_DATE=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
fi
echo "$TARGET_DATE"
```

When past-midnight handling triggers, route through the existing backfill verification below (check the day-tracking record exists; warn if not).

**Backfill mode — "for yesterday" or an explicit date:** if the user says "run check-in for yesterday", "log yesterday", or names a specific past date, use that date instead. Compute yesterday as:

```bash
TZ="${LOCAL_TZ:-America/Denver}" date -d 'yesterday' '+%Y-%m-%d'
```

Before proceeding, verify a day-tracking record already exists for the target date:

```bash
jq -c --arg d "YYYY-MM-DD" 'select(.date == $d)' data/day-tracking.ndjson
```

If it exists and the evening fields (`rating`, `energy`, `focus`, `mood`, `hyperfocused`) are null, proceed with Steps 1–5 using that date. If evening fields are already populated, confirm with the user before overwriting. If no record exists at all, warn the user and ask whether to append a fresh record for that date (Step 4's append branch).

---

## Step 0b — Reconcile calendar completions (`✅`)

Before reviewing focus, sync completed calendar events back into `tasks.ndjson`. Run the reconciliation algorithm from `docs/calendar-scheduling.md` §Completion sync with `TARGET_DATE = <the date from Step 0>`.

Summary of what this does:

1. Fetch `TARGET_DATE`'s primary-calendar events via `mcp__claude_ai_Google_Calendar__list_events` (primary calendar only; do NOT fetch the work calendar here). In backfill mode this is yesterday or an earlier user-named date, not today.
2. For each event whose `summary` starts with `✅ ` and contains `[task-YYYYMMDD-NNN]` (first match wins): if the task is open in `tasks.ndjson`, mark it `done` with `completed = TARGET_DATE`, append a `source:"calendar-sync"` record to `task_events.ndjson`. **Only if a daily-focus record exists for `TARGET_DATE`** (check with `jq -c --arg d "$TARGET_DATE" 'select(.date == $d)' 5-actions/_data/daily-focus.ndjson | head -1`), also update that record's `completed[]` / `bonus_completed`. If no focus record exists for the date, skip the daily-focus update — the task-level update still applies.
3. Print a one-line summary (e.g. `✅ synced 2 tasks from calendar` or `calendar sync: nothing to reconcile`).
4. On any MCP error, print `⚠️ calendar sync skipped: <error>` and continue with Step 1 — do not block the check-in.

The exact jq one-liners are in `docs/calendar-scheduling.md`. Use them verbatim; do not improvise.

---

## Step 0c — Pull Trello completions into repo (fail-safe)

Run **before** focus review and habit tracker so cards the user checked off via the phone widget land in `tasks.ndjson` and `habits-daily.ndjson` first. Otherwise Step 1 misreports focus completion and Step 2 prompts the user about habits already done on the widget.

```bash
python3 automations/scripts/trello_writeback.py sync 2>&1
```

Output is a JSON counters block (`tasks_completed`, `habits_logged`, etc.). On error: print `🟡 Trello sync failed (non-blocking): <error>` and continue — every later step reads from local NDJSON, so a missed sync only means the widget state isn't reflected; the check-in still completes.

If `TRELLO_DASHBOARD_BOARD_ID` is not set in `.env`, skip this step.

(The `move-back-uncompleted` and `render` halves of the Trello dance still run later in Step 4b, after the day-tracking record is written.)

---

## Step 1 — Focus review

```bash
FOCUS=$(jq -c 'select(.date == "YYYY-MM-DD")' 5-actions/_data/daily-focus.ndjson)
```

**If `$FOCUS` is empty (morning planning was skipped):** output one line — `No focus set today (morning planning skipped).` — and skip to Step 1b. Do not fabricate a checklist.

**Otherwise,** for each task (critical1, critical2, bonus, project if present), check completion status:

```bash
jq -c 'select(.id == "TASK-ID")' 5-actions/_data/tasks.ndjson
```

Show as a checklist — done or still open. Include the optional `.project` slot if it's set. Surface unfinished tasks without pressure.

---

## Step 1b — Active project status

Surface velocity for every active project so drift is visible at end-of-day.

```bash
jq -c 'select(.active == true)' 4-projects/_data/projects.ndjson
```

For each active project, render one line:

```
<name>  [====------] 40%  velocity X.X parts/wk → est <YYYY-MM-DD>  vs deadline <YYYY-MM-DD>  🟢|🟡|🔴
```

Velocity calc:
- `days_elapsed = today - started`
- `parts_per_day = completed_parts / max(1, days_elapsed)`
- `est_completion = today + ceil((total_parts - completed_parts) / parts_per_day)` if `parts_per_day > 0`
- 🟢 if `est_completion ≤ deadline` · 🟡 if ≤7 days late · 🔴 if >7 days late

If a project went 🔴 today, ask one question: "Want to reset the deadline, drop scope, or just note it?" — log the answer to the project file's notes field if any. Don't push a full re-plan at end of day.

---

## Step 2 — Habit tracker

```bash
cat config/habit_schema.yaml
jq -c 'select(.date == "YYYY-MM-DD")' 6-habits/_data/habits-daily.ndjson
```

Show each tracked daily habit and whether it's been logged today. For any unlogged habits, ask if completed and offer to log inline.

**Three possible states per habit:** done, missed, or **skipped** (structurally unavailable — e.g. a family-time habit on a night when family is unavailable). If the user says "skipped" or the reason is obvious from context (e.g. a connection-time habit on a night when the people involved are away), log it with `skipped:true, completed:false, skip_reason:"..."` via the skip branch in `pfc-log-habit`. Skipped days drop out of weekly completion math; missed days count against it. Default to **missed** when unclear — don't over-mark as skipped.

**Auto-logged habits — NEVER ASK the user about these.** Any habit in `config/habit_schema.yaml` with an `auto_log:` block is fetched by an automation (see `automations/scripts/auto_log_habits.py`). Skip these in the ask-and-log loop entirely. If today's auto-log hasn't run yet, leave the habit unlogged — the automation will backfill. Do not prompt the user to report it manually. (No habits currently declare `auto_log:` — the framework is preserved for future use.)

**Bedtime-adjacent habits** (e.g. `<bedtime-habit>`) are logged the NEXT morning during daily-focus, not tonight. Skip these too.

---

## Step 3 — Ask evening questions

1. **Day rating** (1–5)
2. **Energy** (1–5)
3. **Focus** (1–5)
4. **Mood** (1–5)
5. **Hyperfocused / inflexible today?** (yes/no — `hyperfocused` field)
6. **Evening notes** — one line reflection (optional)

Do NOT ask about sickness. Do NOT ask about sleep (auto-fetched). Do NOT ask about any habit with an `auto_log:` block in the schema.

---

## Step 3b — Day rating feedback

After ratings are captured, offer a brief interpretation tied to today's observables, OR probe with one question when no signal is obvious. The point is to help the user notice the driver — not lecture, not narrate.

**Observables to scan (already in hand from earlier steps):**
- Focus completion ratio (Step 1: critical+bonus done / total)
- Manual habit completion (Step 2: done / tracked-manual)
- `hyperfocused` (Step 3 answers)
- Project velocity flags (Step 1b: any 🟡 or 🔴)
- Sleep + AZM if already auto-fetched on the day's record (`health.sleep_hours`, `health.active_zone_minutes`)
- **Sleep timing** when available (`health.sleep_bedtime`, `health.sleep_wake_time` — ISO 8601 with timezone offset, e.g. `2026-05-20T22:30:00-06:00`) — when the user went to sleep and when they woke up. These are load-bearing alongside stage architecture. Late bedtime (after ~11:30 PM) and early wake (before ~6:00 AM) often predict low next-day rating independently of total hours or stage breakdown. If timing fields are absent (older records before backfill, or no sleep recorded), skip silently. Convert to 12-hour AM/PM for display per the chat-time rule.

**Strong-signal patterns — name the driver in one sentence, then move on:**
- Rating 4–5, focus mostly done, habits mostly hit → "Focus and habits both landed — that tracks."
- Rating 1–2, focus mostly skipped → "Focus didn't land (X of Y done) — likely the rating driver."
- Rating 1–2 + `hyperfocused: true` → "Hyperfocus today."
- Rating 1–2 + sleep < 6h (when health is populated) → "Short sleep last night usually shows up as low energy + mood."
- Rating 1–2 + bedtime after ~11:30 PM (when timing populated) → "Late bedtime last night — staying-up-late rarely pans out."
- Rating 4–5 + bedtime before ~10:30 PM AND wake before ~7:00 AM → "Early-to-bed-early-to-rise cycle today — good signal to repeat."
- **Mismatch** (rating ≥ 4 but most focus skipped, or rating ≤ 2 but most done) → flag explicitly and probe: "Rated 4 but 1 of 3 focus done — what made the day feel good?"

**No strong signal — probe with ONE question:**
- Rating ≤ 2: "Day rated low — anything specific that pulled it down?"
- Rating ≥ 4: "Day rated high — what worked?"
- Rating = 3: skip the probe. Neutral days don't need narrative.

If the user answers, append the answer to `evening_notes` (concatenate with the original one-line reflection from Step 3, separated by `; `) before Step 4 writes. Keep total `evening_notes` under ~200 chars — trim if needed.

**Hard rules:**
- One sentence of interpretation max. No full breakdown.
- One probe question max. Never stack two.
- If ratings were skipped, skip this step entirely.
- Don't probe on rating = 3.
- Don't repeat back ratings the user just gave.

---

## Step 4 — Update record

First check whether a record already exists for the target date:

```bash
RECORD_EXISTS=$(jq -c --arg d "YYYY-MM-DD" 'select(.date == $d)' data/day-tracking.ndjson | head -1)
```

**Branch A — record exists (morning planning ran):** update in place.

```bash
tmp=$(mktemp)
jq -c \
  --arg date "YYYY-MM-DD" \
  --argjson sick false \
  --argjson rating N \
  --argjson energy N \
  --argjson focus N \
  --argjson mood N \
  --argjson hyperfocused false \
  --arg notes "..." \
  'if .date == $date then . + {sick: $sick, rating: $rating, energy: $energy, focus: $focus, mood: $mood, hyperfocused: $hyperfocused, evening_notes: $notes} else . end' \
  data/day-tracking.ndjson > "$tmp" && mv "$tmp" data/day-tracking.ndjson
```

**Branch B — no record exists (morning planning skipped):** append a fresh record with `null` for health fields (auto-fetch will backfill later).

```bash
jq -cn \
  --arg date "YYYY-MM-DD" \
  --argjson rating N \
  --argjson energy N \
  --argjson focus N \
  --argjson mood N \
  --argjson hyperfocused false \
  --arg notes "..." \
  '{
    date: $date,
    rating: $rating,
    energy: $energy,
    focus: $focus,
    mood: $mood,
    
    sick: false,
    
    hyperfocused: $hyperfocused,
    notes: null,
    evening_notes: $notes,
    health: {
      sleep_minutes: null,
      sleep_hours: null,
      awake_minutes: null,
      sleep_deep_minutes: null,
      sleep_rem_minutes: null,
      sleep_light_minutes: null,
      resting_hr_bpm: null,
      active_zone_minutes: null
    }
  }' >> data/day-tracking.ndjson
```

**Critical:** do NOT run Branch A's update-in-place jq against a missing record — the predicate silently never matches and every field drops on the floor with exit 0.

---

## Step 4b — Refresh Trello dashboard (fail-safe)

The completion-pull half of the Trello sync already ran in **Step 0c**. This step handles the post-record half: move uncompleted 2+1 cards back to ✅ Actions, then re-render so the board reflects today's writes.

**This step is fail-safe:** any error here is logged but does not block the commit step. If Trello is down, your evening checkin still records normally.

1. Move any uncompleted 2+1 cards back to ✅ Actions for tomorrow:
   ```bash
   python3 automations/scripts/trello_writeback.py move-back-uncompleted 2>&1
   ```
   On error: print `🟡 Trello move failed (non-blocking): <error>` and continue.

2. Run a render to refresh the dashboard with the new state:
   ```bash
   # Note: this is the simple form. The full pfc-render-trello workflow
   # also pulls Calendar + Email; for evening, simple is fine.
   python3 automations/scripts/trello_render.py 2>&1
   ```
   On error: print `🟡 Trello render failed (non-blocking): <error>` and continue.

3. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step entirely.

---

## Step 5 — Commit

```bash
git add data/day-tracking.ndjson 6-habits/_data/habits-daily.ndjson
git commit -m "checkin: record YYYY-MM-DD"
git push
```
