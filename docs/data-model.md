# Data Model

Canonical reference for data files in `data/` and their schemas. Keep this in sync with `config/*_schema.yaml` and the actual records on disk — if this doc drifts, fix the doc.

**All NDJSON writes must go through `jq`.** Never use `echo >>`, `sed`, or string concatenation. See [conventions.md](conventions.md) for the exact patterns.

## Formats

| Format | Use case |
|---|---|
| Markdown | Values, area statements, project plans, notes, reports |
| NDJSON | Tasks, habits, day tracking, focus, projects, events |
| YAML | Schemas, configuration, automation settings |
| Generated | Dashboards, charts, reports (reproducible from source) |

## NDJSON files

### `5-actions/_data/tasks.ndjson` — canonical task storage

```json
{"id":"task-20260412-001","status":"open","description":"…","size":"S","location":"PC","impact":"high","urgency":"medium","project":"proj-20260412-002","deadline":"2026-05-01","created":"2026-04-12","source":"morning-planning","notes":"optional free text"}
```

Required: `id`, `status`, `description`, `created`. Canonical schema: [`config/task_schema.yaml`](../config/task_schema.yaml).

- `id` — `task-YYYYMMDD-NNN`
- `status` — `"open"` | `"done"`
- `size` — `"XS"` | `"S"` | `"M"` | `"L"` | `"XL"`
- `location` — `"Home"` | `"PC"` | `"Errand"` | `"Phone"` | `"Anywhere"`
- `impact`, `urgency` — `"low"` | `"medium"` | `"high"`
- `project` — project `id` (e.g. `proj-20260412-002`) or `"none"`. Never `null`.
- `deadline`, `created`, `completed` — `YYYY-MM-DD`
- `source` — where the task was captured (`morning-planning`, `phone`, `email-triage`, etc.)
- `notes` — optional free text
- `area` — optional; lowercase, must match a folder in `2-areas/`. Used for standalone strategic tasks with no project (see [CLAUDE.md](../CLAUDE.md) values-alignment section).
- `depends_on` — optional array of task IDs (`["task-20260422-004", ...]`). The task is considered "blocked" until every listed task has `status == "done"`. `pfc-pick-tasks` hides blocked tasks from suggestions; `scripts/validate.sh` checks each ID resolves and rejects self-references.
- `sequence` — optional 1-based integer. Used on project tasks where order matters (course curricula, ordered method books). `pfc-pick-tasks` and `pfc-morning-checkin` only surface the lowest-sequence open task per project — higher-sequence siblings stay hidden until the prior is done. Standalone tasks (`project: "none"`) leave this null.

### `5-actions/_data/tasks-archive.ndjson`

Same shape as `tasks.ndjson`. Done tasks are moved here at weekly check-in (or when live file exceeds ~200 lines).

### `5-actions/_data/task_events.ndjson` — append-only audit log

```json
{"task_id":"task-20260412-001","event":"created","timestamp":"2026-04-12","source":"morning-planning"}
{"task_id":"task-20260412-001","event":"completed","timestamp":"2026-04-13","note":"low energy after lunch"}
```

- `task_id` — required, matches a task id (may be `null` only for cross-cutting corrections)
- `event` — `"created"` | `"completed"` | `"updated"` | `"archived"`
- `timestamp` — `YYYY-MM-DD`
- `note` — optional free text
- `event_id` — optional `evt-YYYYMMDD-NNN` for the event record itself
- `source` — optional origin

### `4-projects/_data/projects.ndjson`

Registry of short-term projects (max 3 active — see [CLAUDE.md](../CLAUDE.md)).

```json
{"id":"proj-20260412-002","name":"Side Project: Build X","active":true,"excitement":"high","impact":"high","urgency":"high","estimated_months":2,"area":"career","values":["Growth","Learning"],"total_parts":8,"completed_parts":1,"created":"2026-04-12","deadline":"2026-06-04"}
```

Canonical schema: [`config/project_schema.yaml`](../config/project_schema.yaml). Completion % = `completed_parts / total_parts`.

Fields:
- `id` — `proj-YYYYMMDD-NNN`
- `name`, `description`, `goal` — human-readable project context
- `active` — boolean; max 3 active at a time
- `status` — optional lifecycle tag (e.g. `"planned"`, `"in-progress"`, `"paused"`)
- `excitement`, `impact`, `urgency` — `"low"` | `"medium"` | `"high"` (per schema)
- `estimated_months` — optional, 1–3 typical
- `area` — lowercase, must match a folder in `2-areas/`
- `values` — array of values from `1-values/values.md`
- `total_parts`, `completed_parts` — numeric; drive completion %
- `gate` — optional blocker/precondition note
- `priority_order` — optional ordered array of sub-parts
- `created`, `deadline`, `completed` — `YYYY-MM-DD`

### `5-actions/_data/daily-focus.ndjson` — 2+1 morning picks

```json
{"date":"2026-04-16","critical":["task-20260412-002","task-20260415-003"],"bonus":"task-20260412-017","completed":[],"bonus_completed":false,"calendar_events":{"task-20260412-002":{"event_id":"…","start":"2026-04-16T13:30:00Z","end":"2026-04-16T13:45:00Z"}}}
```

- `date` — `YYYY-MM-DD`
- `critical` — array of exactly 2 task ids (strings; must exist in `tasks.ndjson` or `tasks-archive.ndjson`)
- `bonus` — optional task id string (same existence rule)
- `completed` — array of task ids from `critical` that were finished
- `bonus_completed` — boolean
- `calendar_events` — optional object written by `pfc-schedule-focus`; keyed by task id, each value has `event_id`, `start`, `end` (ISO timestamps). Enables bidirectional sync with Google Calendar.

### `6-habits/_data/habits-daily.ndjson`

```json
{"habit_id":"morning-walk","date":"2026-04-24","completed":true,"source":"manual","logged_at":"2026-04-24T07:30:00Z"}
{"habit_id":"read-15-min","date":"2026-04-15","completed":true,"source":"manual","logged_at":"2026-04-15T22:00:00Z"}
{"habit_id":"sleep-on-time","date":"2026-04-21","completed":false,"skipped":true,"skip_reason":"travel day","source":"evening-checkin"}
```

- `habit_id` — must match an `id` in `config/habit_schema.yaml` (active) or `deprecated_habits` (historical only)
- `completed` — boolean; did the habit happen that day
- `source` — `"google_health_auto"` | `"manual"` | `"wearable"` | `"evening-checkin"` | `"morning-checkin"` | `"chat"`
- `value` — optional measurement (e.g. AZM count, bedtime)
- `skipped` — optional boolean; `true` means the day was structurally unavailable (e.g. travel for a connection-time habit, travel, illness). A skipped day is **not a miss** — weekly-review math excludes it from both numerator and denominator: `rate = completed / max(1, target_frequency - skipped_count)`.
- `skip_reason` — optional free-text string; required when `skipped: true`. Short, human-readable (e.g. "travel day", "travel").

When `skipped: true`, `completed` must be `false`. The fields coexist so queries that only filter on `completed == true` keep working unchanged; skip-aware consumers (weekly check-in, trend analysis) read both.

### `6-habits/_data/habits-monthly.ndjson`

Same shape as daily; `date` may be the first of the month. Currently unused (no monthly habits active).

### `data/day-tracking.ndjson` — day tracker

```json
{"date":"2026-04-15","rating":4,"caffeine_mg":200,"sick":false,"energy":4,"focus":4,"mood":"good","evening_notes":"…","sleep_hours":7.2,"active_zone_minutes":34,"resting_hr":58,"health":"green","notes":"ad-hoc observations","logged_at":"2026-04-15T22:00:00Z"}
```

Written by `pfc-log-day` (minimal entry) or updated in place by `pfc-evening-checkin` (full entry with health data auto-fetched from Google Health). Used by `pfc-analyze-trends`.

- `date` — `YYYY-MM-DD`
- `rating`, `energy`, `focus` — 1–5
- `mood` — short label (`"good"`, `"low"`, etc.)
- `caffeine_mg`, `sick` — example custom variables (supplement tracking was previously here but is now in `supplements.ndjson`)
- `morning_movement` — *example custom field* (`true` | `false` | `null`). Track a morning-routine habit (e.g. movement, meditation) within 30 min of waking. Add your own custom fields like this; the schema is open.
- `sleep_hours`, `active_zone_minutes`, `resting_hr` — auto-fetched health
- `health` — optional red/yellow/green tag
- `evening_notes`, `notes` — free text
- `logged_at` — ISO timestamp of the write (optional)

### `2-areas/_data/life-wheel.ndjson` and `2-areas/_data/household-status.ndjson`

Periodic snapshots — one record per monthly check-in. Same shape:

```json
{"date":"2026-04-14","ratings":{"area1":"green","area2":"yellow","area3":"red"},"notes":{"area2":"why yellow","area3":"why red"}}
```

- `date` — `YYYY-MM-DD`
- `ratings` — object keyed by area name, values `"green"` | `"yellow"` | `"red"`
- `notes` — optional object keyed by area name, free text for non-green ratings

For `life-wheel`, area keys come from `2-areas/` folder names. For `household-status`, area keys come from rooms/spaces (Kitchen, Garage, etc.).

### `data/hypotheses.ndjson`

Ad-hoc experiment log. One record per hypothesis.

Schema enforced by `scripts/validate.sh` against [`config/hypothesis_schema.yaml`](../config/hypothesis_schema.yaml).

**Required fields:** `id` (`hyp-YYYYMMDD-NNN`), `status` (`active` | `resolved-graduated` | `resolved-rejected` | `archived`), `hypothesis` (the claim), `domain` (free-form tag), `started` (YYYY-MM-DD).

**Optional fields:** `confidence` (0.0–1.0, nullable), `last_reviewed` (YYYY-MM-DD, nullable), `updated`, `protocol` (object), `mechanism`, `origin`, `related_hypotheses` (array of hyp ids), `evidence` (array), `notes`. Records are intentionally permissive on free-form fields beyond these — each domain has its own structure (dose-response curves, tracking protocols, mechanism notes).

**Status semantics:**
- `active` — open and surfacing in reviews. Default at capture.
- `resolved-graduated` — supporting data met the graduation bar (see `findings.ndjson` below) and the hypothesis was promoted to a finding. The hypothesis record is retained for history.
- `resolved-rejected` — data disconfirmed; the hypothesis is wrong or the effect is too small to chase.
- `archived` — no longer relevant (lost interest, supplanted by a different model, etc.).

**Confidence semantics.** `confidence` is a 0.0–1.0 belief estimate, **review-driven, not time-driven** — it does NOT auto-decay on a clock. It updates when the user explicitly touches the hypothesis during the weekly check-in touch pass. Confidence drift across reviews is itself signal:
- 0.6 → 0.7 → 0.8 across multiple reviews → graduating organically; consider promoting to a finding via the `source: "experience"` path even without n≥30.
- 0.7 → 0.5 → 0.3 → 0.1 → archive or set `status: "resolved-rejected"`.
- Stuck at one value for many reviews → either you're certain (graduate) or you're not gathering evidence (revisit the protocol).

`null` is allowed and means "not yet set" — captured but never reviewed. Backfilled records start with `confidence: null` and get a value on the first weekly-review touch.

**`last_reviewed` semantics.** Date the hypothesis was last touched in any review (weekly check-in touch pass, ad-hoc check). Drives stale-hypothesis surfacing in `/pfc-system-health` and the weekly check-in touch pass. Distinct from `updated`, which changes only when the *content* (protocol, mechanism, evidence) changes — `last_reviewed` updates on every touch even if nothing else changed. `null` means never explicitly reviewed since capture.

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
- **|r| ≥ 0.3** (Cohen's "medium" or larger effect)
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
{"id":"insight-20260420-001","status":"active","insight":"When you can't fall back asleep, avoid checking devices — use a quiet reset technique instead.","area":"health","category":"sleep","source":"evening-checkin","created":"2026-04-20","graduated_to":null,"graduated_date":null,"notes":null}
```

Schema enforced by `scripts/validate.sh` against [`config/insight_schema.yaml`](../config/insight_schema.yaml).

**Required fields:** `id` (`insight-YYYYMMDD-NNN`), `status` (`active` | `archived` | `graduated`), `insight` (text), `source` (`chat` | `evening-checkin` | `morning` | `weekly-review` | `journal` | `experience`), `created` (YYYY-MM-DD).

**Conditional fields:**
- `graduated_to` — required when `status == "graduated"`. The id of the resulting task, project, or habit (`task-...`, `proj-...`, or a habit_id from `habit_schema.yaml`).
- `graduated_date` — required when `status == "graduated"`.

**Optional fields:** `area` (must match a folder in `2-areas/` if present), `category` (free-form tag), `notes`.

**Lifecycle.** Captured via `/pfc-add-insight`. Reviewed during weekly check-in (last 7 days), monthly cadence (last 30 days), or on demand via `/pfc-insights`. Each insight is either kept active, archived (no longer relevant), or graduated to a task/project/habit. Graduation does not delete the insight — the record is preserved with status updated.

### `data/supplements.ndjson`

Baseline registry of daily supplements and medications — items taken every single day, consistently. Governs `pfc-analyze-trends` supplement joins.

```json
{"id":"supp-20260418-001","status":"active","name":"Vitamin D","type":"supplement","dose":"5000 IU","times":["morning"],"purpose":"bone health / immune support","started":"2026-04-18","stopped":null,"notes":null}
```

Canonical schema: [`config/supplement_schema.yaml`](../config/supplement_schema.yaml). Validated by `scripts/validate.sh`.

**Model:** one record per supplement per dose era. A dose change is represented as stopping the old record (`status: "stopped"`, `stopped: YYYY-MM-DD`) and appending a new active record. The active record for a given name on date `D` satisfies `started <= D AND (stopped is null OR stopped > D)` — `started` is inclusive, `stopped` is exclusive.

Fields:
- `id` — `supp-YYYYMMDD-NNN`
- `status` — `"active"` | `"stopped"`
- `name` — human-readable
- `type` — `"supplement"` | `"medication"`
- `dose` — free text (`"2000 IU"`, `"5000 IU"`, `"1 tablet"`, etc.)
- `times` — non-empty array from `["morning", "afternoon", "evening", "bedtime", "with meals"]`
- `purpose` — optional free text
- `started` — `YYYY-MM-DD`
- `stopped` — `YYYY-MM-DD` when stopped, `null` while active; must be `>= started`
- `notes` — optional free text


## Config files

- [`config/task_schema.yaml`](../config/task_schema.yaml) — task record schema (enforced by `scripts/validate.sh`)
- [`config/project_schema.yaml`](../config/project_schema.yaml) — project record schema
- `config/habit_schema.yaml` — habit definitions + `area` mapping (enforced by validator)
- [`config/finding_schema.yaml`](../config/finding_schema.yaml) — finding record schema (enforced by `scripts/validate.sh`)
- [`config/insight_schema.yaml`](../config/insight_schema.yaml) — insight record schema (enforced by `scripts/validate.sh`)
- [`config/supplement_schema.yaml`](../config/supplement_schema.yaml) — supplement record schema (enforced by `scripts/validate.sh`)
- `config/automation_config.yaml` — thresholds and (future) schedule settings; `task_archive_threshold` mirrors the 200-line rule referenced in CLAUDE.md
- `config/persona.yaml` — single field `active: <persona-id>` (or `none`). Selects the assistant's voice overlay. Switched via `/pfc-persona`. Validator confirms `active` resolves to a section in `personas.md`.
- `config/personas.md` — registry of available personas. Each persona is a `## <id>` markdown section with **Vibe**, **Voice rules**, and **Sample**. Injected at session start by `scripts/hook-session-date.sh`.
- `config/trello_calendar_filters.yaml` — title-substring and calendar-name patterns to exclude from the dashboard's `🗓️ Week at a Glance` list. Read by `automations/scripts/trello_render.py` during the `pfc-render-trello` workflow. Tuned by inspection.

**Auth artifacts (gitignored, not part of the data model):**
- `config/google_health_tokens.json` — OAuth tokens for the Google Health connector. Local-only, never committed. Refreshed by `automations/scripts/google_health_auth.py`.

## Query patterns (use jq, not grep)

```bash
# Open tasks
jq -c 'select(.status == "open")' 5-actions/_data/tasks.ndjson

# Tasks by project
jq -c 'select(.project == "proj-20260412-002" and .status == "open")' 5-actions/_data/tasks.ndjson

# Count open tasks
jq -c 'select(.status == "open")' 5-actions/_data/tasks.ndjson | wc -l
```

## Write patterns (always jq, never echo/sed)

```bash
# Append
jq -cn --arg id "task-YYYYMMDD-NNN" --arg desc "…" \
  '{id:$id, status:"open", description:$desc, created:"YYYY-MM-DD"}' \
  >> 5-actions/_data/tasks.ndjson

# Update in place
jq -c 'if .id == "task-YYYYMMDD-NNN" then . + {status:"done", completed:"YYYY-MM-DD"} else . end' \
  5-actions/_data/tasks.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 5-actions/_data/tasks.ndjson

# Archive done tasks
jq -c 'select(.status == "done")' 5-actions/_data/tasks.ndjson >> 5-actions/_data/tasks-archive.ndjson
jq -c 'select(.status != "done")' 5-actions/_data/tasks.ndjson > data/.tasks.tmp && mv data/.tasks.tmp 5-actions/_data/tasks.ndjson
```
