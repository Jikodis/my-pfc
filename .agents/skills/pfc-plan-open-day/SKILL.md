---
name: pfc-plan-open-day
description: Plan a wide-open day (Saturday, holiday, PTO) as a chained sequence of calendar blocks. Use when the user says "plan my Saturday", "plan my day", "open day", "wide open day", "I have a whole day free", "help me plan tomorrow", or when the evening check-in detects a wide-open day tomorrow.
---

# Plan Open Day

Turns a wide-open day into a **chain of calendar blocks where each block starts out of the one before
it** — sized honestly against the day's real free hours, with every cut named out loud.

## Why the chain matters more than the list

An open day fails differently than a structured one. On a workday, each thing bends out of the thing
before it; on an open day every block is a cold start, and for an initiation-limited brain a cold
start reliably loses to "not worth it." A written list of ten things is an invisible object, not a
trigger.

So: **any two adjacent blocks must have a stated transition.** A block with no anchor will not fire, no
matter how much the user wants it.

---

## Step 0 — Derive the date (CRITICAL)

```bash
TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'
TZ="${LOCAL_TZ:-America/Denver}" date '+%H:%M'
```

Use these as `DATE` and `NOW`. Never trust `currentDate`. Accept an optional date argument
(`/pfc-plan-open-day 2025-01-11`); default to today.

If Calendar connector tools aren't available, say so and stop — this skill has no useful output
without them.

---

## Step 1 — Read the day's shape

`list_events` for `DATE` on every in-scope calendar (see `docs/calendar-scheduling.md` § "Calendars in
scope").

**Fetch the day fresh, every run — never reuse a calendar response saved earlier in the session.** The
user edits their own calendar between turns, and a snapshot minutes old can already be wrong. A stale
hard block corrupts every downstream block in the chain.

Extract:

| Signal | How to read it |
|---|---|
| **Hard blocks** | Timed, not `transparency: transparent`. Fixed points the chain must clear. |
| **Travel** | Any hard block with a `location` away from home implies a departure block before and a return block after. **Budget both explicitly** — an unbudgeted 30-minute drive is what turns a workable chain into a missed start. |
| **Family patterns** | All-day markers for family arrangements (kids away / visitors present) change how open the day really is and whether evenings are protected. |
| **All-day markers** | Context, not blocks. **Verify anything that would change the plan's shape** — these go stale. |

Also read `0-me/schedule-patterns.md` for fixed weekly patterns.

---

## Step 2 — Read the state, set the ceiling

```bash
tail -3 data/day-tracking.ndjson | jq -c '{date, rating, sleep: .health.sleep_hours, awake: .health.awake_minutes}'
```

Read **fragmentation, not just hours**, and read the trailing three days — consecutive short nights
compound. The ceiling is a hard input to Step 5, not a footnote:

| State | Ceiling |
|---|---|
| Rested, exercised | 2–3 substantial blocks |
| One short or fragmented night | 1 substantial block + errands |
| Multiple short nights | 1 substantial block, and exercise goes first |

On a depleted day, morning exercise is scheduled **before anything else** — it is the state-change
lever everything downstream is priced off. Never frame a lowered ceiling as a discipline problem — it
is a gauge reading.

---

## Step 3 — Pull the system's claims

Ground the day in what the user said their life is for, not just what is loudest.

### 3a — Monthly habits behind pace

Check `7-habits/_data/habits-monthly.ndjson` against each monthly habit's `frequency`. A behind-pace
monthly habit that needs a bookable time slot (a class, a visit, an appointment-style commitment) is a
**gate**: booking it becomes the first block of the day, and the rest of the chain is built around
whichever slot comes back. On a genuinely open day, surface a behind-pace monthly commitment above
ordinary task picks — open days are when it actually fits.

### 3b — Current Focus

```bash
jq -c 'select(.retired_date == null) | {title, tier, status, area, landing}' 4-focus/_data/focus.ndjson
```

Show foundations and pursuits. **Flag pursuits that haven't been touched recently** — "you haven't
touched the course in three weeks, and an open Saturday is where it fits." Derive recency from
recently-completed tasks in the matching area.

### 3c — Tasks

```bash
jq -c 'select(.status=="open" and (.deferred // false | not)) | {id, description, impact, urgency, size, area, project, deadline}' 6-actions/_data/tasks.ndjson
```

Surface: top items by impact/urgency, anything with a near deadline, and **anything carried in
`daily-focus.ndjson` for 3+ days**. A carried item is a stuck item — it gets a real block or an honest
cut, never another quiet re-listing.

### 3d — Reviews and projects

Due count from `data/review-ledger.ndjson`; active projects from `5-projects/_data/projects.ndjson`.

---

## Step 4 — Show the menu, then take the rattle-off

Present Step 3 as **one table**, then ask what else the user wants. The freeform adds are the point of
this step — a haircut, a friend's project, a walk — none of which exist in the system yet.

**What becomes a task (judgment, not a rule):**

| Kind | Action |
|---|---|
| Errand with a real outcome that nags until done (haircut, oil change) | Create a task |
| Work against an existing pursuit or project | No task — already represented one layer up |
| One-off want with nothing to track (a walk, a call) | Plan-only block |

Ask only when genuinely ambiguous. Do not fill the backlog with noise.

---

## Step 5 — Capacity math and the honest cut

**This is the step that makes this skill different from `/pfc-pick-tasks`. Do not skip it.**

1. Total the free hours: now (or wake time) → first hard block, plus gaps, **minus travel**.
2. Total the asks at realistic durations, including setup and travel.
3. State the overage in plain numbers: *"nine hours of wants into five hours forty."*
4. Cut to fit, ranked by the system's claims — foundations and stated must-dos survive, the rest is negotiable.
5. **Name every cut explicitly, with the reason.** A silently dropped item reads as "we covered
   everything" and is a defect. *"The course loses to a 5 PM commitment and 5.5 hours of sleep, not to
   being unimportant."*

If the must-do set still doesn't fit, push back **once** with the numbers. If the user reaffirms,
build it and say plainly what will be tight.

---

## Step 6 — Build the chain

- **30–60 minutes** per block; up to **2 hours** for one protected deep-work block.
- **Never plan to 15 minutes.** Sub-30-minute blocks read as noise and don't get executed.
- **Transitions get their own blocks** when they involve a state change: drives, showers, changing
  clothes. This is where open days actually break.

Every block description carries:

- **The anchor**, written as an instruction, not a description: "Leave straight from lunch — do not sit
  down at the computer first," not "after lunch."
- **Music ON** (or the user's equivalent low-effort starter ritual) before any low-reward block —
  before, never after stalling. When a drive precedes the block, start the music in the car so it is
  already running on sit-down.
- **Hard stops** where a later fixed point demands one.

---

## Step 7 — Confirm, then write to the calendar

Show the full chain as a table. **Get a yes before any write.**

Then:

1. **Move the day's `PFC - 🎯 2+1 anchor` instance into the chain — never delete it.** The 2+1 still
   exists on an open day; it just stops being a separate 30-minute container off to one side. Update the
   instance (`<seriesId>_<YYYYMMDD>T…`) so it *becomes* the block where critical 1 actually happens:
   retime it to that block, title it `PFC - 🎯 2+1: <critical 1 gist>`, and list all three picks in the
   description with a note of where each one lands in the day. Then build every other block around it.

   Criticals that land inside an existing commitment get their **own** block at that time, and the
   anchor description points at it. Never `delete_event` an anchor instance, and never let an open day
   end up with no `daily-focus` record.
2. `create_event` per block on the **primary** calendar:
   - Title: `PFC - {emoji} {activity}` — the literal `PFC - ` prefix first, always.
   - `colorId: "5"` (banana) — the PFC visual signature.
   - `description`: anchor + starter ritual + hard stop.
   - `location` on any block involving travel.
3. Titles carry the **actual activity**, so the day is readable from the calendar alone.

Fail-safe per call: log `🟡 Calendar write failed for <block> (non-blocking): <error>` and continue.

---

## Step 8 — Persist and commit

**The calendar is the plan. No new NDJSON file.**

- Tasks created in Step 4 → append to `6-actions/_data/tasks.ndjson` via `jq`.
- Leave `daily-focus.ndjson` alone.

```bash
scripts/validate.sh
git add -A && git commit -m "focus: plan open day $DATE" && git push
```

Then run the bare Trello render as a fail-safe end-step (any error logs 🟡 and continues):

```bash
python3 automations/scripts/trello_render.py
```

---

## Triggering

1. **Manual** — `/pfc-plan-open-day [date]`.
2. **The evening check-in the night before** — `pfc-evening-checkin` detects a wide-open tomorrow and
   offers to build the plan then. This is the real fix: a morning intention to run this skill goes
   invisible overnight, while a plan built the evening before already exists at wake-up.

## What this skill does NOT reuse

`automations/scripts/find_focus_slots.py` fits fixed-size tasks into calendar gaps. This needs the
opposite — a contiguous chain sized to fill the day. Calendar conventions from `pfc-schedule-focus`
carry over; the slot-finder does not.
