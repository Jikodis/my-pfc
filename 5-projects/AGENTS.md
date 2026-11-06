# Agents — projects folder

Folder-scoped operational rules for any agent reading or writing in `5-projects/`. Cross-cutting rules live in the repo-root `AGENTS.md`.

## File summary

| Path | Shape | Mutability |
|---|---|---|
| `_data/projects.ndjson` | One project per line | Mutable in place (status, completed_parts, deadline) |
| `<slug>.md` | Free-form markdown | Mutable; lifecycle tied to the registry record |

Schema: `config/project_schema.yaml`.

## Hard rules

1. **No small cap on active projects — the backstop is 12.** A project is a group of tasks that belong together, not a claim on attention, so several can be `active` while only a few get worked at a time. Never ask the user to demote a project just to make room, and never treat a high active count as drift. The validator fails only above 12, which is a runaway guard. The real scarcity layer is `4-focus/` (max 6 active pursuits) — that is what answers "what am I actually on right now." 
2. **Active-project area must match a folder under `2-areas/`.** Same integrity rule that applies to tasks and habits.
3. **All structured writes go through `jq`.** Mutating updates use the atomic temp-file pattern.
4. **Date stamps in `$LOCAL_TZ`.** Project IDs use `proj-YYYYMMDD-NNN`.

## Canonical query patterns

```bash
# Active projects
jq -c 'select(.status == "active")' 5-projects/_data/projects.ndjson

# Projects in a specific area
jq -c 'select(.area == "career" and .status == "active")' 5-projects/_data/projects.ndjson

# Count active (must be < 3 before activating a new one)
jq -c 'select(.status == "active")' 5-projects/_data/projects.ndjson | wc -l
```

## Velocity calculation

For each active project with `total_parts > 0`:

- `parts_per_day = completed_parts / max(1, days_elapsed_since_started)`
- `remaining_days = (total_parts - completed_parts) / parts_per_day` (skip if `parts_per_day == 0`)
- `estimated_completion = today + remaining_days`
- Compare against `deadline`:
  - 🟢 on track
  - 🟡 within 7 days late
  - 🔴 >7 days late

Surface this in `pfc-summarize-project`, `pfc-status`, `pfc-daily-summary`, and the web page's Projects band (velocity and days idle come from one Python function, `automations/scripts/project_gauges.py`). Do NOT pre-schedule a project's parts as calendar events to "lock in" the pace — life intervenes and the calendar churn is wasted work. Velocity is the steering wheel, not the cement.

## Daily project status

The home page's Projects band (`http://127.0.0.1:4323/`) and `pfc-daily-summary` show, for each active project: name, completion %, today's project task (if any), estimated completion date based on observed velocity, and an OK/WARN flag if velocity slipped past the project deadline. Goal: keep multiple active projects in view daily so the user can shift effort instead of rediscovering drift at the next review pass.

The optional 4th daily-focus slot is reserved for a pre-planned active-project task — see `../6-tasks/AGENTS.md` § Daily focus.

## Slippage intervention — pfc-revive

**A slipping project is the highest-priority slippage signal in this system** — projects are vision-aligned and values-aligned, so drift here costs more than a slipped action. The `pfc-revive` skill is the intervention surface.

A slipped item is a task or project that's lost momentum:

- **Project triggers** (higher priority): velocity 🔴, project at 0 parts for ≥14 days, active project with no `task_event` activity for ≥10 days.
- **Task triggers**: open task ≥30 days, high-impact open task ≥7 days, same task carried in 2+1 ≥3 days without completion.

**A stalled project gets the four-way choice, not an open question.** "What's blocking this?" asks the user to hold a whole stalled project in working memory and generate an answer — the exact shape that produces silence for a working-memory-limited brain. Give exactly four options, with the project's name, last activity date, and next part shown inline: **re-land** (the anchor is wrong — rebuild it anchor-first per `../docs/calendar-scheduling.md`), **lower** (shrink the next part until it's clearable — often the two-minute version of just its first step), **park** (a deliberate, guilt-free stop), **retire** (it's over). There is deliberately no fifth "keep trying" option, and no more than two forced choices per run. Same mechanism as a focus red two weeks running — see [`docs/habit-mechanics.md`](../docs/habit-mechanics.md) § The four-way choice.

The skill detects these via `automations/scripts/revive_watchlist.py`, walks each item with a multi-select diagnostic (Initiation / Implementation intention / Dependency / Salience / Delay discounting / Behavioral activation / Honest exit), and brainstorms a tailored intervention. Surfaces via the `stale-task-triage` rolling review in the evening check-in and `/pfc-review`. Always available as `/pfc-revive`. Outcomes are reviewed 30 days later via `/pfc-revive --review-outcomes`. Distinct from `pfc-stuck` (body-state).

## Vision linkage

When a project's `vision:` field is set, the vision must exist as a file in `3-visions/<slug>.md`. Validator enforces this. When archiving the last project linked to a vision, surface the resulting "drift" state to the user — they may want to pause the vision too.

## See also

- Repo-root [`AGENTS.md`](../AGENTS.md) — daily-focus 2+1 rules, project status surfacing.
- [`docs/data-model.md`](../docs/data-model.md) — full project schema.
