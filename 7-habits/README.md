# Habits

Recurring practices, daily and monthly. The "maintenance" layer of VAVFPAH — the small things that compound when done consistently.

## What lives here

- **Daily habits** (`_data/habits-daily.ndjson`) — one entry per habit per day. Max 5 tracked at a time; frequency 1–7 per week per habit.
- **Monthly habits** (`_data/habits-monthly.ndjson`) — one entry per habit per month. Max 5 tracked; frequency 1–4 per month per habit.

Habit *definitions* (name, target frequency, area, area-statement link) live in `config/habit_schema.yaml`. This folder holds only the *logs*.

## Key skills

| Skill | What it does |
|---|---|
| `/pfc-log-habit` | Log a daily or monthly habit completion |
| `/pfc-evening-checkin` | End-of-day habit summary + bulk log |
| `/pfc-usage-audit` | Surface logging gaps and missed-target streaks |

## Two important distinctions

**Habits with an objective signal are pre-filled, not asked cold.** When a habit has an obvious answer in the day's auto-fetched health data (a tracked workout for an exercise habit, a logged sleep session for a bedtime habit), the evening check-in presents it pre-filled for a one-tap confirm. The habit log stays the source of truth — health data is a prompt, never an auto-write.

**Logging gaps ≠ missed habits.** A day with no entry for a habit means *not logged*, not *habit failed*. The system never backfills `completed: false` after the fact. This matters for stats: an empty entry is a system-hygiene signal (you missed logging), not a behavioral failure.

## Agent operations

If you're an agent reading or writing habit logs, see [`AGENTS.md`](AGENTS.md) at this level for the operational rules (auto-log gate, logging-gap rule, jq patterns).
