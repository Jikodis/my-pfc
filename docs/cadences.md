# System Cadences

How and when the productivity system is used. These cadences keep you grounded, focused, and moving forward.

## Daily — the evening spine

The daily loop is one ritual: the evening check-in. It closes out today and pre-commits tomorrow, so there's no separate morning ritual to remember.

| Activity | When | What happens |
|---|---|---|
| Evening check-in | End of day | Run `/pfc-evening-checkin`: rate/log today (energy, focus, mood → derived rating), log supplements, walk the habit tracker, run the rolling reviews (≤2 due items), trickle Current Focus into view, then pick tomorrow's 2+1 and annotate tomorrow's anchor slot. |
| Rolling reviews | → part of evening check-in | At most 2 due-and-actionable items from `data/review-ledger.ndjson` surface per night, most-overdue first. Each is a one-line pointer at its owning skill. See "Rolling Reviews" below. |
| Current Focus trickle | → part of evening check-in | Read-only display of Foundations + 🟢 Pursuits with landings — keeps long-running interests (e.g. an instrument, a language) in perception before picking tomorrow's 2+1. Manage via `/pfc-focus`. |
| Set tomorrow's 2+1 | → part of evening check-in | Pick 2 critical + 1 bonus (+ optional project slot) for tomorrow and annotate tomorrow's anchor-slot calendar instance. |
| Habit logging | Throughout day | Log daily habit completions as they happen. |
| Insight capture | Throughout day | Capture observations / noticings via `/pfc-add-insight`. Lower bar than findings. |
| Open-day plan | The evening before, or on demand | When tomorrow is a weekend / holiday / PTO day with under ~2 h of hard commitments, the evening check-in offers `/pfc-plan-open-day`. It lays the whole day out as a chain of calendar blocks — each anchored to the one before it — sized against real free hours, and replaces that day's 2+1 rather than sitting beside it. |

## Rolling Reviews (folded into the evening)

The old weekly, monthly, and quarterly ritual check-ins are gone. Their review work is now a **rolling ledger** (`data/review-ledger.ndjson`). Each item carries a `cadence_days` and a `last_done`; it becomes due once `today − last_done ≥ cadence_days`.

- **The evening drip.** The evening check-in surfaces at most **2** due items per night — only ones that both are due AND have something to act on — pointing at each item's owning skill (`/pfc-revive`, `/pfc-focus`, `/pfc-insights`, `/pfc-analyze-trends`, life-wheel rating, etc.). A no-review night stays fast. Engaging with an item stamps its `last_done` to today; ignoring it lets it re-surface on cadence.
- **The catch-up.** `/pfc-review` runs the **same** ledger with **no cap** — every currently-due, actionable item in one deliberate sitting, tier-ordered (weekly → monthly → quarterly). Use it when reviews have piled up.

The former weekly items (stale-task triage, tasks-missing-area, focus accuracy, vision relevance, habit rates, values alignment, day-trend peek), monthly items (life wheel, project progress, vision activation, monthly habits, insights review, trend analysis, revive outcomes, usage audit — the "is the system being used" check: data freshness, possibly-unused surfaces, logging gaps), and quarterly items (Focus re-pick, vision brainstorm, strengths refresh) all live in the ledger. The gate logic and owning-skill map are canonical in the `pfc-evening-checkin` skill.

## Quarterly

| Activity | When | What happens |
|---|---|---|
| Current Focus re-pick | Start of each quarter | Run `/pfc-focus` (re-pick): the deliberate swap — for each 🎯 Active Pursuit keep 🟢 / ease 🟡 / pause 🔴 / retire / graduate to a 🧱 Foundation; confirm foundations; build or refresh each pursuit's **landing** anchor-first against the calendar + `0-me/schedule-patterns.md`; bump the `quarter` tag. Respect the hard cap of 6 pursuits. |
| Vision brainstorm | Start of each quarter | Run `/pfc-vision-brainstorm`: dump what you want; triage into visions / projects / focuses / habits. |
| Strengths update | Quarterly | Refresh the strengths/profile picture if new assessments or shifts. |
| Trend analysis | Quarterly | Deeper day-tracking trend pass (also runs monthly + yearly). |

## Yearly

| Activity | When | What happens |
|---|---|---|
| Yearly check-in | Once a year | Run `/pfc-yearly-checkin`: orchestrates all yearly items below. |
| Values review | → part of yearly check-in | Re-read values list. Still accurate? Reorder if priorities have shifted. |
| Area statements review | → part of yearly check-in | Re-read each area statement. Revise any that no longer resonate. Update the year tag. |
| Questions review | → part of yearly check-in | Revisit the questions list. Remove answered ones, add new ones. |
| Vision brainstorm refresh | → part of yearly check-in | 5-minute brainstorm session. Add new items. Move accomplished items to Done. |
| Personality & psychology review | → part of yearly check-in | Re-read `0-me/personality.md` + `0-me/core-psychology.md`. Update anything that no longer reflects current self-understanding. |
| Trend analysis | → part of yearly check-in | Analyze day tracking data for patterns over the past year. Cross-reference with your wearable, habits, and check-in data. Also runs on its monthly cadence as the `trend-analysis` rolling-review item (`/pfc-analyze-trends`). |

## ADHD-Aware Design

- **Stale task triage prevents guilt spirals.** Tasks that sit too long become anxiety triggers. Better to eliminate or re-scope them.
- **Project breakdown reduces overwhelm.** When a project feels too big, break it into the smallest possible next actions.
- **Task breakdown on request.** Any time a task feels daunting, ask Claude to break it into 15-minute chunks.
- **Daily focus limits scope.** Only 3 tasks per day keeps the system from becoming a source of stress.
- **Flexible cadences.** These are guidelines, not obligations. Skipping an evening check-in or letting a review sit is fine — the ledger just re-surfaces it on cadence, and the system is here to help, not to judge.
