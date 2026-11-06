# Data Model

Canonical reference for data files and their schemas. Keep this in sync with `config/*_schema.yaml` and the actual records on disk — if this doc drifts, fix the doc.

**All NDJSON writes must go through `jq`.** Never use `echo >>`, `sed`, or string concatenation. See [conventions.md](conventions.md) for the exact patterns.

Two scripts rewrite NDJSON in Python instead: the web UI's writer (`automations/scripts/web_write.py`) and the Trello sync (`trello_writeback.py`). Both make their record changes in `automations/scripts/pfc_writes.py` and write files through `automations/scripts/ndjson_file.py`, which keeps untouched lines byte for byte, writes changed lines the way `jq -c` does, and replaces the file atomically.

## Formats

| Format | Use case |
|---|---|
| Markdown | Values, area statements, project plans, notes, reports |
| NDJSON | Tasks, habits, day tracking, focus, projects, events |
| YAML | Schemas, configuration, automation settings |
| Generated | Dashboards, charts, reports (reproducible from source) |

## NDJSON files

### `6-tasks/_data/tasks.ndjson` — canonical task storage

```json
{"id":"task-20250101-001","status":"open","description":"…","size":"S","location":"PC","impact":"high","urgency":"medium","project":"proj-20250101-002","deadline":"2025-02-01","created":"2025-01-01","source":"daily-planning","notes":"optional free text"}
```

Required: `id`, `status`, `description`, `created`. Canonical schema: [`config/task_schema.yaml`](../config/task_schema.yaml).

- `id` — `task-YYYYMMDD-NNN`
- `status` — `"open"` | `"done"`
- `size` — `"XS"` | `"S"` | `"M"` | `"L"` | `"XL"`
- `location` — `"Home"` | `"PC"` | `"Errand"` | `"Phone"` | `"Anywhere"`
- `impact`, `urgency` — `"low"` | `"medium"` | `"high"`
- `project` — project `id` (e.g. `proj-20250101-002`) or `"none"`. Never `null`.
- `deadline`, `created`, `completed` — `YYYY-MM-DD`
- `source` — where the task was captured (`daily-planning`, `phone`, `email-triage`, etc.)
- `notes` — optional free text
- `area` — optional; lowercase, must match a folder in `2-areas/`. Used for standalone strategic tasks with no project (see the values-alignment section of `AGENTS.md`).
- `depends_on` — optional array of task IDs (`["task-20250101-004", ...]`). The task is considered "blocked" until every listed task has `status == "done"`. `pfc-pick-tasks` hides blocked tasks from suggestions; `scripts/validate.sh` checks each ID resolves and rejects self-references.
- `deferred` — optional boolean, default `false`. **Parked by the user: still open work, just deliberately out of rotation until they ask for it back.** Not a status — a deferred task is neither done nor abandoned. Set it when the user says "take it off the rotation", "park it", "stop offering it". Deferred tasks are hidden from `pfc-pick-tasks`, the home page's 2+1 suggestions, the Trello `✅ Tasks` list, and `pfc-revive`'s slippage signals (so the system stops nagging about something the user consciously set down). They stay visible in `/pfc-list-tasks` under `⏸️ Parked (not in rotation)` — that is the only surface they appear on. Un-park by setting it to `false`. Why this exists: without it, the only ways to stop a task recurring in picks were to delete it or fake-complete it, both of which lose real work.
- `deferred_reason` — optional string, nullable. Why it was parked, in the user's own words. Shown alongside the task in `/pfc-list-tasks` so the reason is in view at un-park time.
- `sequence` — optional 1-based integer. Used on project tasks where order matters (course curricula, ordered method books). `pfc-pick-tasks` and the home page's 2+1 suggestions only surface the lowest-sequence open task per project — higher-sequence siblings stay hidden until the prior is done. Standalone tasks (`project: "none"`) leave this null.
- `source_email_thread_id` — optional Gmail thread ID. Set when `source: "email-triage"`. Primary dedup key for the email-surfacing skills (`pfc-email-triage`, run every morning by the daily sync job): before creating a task from an email, those skills query `tasks.ndjson` + `tasks-archive.ndjson` by this field. Encodes the "labeled email = at least one linked task" principle.
- `source_email_subject` — optional raw subject line (including any `Re:` / `Fwd:` prefix). Fallback dedup key when the thread ID is missing or no match is found; also surfaced to the user during dedup confirmation.

### `6-tasks/_data/tasks-archive.ndjson`

Same shape as `tasks.ndjson`. Done tasks are moved here during the `stale-task-triage` review pass (or when the live file exceeds ~200 lines).

### `6-tasks/_data/task_events.ndjson` — append-only audit log

```json
{"task_id":"task-20250101-001","event":"created","timestamp":"2025-01-01","source":"daily-planning"}
{"task_id":"task-20250101-001","event":"completed","timestamp":"2025-01-02","note":"knocked out after lunch"}
```

- `task_id` — required, matches a task id (may be `null` only for cross-cutting corrections)
- `event` — `"created"` | `"completed"` | `"updated"` | `"archived"`
- `timestamp` — `YYYY-MM-DD`
- `note` — optional free text
- `event_id` — optional `evt-YYYYMMDD-NNN` for the event record itself
- `source` — optional origin

### `5-projects/_data/projects.ndjson`

Registry of short-term projects (up to 12 active — a runaway backstop, not a focus cap; see `AGENTS.md`).

```json
{"id":"proj-20250101-002","name":"Example Course Track","active":true,"excitement":"high","impact":"high","urgency":"high","estimated_months":2,"area":"learning","values":["Growth","Learning"],"total_parts":8,"completed_parts":1,"created":"2025-01-01","deadline":"2025-03-01"}
```

Canonical schema: [`config/project_schema.yaml`](../config/project_schema.yaml). Completion % = `completed_parts / total_parts`.

Fields:
- `id` — `proj-YYYYMMDD-NNN`
- `name`, `description`, `goal` — human-readable project context
- `active` — boolean; backstop of 12 active at a time
- `status` — optional lifecycle tag: `"active"`, `"on-deck"` (wanted next, not started; `active: false`), `"parked"` (deliberately stopped for now; `active: false`), `"done"`, or `"dropped"`. A row with no `status` reads as `active` when `active` is true and `on-deck` otherwise.
- `excitement`, `impact`, `urgency` — `"low"` | `"medium"` | `"high"` (per schema)
- `estimated_months` — optional, 1–3 typical
- `area` — lowercase, must match a folder in `2-areas/`
- `values` — array of values from `1-values/values.md`
- `total_parts`, `completed_parts` — numeric; drive completion %
- `gate` — optional blocker/precondition note
- `priority_order` — optional ordered array of sub-parts
- `created`, `deadline`, `completed` — `YYYY-MM-DD`

### `6-tasks/_data/daily-focus.ndjson` — the 2+1 picks

```json
{"date":"2025-01-16","critical":["task-20250101-002","task-20250115-003"],"bonus":"task-20250101-017","completed":[],"bonus_completed":false}
```

- `date` — `YYYY-MM-DD`. After about 6 PM the tour's picks step pre-stages **tomorrow's** record, so a date up to 1 day in the future is valid (the validator allows the +1-day ceiling).
- `critical` — array of task ids (strings; must exist in `tasks.ndjson` or `tasks-archive.ndjson`). At most 2 of them are undone; the rest are picks already done that day, kept when more work is pulled in after the first ones were finished (`web_write.py set-picks`). A record may carry `critical: []` when it holds only skips.
- `bonus` — optional task id string (same existence rule)
- `completed` — array of task ids from `critical` that were finished
- `skipped` — optional array of task ids (same existence rule) the home page stops suggesting for that date (`web_write.py skip-suggestion`, read by `home_data.suggest`). A task named here moves to the archive when dropped, like a pick.
- `bonus_completed` — boolean
- `project` — optional task id for the 4th slot, a pre-planned active-project task (see `6-tasks/AGENTS.md` § Daily focus)
- `project_completed` — boolean, present only when `project` is set
- `calendar_events` — optional object written by `pfc-schedule-focus` for manually-placed per-task events; keyed by task id, each value has `event_id`, `start`, `end` (ISO timestamps).

### `7-habits/_data/habits-daily.ndjson`

```json
{"habit_id":"morning-cardio-20min","date":"2025-01-24","completed":true,"source":"manual","logged_at":"2025-01-24T07:30:00Z"}
{"habit_id":"family-reading","date":"2025-01-21","completed":false,"skipped":true,"skip_reason":"travel","source":"chat"}
```

- `habit_id` — must match an `id` in `config/habit_schema.yaml` (active) or `deprecated_habits` (historical only)
- `completed` — boolean; did the habit happen that day
- `source` — `"google_health_auto"` | `"manual"` | `"fitbit"` | `"chat"` | `"trello"` | `"web"` (legacy read value on older rows, not written anew: `"evening-checkin"`)
- `value` — optional measurement (e.g. active-minutes count, bedtime)
- `skipped` — optional boolean; `true` means the day was structurally unavailable (e.g. travel, illness, a family-time habit on a night the family is away). A skipped day is **not a miss** — habit-rate math excludes it from both numerator and denominator: `rate = completed / max(1, target_frequency - skipped_count)`.
- `skip_reason` — optional free-text string; required when `skipped: true`. Short, human-readable.

When `skipped: true`, `completed` must be `false`. The fields coexist so queries that only filter on `completed == true` keep working unchanged; skip-aware consumers (the `habit-rate` rolling review, trend analysis) read both.

**Unlogged = missed.** A day with no record for an active habit counts as a miss in rate math — only an explicit `skipped: true` record excuses a day. This keeps rates honest when logging lapses.

**`ramp` on the habit definition.** A habit in `config/habit_schema.yaml` that is not yet automatic carries `ramp: {starter, target, two_minute}`. `frequency` is the **live, ramped value** — never read `ramp.target` for rate math. Two consecutive green weeks propose a +1 step toward `target` (needs an explicit yes); one red week steps −1 automatically and never below `starter`. `two_minute` is the scaled-down version the never-miss-twice rule offers after two consecutive misses. Habits with no `ramp` block never step. Full mechanics: [`docs/habit-mechanics.md`](habit-mechanics.md).

Caps: **14 daily, 6 monthly.** The daily cap is enforced in `scripts/validate.sh` and documented in the schema comment — keep both in sync (`pfc-repo-maintenance` checks for drift between them).

### `7-habits/_data/habits-monthly.ndjson`

Same shape as daily; `date` may be the first of the month.

### `data/day-tracking.ndjson` — daily day tracker

```json
{"date":"2025-01-21","rating":4,"energy":3,"focus":4,"mood":4,"sick":false,"exercised":null,"hyperfocused":true,"notes":null,"evening_notes":"…","health":{"sleep_minutes":423,"sleep_hours":7.0,"awake_minutes":14,"sleep_deep_minutes":87,"sleep_rem_minutes":99,"sleep_light_minutes":236,"sleep_bedtime":"2025-01-20T22:30:00-07:00","sleep_wake_time":"2025-01-21T06:23:00-07:00","resting_hr_bpm":70,"active_zone_minutes":null,"awakenings":[{"start":"2025-01-21T04:59:00-07:00","minutes":12}],"awakenings_count":1}}
```

Written by `pfc-log-day` (minimal entry) or updated in place by the tour's rating step (`web_write.py rate-day`: energy, mood, focus, and the optional yes/no taps; the `health` object is populated by `automations/scripts/auto_fetch_health.py` on a schedule). Used by `pfc-analyze-trends`.

- `date` — `YYYY-MM-DD`
- `energy`, `focus`, `mood` — 1–5. **These three are the PRIMARY capture** — discrete component readouts beat an integrative "rate your day" guess. `mood` reads the **general sense of well-being across the day as a whole**, not the peak moment; it tends to run higher than the other two, so it's kept but not given outsized weight. It is a real reading, never something to discount.
- `rating` — 1–5, **DERIVED, not asked**: `round(mean(energy, mood, focus))`, computed and stored at write time (so readers like the Trello render and `grep '"rating":5'` keep working). Equal weight across the three.
- **Physiology composite (`mean(energy, focus)`, mood excluded)** — NOT a stored field; computed in `analyze_day_trends.py` as the clean "physiological best self" target for sleep/physiology analysis, since mood measures well-being rather than the body's sleep response. Use the 3-way `rating` for a general headline; use energy+focus for physiology.
- `sick` — boolean variable tracking; add your own boolean/numeric variable fields as needed (they flow into trend analysis).
- `exercised` — `true` | `false` | `null`. Whether the anchor exercise habit happened that day, any time. **Derived** from that habit's completion log — `rate-day` (`pfc_writes.rate_day`) mirrors the habit log into this field; it is not a separate question. `null` if no signal for the day. (Readers also accept a legacy `morning_movement` boolean.)
- `hyperfocused` — `true` | `false` | `null`. Self-report, an optional one-tap in the tour's rating step.
- **No event tagging.** There is no `life_event` field. Events (a great evening, a concert, a milestone) are a normal, frequent part of a life, so excluding those days biases every analysis toward uneventful ones — and since `mood` already reads the day as a whole, a good number on an event day is a real reading. **No day is ever dropped for what happened in it.** What happened goes in `evening_notes`, as description, not as a discount.
- `qqrt` — nested object | `null`. The QQRT sleep composite for the night (Quantity + Quality + Regularity + Timing). **Derived** from `health`, not entered. `null` when the day has no sleep data. Fields:
  - `score` (0–3) — **Quantity + Quality + Timing only** by default.
  - `quantity`/`quality`/`timing` (bool) — the three scored levers.
  - `regularity` (bool), `regularity_stdev_min` (int | null — sleep-midpoint spread in minutes over a trailing 14 nights), `regularity_eligible` (bool — ≥7 nights of data). **Computed but NOT in the score** by default — add it to the score once your own data shows a regular stretch to measure against.
  - `sleep_debt` (object | null) — `{need_hours, nights, avg_shortfall_min, cumulative_hours}` over a trailing 14 nights (≥5 nights). A **companion predictor, not a score lever**: low debt beats high debt at every score rung. `need_hours` defaults to 8.0 — an **operational target**, not a biological-need claim; tune it to the top of your own best-performing sleep range via `/pfc-analyze-trends`.
  - Lever logic lives once in `automations/scripts/qqrt.py`; persisted by `backfill_qqrt.py` and auto-recomputed inside `auto_fetch_health.py` after each nightly fetch (everything looks only at prior nights, so a new night never changes an earlier score). Default bars (tune from your data): Q ≥7h · Quality efficiency ≥97% & deep ≥20% · T bed ≤11 PM · R sleep-midpoint spread ≤60 min over 14 nights (tracked only).
- `notes`, `evening_notes` — free text
- `health` — nested object, all fields auto-fetched from Google Health (`auto_fetch_health.py` / `google_health_backfill.py`); `null` until fetched:
  - `sleep_minutes`, `sleep_hours` — total minutes/hours asleep (the primary overnight sleep period; a separate daytime nap ≥ 3h away is excluded — see continuity below)
  - `awake_minutes` — total wake-after-sleep-onset minutes across the night = awake **within** sessions **plus** awake in the gaps **between** split sessions
  - `awake_intrasession_minutes` — the awake portion recorded *inside* sleep sessions
  - `sleep_awake_gap_minutes` — awake minutes in the gaps *between* the night's sessions; `0` on a single-session night
  - `sleep_sessions` — how many separate sleep logs the device recorded for the night (after nap de-clustering); `1` = continuous
  - `sleep_continuity` — `"fragmented"` if `sleep_awake_gap_minutes ≥ 20`, else `"continuous"`. A fragmented night is a low-rating driver regardless of total hours; the tour's body step reads awake minutes for its broken-night branch.
  - `sleep_deep_minutes`, `sleep_rem_minutes`, `sleep_light_minutes` — stage architecture (all `0` on an unstaged night that reports only `ASLEEP`)
  - `sleep_bedtime`, `sleep_wake_time` — ISO 8601 with timezone offset. Span endpoints of the **primary overnight sleep period**: bedtime = earliest session start, wake_time = latest session end, after dropping any daytime-nap cluster (> 180 min gap). Both `null` if no sleep was recorded.
  - `resting_hr_bpm` — daily resting heart rate, integer BPM
  - `active_zone_minutes` — passive active-zone minutes + logged-exercise minutes combined. Both endpoints paginate: they are read with `api_get_all` (follows `nextPageToken`), because a single unpaginated page silently truncates a busy day's total.
  - `workouts` — array of tracked exercise sessions, ordered by start: `{"type": "ROWING_MACHINE", "name": "Rowing machine", "start": ISO-8601-local, "minutes": int, "azm": int, "avg_hr_bpm": int, "vigorous_minutes": int, "calories": int}`. `vigorous_minutes` = vigorous + peak heart-rate zone time. Reduction lives once in `automations/scripts/exercise_reduce.py`, imported by both fetch and backfill. `[]` on a day with no tracked session; `null` only if the fetch failed.
  - `workout_count`, `workout_minutes`, `workout_azm`, `workout_vigorous_minutes` — day sums over `workouts`
  - **`minutes` / `workout_minutes`, `calories`, and `avg_hr_bpm` come from the watch's session timer and can be unreliable.** A session started on the watch and not stopped runs long, and the inflated duration drags `calories` up and `avg_hr_bpm` down (idle minutes dilute the average). `analyze_day_trends.py` does not use `workout_minutes` as a predictor for this reason; prefer `workout_azm` and `workout_vigorous_minutes`, which only count elevated heart rate.
  - `first_workout_time` — start of the day's first tracked session, ISO 8601 local. The timing variable `active_zone_minutes` cannot express: a 6:30 AM workout and a 12:30 PM workout are otherwise identical in the data.
  - `azm_outside_workouts` — `active_zone_minutes` minus `workout_azm`. **This is not a stress measure.** It holds untracked workouts, walking, yard work, and chores as well as elevated resting heart rate — a day with no tracked session is not evidence of a day with no exercise. Only the `workouts` fields describe deliberate exercise.
  - `awakenings` — array of `{"start": ISO-8601-local, "minutes": int}`, one per real awakening (an AWAKE stage ≥ 4 minutes; shorter ones are micro-arousals and excluded). The **full-night** list is stored unwindowed so analysis can re-window it (e.g. "after 2 AM") without re-fetching. Sleep reduction (awakenings, stage totals, awake-gap accounting) lives once in `automations/scripts/sleep_reduce.py`, imported by both fetch and backfill — single source of truth, no drift. `null` until fetched; `[]` if the night had no qualifying awakening.
  - `awakenings_count` — integer length of `awakenings`; `null` until fetched
  - `hrv_ms` — daily heart-rate variability, average RMSSD in milliseconds. A core recovery/stress signal — lower HRV often precedes a low-rating day.
  - `spo2_avg_pct`, `spo2_lower_pct`, `spo2_upper_pct` — overnight blood-oxygen saturation: average + lower/upper bounds
  - `respiratory_rate_bpm` — overnight breathing rate, breaths per minute; `null` on days with no reading
  - `skin_temp_nightly_c`, `skin_temp_baseline_c` — nightly skin temperature and the rolling baseline, °C. The **deviation** (`nightly − baseline`) is the signal — a spike often precedes feeling off / illness.
  - `vo2max` — estimated VO2max / cardio fitness; `cardio_fitness_level` — the device's banding (`POOR`|`FAIR`|`GOOD`|`VERY_GOOD`|`EXCELLENT`)

  All daily metrics are single values per day, fetched by `fetch_daily_metrics` (in both `google_health_fetch.py` and `google_health_backfill.py` — keep in sync); `null` until fetched or on days the device recorded nothing. Activity totals (steps, distance, calories) are interval-based and live in the raw store (`data/health-raw/`), not here.

  The full unflattened API responses — including per-minute heart rate and intraday HRV/SpO2 — are archived separately in **`data/health-raw/`** (see below).

### `data/health-raw/YYYY-MM-DD.json.gz` — comprehensive raw health archive

One **gzipped** JSON file per local day, holding the full unflattened Google Health API responses for every available data type. This is the raw insurance layer: `day-tracking.ndjson` holds the derived day-level metrics for trend analysis; this store keeps EVERYTHING ELSE so a future analysis is never blocked by what you chose to compute today. Written by `automations/scripts/google_health_raw.py` and, nightly, by `auto_fetch_health.py` (best-effort — a raw failure never blocks the day-tracking commit).

- **One file per local day, rewritten only while the day is still open.** A file captured mid-day is re-fetched by any later run until one lands after local midnight; from then on the day is final and the file is never touched again. Force a rewrite of a finalized day with `--force`.
- **Heart rate is downsampled to 1-minute means** (`heart-rate-1min`: `{t, bpm, n}`). Raw device HR is ~2-second resolution (~11 MB/day ≈ 4 GB/yr) — beyond any realistic analysis need and a fast path to a repo-size problem. **Every other stream is full resolution** (HRV, SpO2, sleep stages, respiratory, steps, distance, energy). Net size ≈ 30 KB/day gzipped.
- **Not NDJSON, not schema-validated** — `scripts/validate.sh` globs `data/*.ndjson` and does not touch this subdir. Read with `gzip.open(path, "rt")` then `json.load`.
- Backfill the in-retention window with `google_health_raw.py --range START END`. Intraday data has a short retention horizon on the provider side, so it must be captured going forward — that's why the nightly job writes it.

### `2-areas/_data/life-wheel.ndjson` and `2-areas/_data/household-status.ndjson`

Periodic snapshots — one record per rating pass. Same shape:

```json
{"date":"2025-01-14","ratings":{"area1":"green","area2":"yellow","area3":"red"},"notes":{"area2":"why yellow","area3":"why red"}}
```

- `date` — `YYYY-MM-DD`
- `ratings` — object keyed by area name, values `"green"` | `"yellow"` | `"red"`
- `notes` — optional object keyed by area name, free text for non-green ratings

For `life-wheel`, area keys come from `2-areas/` folder names. For `household-status`, area keys come from rooms/spaces (Kitchen, Garage, etc.).

### `3-visions/_data/vision-brainstorm.ndjson` — the brainstorm that feeds visions

One record per brainstormed idea — the generative dump upstream of the whole VAVFPTH chain. Each idea carries a lifecycle and a lineage so it can be triaged and promoted. Written via `/pfc-vision-brainstorm` (never hand-authored).

```json
{"id":"vb-20250101-001","text":"Run a marathon","created":"2025-01-01","area":"health","status":"promoted","became":{"type":"vision","ref":"run-a-marathon"},"note":null}
```

- `id` — `vb-YYYYMMDD-NNN`
- `text` — the idea in the user's words
- `created` — `YYYY-MM-DD`
- `area` — a `2-areas/` folder name, or `null` if unclear
- `status` — `raw` (un-acted) · `promoted` (became a vision/project/task/habit) · `done` (already true) · `dropped` (not wanted)
- `became` — `null`, or `{type, ref}` pointing at the vision slug / project id it graduated into
- `note` — optional context

### `data/hypotheses.ndjson`

Ad-hoc experiment log. One record per hypothesis.

Schema enforced by `scripts/validate.sh` against [`config/hypothesis_schema.yaml`](../config/hypothesis_schema.yaml).

**Required fields:** `id` (`hyp-YYYYMMDD-NNN`), `status` (`active` | `resolved-graduated` | `resolved-rejected` | `archived`), `hypothesis` (the claim), `domain` (free-form tag), `started` (YYYY-MM-DD).

**Optional fields:** `confidence` (0.0–1.0, nullable), `last_reviewed` (YYYY-MM-DD, nullable), `updated`, `protocol` (object), `mechanism`, `origin`, `related_hypotheses` (array of hyp ids), `evidence` (array), `notes`. Records are intentionally permissive on free-form fields beyond these — each domain has its own structure.

**Status semantics:**
- `active` — open and surfacing in reviews. Default at capture.
- `resolved-graduated` — supporting data met the graduation bar (see `findings.ndjson` below) and the hypothesis was promoted to a finding. The hypothesis record is retained for history.
- `resolved-rejected` — data disconfirmed; the hypothesis is wrong or the effect is too small to chase.
- `archived` — no longer relevant (lost interest, supplanted by a different model, etc.).

**Confidence semantics.** `confidence` is a 0.0–1.0 belief estimate, **review-driven, not time-driven** — it does NOT auto-decay on a clock. It updates when the user explicitly touches the hypothesis. Confidence drift across reviews is itself signal:
- 0.6 → 0.7 → 0.8 across multiple reviews → graduating organically; consider promoting to a finding via the `source: "experience"` path even without n≥30.
- 0.7 → 0.5 → 0.3 → 0.1 → archive or set `status: "resolved-rejected"`.
- Stuck at one value for many reviews → either you're certain (graduate) or you're not gathering evidence (revisit the protocol).

`null` is allowed and means "not yet set" — captured but never reviewed.

**`last_reviewed` semantics.** Date the hypothesis was last touched in any review. Drives stale-hypothesis surfacing (the `hypotheses-review` rolling-review item). Distinct from `updated`, which changes only when the *content* (protocol, mechanism, evidence) changes — `last_reviewed` updates on every touch even if nothing else changed. `null` means never explicitly reviewed since capture.

### `data/findings.ndjson`

Hard-won, critical insights. Small set, slowly grown. Added rarely.

Schema enforced by `scripts/validate.sh` against `config/finding_schema.yaml`.

**Required fields:** `id` (`finding-YYYYMMDD-NNN`), `status` (`active` | `superseded`), `finding` (one-sentence claim), `domain` (free-form tag), `source` (`data` | `experience` | `hypothesis`), `created` (YYYY-MM-DD).

**Conditional fields:**
- `source_hypothesis_id` — required when `source == "hypothesis"`; points to a record in `hypotheses.ndjson`.
- `superseded_by` — required when `status == "superseded"`; points to the replacement finding.

**Optional fields:** `evidence`, `confidence` (`strong` | `very-strong`), `updated`, `notes`.

**Graduation bar (data-derived findings).** A hypothesis may graduate to a finding when **all three** hold on the supporting data:

- **n ≥ 30** observations (≈ one month of daily tracking)
- **|r| ≥ 0.3** (a medium or larger effect)
- **p < 0.01** (conservative alpha; stricter than the usual 0.05)

Rationale: n=30 stabilizes correlations; |r|≥0.3 filters weak-but-significant noise; p<0.01 guards against false positives from testing many patterns over time.

For `source: "experience"` findings, no statistical test applies — the bar is the user's judgment that the insight is hard-won and critical. `evidence` documents the experiential basis.

**Graduation flow.**
1. A hypothesis in `hypotheses.ndjson` accumulates evidence.
2. When the graduation bar is met, a new finding is written with `source: "hypothesis"` and `source_hypothesis_id` set.
3. The hypothesis record's `status` is updated to `resolved-graduated`. The hypothesis record is retained for history.

### `data/insights.ndjson`

Personal observations, revelations, and noticings captured throughout the week. Lower bar than a finding (no statistical threshold). May graduate into a Project, Action (task), or Habit.

```json
{"id":"insight-20250120-001","status":"active","insight":"Afternoon caffeine correlates with my restless nights — cut off at noon.","area":"health","category":"sleep","source":"chat","created":"2025-01-20","graduated_to":null,"graduated_date":null,"notes":null}
```

Schema enforced by `scripts/validate.sh` against [`config/insight_schema.yaml`](../config/insight_schema.yaml).

**Required fields:** `id` (`insight-YYYYMMDD-NNN`), `status` (`active` | `archived` | `graduated`), `insight` (text), `source` (`chat` | `evening-checkin` | `journal` | `experience` | `rolling-review`; `evening-checkin` is a historical value), `created` (YYYY-MM-DD).

**Conditional fields:**
- `graduated_to` — required when `status == "graduated"`. The id of the resulting task, project, or habit.
- `graduated_date` — required when `status == "graduated"`.

**Optional fields:** `area` (must match a folder in `2-areas/` if present), `category` (free-form tag), `notes`.

**Lifecycle.** Captured via `/pfc-add-insight`. Reviewed via the `insights-review` rolling review (monthly cadence, last 30 days) or on demand via `/pfc-insights`. Each insight is either kept active, archived, or graduated to a task/project/habit. Graduation does not delete the insight — the record is preserved with status updated.

### `data/grounding.ndjson` — Front-of-Mind anchors

A small, **cycling** set of "keep this front-of-mind right now" anchors — the most important things to stay grounded in. Distinct from insights (a noticing to triage) and findings (a proven conclusion): this is a curated, present-tense reminder set that surfaces on the Trello `🧠 Front of Mind` list. It holds *frameworks* to stay grounded in, not mantras to recite.

**One card per TOPIC, not per bullet.** Each record is a front-of-mind *theme* — `title` is the Trello card name, `body` holds the points (multi-line, bulleted). A heavy topic is a single card with its points in the description, so the life-wide list stays scannable.

```json
{"id":"ground-20250127-001","title":"Big launch month — protect the mornings","body":"• Deep work before email\n• One commitment per evening, max\n• Say no by default until the launch ships","area":"career","status":"active","created":"2025-01-27","retired_date":null,"notes":null}
```

**Required fields:** `id` (`ground-YYYYMMDD-NNN`), `title` (card name), `status` (`active` | `retired`), `created` (YYYY-MM-DD).

**Optional fields:** `body` (card description — the points), `area` (must match a folder in `2-areas/` if present), `retired_date` (required when `status == "retired"`), `notes`.

**Soft cap:** 10 active **topic cards** (`GROUNDING_CAP` in `automations/scripts/trello_render.py`). The renderer renders all active cards but logs a 🟡 warning when over cap — curate by retiring (set `status: "retired"`, `retired_date`), never by silent truncation.

### `4-focus/_data/focus.ndjson` — Current Focus layer

One record per active or retired focus — the capped, traffic-lit set of what's being actively pursued **this quarter** (Area → Vision → **Focus** → Habit). See [`docs/system-map.md`](system-map.md). Managed by `/pfc-focus`; rendered to the `🎯 Current Focus` Trello list.

Fields: `id` (`focus-YYYYMMDD-NNN`), `tier` (`foundation`|`pursuit`|`consuming`), `area` (matches a `2-areas/` folder — the backbone), `title`, `medium` (`book`|`podcast`|`audiobook` for consuming, else null), `link` (`{type: vision|habit|project, ref}` — nearest real parent, or null), `habits` (ordered habit ids — the vehicles), `impact` / `urgency` (`high`|`medium`|`low`), `status` (`green`|`yellow`|`red` — **derived**), `parked` (bool), `quarter` (`YYYY-QN`), `landing` (anchor-first when/where/trigger, or null), `created`, `retired_date`, `notes`.

**`habits` — the vehicle link.** An ordered array of habit ids from `config/habit_schema.yaml`. The **first entry is primary and drives the traffic light**; later entries are supporting and are displayed but do not set the headline. Required for `foundation` and `pursuit` (validated); `consuming` is exempt — a podcast is not a rep. This is a **downward** link, distinct from `link`, which points one hop **up** to the nearest real parent. Both may be set. A focus with no vehicle is unmeasurable, which is why the validator fails on it.

**`status` is DERIVED, never hand-typed.** `automations/scripts/focus_status.py` computes it from the primary vehicle's trailing-28-day completion rate — 🟢 ≥70% · 🟡 40–69% · 🔴 <40% — and `--write` stamps it back into the file so non-Python readers stay correct. The window for a habit never starts before that habit's `started` date.

**`red` vs `parked`.** `status: red` means **not happening**, and a red pursuit still occupies a pursuit slot. A deliberate stop is `parked: true`, which renders 🅿️, frees a slot, and is exempt from the two-red-weeks forcing function.

**`impact` / `urgency`** use the same `high|medium|low` enum as tasks and render as a two-letter code with impact first (A=high, B=medium, C=low): `AA` … `CC`. Trello focus card titles lead with the code so an alphabetical sort surfaces the most important focuses first. The ranking is a tie-breaker on short days, not a hit list.

**Tiers + caps** (`config/focus.yaml`): 🧱 Foundations (soft ~4), 🎯 Active Pursuits (**hard cap 6**), 🎧 Currently Consuming (book 1 · podcast 3 · audiobook 1). Caps are soft-enforced at render (warn 🟡, never truncate — curate by parking or retiring). Canonical schema: [`config/focus_schema.yaml`](../config/focus_schema.yaml). Validated by `scripts/validate.sh` (schema + id format, area cross-ref, every non-consuming focus declares ≥1 vehicle habit, vehicle ids resolve against `config/habit_schema.yaml`, impact/urgency enums, pursuit cap ≤6 counting unparked pursuits, future-date guard).

### `data/review-ledger.ndjson` — Rolling Reviews ledger

One record per review item — the weekly/monthly/quarterly review work that used to live in separate batch check-in rituals, now surfaced one at a time instead of batched into standalone events. Managed by the home page tour (at most 1 due item, stamped on tap through `web_write.py stamp-review`) and `/pfc-review` (catch up on everything due at once).

Fields: `id` (stable slug mapped to a gate in `pfc-review`, e.g. `stale-task-triage`), `label` (human-readable name), `tier` (`weekly`|`monthly`|`quarterly`), `cadence_days` (minimum days between surfacings — 7/30/90 respectively), `weekday_hint` (optional `0`=Mon..`6`=Sun soft ordering preference, or `null`), `last_done` (`YYYY-MM-DD` it was last surfaced-and-engaged; seeded with a far-past sentinel like `2000-01-01` meaning "never").

**Due/gate/cap model:** an item is a *candidate* once `today − last_done ≥ cadence_days`. Candidates are then filtered through a per-id **gate** — a small check (in `pfc-review` Step 1) that returns a reason string only if there's genuinely something to act on (e.g. `tasks-missing-area` gates on an open task with no area); a due-but-empty-gate item silently passes without stamping and re-checks next time. `/pfc-review` surfaces every gated candidate at once, tier-ordered. The tour shows at most 1 due item and uses cadence only, no gate (`_due_review` in `home_data.py`). Only items the user actually engages get `last_done` stamped to today; ignored items are left alone and re-surface on cadence. Seeded with items spanning all three tiers (stale-task triage, missing-area/values checks, focus accuracy, vision relevance, habit rates, day-trend peek, hypotheses review, life wheel, household status, project progress, vision activation, monthly habits, insights review, findings alignment, trend analysis, revive outcomes, usage audit, quarterly focus re-pick, vision brainstorm, strengths refresh).

Canonical schema: [`config/review_ledger_schema.yaml`](../config/review_ledger_schema.yaml). Validated by `scripts/validate.sh` (schema conformance, unique ids, no future `last_done`).

### `data/supplements.ndjson`

Baseline registry of daily supplements and medications — items taken every single day, consistently. Governs `pfc-analyze-trends` supplement joins.

```json
{"id":"supp-20250118-001","status":"active","name":"Vitamin D","type":"supplement","dose":"1000 IU","times":["morning"],"food_requirement":"with_fat","purpose":"baseline","started":"2025-01-18","stopped":null,"stopped_reason":null,"notes":null}
```

Canonical schema: [`config/supplement_schema.yaml`](../config/supplement_schema.yaml). Validated by `scripts/validate.sh`.

**Model:** one record per supplement per dose era. A dose change is represented as stopping the old record (`status: "stopped"`, `stopped: YYYY-MM-DD`) and appending a new active record. The active record for a given name on date `D` satisfies `started <= D AND (stopped is null OR stopped > D)` — `started` is inclusive, `stopped` is exclusive.

Fields:
- `id` — `supp-YYYYMMDD-NNN`
- `status` — `"active"` | `"stopped"`
- `name` — human-readable
- `type` — `"supplement"` | `"medication"`
- `dose` — free text (`"1000 IU"`, `"1 tablet"`, etc.)
- `times` — non-empty array from `["morning", "afternoon", "evening", "bedtime", "with meals"]`
- `food_requirement` — `"empty_stomach"` | `"with_food"` | `"with_fat"` | `"either"` | `null`. Metadata about HOW to take the compound, not part of the dated dose record — the **one field** that may be edited in place (no stop+add) via `/pfc-supplement` assess intent. `null` = not yet assessed.
- `purpose` — optional free text
- `started` — `YYYY-MM-DD`
- `stopped` — `YYYY-MM-DD` when stopped, `null` while active; must be `>= started`. May be future-dated to schedule a planned stop.
- `stopped_reason` — optional brief reason, `null` while active
- `notes` — optional free text

### `data/revive-events.ndjson` — append-only revive-watchlist event log

Records every revive intervention applied via `/pfc-revive` so the slippage detector can dedupe recently-handled items and the `revive-outcomes` rolling review can roll forward outcomes.

```json
{"id":"revive-20250117-001","date":"2025-01-17","subject_type":"task","subject_id":"task-20250101-006","reason":"open >30d, no activity 12d","intervention":"break-down","outcome":null,"outcome_date":null,"notes":null}
```

Canonical schema: [`config/revive_event_schema.yaml`](../config/revive_event_schema.yaml). Validated by `scripts/validate.sh`. Read by `automations/scripts/revive_watchlist.py` (slippage detector) and `/pfc-revive` itself. Outcome rows are updated in place (`revived` / `still-stuck` / `exited`) during the `revive-outcomes` review pass.

### `data/calendar-cache.json` — durable Calendar snapshot for TRMNL

A single JSON object, overwritten in place by `pfc-render-trello` Step 1 right after it fetches events via MCP. The daily sync job (`scripts/daily-sync.sh`) runs that step every morning and commits only this file (`track: refresh calendar cache`); any full `/pfc-render-trello` writes it too:

```json
{"fetched_at": "2025-01-26T20:15:00-07:00", "events": [{"summary": "…", "start": {"dateTime": "…"}, "recurringEventId": "…"}]}
```

Read by `build_pfc_week` in `automations/scripts/trmnl_push.py` — the TRMNL `pfc-week` builder has no MCP access, so this committed file is its only data source, and it must be committed + pushed to reach the VPS. The builder shows a stale flag when `fetched_at` is older than ~26 hours.

## Config files

- [`config/task_schema.yaml`](../config/task_schema.yaml) — task record schema (enforced by `scripts/validate.sh`)
- [`config/project_schema.yaml`](../config/project_schema.yaml) — project record schema
- `config/habit_schema.yaml` — habit definitions + `area` mapping (enforced by validator)
- [`config/finding_schema.yaml`](../config/finding_schema.yaml) — finding record schema (enforced by `scripts/validate.sh`)
- [`config/insight_schema.yaml`](../config/insight_schema.yaml) — insight record schema (enforced by `scripts/validate.sh`)
- [`config/supplement_schema.yaml`](../config/supplement_schema.yaml) — supplement record schema (enforced by `scripts/validate.sh`)
- [`config/revive_event_schema.yaml`](../config/revive_event_schema.yaml) — revive-watchlist event schema (enforced by `scripts/validate.sh`)
- [`config/grounding_schema.yaml`](../config/grounding_schema.yaml) — Front-of-Mind anchor schema (enforced by `scripts/validate.sh`)
- [`config/focus_schema.yaml`](../config/focus_schema.yaml) — Current Focus record schema (enforced by `scripts/validate.sh`)
- [`config/focus.yaml`](../config/focus.yaml) — Current Focus tier labels + caps (🧱 Foundations soft ~4 · 🎯 Active Pursuits hard 6 · 🎧 Currently Consuming per-medium); read by `automations/scripts/trello_render.py` and `/pfc-focus`
- [`config/review_ledger_schema.yaml`](../config/review_ledger_schema.yaml) — Rolling Reviews ledger record schema (enforced by `scripts/validate.sh`)
- [`config/onboarding_schema.yaml`](../config/onboarding_schema.yaml) — schema for the append-only onboarding event log at `config/onboarding.ndjson` (one record per `{feature, status, date}` event, where `status` is `introduced`/`tried`/`dismissed`; most-recent event wins). Enforced by `scripts/validate.sh`. Drives the `/pfc-onboarding` skill's feature-coverage tracking.
- `config/automation_config.yaml` — thresholds and schedule settings; `task_archive_threshold` mirrors the 200-line rule referenced in `AGENTS.md`
- `config/persona.yaml` — single field `active: <persona-id>` (or `none`). Selects the assistant's voice overlay. Switched via `/pfc-persona`. Validator confirms `active` resolves to a section in `personas.md`.
- `config/personas.md` — registry of available personas. Each persona is a `## <id>` markdown section with **Vibe**, **Voice rules**, and **Sample**. Injected at session start by `scripts/hook-session-date.sh`.
- `config/trello_calendar_filters.yaml` — title-substring and calendar-name patterns to exclude from the dashboard's `🗓️ Week at a Glance` list. Read by `automations/scripts/trello_render.py` during the `pfc-render-trello` workflow. Tuned by inspection.

**Auth artifacts (gitignored, not part of the data model):**
- `config/google_health_tokens.json` — OAuth tokens for the Google Health connector. Local-only, never committed. Refreshed by `automations/scripts/google_health_auth.py`.

## Query patterns (use jq, not grep)

```bash
# Open tasks
jq -c 'select(.status == "open")' 6-tasks/_data/tasks.ndjson

# Tasks by project
jq -c 'select(.project == "proj-20250101-002" and .status == "open")' 6-tasks/_data/tasks.ndjson

# Count open tasks
jq -c 'select(.status == "open")' 6-tasks/_data/tasks.ndjson | wc -l
```

## Write patterns (always jq, never echo/sed)

```bash
# Append
jq -cn --arg id "task-YYYYMMDD-NNN" --arg desc "…" \
  '{id:$id, status:"open", description:$desc, created:"YYYY-MM-DD"}' \
  >> 6-tasks/_data/tasks.ndjson

# Update in place
jq -c 'if .id == "task-YYYYMMDD-NNN" then . + {status:"done", completed:"YYYY-MM-DD"} else . end' \
  6-tasks/_data/tasks.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 6-tasks/_data/tasks.ndjson

# Archive done tasks
jq -c 'select(.status == "done")' 6-tasks/_data/tasks.ndjson >> 6-tasks/_data/tasks-archive.ndjson
jq -c 'select(.status != "done")' 6-tasks/_data/tasks.ndjson > data/.tasks.tmp && mv data/.tasks.tmp 6-tasks/_data/tasks.ndjson
```
