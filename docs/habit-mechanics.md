# Habit mechanics

How habits start, recover, and get retired in this system. The mechanisms below are drawn from *Atomic Habits* (James Clear) and adapted to how this system's user model actually works — several are modified, and one is deliberately rejected. This page is the wiring, not a book summary; read the book for the theory.

Skills reference this page rather than restating the rules, so there is one place to correct.

## Why this exists

A habit can have everything the system knows how to give it — a definition, a frequency, a landing anchor, and a Trello card — and still run zero reps for a month while its focus displays green. Measurement alone changes nothing.

Two things close that gap, and both are built in: a bar low enough to clear on a bad day, and a forced decision when the bar is missed anyway.

## The ramp

For most people with initiation-side executive-function trouble, *starting* is the hard part and sustaining is not. A fixed frequency you fail against is therefore the wrong instrument. Frequencies self-tune.

Every habit that is not yet automatic carries a `ramp` block in `config/habit_schema.yaml`:

```yaml
ramp:
  starter: 1      # the floor — a two-minute-sized number it can always return to
  target: 3       # where it is headed
  two_minute: "Open the course and watch one video"
```

- `frequency` is always the **live, ramped value**. Rate math, the evening check-in, and `focus_status.py` all read `frequency`, never `ramp.target`.
- **Two consecutive green weeks** → propose stepping `frequency` up by 1 toward `target`. This needs an explicit yes.
- **One red week** → step `frequency` down by 1, **automatically, no permission**. Never below `starter`.
- A habit with no `ramp` block never steps. Habits that are already stable don't need one; if a stable habit starts failing, that is a signal to re-land it, not to lower the bar.

**Why down is automatic and up is not:** the response to "even a trivial task is too much" is to lower the bar, never to push through. Asking permission to fall inserts a decision at the exact moment decisions are most expensive. Asking permission to rise keeps the user in control of their own ambition.

## Never miss twice

- **One miss is noise.** Say nothing.
- **Two consecutive misses on the same habit** → the check-in offers that habit's `ramp.two_minute` version for *today*, as a single line.

No lecture, no streak talk, no repeat within the same check-in. The rule exists because the second miss, not the first, is where a habit dies.

Skipped days (`{completed: false, skipped: true}`) do not count toward the two — a structurally unavailable day is not a miss.

## The two-minute first step

Applies to tasks and projects, not just habits.

When a task is broken down, the **first** sub-step must be doable in about two minutes: "open the file", "put the case by the door", "open the course" — not "draft the section" or "review the doc". If the first step would take longer, break it down again.

Why the first step specifically: the effort-cost calculation prices the *first* action, not the average one. A 15-minute task whose first step is 15 minutes reads as "not worth it"; the same task whose first step is 30 seconds fires. This sharpens the ~15-minute chunk rule at the exact point where launch fails.

## The four-way choice

When something has been red for two consecutive weeks, the system stops displaying and starts requiring. Applies to three cases:

- a **focus** whose primary vehicle has been red two weeks running (weekly `focus-accuracy` review)
- a **supporting vehicle habit** red two weeks running (scoped to that habit; the focus is untouched)
- a **stalled project** in `pfc-revive`

Exactly four options, with the item's current state shown inline so nothing has to be recalled:

1. **Re-land it** — the anchor is wrong. Rebuild it anchor-first per `docs/calendar-scheduling.md`: name the running state it bends out of, then the place, then the clock.
2. **Lower it to something real** — drop `ramp.starter` (or shrink the project's next part). The bar was never clearable.
3. **Park it** — a deliberate, guilt-free stop. `parked: true` on a focus frees a pursuit slot.
4. **Retire it** — set `retired_date`. It's over.

**There is deliberately no fifth "keep trying" option.** That is the whole mechanism. "Keep trying" is what produces a green card with zero reps behind it.

Cap forced choices at **two per review**. More than two decisions in one sitting is the overload this system exists to prevent; the rest surface next week.

Why two weeks rather than nightly: a nightly red nag becomes wallpaper within days. A decision demanded every other week does not.

## What we deliberately did NOT take from the book

**The visible habit tracker — the wall chart, the streak counter, "don't break the chain."** Clear treats it as a core mechanism. For a brain where object-based reminders go invisible within a couple of days — sticky notes, sand timers, progress bars, calendar squares — it is inert.

The tracker that works here is **the evening check-in asking you**. That is a person-shaped prompt at a fixed time, not an object waiting to be noticed.

Do not add a streak display, a progress bar, a chain grid, or a "days since" counter to Trello, TRMNL, or any skill output. It will feel like an improvement and it will stop being seen within the week.

## Mapping

| Principle | Already in this system | What wired it in |
|---|---|---|
| Implementation intention — "I will X at TIME in PLACE" | the `landing` field on focuses | `landing` should carry a place, not only an anchor |
| Habit stacking — "after X, I will Y" | anchor to a running state — the same mechanism | `landing` names the *preceding activity*, not a clock |
| Two-Minute Rule | — | `ramp.two_minute` + `ramp.starter`; the two-minute first step in task breakdown |
| Never miss twice | — | the check-in and `pfc-log-habit` |
| Make it easy / cut friction | lower the effort side, don't raise willpower | environment prep folded into `landing` |
| Make it satisfying — immediate reward | the habit log + the Trello checkbox | unchanged |
| Identity-based habits | the Visions layer already is this ("become a musician," not "practice guitar") | the nightly Focus trickle prints the linked vision beside each focus |
| Goldilocks — difficulty just past ability | — | the ramp's step-up rule |
| Visible chain tracker | — | **deliberately not built** — see above |

## See also

- [`config/habit_schema.yaml`](../config/habit_schema.yaml) — habit definitions and live frequencies
- [`7-habits/AGENTS.md`](../7-habits/AGENTS.md) — the hard rules for reading and writing habit data
