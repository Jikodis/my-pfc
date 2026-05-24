---
name: pfc-analyze-trends
description: Analyze day tracking data for statistical trends. Finds the strongest predictors of good vs bad days using correlation and effect size. Use when the user says "analyze trends", "what makes my good days", "day trend analysis", "what's affecting my ratings", or "trend report".
---

# Day Trend Analysis

Run the statistical analysis script and present findings with interpretation.

## Step 1 — Run analysis

```bash
python3 automations/scripts/analyze_day_trends.py
```

## Step 2 — Present findings

Show the full output from the script, then add your own interpretation:

- Call out the **top 2-3 predictors** in plain language
- Note any **surprises or counterintuitive findings**
- Flag anything with **too little data** to be reliable (n < 7)
- Connect findings to **hypotheses** in `data/hypotheses.ndjson` if relevant — does this confirm or challenge existing hypotheses?
- Suggest **1-2 actionable changes** the user could make based on the data

## Step 3 — Hypothesis update (optional)

If the findings confirm or contradict an existing hypothesis, offer to update `data/hypotheses.ndjson`.
If a strong new pattern emerges that isn't tracked yet, offer to add it as a new hypothesis.

## Notes

- The analysis requires at least 5 rated records
- Supplement data (whatever's registered in `data/supplements.ndjson`) is joined from `data/supplements.ndjson` by date range. The active record on a given date D is the one where `started <= D AND (stopped is null OR stopped > D)`. Historical correlations are only as deep as the registry's backfill — edit `data/supplements.ndjson` if the timeline is wrong.
- Sleep data covers the full dataset — those findings are more reliable
- Re-run with `--all` flag if you want to refresh cached health data

## Sleep analysis — what to look at

Sleep is not just architecture (stage minutes). Treat these as co-equal load-bearing variables:

1. **Total sleep duration** (`health.sleep_hours`)
2. **Stage architecture** — deep, REM, light, wake minutes (`health.sleep_deep_minutes`, `health.sleep_rem_minutes`, `health.sleep_light_minutes`, `health.awake_minutes`)
3. **Sleep timing** — bedtime + wake time (`health.sleep_bedtime`, `health.sleep_wake_time`, ISO 8601 with timezone offset). When the user fell asleep and when they woke up are independently predictive of next-day rating. A 7-hour night from 11 PM → 6 AM is not the same as 7 hours from 2 AM → 9 AM, even with identical stage breakdown.
4. **Continuity** — wake minutes (fragmentation)

When narrating a sleep finding, name which dimension drove it — duration, architecture, timing, or continuity. "You slept better last night" is too vague; "You went to bed 90 minutes earlier" or "you got 30 more minutes of REM" is actionable.

Older records (before timing-field backfill) may not have `sleep_bedtime`/`sleep_wake_time` populated. Run `python3 automations/scripts/google_health_backfill.py --all` to fill them. Treat absent timing on old days as a data gap, not a signal.
