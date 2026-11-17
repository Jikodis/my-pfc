# Agents — habits folder

Folder-scoped operational rules for any agent reading or writing in `7-habits/`. Cross-cutting rules live in the repo-root `AGENTS.md`.

## File summary

| Path | Shape | Mutability |
|---|---|---|
| `_data/habits-daily.ndjson` | One entry per habit per day | Append-only — never rewrite an existing log entry |
| `_data/habits-monthly.ndjson` | One entry per habit per rep date | Append-only |

Definitions live in `config/habit_schema.yaml`.

## Hard rules

1. **Pre-fill from health data, don't ask cold.** When today's day-tracking `health` block already answers a habit (e.g. a tracked workout in `health.workouts` for an exercise habit), present it pre-filled for a one-tap confirm in the check-in instead of asking blind. The habit log stays the source of truth — health data is a prompt, never an auto-write, except for the habits that log themselves (rules 10 and 11).

2. **Unlogged = missed, in rate math.** In review and trend skills (habit-rate reviews, monthly habit reviews, trend analysis), a day inside the window with *no entry* for a habit counts as a **miss** — the same as `completed: false`. Recording is the user's job, and counting blanks against the rate is a deliberate accountability incentive: the alternative ("unlogged days don't count") lets a habit quietly stop being tracked while the rate stays flattering. Accept that the rate may skew slightly low as the price.

   **This is a defensible default, not a law — flip it if it doesn't suit you.** Some people log erratically but do the habit reliably, and for them a punishing rate is noise. If that's you, change this rule to "unlogged days drop out of the denominator" and make sure the review and trend skills agree with whichever way you set it. What's *not* defensible is the two halves of the system disagreeing.

   Three things this rule does NOT mean:

   a. **Structurally-unavailable days are still carved out.** A day the habit genuinely could not happen — travel blocking a home-only habit, illness blocking a workout habit, a schedule that makes the habit impossible that day — drops out of *both* numerator and denominator. Mark these with `skipped: true` (see `pfc-log-habit` § skip a structurally unavailable day) or derive them from the schedule; either way they aren't penalized.

   b. **No phantom backfill.** Never write `completed: false` records onto long-blank past days. Absence is interpreted as a miss at *compute time*; it is not stamped into the data. Live check-ins still write real records as the user reports them.

   c. **A sustained logging blackout is surfaced as its own line.** When a low rate is mostly unrecorded days rather than logged misses, say so explicitly (e.g. in `/pfc-usage-audit`), so the user can tell "didn't do it" from "didn't log it."

3. **During an active check-in, ask what the user DID.** Don't enumerate yes/no for every tracked habit. Present the unlogged habits as a **TABLE** (one row per habit, columns `Habit | State`) with one prompt above it ("Which of these did you do?"), then log the positives. Never a comma-separated inline list — a run-on list is hard to scan and habits get dropped in it; the row-per-habit layout is what makes a missed habit visible. This table rule holds any time a habit set is shown for confirmation, in any skill. Anything unmentioned **in that active check-in** logs as `completed: false`. Outside of an active check-in, leave entries absent.

4. **All structured writes go through `jq`.** Never raw `echo >>` or `sed`.

5. **Date stamps are derived in `$LOCAL_TZ`.** See repo-root `AGENTS.md` § Dates and time.

6. **Frequency is the LIVE ramped value; `ramp.target` is the destination.** Rate math, the evening check-in, and `focus_status.py` all read `frequency`, never `ramp.target`. Two consecutive green weeks → propose stepping `frequency` up by 1 toward `ramp.target` (needs an explicit yes). One red week → step it down by 1 **automatically**, never below `ramp.starter`, no permission needed — falling should never require approval; the response to "too much" is lower the bar. Habits with no `ramp` block never step. Full mechanics: [`docs/habit-mechanics.md`](../docs/habit-mechanics.md).

7. **Never miss twice.** One miss is noise — say nothing. Two consecutive misses on the same habit: the check-in offers that habit's `ramp.two_minute` version for *today*, as a single line, not a lecture. This is the recovery mechanism; it does not repeat within the same check-in, and skipped days don't count toward the two.

8. **Show only habits due today.** With a full roster of daily habits, listing all of them every night makes the check-in a chore, and degraded logging corrupts every derived focus light downstream. A habit at 1×/week appears at most once that week: on the night its landing anchor exists, or on the last night of the week if the week's rep is still owed. Habits at 5+/week appear nightly. A habit not shown is simply absent, and absence is already interpreted as a miss at compute time — never backfill a `completed: false` for a night it wasn't shown.

9. **Retiring a habit — delete its Trello card too.** When you retire a habit (remove it from the active block in `config/habit_schema.yaml`, move it to `deprecated_habits`, keep the history), also delete that habit's card from the Trello board. The render does not auto-prune a card whose `pfc-id` no longer exists, so a retired habit's card lingers on the dashboard until removed by hand. Do it in the same change.

10. **Auto-derived habits log themselves — never ask about them, never log them by hand.** A habit with `auto_derived: true` in `config/habit_schema.yaml` has a feed: the starter `sleep-on-time` habit from the wearable's sleep timing (`automations/scripts/derive_sleep_habit.py`, `source: "fitbit-derived"`, run by every health fetch; the starter schema ships with the flag set, so remove `auto_derived: true` from `sleep-on-time` if you have no wearable and log it by hand), and every habit with a `calendar: {match, exclude}` rule from the calendar cache (`automations/scripts/derive_calendar_habits.py`, `source: "calendar-derived"`). Leave them out of any habit set shown for confirmation. If the user reports one anyway, log it normally: a row from any other source wins over the derived one. The derivers rewrite only their own rows, the one exception to append-only in this folder.

11. **Workout habits log themselves when the watch tracked the session, and still take a hand log.** A daily habit with a `workout: {types: [...], min_minutes: N}` rule is written by `automations/scripts/derive_workout_habits.py` (run by every health fetch, `source: "health-derived"`) for any date with a matching session in `health.workouts`. These habits are not `auto_derived`: when the user says they did it and there is no row yet (no watch, or the watch has not synced), log it normally, and their row wins. Do not ask "did you do it?" about a date that already has a derived row.

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
