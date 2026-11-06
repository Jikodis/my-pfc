# Agents — habits folder

Folder-scoped operational rules for any agent reading or writing in `7-habits/`. Cross-cutting rules live in the repo-root `AGENTS.md`.

## File summary

| Path | Shape | Mutability |
|---|---|---|
| `_data/habits-daily.ndjson` | One entry per habit per day | Append-only — never rewrite an existing log entry |
| `_data/habits-monthly.ndjson` | One entry per habit per month | Append-only |

Definitions live in `config/habit_schema.yaml`.

## Hard rules

1. **Pre-fill from health data, don't ask cold.** When today's day-tracking `health` block already answers a habit (e.g. a tracked workout in `health.workouts` for an exercise habit), present it pre-filled for a one-tap confirm (the tour's habit step, or a chat log) instead of asking blind. The habit log stays the source of truth — health data is a prompt, never an auto-write.

2. **Unlogged = missed, in rate math.** In review and trend skills (habit-rate reviews, monthly habit reviews, trend analysis), a day inside the window with *no entry* for a habit counts as a **miss** — the same as `completed: false`. Recording is the user's job, and counting blanks against the rate is a deliberate accountability incentive: the alternative ("unlogged days don't count") lets a habit quietly stop being tracked while the rate stays flattering. Accept that the rate may skew slightly low as the price.

   **This is a defensible default, not a law — flip it if it doesn't suit you.** Some people log erratically but do the habit reliably, and for them a punishing rate is noise. If that's you, change this rule to "unlogged days drop out of the denominator" and make sure the review and trend skills agree with whichever way you set it. What's *not* defensible is the two halves of the system disagreeing.

   Three things this rule does NOT mean:

   a. **Structurally-unavailable days are still carved out.** A day the habit genuinely could not happen — travel blocking a home-only habit, illness blocking a workout habit, a schedule that makes the habit impossible that day — drops out of *both* numerator and denominator. Mark these with `skipped: true` (see `pfc-log-habit` § skip a structurally unavailable day) or derive them from the schedule; either way they aren't penalized.

   b. **No phantom backfill.** Never write `completed: false` records onto long-blank past days. Absence is interpreted as a miss at *compute time*; it is not stamped into the data. A chat log still writes real records as the user reports them.

   c. **A sustained logging blackout is surfaced as its own line.** When a low rate is mostly unrecorded days rather than logged misses, say so explicitly (e.g. in `/pfc-usage-audit`), so the user can tell "didn't do it" from "didn't log it."

3. **When a habit set is shown in chat, ask what the user DID.** Don't enumerate yes/no for every tracked habit. Present the unlogged habits as a **TABLE** (one row per habit, columns `Habit | State`) with one prompt above it ("Which of these did you do?"), then log the positives. Never a comma-separated inline list — a run-on list is hard to scan and habits get dropped in it; the row-per-habit layout is what makes a missed habit visible. This table rule holds any time a habit set is shown for confirmation, in any skill. Log only what the user answers; never write `completed: false` for a habit they did not mention. The tour's habit step writes only the ticks the user taps, and an untapped habit stays absent, which rate math already counts as a miss (rule 2).

4. **All structured writes go through `jq`.** Never raw `echo >>` or `sed`.

5. **Date stamps are derived in `$LOCAL_TZ`.** See repo-root `AGENTS.md` § Dates and time.

6. **Frequency is the LIVE ramped value; `ramp.target` is the destination.** Rate math, the web page, and `focus_status.py` all read `frequency`, never `ramp.target`. Two consecutive green weeks → propose stepping `frequency` up by 1 toward `ramp.target` (needs an explicit yes). One red week → step it down by 1 **automatically**, never below `ramp.starter`, no permission needed — falling should never require approval; the response to "too much" is lower the bar. Habits with no `ramp` block never step. Full mechanics: [`docs/habit-mechanics.md`](../docs/habit-mechanics.md).

7. **Never miss twice.** One miss is noise — say nothing. Two consecutive misses on the same habit: `pfc-log-habit` offers that habit's `ramp.two_minute` version for *today*, as a single line, not a lecture, when it logs the second miss. It is not part of any daily flow: the tour does not offer it. Skipped days don't count toward the two.

8. **Show only habits due today.** With a full roster of daily habits, listing all of them every time makes logging a chore, and degraded logging corrupts every derived focus light downstream. When a skill shows a habit set in chat, a habit at 1×/week appears at most once that week: on the day its landing anchor exists, or on the last day of the week if the week's rep is still owed. Habits at 5+/week appear daily. (The tour's habit step shows the focus vehicle habits from `home_data.py`, not this filter.) A habit not shown is simply absent, and absence is already interpreted as a miss at compute time — never backfill a `completed: false` for a day it wasn't shown.

9. **Retiring a habit — delete its Trello card too.** When you retire a habit (remove it from the active block in `config/habit_schema.yaml`, move it to `deprecated_habits`, keep the history), also delete that habit's card from the Trello board. The render does not auto-prune a card whose `pfc-id` no longer exists, so a retired habit's card lingers on the dashboard until removed by hand. Do it in the same change.

## Canonical query patterns

```bash
# All entries for a specific habit
jq -c 'select(.habit_id == "morning-walk")' 7-habits/_data/habits-daily.ndjson

# Today's logs
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
jq -c --arg d "$TODAY" 'select(.date == $d)' 7-habits/_data/habits-daily.ndjson

# This month's logs
THIS_MONTH=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m')
jq -c --arg m "$THIS_MONTH" 'select(.date | startswith($m))' 7-habits/_data/habits-monthly.ndjson
```

## Append pattern

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
NOW=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%dT%H:%M:%S%z')
jq -cn --arg id "morning-walk" --arg d "$TODAY" --arg ts "$NOW" \
  '{habit_id:$id, date:$d, completed:true, source:"manual", logged_at:$ts}' \
  >> 7-habits/_data/habits-daily.ndjson
```

## See also

- Repo-root [`AGENTS.md`](../AGENTS.md) § Habit tracking — the canonical reference.
- [`docs/data-model.md`](../docs/data-model.md) — full habit schema and field semantics.
