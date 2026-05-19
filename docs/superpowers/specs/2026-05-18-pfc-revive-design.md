# pfc-revive — design spec

**Date:** 2026-05-18
**Status:** Approved design, pending implementation plan
**Author:** Brainstorming session (user + Claude)

## Purpose

`pfc-revive` is a project/action **slippage** intervention skill. The system continuously generates evidence that work is losing momentum (open tasks aging out, projects with no recent activity, items repeatedly carried forward in the daily 2+1 without completion). Today that evidence is implicit — it sits in the data but nothing surfaces it as a prompt to *do something*. `pfc-revive` makes the slippage visible, diagnoses *why* a given item slipped, and brainstorms a tailored intervention with the user.

It is **distinct from `pfc-stuck`**, which handles human body-state stuck (frozen, locked-in, foggy, tired). `pfc-stuck` works on the person; `pfc-revive` works on the work.

Interventions draw on established motivation and ADHD frameworks (initiation deficit, implementation intentions, habit stacking, delay discounting, behavioral activation, honest exit). The skill **names** the framework next to each option so the user recognizes what they're drawing on; it does **not** synthesize or explain the science (per the user's "no LLM-synthesized knowledge" rule).

## Trigger signals

A "watchlist item" is any task or project that matches at least one of the following signals on the day of check.

| ID | Signal | Threshold | Scope |
|---|---|---|---|
| A | Active project velocity 🔴 | `>7` days late vs `deadline` (existing CLAUDE.md velocity calc) | `active==true` only |
| B | Active project at 0 completed parts since `started` | `≥14` days | `active==true` only |
| C | Open task age | `≥30` days since `created` | standalone + project tasks |
| D | High-impact open task age | `≥7` days since `created` AND `impact=="high"` | standalone + project tasks |
| E | Same task carried in 2+1 without completion | appeared in `5-actions/_data/daily-focus.ndjson` (any of `critical`/`bonus`/`project`) on `≥3` distinct days, status still `open` | once per task (no re-trigger nag) |
| F | Active project with no `task_event` activity | no `task_events.ndjson` row referencing any task with `project==<id>` for `≥10` days | `active==true` only |

**Hierarchy rule:** if a task surfaces via C/D **and** its parent project surfaces via A/B/F, list it once under the project, not twice. The user reasons about the project's slip; the task is shown as a sub-bullet for context.

**Active-only constraint** for A, B, F is intentional. Projects with `active==false` are paused-but-detailed by design; surfacing them as slips would generate noise on work the user has consciously deprioritized.

**E fires once per task.** Once a task is logged as a revive event with signal E, it is suppressed from future E checks regardless of subsequent carry-forwards, until the task is either completed or cancelled. This prevents nagging on the same task every morning.

## Surfacing

| Surface | Behavior |
|---|---|
| **Morning check-in** (`pfc-morning-checkin`) | After 2+1 is set, append a `🔁 Revive watchlist` block: numbered list of slipped items + signal. Prompt: "Walk any of these now? (1, 2, …, all, none)". Defaults to skip if user just answers focus questions. Cheap glance, opt-in walk. |
| **Weekly check-in** (`pfc-weekly-checkin`) | Dedicated section after stale-task triage. Walks every watchlist item one-by-one. Higher bandwidth surface. |
| **Standalone** (`/pfc-revive`) | Always available. Walks the full watchlist. Same flow as weekly. |

**Skip cooldown.** When the user picks `skip` on an item during a walk, that item is suppressed from the watchlist for `7` days. After the cooldown, if the signal still holds, the item re-fires. This prevents nag fatigue while keeping unresolved slippage visible over time.

**Surfaces explicitly excluded:**
- Evening check-in (already heavy).
- `/pfc-daily-summary` (would duplicate morning).
- Post-commit auto-notification (slippage is a slow-burn signal, not a moment-in-time alert; noise rejected).

**Letter-space disambiguation.** Signals (A–F) and diagnostic answers (A–G) use overlapping letters but are independent label sets. In the data model they live in separate fields (`signals` vs `diagnostic`) so there is no ambiguity in storage. In chat output, always render diagnostic answers with their label (e.g. `A — Too big`) rather than the bare letter.

## Walk flow (per item)

```
1. Show
     <item title>
       └ Signal: <which trigger fired + concrete data, e.g. "open 47 days, high-impact">
       └ Project (if applicable): <name> · velocity: 🔴/🟡/🟢

2. Ask — diagnostic (multi-select A–G)
     "What's the actual block?"
       A — Too big / activation energy too high       [Initiation deficit]
       B — Wrong time or context                      [Implementation intention]
       C — Missing prereq or dependency               [Dependency mapping]
       D — Out of sight / kept forgetting             [Salience]
       E — Reward too distant / no payoff in sight    [Delay discounting]
       F — Aversive / feels bad                       [Behavioral activation]
       G — Not actually important anymore             [Honest exit]

3. Brainstorm
     Agent proposes a tailored intervention drawing on the menu below.
     User iterates ("actually, what if we pair AND reschedule") until approved.
     Diagnostic answers are starting points, not auto-routes — agent uses
     judgment to combine palette items for the specific item.

4. Commit
     Apply edits to task/project records (jq), append new tasks if any,
     drop calendar block if any (Google Calendar via MCP).

5. Log
     Append a row to data/revive-events.ndjson (schema below).
```

### Intervention palette

| Intervention | Action | Framework label |
|---|---|---|
| `break_down` | Split into 15-min chunks (existing `pfc-add-task` breakdown flow). For projects: re-break the next part. | Initiation deficit |
| `pair_stack` | Anchor to an existing habit ("after morning row, do 15 min of X"). Writes a `notes` field on the task or project. | Habit stacking |
| `reschedule` | Drop on the calendar as a dedicated block (via `pfc-schedule-focus` or direct event). | Implementation intention |
| `boost_visibility` | Any one or more of: pin to top of next 2+1, drop calendar block, physical cue (sticky / placement reminder), notes-field reminder, bump urgency tier. | Salience |
| `lower_scope` | For tasks: lower `impact` and/or `urgency`. For projects: reduce `total_parts`. Admit the original framing was too ambitious. | Right-sizing |
| `pause_archive` | For tasks: status → `cancelled` (archive without completion). For projects: flip `active: false` (move to dormant). | Honest exit |
| `walk_aversion` | Sub-questions: what specifically is aversive? when did it start? is it safe to lower scope or pause? Output is usually a *different* intervention from the menu. | Behavioral activation |
| `skip` | Acknowledge, do nothing this round. Triggers 7-day cooldown on that item. | — |

### Diagnostic-to-palette guidance (defaults, not rules)

The agent uses these as starting suggestions when proposing an intervention; multi-select diagnostics combine.

| Diagnostic | Default palette suggestion |
|---|---|
| A | `break_down` |
| B | `reschedule` or `pair_stack` |
| C | `break_down` + add `depends_on` to the task |
| D | `boost_visibility` (full palette, not just `pair_stack`) |
| E | `break_down` so completion happens sooner |
| F | `walk_aversion` first; intervention falls out of that conversation |
| G | `lower_scope` or `pause_archive` |

## Data model

### `data/revive-events.ndjson`

Append-only NDJSON, one row per revive interaction.

```json
{
  "id": "revive-YYYYMMDD-NNN",
  "date": "YYYY-MM-DD",
  "item_type": "task",
  "item_id": "task-20260412-007",
  "signals": ["D", "E"],
  "diagnostic": ["A", "F"],
  "intervention": ["break_down", "reschedule"],
  "intervention_notes": "Split into 4 chunks; first chunk dropped on Tue 9am block",
  "outcome": null,
  "outcome_checked": null
}
```

Field semantics:

- `id` — `revive-YYYYMMDD-NNN`, sequential per day. NNN starts at 001.
- `date` — local-timezone date the revive interaction happened (Mountain Time per CLAUDE.md).
- `item_type` — enum: `task`, `project`.
- `item_id` — references a row in `5-actions/_data/tasks.ndjson` or `4-projects/_data/projects.ndjson`.
- `signals` — array of letters from {A,B,C,D,E,F}. Captures which trigger(s) put this item on the watchlist on that date.
- `diagnostic` — array of letters from {A,B,C,D,E,F,G}. User's multi-select picks. Empty array `[]` if the user picked `skip` without diagnosing.
- `intervention` — array of palette enums from {`break_down`, `pair_stack`, `reschedule`, `boost_visibility`, `lower_scope`, `pause_archive`, `walk_aversion`, `skip`}. May contain multiple if the brainstorm combined approaches.
- `intervention_notes` — free-text string. Captures the brainstorm result — what specifically was done. Nullable.
- `outcome` — populated 30 days later. Enum: `still_open`, `completed`, `archived`, `re_slipped`. `null` until checked.
- `outcome_checked` — `YYYY-MM-DD` the outcome was assessed. `null` until checked.

### `config/revive_event_schema.yaml`

Standard YAML schema mirroring the JSON shape. Used by `scripts/validate.sh` to verify NDJSON parse and field types on every commit.

### Outcome review

Outcomes are populated by either:
- `/pfc-revive --review-outcomes` — scans `revive-events.ndjson` for rows where `date <= today - 30 days` AND `outcome is null`, walks them with the user.
- Weekly check-in optional adoption — if the user wants, weekly can absorb this prompt.

The skill ships with the standalone `--review-outcomes` flag. Weekly integration is **out of scope for the initial cut.**

### Downstream pattern analysis (out of scope for the initial skill)

Once the log has 30+ rows, `/pfc-analyze-trends` (or a new `--revive` flag on it) can compute:
- Diagnostic-answer frequency by area.
- 30-day completion rate per intervention, conditioned on diagnostic.
- Which signals most predict eventual `archived` vs `completed`.

These analyses are read-only and are not implemented in the initial skill. The schema must be stable enough to support them — that constrains the data model now even though the analysis ships later.

## Integration points

| File | Change |
|---|---|
| `.claude/skills/pfc-revive/SKILL.md` | New skill — full workflow per "Walk flow" above. |
| `.claude/skills/pfc-morning-checkin/SKILL.md` | Add step: render watchlist block after 2+1, prompt for opt-in walk. |
| `.claude/skills/pfc-weekly-checkin/SKILL.md` | Add "Revive walk" section after stale-task triage. |
| `config/revive_event_schema.yaml` | New schema file. |
| `data/revive-events.ndjson` | New (empty initially) data file. |
| `scripts/validate.sh` | Add revive-events NDJSON parse + schema check. |
| `CLAUDE.md` | Add 1-paragraph section on revive + cross-link to skill. |
| `docs/cadences.md` | Note revive surfaces in morning + weekly. |
| `.claude/skills/pfc-repo-maintenance/SKILL.md` | Add: revive log presence, schema validity, integration-point references intact. |
| `.claude/skills/pfc-system-health/SKILL.md` | Add: revive watchlist freshness check (active projects + tasks scanned against thresholds; flag if watchlist generation fails). |

## Out of scope (initial cut)

- **Trello watchlist rendering.** Defer to a follow-up after the skill stabilizes. The watchlist can graduate to its own Trello list once the skill's heuristics are tuned.
- **Auto-applying interventions without user approval.** Always opt-in. The skill proposes; the user commits.
- **Cross-project priority arbitration** ("which project should I revive first"). List order on the watchlist is signal-severity (🔴 first), not strategic priority — strategic prioritization is a different skill (`pfc-pick-tasks` / weekly check-in).
- **Suggesting *new* projects based on slippage patterns.** Read-only pattern view only when the analysis ships.
- **Post-commit auto-notification.** Rejected during brainstorm — slippage is a slow-burn signal, not a moment-in-time alert.
- **Weekly check-in absorbing outcome review.** `/pfc-revive --review-outcomes` ships standalone; weekly integration is a follow-up if the user wants it.

## Open questions / known unknowns

- **Threshold tuning.** All thresholds (N=14, N=30, N=7, K=3, N=10) are first-pass defaults grounded in the user's working style. They may need adjustment after ~4 weeks of real watchlist data. Expose them in `config/revive_thresholds.yaml` for easy tuning rather than burying them in skill prose.
- **What if the watchlist is consistently empty?** Either the user is operating cleanly (good) or the thresholds are too loose (bad). After 4 weeks, check signal-fire rates and adjust if no signal has fired more than once.
- **What if the watchlist is consistently >10 items?** That's a real problem — either the user is genuinely backed up (use it as a wake-up call) or the thresholds are too tight. Triage threshold tuning before triaging items.

## Acceptance criteria (for the implementation plan)

1. `/pfc-revive` invocable standalone. Walks the watchlist with the diagnostic + brainstorm + commit + log flow.
2. Morning check-in renders watchlist block after 2+1; opt-in walk works.
3. Weekly check-in walks the full watchlist after stale-task triage.
4. Slippage detection covers all six signals (A–F) with the configured thresholds.
5. Hierarchy rule: project slip subsumes its task slips (no duplicates).
6. Active-only constraint correctly excludes `active==false` projects from A, B, F.
7. `data/revive-events.ndjson` and `config/revive_event_schema.yaml` exist; `scripts/validate.sh` validates the new file.
8. Skip cooldown works (skipped item suppressed for 7 days, re-fires if still slipping).
9. E fires once per task — re-carries don't re-trigger.
10. `pfc-repo-maintenance` and `pfc-system-health` updated per the integration-points table.
11. `CLAUDE.md` and `docs/cadences.md` updated.
12. `/pfc-revive --review-outcomes` walks rows where `date <= today - 30 days` AND `outcome is null`.
