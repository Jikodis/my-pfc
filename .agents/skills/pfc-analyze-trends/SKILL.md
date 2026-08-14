---
name: pfc-analyze-trends
description: Analyze day tracking data for statistical trends. Finds the strongest predictors of good vs bad days using correlation and effect size. Use when the user says "analyze trends", "what makes my good days", "day trend analysis", "what's affecting my ratings", or "trend report".
---

# Day Trend Analysis

Run the statistical analysis, classify each factor by the SHAPE of its effect, then turn the robust findings into concrete repo changes.

## Step 1 — Run the analysis

```bash
python3 automations/scripts/analyze_day_trends.py
```

The script prints, in order: correlations and effect sizes, a good-vs-bad profile, top predictors, the gate/gradient pass, sleep and workout breakdowns, multi-day context (lagged, rolling debt, schedule steadiness, partial correlation, day of week), and the QQRT sleep-threshold section.

Requires at least 5 rated records.

## Step 2 — Present findings

Show the script output, then add interpretation:

- The **top 2-3 predictors** in plain language.
- Any **surprise** — a factor that moved opposite to expectation.
- Anything with **too little data** to trust (n < 7). Say so rather than reporting it as a result.
- Whether this **confirms or challenges a hypothesis** in `data/hypotheses.ndjson`.
- **1-2 actionable changes** the user could make.

## Step 3 — Name each factor's shape: GATE or GRADIENT

The correlation pass lumps outcomes into good and bad and cannot tell a dial from a switch. The script's **gate/gradient** section computes each factor's mean inside *every* rating bucket, which borrows power from all your rated days instead of only the sparse top bucket. Always report this classification — it converts "what predicts a good day" into "what do I actually pull."

| Class | Shape | What it means | How to surface it |
|---|---|---|---|
| **GRADIENT** | Climbs steadily across every bucket; the final step carries ≤ ~55% of the total span | A dose-response dial — every increment pays, and your mid-rated days genuinely tighten the target | Daily surface: a habit or a pulse lever |
| **GATE** | Flat across the low and middle buckets, then jumps at the top (final step ≥ ~50% of span) | A pass/fail condition the best days clear, not something to trend toward | A checkbox, not a dial — it usually comes along once the gradient levers are in range |
| **noisy / floor** | Tiny magnitude, or no clean pattern | A non-driver, however interesting the metric sounds | Report honestly. Do NOT promote it to a lever |

The test is where the movement *lands*, not raw monotonicity — a front-flat factor is technically monotonic and is still a gate.

**Practical read:** to trend upward, push the gradient levers. The gates are necessary conditions that mostly follow.

## Step 4 — Sleep: read the threshold, not the correlation

**Read the § QQRT SLEEP THRESHOLD section before concluding "sleep doesn't matter."** Total sleep hours often reads FLAT against day rating, which is a property of the statistic, not of sleep: a linear correlation is structurally blind to a threshold effect. The real pattern is usually that a night either clears a bar or it doesn't.

- **QQRT** = Quantity + Quality + Timing scored (0–3), with **Regularity computed and tracked but not scored** until there's a steady stretch to compare against. Bars live in `automations/scripts/qqrt.py`, tunable in `config/automation_config.yaml` → `health.sleep`.
- **Quality is computed from raw efficiency and deep-sleep share.** The provider's own 0–100 sleep score is not fetchable — it's app-proprietary. Don't go looking for it.
- Report the **above/below-bar split** and the **composite ladder**, not just the linear r.
- **Sleep debt** is a companion number, not a score lever: the 14-night average nightly shortfall against the target, persisted per day as `qqrt.sleep_debt`. It's the built-in "looks good on paper" detector — a long, continuous night taken *while still in debt* underperforms the same night taken rested.
- **Trailing 2-night WORST night.** A 4-hour night followed by an 8-hour night averages to "fine" and still wrecks the day. A rolling mean hides that; the minimum surfaces it. Read this before blaming anything else for a bad day after a good night.

**A day rating is multi-causal**, so the sleep section measures against a **physiology composite (energy + focus, mood dropped)** — mood reads general well-being, which is a different construct from the body's sleep response. **No day is excluded for what happened in it.** There is no `life_event` field: events are frequent and normal, so filtering event days out biases the sample toward uneventful ones. Never narrate a result as "that day was just event-driven." 

## Step 5 — Hypothesis update

If findings confirm or contradict a hypothesis in `data/hypotheses.ndjson`, offer to update it. If a strong new pattern emerges that isn't tracked, offer to add one via `/pfc-add-hypothesis`.

## Step 6 — Close the loop: turn trends into repo changes

**Analysis that doesn't change the repo is wasted.** A trend only matters if the system starts surfacing or acting on it. Map every robust finding (not the noisy ones) to a concrete change and propose them in one table: `# | Finding | Proposed change | Where`.

| Finding shape | Repo change | Where |
|---|---|---|
| GRADIENT lever with no daily surface | Add a Daily Pulse lever, with the band grounded in the bucket means | `automations/scripts/pulse.py` (or `config/automation_config.yaml` → `health.pulse` if only the band moves) |
| GRADIENT lever that's a controllable behavior (bedtime, exercise, screens) | Add or adjust a habit | `config/habit_schema.yaml` + `/pfc-log-habit` |
| Confirmed strong predictor worth promoting | Move a pulse lever MODERATE → CRITICAL so it drives the verdict | `pulse.py` lever tier |
| A new causal pattern | Add or update a hypothesis | `data/hypotheses.ndjson` via `/pfc-add-hypothesis` |
| A durable "remember this" takeaway | Add an insight | `data/insights.ndjson` via `/pfc-add-insight` |
| A threshold that's plainly wrong for this person | Edit the band | `config/automation_config.yaml` → `health.sleep` / `health.pulse` |

Rules: auto-capturable records (hypothesis, insight) may be written on a yes. **Structural changes — a new or promoted pulse lever, a new habit, a threshold edit — ask first** per the commit policy. When promoting a lever into the verdict, check the new bar still reproduces the verdict on your known best days before shipping; don't tighten a working formula by accident.

## Sleep analysis — the four dimensions

Sleep is not just stage architecture. Treat these as co-equal:

1. **Duration** — `health.sleep_hours`
2. **Architecture** — `health.sleep_deep_minutes`, `sleep_rem_minutes`, `sleep_light_minutes`
3. **Timing** — `health.sleep_bedtime`, `health.sleep_wake_time` (ISO 8601 with offset). When someone fell asleep and woke is independently predictive: 7 hours from 11 PM is not 7 hours from 2 AM, even with identical stage minutes. The script's partial correlation tests exactly this — bedtime's effect *controlling for* total sleep.
4. **Continuity** — `health.awake_minutes` (total fragmentation), `health.awakenings_count`, and `health.awakenings` (each real waking's clock time and length). `sleep_continuity` reads `"fragmented"` when the night was split across sessions.

**Continuity deserves special weight, and it's the easiest thing to get wrong.** A fragmented night is logged as several separate sessions, and the awake time *between* them belongs to none of them — naive parsing both undercounts awake minutes and makes the night read as continuous, inflating efficiency on exactly the broken nights that should fail. `sleep_reduce.py` fixes this; `sleep_awake_gap_minutes` shows how much awake time sat between sessions. Adequate total hours with a broken night is still a poor night — never pass a "good sleep" judgment on `sleep_hours` alone.

`awakenings` is stored as the full list, not a count, so you can re-window it after the fact: derive an "awakenings after 2 AM" predictor to test an early-waking pattern that a nightly total can never surface.

When narrating a sleep finding, **name which dimension drove it**. "You slept better" is useless; "you went to bed 90 minutes earlier" or "you woke 4 times instead of once" is actionable.

## Recovery metrics — co-equal predictors, not just sleep

Correlate these daily readouts against rating, energy, and mood:

5. **Heart-rate variability** (`health.hrv_ms`) — the headline recovery/stress signal. A drop below the recent norm can lead a low day. Check its *magnitude* before promoting it: if the whole spread across your rating buckets is a millisecond or two, it's a floor, not a driver.
6. **Resting heart rate** (`health.resting_hr_bpm`) — elevated tracks stress, under-recovery, oncoming illness.
7. **Skin-temperature deviation** (`health.skin_temp_nightly_c` − `health.skin_temp_baseline_c`) — a positive spike often precedes illness.
8. **Breathing rate** (`health.respiratory_rate_bpm`) and **blood oxygen** (`health.spo2_avg_pct`) — slower-moving; shifts flag respiratory stress.

Objective readouts are the trustworthy signal on any day the self-report is unreliable. The full intraday streams live in `data/health-raw/` when a daily aggregate isn't enough.

## Tracked workouts — what Active Zone Minutes cannot express

AZM is one daily number that mixes a hard workout with a stressful afternoon at an elevated heart rate. A tracked session carries what that number can't (§ TRACKED WORKOUT BREAKDOWN):

9. **Intensity** — `health.workout_azm`, `health.workout_vigorous_minutes`. A 30-minute hard session and a 30-minute walk are not the same input.
10. **Timing** — `health.first_workout_time`. A 6:30 AM session and a 12:30 PM session are indistinguishable in AZM and may not be equivalent for the rest of the day.
11. **Type** — `health.workouts[].type`, so one modality can be separated from movement generally.

**Never read a no-session day as a rest day.** Working out without starting a session on the watch is common, so the self-reported `exercised` field and a tracked session measure different things — intent versus what the device recorded. Keep both, and say which one a finding rests on. By the same rule, **`azm_outside_workouts` is not a stress measure**: it holds untracked workouts, walking, and chores alongside an elevated resting heart rate. Never present it as anxiety AZM.

Session coverage only starts when workout tracking starts. Treat earlier nulls as a data gap, not as rest.

## Best-days comparison — "what tips a good day into a great one"

Low ratings have obvious causes (short or broken sleep, illness, stress). The useful, non-obvious question is what separates a **good** day from your **best** day. The standard pass (Step 1) lumps all good days together and misses that boundary. Run this on request ("compare my good vs best days", "what makes a great day"), and after **any** new top-rated day, so the fingerprint keeps sharpening.

**Method** (a custom pass over `data/day-tracking.ndjson`, not in the script):

1. Split rated days into top-bucket and next-bucket groups. For every health factor (`sleep_hours`, `awake_minutes`, `sleep_deep/rem/light_minutes`, `awakenings_count`, `hrv_ms`, `resting_hr_bpm`, `sleep_bedtime`, `sleep_wake_time`, `active_zone_minutes`, `workout_azm`, `workout_vigorous_minutes`, `first_workout_time`), compute each group's mean. Where a factor has thin coverage in the top group, report it as **coverage-limited**, not as a null result.
2. Find **look-alike days** — next-bucket days whose profile matches a top day. A good day that *looks* like a great one is the most informative case; inspect exactly what differs.
3. For any anomaly, read that day's **stored trailing sleep debt** (`qqrt.sleep_debt` → `avg_shortfall_min`, `cumulative_hours`). A look-alike day carrying high trailing debt is a debt-masked good day, not a great one. Don't hand-roll a trailing window — the number is already persisted per day.
4. Then run the **ordinal gate/gradient pass across all buckets** (Step 3). The binary top-vs-next split is nearly always underpowered; the ordinal pass uses every rated day and is what should actually decide a lever change.

A directional finding from a handful of top days is a lead, not a conclusion. Say so.

## Notes

- Supplement data is joined from `data/supplements.ndjson` by date range: the active record on date D is the one where `started <= D AND (stopped is null OR stopped > D)`. Historical correlations only go as deep as the registry — fix the timeline there if it's wrong. To correlate a specific supplement, add a column in `load_records()`.
- Older records won't have timing, workout, or recovery fields until `python3 automations/scripts/google_health_backfill.py --all` runs. Treat absent fields on old days as a data gap, not a signal.
- Every threshold in this pipeline is a generic starting default. Two rules when tuning: a bar almost every night clears carries no information, and a bar you never clear stops being actionable.
