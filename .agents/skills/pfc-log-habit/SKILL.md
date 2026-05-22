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
- **Unlogged days count as missed in rate math.** A day inside a review window with no entry for a habit is counted as a miss, the same as `completed: false`. That makes recording part of the habit, not an optional extra. Two guardrails: never *backfill* `completed: false` onto blank past days (absence is interpreted at compute time, not written into the data), and use `skipped: true` for days the habit genuinely couldn't happen — those drop out of both numerator and denominator. Full rule and how to flip the default: [`7-habits/AGENTS.md`](../../../7-habits/AGENTS.md) § Hard rules.

## Steps

1. Identify which habit the user completed from their input.
2. Check `config/habit_schema.yaml` for the habit ID and type (daily or monthly).
3. Resolve the target date:
   - Default: today (`TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'`).
   - If user specifies "yesterday", "Monday", etc., resolve to an absolute date.
4. Write or update the entry (see commands below).
5. Show current week/month completion count for that habit (see queries below).
6. Commit and push: `git add 7-habits/_data/habits-*.ndjson && git commit -m "habit: log YYYY-MM-DD" && git push`
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
    7-habits/_data/habits-daily.ndjson > /dev/null; then
  # Update in place
  jq -c --arg h "$HID" --arg d "$DATE" --argjson c "$COMPLETED" \
    'if (.habit_id // .habit) == $h and .date == $d
     then . + {habit_id:$h, date:$d, completed:$c, logged_at:(now | strftime("%Y-%m-%dT%H:%M:%S%z"))}
     else . end' \
    7-habits/_data/habits-daily.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 7-habits/_data/habits-daily.ndjson
else
  # Append new record
  jq -cn --arg h "$HID" --arg d "$DATE" --argjson c "$COMPLETED" \
    '{habit_id:$h, date:$d, completed:$c, logged_at:(now | strftime("%Y-%m-%dT%H:%M:%S%z"))}' \
    >> 7-habits/_data/habits-daily.ndjson
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
    7-habits/_data/habits-daily.ndjson > /dev/null; then
  jq -c --arg h "$HID" --arg d "$DATE" --arg r "$REASON" \
    'if (.habit_id // .habit) == $h and .date == $d
     then . + {habit_id:$h, date:$d, completed:false, skipped:true, skip_reason:$r, logged_at:(now | strftime("%Y-%m-%dT%H:%M:%S%z"))}
     else . end' \
    7-habits/_data/habits-daily.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 7-habits/_data/habits-daily.ndjson
else
  jq -cn --arg h "$HID" --arg d "$DATE" --arg r "$REASON" \
    '{habit_id:$h, date:$d, completed:false, skipped:true, skip_reason:$r, logged_at:(now | strftime("%Y-%m-%dT%H:%M:%S%z"))}' \
    >> 7-habits/_data/habits-daily.ndjson
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
    7-habits/_data/habits-monthly.ndjson > /dev/null; then
  jq -c --arg h "$HID" --arg m "$MONTH" --arg d "$DATE" \
    'if (.habit_id // .habit) == $h and (.month == $m or (.date[:7] == $m))
     then . + {habit_id:$h, month:$m, date:$d, completed:true}
     else . end' \
    7-habits/_data/habits-monthly.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 7-habits/_data/habits-monthly.ndjson
else
  jq -cn --arg h "$HID" --arg m "$MONTH" --arg d "$DATE" \
    '{habit_id:$h, month:$m, date:$d, completed:true}' \
    >> 7-habits/_data/habits-monthly.ndjson
fi
```

## Queries

**Current week count (daily):**
```bash
WEEK_START=$(TZ="${LOCAL_TZ:-America/Denver}" date -d 'monday -7 days' '+%Y-%m-%d' 2>/dev/null)
jq -c --arg h "HABIT_ID" --arg w "$WEEK_START" \
  'select((.habit_id // .habit) == $h and .date >= $w and .completed == true)' \
  7-habits/_data/habits-daily.ndjson | wc -l
```

**Completion rate over a window (daily) — unlogged days count as misses.** The denominator is every day in the window minus the days explicitly marked `skipped: true`; the numerator is the days with `completed: true`. Days with no record at all land in the denominator only.

```bash
HID="HABIT_ID"; DAYS=14
END=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
START=$(TZ="${LOCAL_TZ:-America/Denver}" date -d "$END - $((DAYS-1)) days" '+%Y-%m-%d')
jq -s -r --arg h "$HID" --arg s "$START" --arg e "$END" --argjson n "$DAYS" '
  [ .[] | select((.habit_id // .habit) == $h and .date >= $s and .date <= $e) ] as $rows
  | ([$rows[] | select(.skipped == true)] | length) as $skipped
  | ([$rows[] | select(.completed == true)] | length) as $done
  | ($n - $skipped) as $denom
  | ($n - ($rows | length)) as $unlogged
  | "\($done)/\($denom) (\(if $denom > 0 then (($done * 100 / $denom) | floor) else 0 end)%) — \($unlogged) day(s) unlogged, counted as misses"
' 7-habits/_data/habits-daily.ndjson
```

**Current month count (monthly):**
```bash
MONTH=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m')
jq -c --arg h "HABIT_ID" --arg m "$MONTH" \
  'select((.habit_id // .habit) == $h and (.month == $m or (.date[:7] == $m)) and .completed == true)' \
  7-habits/_data/habits-monthly.ndjson | wc -l
```

## Two consecutive misses — offer the two-minute version

When logging a miss, check whether the same habit was also missed the day before (not skipped):

```bash
YDAY=$(TZ="${LOCAL_TZ:-America/Denver}" date -d yesterday '+%Y-%m-%d')
jq -r --arg h "$HABIT_ID" --arg y "$YDAY" \
  'select(.habit_id==$h and .date==$y and .completed==false and (.skipped//false)==false) | .habit_id' \
  7-habits/_data/habits-daily.ndjson
```

If it comes back, offer that habit's `ramp.two_minute` string from `config/habit_schema.yaml` as a single line for *today* — e.g. "Two in a row on guitar. Two-minute version: sit down and play one song."

One miss is noise; say nothing. This fires on the second only, once, without a lecture. See [`docs/habit-mechanics.md`](../../../docs/habit-mechanics.md) § Never miss twice.

## Ramped frequencies

A habit's `frequency` is the **live, ramped value** — not a fixed target. It steps down automatically after a red week and steps up (with an explicit yes) after two green weeks, bounded by `ramp.starter` and `ramp.target`. When logging, always read `frequency`, never `ramp.target`. Frequency changes are made by the weekly `habit-rate` review, not here.

## Limits

- Daily habits: max 14 tracked at a time, frequency 1–7 per week (see `config/habit_schema.yaml`; the cap is enforced in `scripts/validate.sh`)
- Monthly habits: max 6 tracked at a time, frequency 1–4 per month
