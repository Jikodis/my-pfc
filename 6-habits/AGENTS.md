# Agents — habits folder

Folder-scoped operational rules for any agent reading or writing in `6-habits/`. Cross-cutting rules live in the repo-root `AGENTS.md`.

## File summary

| Path | Shape | Mutability |
|---|---|---|
| `_data/habits-daily.ndjson` | One entry per habit per day | Append-only — never rewrite an existing log entry |
| `_data/habits-monthly.ndjson` | One entry per habit per month | Append-only |

Definitions live in `config/habit_schema.yaml`.

## Hard rules

1. **Auto-logged habits are off-limits to ask-loops.** Any habit definition with an `auto_log:` block in `config/habit_schema.yaml` is fetched by an automation (typically Google Health). **Never prompt the user about these in any check-in or skill** — evening-checkin, morning-checkin, log-habit, daily-summary. If today's auto-log hasn't run yet, leave the habit unlogged; the automation will backfill on the next fetch.

2. **Missed logging ≠ missed habit.** A day with no entry for a manual habit means *not logged*. **Never backfill `completed: false` after the fact.** Absence is a system-hygiene signal (prompt to log next time), not evidence the habit failed. Health stats and review skills must distinguish the two — a logging gap and a behavioral miss are different categories.

3. **During an active check-in, ask what the user DID.** Don't enumerate yes/no for every tracked habit. List unlogged manual habits in one prompt ("Which of these did you do?") and log positives. Anything unmentioned **in that active check-in** logs as `completed: false`. Outside of an active check-in, leave entries absent.

4. **All structured writes go through `jq`.** Never raw `echo >>` or `sed`.

5. **Date stamps are derived in `$LOCAL_TZ`.** See repo-root `AGENTS.md` § Dates and time.

## Canonical query patterns

```bash
# All entries for a specific habit
jq -c 'select(.habit_id == "morning-walk")' 6-habits/_data/habits-daily.ndjson

# Today's logs
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
jq -c --arg d "$TODAY" 'select(.date == $d)' 6-habits/_data/habits-daily.ndjson

# This month's logs
THIS_MONTH=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m')
jq -c --arg m "$THIS_MONTH" 'select(.date | startswith($m))' 6-habits/_data/habits-monthly.ndjson
```

## Append pattern

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
NOW=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%dT%H:%M:%S%z')
jq -cn --arg id "morning-walk" --arg d "$TODAY" --arg ts "$NOW" \
  '{habit_id:$id, date:$d, completed:true, source:"manual", logged_at:$ts}' \
  >> 6-habits/_data/habits-daily.ndjson
```

## See also

- Repo-root [`AGENTS.md`](../AGENTS.md) § Habit tracking — the canonical reference.
- [`docs/data-model.md`](../docs/data-model.md) — full habit schema and field semantics.
