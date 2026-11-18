# Config

Schemas and configuration files that define the *shape* of every typed record in the system. If you're a human reading this, treat it as reference — most files here are edited via skills, not by hand.

## What lives here

### Schemas — the shape of each record type

| File | Defines the shape of |
|---|---|
| `task_schema.yaml` | Tasks in `6-tasks/_data/tasks.ndjson` |
| `habit_schema.yaml` | Habit definitions (referenced by daily/monthly habit logs) |
| `project_schema.yaml` | Projects in `5-projects/_data/projects.ndjson` |
| `supplement_schema.yaml` | Supplements in `data/supplements.ndjson` |
| `insight_schema.yaml` | Insights in `data/insights.ndjson` |
| `hypothesis_schema.yaml` | Hypotheses in `data/hypotheses.ndjson` |
| `finding_schema.yaml` | Findings in `data/findings.ndjson` |
| `revive_event_schema.yaml` | Revive-watchlist events in `data/revive-events.ndjson` |
| `focus_schema.yaml` | Current Focus records in `4-focus/_data/focus.ndjson` |
| `onboarding_schema.yaml` | Onboarding state in `config/onboarding.ndjson` |
| `area_item_schema.yaml` | Area items in `2-areas/_data/area-items.ndjson` and their check-in answers in `2-areas/_data/area-checkins.ndjson` |

### Runtime state

| File | Purpose |
|---|---|
| `persona.yaml` | Currently-active assistant persona (default: `none`) |
| `personas.md` | Registry of available personas (voice/character overlays) |
| `onboarding.ndjson` | Event log of what onboarding lessons you've tried/dismissed |
| `automation_config.yaml` | Settings for automation scripts (cadences, thresholds) |
| `focus.yaml` | Tier labels and caps for the Current Focus layer (Foundations · Active Pursuits max 6 · Currently Consuming) |
| `trello_calendar_filters.yaml` | Which calendar events to leave out of the Trello and TRMNL week views |

## Habit schema — the one to actually edit by hand

`habit_schema.yaml` is the file you're most likely to open directly. It defines every tracked habit — id, area, frequency, optional auto-log automation. The shipped version has a small starter set; edit to match the habits you actually want to track. Daily habits are capped at 5 active; monthly at 5 active.

The other schemas are mostly stable — you'd only edit them to add a custom field or rename one. Most of those changes ripple through skills, so it's usually better to leave them alone.

## Persona system

The `persona.yaml` file holds your currently-active persona (defaults to `none`, meaning standard repo voice). Personas are tone-only overlays — they change how the agent talks, but never what it does. Switch via `/pfc-persona`.

See `personas.md` for the registry of available personas and what each one sounds like.

## Trello calendar filters

If you've set up the Trello dashboard, `trello_calendar_filters.yaml` controls which events are left out of the `🗓️ Week` list, the web Week band and the TRMNL week screen (e.g. US Holidays, PFC scaffolding blocks, known weekly patterns).

**Recurring events are not dropped for being recurring**, because most real commitments are recurring series. The file's four lists (prefixes, titles, titles when recurring, calendars) say what to hide; its header explains each one.

## See also

- Repo-root [`AGENTS.md`](../AGENTS.md) § Data formats — overall conventions.
- [`docs/data-model.md`](../docs/data-model.md) — full record schemas and field semantics.
- Repo-root [`AGENTS.md`](../AGENTS.md) § Personas — how persona overlays interact with system rules.
