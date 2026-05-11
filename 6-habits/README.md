# Habits

Recurring practices, daily and monthly. The "maintenance" layer of VAVPAH — the small things that compound when done consistently.

## What lives here

- **Daily habits** (`_data/habits-daily.ndjson`) — one entry per habit per day. Max 5 tracked at a time; frequency 1–7 per week per habit.
- **Monthly habits** (`_data/habits-monthly.ndjson`) — one entry per habit per month. Max 5 tracked; frequency 1–4 per month per habit.

Habit *definitions* (name, target frequency, area, area-statement link) live in `config/habit_schema.yaml`. This folder holds only the *logs*.

## Key skills

| Skill | What it does |
|---|---|
| `/pfc-log-habit` | Log a daily or monthly habit completion |
| `/pfc-evening-checkin` | End-of-day habit summary + bulk log |
| `/pfc-system-health` | Surface logging gaps and missed-target streaks |

## Two important distinctions

**Auto-logged vs. manual habits.** Some habits are fetched from external sources (e.g. health-wearable activity, sleep). They have an `auto_log:` block in `config/habit_schema.yaml` and are populated by an automation. The system never prompts you about these in any check-in — they fill in on their own.

**Logging gaps ≠ missed habits.** A day with no entry for a habit means *not logged*, not *habit failed*. The system never backfills `completed: false` after the fact. This matters for stats: an empty entry is a system-hygiene signal (you missed logging), not a behavioral failure.

## Agent operations

If you're an agent reading or writing habit logs, see [`AGENTS.md`](AGENTS.md) at this level for the operational rules (auto-log gate, logging-gap rule, jq patterns).
