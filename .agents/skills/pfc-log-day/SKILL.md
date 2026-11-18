---
name: pfc-log-day
description: Log a daily tracker entry. Use when the user says "log my day", "rate my day", "day rating", or shares how their day went with a rating.
---

# Log Day — Daily Tracker

Track daily ratings and variables to find what causes great or bad days. Wearable data (via the connector of your choice) fills in the physiology side automatically.

## Fields

| Field | Type | Notes |
|---|---|---|
| `date` | YYYY-MM-DD | |
| `energy`, `mood`, `focus` | 1–5 each | **The primary capture — ask for these three, not an overall rating.** |
| `rating` | 1–5 | **DERIVED, never asked.** Compute `round(mean(energy, mood, focus))` and store it — many readers depend on the field. Equal weight, no decimal weighting. |
| `exercised` | true / false | Did the keystone workout happen **at all, at any time**. Deliberately not time-boxed (see below). |
| `sick` | false, or a string | A short description when unwell. |
| `notes` | free text | Anything else worth keeping. |

Add fields over time as you start tracking new variables.

**Why the rating is derived.** A single overall number is a guess, and mood is the component most contaminated by events — a great evening lifts mood without changing how the body ran. Capturing the three components separately means the analyzer can use **energy + focus alone** as a clean physiology outcome for sleep analysis, while `rating` stays a faithful summary of the whole day. It also gets around the fact that "the day was a 3" is a much harder judgment than "energy was clearly low."

**Why `exercised` isn't time-boxed.** An earlier design asked whether the workout happened in a specific morning window, which threw away every session that happened later and made the field mostly false. The question that actually predicts anything is whether it happened at all. (If a record carries a legacy `morning_movement` field, the analyzer reads it as a fallback — no migration needed.)

**Do NOT tag or discount days for external events.** There is no `life_event` field. Events (a great evening, a concert, a milestone) are a normal, frequent part of a life, not noise to filter out — and since `mood` is rated for the day as a whole, a good number on an event day is a real reading. Never say or record "the high mood was just the event." What happened goes in `notes`, as description, not as a discount.

## Steps

1. Ask for or parse from the user's input:
   - **Energy, mood, focus (1–5 each, required).** Then compute `rating = round((energy + mood + focus) / 3)`. Never ask for the overall rating.
   - Whether the keystone workout happened (if mentioned).
   - Sick (if mentioned).
   - Notes.
2. Append to `data/day-tracking.ndjson` using jq (never raw `echo >>` — see the repo commit rules):
   ```bash
   jq -cn \
     --arg date "YYYY-MM-DD" \
     --argjson energy E --argjson mood M --argjson focus F \
     --argjson rating R \
     --argjson exercised false \
     --argjson sick false \
     --arg notes "..." \
     '{date:$date, rating:$rating, energy:$energy, focus:$focus, mood:$mood, exercised:$exercised, sick:$sick, notes:$notes}' \
     >> data/day-tracking.ndjson
   ```
   `R` is the computed `round((E+M+F)/3)` — compute it before the call. Use `--argjson` for numbers, booleans, and `null` (pass a literal `null`); `--arg` for strings. For an illness description, swap `--argjson sick false` → `--arg sick "fever"`.
3. **Refresh the sleep composite.** Health data may have landed since the last fetch, and `qqrt` must not lag it:
   ```bash
   python3 automations/scripts/backfill_qqrt.py
   ```
   Idempotent — it prints how many records changed, and 0 is a normal result. On error, print `🟡 QQRT recompute failed (non-blocking): <error>` and continue.
4. Commit: `git add data/day-tracking.ndjson && git commit -m "track: log day YYYY-MM-DD" && git push`
5. **Refresh Trello dashboard** (fail-safe)

   If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, refresh the board so the new day rating shows on `📈 Trends` and the rating card leaves `🦸 Body first` immediately.

   ```bash
   python3 automations/scripts/trello_render.py 2>&1
   ```

   On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step.

## What the wearable fills in

Don't ask for anything the fetch already writes. `automations/scripts/auto_fetch_health.py` populates `health` on the record with sleep (duration, stages, bedtime/wake, continuity, per-night awakenings), resting heart rate, Active Zone Minutes, tracked workout sessions, and daily recovery metrics (heart-rate variability, blood oxygen, breathing rate, skin temperature, VO2 max). It then writes the `qqrt` sleep composite and its trailing sleep-debt ledger.

If health data is missing for the date, run `python3 automations/scripts/auto_fetch_health.py YYYY-MM-DD` before logging — it's idempotent and updates in place.

## Quick looks

```bash
# Top-rated days
grep '"rating":5' data/day-tracking.ndjson

# Low-rated days
grep '"rating":[12]' data/day-tracking.ndjson

# Last 10 nights: sleep hours, awake minutes, QQRT score, trailing debt
jq -r 'select(.health.sleep_hours != null)
       | [.date, .health.sleep_hours, .health.awake_minutes,
          (.qqrt.score // "-"), (.qqrt.sleep_debt.avg_shortfall_min // "-")]
       | @tsv' data/day-tracking.ndjson | tail -10
```

Reading a single night: **adequate hours with a broken night is still a poor night.** Check `awake_minutes` and `sleep_continuity` before calling any night good on hours alone.

For real analysis — correlations, gate-versus-gradient classification, the QQRT threshold split, sleep debt, and the trailing-2-night worst night — use `/pfc-analyze-trends`.
