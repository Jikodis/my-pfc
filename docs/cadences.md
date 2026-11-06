# System Cadences

How and when the productivity system is used. These cadences keep you grounded, focused, and moving forward.

## Daily — the tour, any time

The daily loop is one guided tour on the web page (`http://127.0.0.1:4323/`, the `Walk me through` button). It runs whenever you open it; there's no fixed morning or evening ritual. Each step can be skipped.

| Activity | When | What happens |
|---|---|---|
| The tour | Any time | Rate a day (yesterday before about 6 PM, today after; energy, mood, focus → derived rating), a body check (sleep, exercise, habit ticks), what needs you (the top 1–2 urgent items, else at most 1 due rolling review), the 2+1 picks (the rest of today, tomorrow's after 6 PM), and one focus with its vision and value, rotating daily — keeps long-running interests (e.g. an instrument, a language) in perception. |
| Rolling reviews | → part of the tour, or `/pfc-review` | At most 1 due item from `data/review-ledger.ndjson` shows in the tour, only when nothing urgent is listed; tapping it opens its owning skill and stamps it. See "Rolling Reviews" below. |
| Daily sync job | Early morning (`scripts/daily-sync.sh`) | Pulls Trello completions into the repo, runs the Gmail inbox-to-task reconcile, and refreshes `data/calendar-cache.json`. See [`install/daily-sync.md`](install/daily-sync.md). |
| Habit logging | Throughout day | Log daily habit completions as they happen (the page's `Log today` buttons, the Trello widget, or `/pfc-log-habit`). |
| Insight capture | Throughout day | Capture observations / noticings via `/pfc-add-insight`. Lower bar than findings. |
| Open-day plan | Friday or Saturday after 6 PM, or on demand | When tomorrow is a weekend / holiday / PTO day with under ~2 h of hard commitments, the tour's picks step offers `Plan tomorrow as an open day`, which runs `/pfc-plan-open-day`. It lays the whole day out as a chain of calendar blocks — each anchored to the one before it — sized against real free hours, with the 2+1 placed inside the chain. |

## Rolling Reviews

The old weekly, monthly, and quarterly ritual check-ins are gone. Their review work is now a **rolling ledger** (`data/review-ledger.ndjson`). Each item carries a `cadence_days` and a `last_done`; it becomes due once `today − last_done ≥ cadence_days`.

- **One a day in the tour.** The tour's What needs you step shows at most **1** due item (never-done first, then most overdue; `automations/scripts/home_data.py`), and only when nothing urgent is listed. It is a button that opens the item's owning skill (`/pfc-revive`, `/pfc-focus`, `/pfc-insights`, `/pfc-analyze-trends`, life-wheel rating, etc.) in the chat drawer; tapping it stamps `last_done` to today. Ignoring it lets it re-surface on cadence.
- **The catch-up.** `/pfc-review` runs the **same** ledger with **no cap** — every currently-due, actionable item in one deliberate sitting, tier-ordered (weekly → monthly → quarterly). Use it when reviews have piled up.

The former weekly items (stale-task triage, tasks-missing-area, focus accuracy, vision relevance, habit rates, values alignment, day-trend peek), monthly items (life wheel, project progress, vision activation, monthly habits, insights review, trend analysis, revive outcomes, usage audit — the "is the system being used" check: data freshness, possibly-unused surfaces, logging gaps), and quarterly items (Focus re-pick, vision brainstorm, strengths refresh) all live in the ledger. The gate logic and owning-skill map are canonical in the `pfc-review` skill.

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
- **Flexible cadences.** These are guidelines, not obligations. Skipping the tour or letting a review sit is fine — the ledger just re-surfaces it on cadence, and the system is here to help, not to judge.
