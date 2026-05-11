---
name: pfc-log-day
description: Log a daily tracker entry. Use when the user says "log my day", "rate my day", "day rating", or shares how their day went with a rating.
---

# Log Day — Daily Tracker

Track daily ratings and variables to identify patterns in what causes great or bad days. Wearable data (via the connector of your choice) can supplement this when available.

## Fields

- `date`: YYYY-MM-DD
- `rating`: 1-5 (5 = best day)
- `sick`: false, or a string describing illness
- `notes`: free text observations about the day

Additional fields can be added over time as new variables are tracked.

## Steps

1. Ask for or parse from the user's input:
   - Day rating (1-5, required)
   - Sick (if mentioned)
   - Notes (anything else they share about the day)
2. Append to `data/day-tracking.ndjson` using jq (never raw `echo >>` — CLAUDE.md rule):
   ```bash
   jq -cn \
     --arg date "YYYY-MM-DD" \
     --argjson rating N \
     --argjson sick false \
     --arg notes "..." \
     '{date:$date, rating:$rating, sick:$sick, notes:$notes}' \
     >> data/day-tracking.ndjson
   ```
   Use `--argjson` for numbers and booleans; `--arg` for strings.
3. Commit: `git add data/day-tracking.ndjson && git commit -m "track: log day YYYY-MM-DD" && git push`
4. **Refresh Trello dashboard** (fail-safe)

   If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, refresh the board so the new day rating shows up on `⬅ Last 7 Days` immediately.

   ```bash
   python3 automations/scripts/trello_render.py 2>&1
   ```

   On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step.

## Analysis

When asked to analyze day tracking data, use grep/jq to find patterns:
```bash
# Find all 5-star days
grep '"rating":5' data/day-tracking.ndjson

# Find low-rated days
grep '"rating":[12]' data/day-tracking.ndjson
```

Cross-reference with wearable sleep data, when available, to correlate sleep metrics with day ratings.
