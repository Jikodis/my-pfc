# Calendar Scheduling Rules

**Read this before creating or moving any calendar event.**

## Title prefix — every PFC-generated event starts with `PFC - `

**Any event the PFC system creates gets the literal prefix `PFC - ` at the very start of the title.** No exceptions, no emoji before it — the prefix has to be the first characters so the calendar sorts and filters cleanly. This tells you at a glance which events came from the productivity system versus real life.

```
PFC - 🎯 2+1 anchor (post-work)
PFC - Evening Checkin
PFC - ⭐ [AA-S] Complete important task [task-YYYYMMDD-NNN]
```

Applies to everything the system writes: the 2+1 anchors, check-in reminders, `pfc-schedule-focus` per-task events, course/study series batches, and any recurring block a skill creates. It does **not** apply to events the user made themselves — never rename a personal event into the PFC namespace.

This is a naming convention only. Lookups still find events by **time window**, never by title — so the prefix is safe to change and safe to rely on for human scanning, not for matching.

## Calendars in scope

Always operate against exactly these two when reading availability or writing events:

| Calendar | ID | Use for |
|---|---|---|
| Primary (`your.email@example.com`) | `primary` | Read availability, write personal events / focus picks / course study |
| Work | `<your-work-calendar-id>@group.calendar.google.com` | Read availability. Do NOT create new personal errands here or edit work meetings — but if some of your personal routines live here (anchored to the work-day rhythm), editing those is fine |

**If personal routines live on the work calendar, search BOTH when looking up an event by name.** A name search that queries only `primary` will report a real event as "missing." Any `list_events` lookup for a specific named event should run against `primary` AND the work calendar.

**Excluded — do NOT read for conflicts and do NOT write to:**

| Calendar | ID | Why excluded |
|---|---|---|
| Example Shared Calendar 1 | `<example-shared-calendar-id-1>@group.calendar.google.com` | example shared informational calendar — informational only, not a personal blocker |
| Example Shared Calendar 2 | `<example-shared-calendar-id-2>@group.calendar.google.com` | example shared informational calendar — opt-in, not a personal blocker |

**Context-only (read for awareness, never blocks):** US Holidays calendar.

If a user request touches a calendar not in the table above (a new shared calendar, a vendor invite), ask before treating it as a blocker or a write target.

## Personal-task time windows (where events may land)

These are the only windows on which any personal task — focus picks, course study, course-series batches, errands, anything not work-related — may be scheduled on the primary calendar:

| Day type | Allowed personal-task windows (your local timezone) |
|---|---|
| Weekdays (Mon–Fri) | 8:00–9:00 AM · 12:00–1:00 PM (lunch) · 5:00–9:00 PM (default — edit to match your schedule) |
| Weekends (Sat/Sun) | 8:00 AM – 9:00 PM |

Work hours (Mon–Fri 9 AM – noon, 1 PM – 5 PM) are excluded — personal tasks must not land there. Note that **other blockers may further restrict these windows** (family commitments, appointments, recurring meetings, all-day blocks). Read `0-me/schedule-patterns.md` for the fixed-pattern blockers, then run the per-day conflict check below.

These windows apply equally to:
- `pfc-schedule-focus` (the focus-task slot finder enforces them via `find_focus_slots.py`)
- Course-series batch scheduling (any multi-event series)
- Any ad-hoc personal event the assistant places on the calendar

If a window collides with an existing event on a given day, pick a different window from the table above for that day. If all windows on a day are blocked, push to the next available day rather than overlapping.

## The anchor rule (before any slot rule)

**Recurring blocks anchor to a running state, not a clock time.** Before placing a recurring event, ask: what state does it bend out of? Naming the anchor (e.g. "end of the daily standup," "after the morning workout," "right after dinner") is the actual scheduling decision. The clock time is just the most-common-case label that follows from the anchor — it can move when the anchor moves. If you can't name the running state, you don't have an anchor; you have a sticky note on the calendar, and object-based reminders go invisible within days.

When creating a recurring event, the description must name the anchor explicitly so future-you (and the user) can override the clock on a given day without losing the rule.

### Check recurrence before treating a conflict as constant

Conflicts that show up on next Monday are not necessarily Monday-every-week. Before scheduling around an existing event:

1. If the event has `recurringEventId` in the `list_events` response, **do not assume weekly**. Pull at least 4 weeks of instances of that event (e.g. via `fullText` on its summary across a 4–8 week window).
2. Walk the start dates. Possible patterns: weekly, biweekly, monthly, quarterly, sporadic.
3. Treat the conflict only as severely as the pattern warrants. A biweekly conflict is a 50% conflict, not a Mondays-are-blocked conflict.
4. When the anchor wants a slot that a **sporadic** conflict sometimes occupies: your recurring event stays at the anchored time, and **the agent cancels the few conflicting instances of its own series** (an instance-level delete that leaves the user's one-off untouched — never the reverse). Do not pre-emptively shift the entire series to clear the worst case — that breaks the anchor most of the time to satisfy a minority of conflicts. (For a conflict that recurs on a *fixed cadence*, do NOT delete instances one at a time — alternate the series; see below.)

**One calendar pull is a snapshot, not a pattern.** Pull the recurrence before locking the rule. And never tell the user to drag a recurring conflict by hand — see § "Alternating recurring events" below.

### Recurring conflict vs. one-off conflict — the deciding question

Once you know the conflict's cadence, the response splits cleanly:

- **Recurring conflict** (weekly / biweekly / monthly — it collides every cycle): never place your recurring event on top. Phase or alternate around it with `INTERVAL=N` (next section). Dragging it by hand every cycle is not a system.
- **Sporadic / one-off conflict** (an occasional game, appointment, or party — no fixed cadence): place your recurring event at its anchored time anyway. When a one-off lands on top, **the agent cancels that single instance of its own recurring series** — an instance-level delete, leaving the user's one-off fully intact. The user never cleans these up by hand. A few instance cancellations now and then is fine; engineering around sporadic noise is not.

The deciding question is **not** "is there a conflict on the next instance?" — it's **"does the conflict itself recur on a fixed cadence?"** Only fixed-cadence conflicts justify alternating events; sporadic ones are handled by the slot-loss rule, with the agent cancelling the colliding instances of its own series automatically.

**When the agent cancels instances:** (a) at creation/maintenance — during the audit pass below, scan the horizon (~8 weeks) and cancel any anchor instance overlapping a one-off; (b) ongoing — the evening check-in cancels tomorrow's instance if a one-off has since appeared on the slot. Always delete the INSTANCE (`<seriesId>_<YYYYMMDD>T…`), never the whole series, and never the user's event.

## Alternating recurring events for biweekly / monthly conflicts

**Hard rule: never place a recurring event over a known recurring conflict.** The user can't do two things at once. "Drag it manually every N weeks" is not a fix — it's manual upkeep, the same failure mode as object-based reminders on the wall.

When the conflicting event repeats on a known cadence (biweekly, monthly, quarterly), build **alternating recurring events with `INTERVAL=N`** so every instance lands free:

| Conflict pattern | Solution |
|---|---|
| Biweekly Mon — sometimes free, sometimes blocked | Two `RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=MO` events with different `DTSTART` dates (one week apart) at different times. Each fires every 2 weeks; together they cover every Monday. |
| Monthly | Two events with `INTERVAL=4` offset by the conflict's phase, or one `INTERVAL=4;BYDAY=1MO` + a weekly base that excludes that Monday via `EXDATE`. |
| Quarterly | Same shape with `INTERVAL=12` or `INTERVAL=13` depending on whether the conflict drifts. |

Worked example — a daily study block anchored to "end of the last morning meeting," where Mondays alternate between a 10–11 AM planning meeting (biweekly) and a free 10 AM:

- Tue/Wed/Thu/Fri: `RRULE:FREQ=WEEKLY;BYDAY=TU,WE,TH,FR` at 10:00–10:30 — clean every week.
- Planning-meeting Mondays: `RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=MO` at 11:00–11:30, `DTSTART` on a meeting week — fires after the meeting ends.
- Off-meeting Mondays: `RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=MO` at 10:00–10:30, `DTSTART` one week later — fires at the same 10:00 anchor as Tue–Fri.

The combined effect: the block fires every weekday after the last morning meeting ends, with zero overlap and zero manual upkeep.

**Audit before declaring done.** After building alternating events, pull 4 weeks of both calendars and confirm every instance of the new event has zero overlap with the conflicting recurring event. The "biweekly events alternate" math is right on paper; verify it landed correctly on the calendar.

## The rule: never schedule over an existing event

Before creating/moving an event on date `D` at time `[T_start, T_end]`, you MUST:

1. Pull the **full day** of events on calendar `D` from both the primary calendar AND the work calendar (`<your-work-calendar-id>@group.calendar.google.com`).
2. Compute overlap: an existing event `[E_start, E_end]` conflicts with the target slot iff `E_start < T_end AND E_end > T_start`.
3. Treat all-day events as "blocked context only" — they don't block timed slots, but note them (e.g., "In Office").
4. Treat events marked `transparency: "transparent"` as non-blocking (free/available).
5. If there's any conflict, pick a different slot. Do not schedule on top.
6. **For any conflicting recurring event:** before adapting your slot to it, run the "check recurrence" procedure above. A biweekly conflict deserves a different response than a weekly one.

## Reading event titles

Read calendar titles **literally**. When a title is ambiguous (`Appointment`, `Block`, `Meeting`), report it as-is — do NOT guess who or what it is for, since the same title can mean many different things. Only treat a title as a specific commitment when the wording is explicit. When in doubt, ask.

## Embedding task/project IDs in event titles

When creating a calendar event for work that corresponds to a tracked task or project, embed the identifier in brackets at the end of the title so "I did the thing on my calendar today" resolves mechanically via regex (`\[task-\d{8}-\d{3}\]` or `\[proj-\d{8}-\d{3}\]`):

- `Course: Module Lesson - D2 [task-YYYYMMDD-NNN]`
- `Project: Session Block (example) [proj-YYYYMMDD-NNN]`
- `⭐ [AA-S] Complete important task [task-YYYYMMDD-NNN]` (focus-task format)

Prefer the task ID when the event maps to one specific task. Project ID is acceptable for umbrella practice blocks where each session maps loosely to 1–2 tasks. The `✅` completion-sync section below relies on this convention.

## Common failure modes (don't repeat these)

- **Filtering `list_events` by `fullText` and trusting the result for conflict checks.** A `fullText: "course-name"` query returns only matching events. It will NOT show the All-Day Event, Appointment, Pickup appointment, In-Office work blocks, or any other event on the same day. `fullText` is for *finding events to update or delete*, never for *finding conflicts*. For conflict checks, re-pull the day with NO `fullText` filter.
- **Only checking the target hour.** A 9 AM–2 PM field trip blocks 11 AM. Check the whole day.
- **Assuming "10 AM free" means "11 AM free".** A 10–11 AM meeting might be followed by a 11 AM–12 PM travel block. Check both.
- **Ignoring travel/prep blocks.** Travel to/from an appointment is a real event; don't overlap.
- **Ignoring recurring events on work calendar.** recurring planning, team meetings, and 1:1s live on the work calendar.
- **Ignoring schedule-pattern blocks.** `0-me/schedule-patterns.md` lists fixed weekly blockers (e.g. Friday noon – 1 PM "Standing meeting" weekly). These ARE on the calendar, but read the patterns doc first so you know what to expect — it's faster than discovering them mid-conflict.

### Scar reference: a real batch-scheduling incident

Symptoms: scheduled 17 new lunch/weekend events without per-day conflict checks. 6 of 17 landed on top of existing events (All-Day Event 9–14, Recurring Friday blocker 11:45–12:45 ×3, In Office 9–14 ×2). Root cause: used `fullText: "course-name"` filters to plan and assumed those results were exhaustive — they were not. Lesson: when batch-creating events, the conflict pull is **per-target-date, no filter, both calendars**, even if it's slow.

## Algorithm for finding a slot

Given a target duration (e.g., 1 hour) on date `D`, and a preferred time (e.g., 10 AM):

1. Fetch the full day from both calendars.
2. Build a list of `[start, end]` blocks from all **non-transparent, non-all-day** events.
3. Try the preferred time first. If it overlaps any block, try:
   - The earliest free 1-hour window starting ≥ 8 AM
   - If nothing fits between 8 AM and 5 PM, push to the next weekday and retry.
4. If the whole day is blocked, skip it entirely and shift the series.

## For batch scheduling (e.g., course series, multi-week reschedules)

This is the **mandatory** sequence when creating more than ~3 events at once. Skipping any step is what produces the scar above.

1. **Read `0-me/schedule-patterns.md`** to know fixed blockers (office days, recurring weekday blockers, all-day events).
2. **Pull both calendars for the full date range, with NO `fullText` filter.** Primary + work (`<your-work-calendar-id>@group.calendar.google.com`). If the response is truncated, pull per-day or per-week.
3. **Build a proposed schedule offline** — date, start, end, task ID — and run the per-day conflict check (`E_start < T_end AND E_end > T_start`) for every proposed event against every existing event on that date from BOTH calendars.
4. **Show the user the full proposed schedule** (table: date · time · summary · "free" or "conflict with X") BEFORE creating any events. Wait for confirmation. This is the single most important step — once events are created, fixing them is several times more work than running the check.
5. Only after confirmation: create the events.
6. **Verify after creation:** re-pull each target date with NO `fullText` filter and confirm zero overlaps. If any, fix before reporting "done."

If a slot has no clean window the same day, push the task to the next available day rather than scheduling on top.

## Verification after creation

After batch-creating events, re-pull every target date (no `fullText` filter, both calendars) and confirm no overlaps. If any exist, fix them before reporting "done." Spot-checking 3 random days is not enough for batches > 10 — check all of them.

## Focus-task scheduling

The 2+1 lands on the calendar via a **recurring anchor slot** (one event per day — pick times that fit your week, e.g. weekday late-afternoon, weekend morning). The evening check-in annotates **tomorrow's** anchor instance with tomorrow's pre-committed tasks; no per-task events are created.

**Every 2+1 change re-annotates that day's anchor (mandatory).** Any time the 2+1 for a date is set, re-picked, or has a single slot swapped — night-before flow OR an ad-hoc same-day change — update that date's specific anchor instance (`<seriesId>_<YYYYMMDD>T…`) so its description matches `daily-focus.ndjson`. The calendar must never show stale picks after a 2+1 write.

The standalone `pfc-schedule-focus` skill remains available for manual placement when a specific task needs a dedicated time block outside the anchor (e.g. invoked by `pfc-revive` for a reschedule). Its slot-finder (`automations/scripts/find_focus_slots.py`) enforces:

**Allowed windows (your local timezone — defaults shown):**
- Weekdays (Mon–Fri): 8–9 AM, 12–1 PM, 5–9 PM
- Weekends (Sat/Sun): 8 AM – 9 PM

Work hours (default 9 AM – noon, 1–5 PM — edit to match your schedule) are excluded on weekdays — personal tasks should not land during work, except at lunch.

**Durations by task size (calendar block):** XS = 15 min · S = 15 min · M = 30 min · L = 60 min · XL = 120 min · null → M.

A 15-minute floor applies to every placement (`MIN_SLOT_MINUTES` in `find_focus_slots.py`). XS tasks represent ~5 minutes of effort but still get a 15-minute calendar block — tiny events are hard to see and easy to miss.

**Title format:** `⭐ [AA-S] {description} [task-id]` (critical) or `Bonus: [AA-S] ...` (bonus). `AA-S` encodes impact + urgency + size, with impact/urgency mapped high→A, medium→B, low→C (same scheme as Gmail priority labels).

**Color:** all PFC-scheduled events use banana (`colorId: "5"`). One color is the visual signature that an event came from the PFC system — never vary by tier. The title prefix (`⭐ ` for critical, `Bonus: ` for bonus) carries the tier distinction.

**Event IDs** are persisted in `6-tasks/_data/daily-focus.ndjson` under `calendar_events`, so carry-forwards can move the same event rather than duplicate it.

When in doubt, re-run `pfc-schedule-focus` — it's idempotent: updates existing events, creates missing ones, deletes orphans of swapped-out tasks.
