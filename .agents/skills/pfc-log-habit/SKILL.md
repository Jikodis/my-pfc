---
name: pfc-log-habit
description: Log daily or monthly habit completion. Use when the user says "did my habit", "log habit", "track habit", "worked out", or mentions completing a tracked habit.
---

# Log Habit

## Rules

- **Exactly one entry per (habit_id, date)** for daily, or per (habit_id, month) for monthly. Never append a duplicate.
- If an entry already exists for that slot, **update it in place** (do not append a second record).
- All writes go through `jq` — never `echo >>` for structured data.
- Use the field name `habit_id` (not `habit`) for new entries.

## Steps

1. Identify which habit the user completed from their input.
2. Check `config/habit_schema.yaml` for the habit ID and type (daily or monthly).
3. Resolve the target date:
   - Default: today (`TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'`).
   - If user specifies "yesterday", "Monday", etc., resolve to an absolute date.
4. Write or update the entry (see commands below).
5. Show current week/month completion count for that habit (see queries below).
6. Commit and push: `git add 6-habits/_data/habits-*.ndjson && git commit -m "habit: log YYYY-MM-DD" && git push`
7. **Refresh Trello dashboard** (fail-safe)

   If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, refresh the board so the habit's status on `☀️ Daily Habits` / `🌙 Monthly Habits` reflects the new log.

   ```bash
   python3 automations/scripts/trello_render.py 2>&1
   ```

   On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step.

## Daily habit — write or update

```bash
HID="HABIT_ID"
DATE="YYYY-MM-DD"
COMPLETED=true   # or false for a missed-day log

# If an entry exists for (habit_id, date), update it; else append.
if jq -e --arg h "$HID" --arg d "$DATE" \
    'select((.habit_id // .habit) == $h and .date == $d)' \
    6-habits/_data/habits-daily.ndjson > /dev/null; then
  # Update in place
  jq -c --arg h "$HID" --arg d "$DATE" --argjson c "$COMPLETED" \
    'if (.habit_id // .habit) == $h and .date == $d
     then . + {habit_id:$h, date:$d, completed:$c, logged_at:(now | strftime("%Y-%m-%dT%H:%M:%S%z"))}
     else . end' \
    6-habits/_data/habits-daily.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 6-habits/_data/habits-daily.ndjson
else
  # Append new record
  jq -cn --arg h "$HID" --arg d "$DATE" --argjson c "$COMPLETED" \
    '{habit_id:$h, date:$d, completed:$c, logged_at:(now | strftime("%Y-%m-%dT%H:%M:%S%z"))}' \
    >> 6-habits/_data/habits-daily.ndjson
fi
```

## Daily habit — skip a structurally unavailable day

Use when the day was not a miss — the habit couldn't happen (e.g. travel blocks `sleep-on-time`, travel blocks a home-only habit, illness blocks a workout habit). A skip drops out of both numerator and denominator in weekly completion math; a miss counts against it. If the user is just reporting "didn't do it," that's a miss (use the block above with `COMPLETED=false`). Only mark skipped when the day was unavailable.

```bash
HID="HABIT_ID"
DATE="YYYY-MM-DD"
REASON="travel"   # required; short human-readable

# Upsert (habit_id, date) with skipped:true, completed:false, skip_reason:$REASON.
if jq -e --arg h "$HID" --arg d "$DATE" \
    'select((.habit_id // .habit) == $h and .date == $d)' \
    6-habits/_data/habits-daily.ndjson > /dev/null; then
  jq -c --arg h "$HID" --arg d "$DATE" --arg r "$REASON" \
    'if (.habit_id // .habit) == $h and .date == $d
     then . + {habit_id:$h, date:$d, completed:false, skipped:true, skip_reason:$r, logged_at:(now | strftime("%Y-%m-%dT%H:%M:%S%z"))}
     else . end' \
    6-habits/_data/habits-daily.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 6-habits/_data/habits-daily.ndjson
else
  jq -cn --arg h "$HID" --arg d "$DATE" --arg r "$REASON" \
    '{habit_id:$h, date:$d, completed:false, skipped:true, skip_reason:$r, logged_at:(now | strftime("%Y-%m-%dT%H:%M:%S%z"))}' \
    >> 6-habits/_data/habits-daily.ndjson
fi
```

## Monthly habit — write or update

```bash
HID="HABIT_ID"
DATE="YYYY-MM-DD"
MONTH="${DATE:0:7}"   # YYYY-MM

# One entry per (habit_id, month) — check presence, then update or append
if jq -e --arg h "$HID" --arg m "$MONTH" \
    'select((.habit_id // .habit) == $h and (.month == $m or (.date[:7] == $m)))' \
    6-habits/_data/habits-monthly.ndjson > /dev/null; then
  jq -c --arg h "$HID" --arg m "$MONTH" --arg d "$DATE" \
    'if (.habit_id // .habit) == $h and (.month == $m or (.date[:7] == $m))
     then . + {habit_id:$h, month:$m, date:$d, completed:true}
     else . end' \
    6-habits/_data/habits-monthly.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 6-habits/_data/habits-monthly.ndjson
else
  jq -cn --arg h "$HID" --arg m "$MONTH" --arg d "$DATE" \
    '{habit_id:$h, month:$m, date:$d, completed:true}' \
    >> 6-habits/_data/habits-monthly.ndjson
fi
```

## Queries

**Current week count (daily):**
```bash
WEEK_START=$(TZ="${LOCAL_TZ:-America/Denver}" date -d 'monday -7 days' '+%Y-%m-%d' 2>/dev/null)
jq -c --arg h "HABIT_ID" --arg w "$WEEK_START" \
  'select((.habit_id // .habit) == $h and .date >= $w and .completed == true)' \
  6-habits/_data/habits-daily.ndjson | wc -l
```

**Current month count (monthly):**
```bash
MONTH=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m')
jq -c --arg h "HABIT_ID" --arg m "$MONTH" \
  'select((.habit_id // .habit) == $h and (.month == $m or (.date[:7] == $m)) and .completed == true)' \
  6-habits/_data/habits-monthly.ndjson | wc -l
```

## Limits

- Daily habits: max 5 tracked at a time, frequency 1–7 per week (see `config/habit_schema.yaml`)
- Monthly habits: max 5 tracked at a time, frequency 1–4 per month
