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
| Web home page (optional) | Any time | With the local web UI installed ([`install/web-ui.md`](install/web-ui.md)), `http://127.0.0.1:4323/` runs the same daily loop with buttons: the rating card while the day is unrated, habit Log buttons, today's 2+1 (tomorrow's from 6 PM on), and the one due rolling review. Its writes land in the same files the check-in reads, so a day rated, a habit logged, or tomorrow's picks set on the page are not asked again in the check-in. |
| reMarkable pages (optional) | Every 10 minutes (server timer `pfc-remarkable-sync`) | With a reMarkable set up ([`remarkable.md`](remarkable.md)), `remarkable_sync.py` reads new ink on the tablet pages (Claude only when a page has ink), saves ratings, ticks, picks and area lights through `web_write.py`, sends notes to Trello's 📥 Inbox for `/pfc-trello-inbox`, applies a filled review form, and redraws the pages from `home_data`. |
| Daily sync (optional) | Each morning from 5:00 AM, hourly until one clean run (Mac launch agent `com.pfc.daily-sync`, on with `PFC_DAILY_SYNC=1`) | `scripts/daily-sync.sh` pulls Trello ticks into the repo, turns labeled emails into tasks, refreshes `data/calendar-cache.json`, logs calendar-derived habits, then commits and pushes. The web home page footer shows its last run, and a failed or stale run is listed under What needs you ([`install/daily-sync.md`](install/daily-sync.md)). |
| Trello write-backs | Every Trello sync (the daily sync, `/pfc-sync-trello`, every render) | Ticked tasks and habits land in the repo; the `🦸 Body first` rating card saves the day once each list has one tick; an archived `✅ The 2+1` card drops that pick; before 6 PM a day with no picks gets the home page's suggestions as its 2+1 (`source: "auto"`) ([`trello-dashboard.md`](trello-dashboard.md)). |
| Unattended Trello inbox (optional) | Every 10 minutes (server timer `pfc-trello-inbox`, on with `PFC_TRELLO_INBOX=1`) | `scripts/trello-inbox-auto.sh` runs `/pfc-trello-inbox unattended`: every clear card is carried out and deleted, and an unclear one is renamed `❓ <title>` to wait for an interactive run. |
| AI News (optional) | Daily, 5:30 AM (server timer `pfc-ai-news`) | `ai_news.py` checks the blogs in `config/ai_news.yaml`, keeps the posts that fit your criteria as reMarkable EPUBs and private podcast episodes, and logs each in `data/ai-news.ndjson` ([`ai-news.md`](ai-news.md)). |
| Open-day plan | The evening before, or on demand | When tomorrow is a weekend / holiday / PTO day with under ~2 h of hard commitments, the evening check-in offers `/pfc-plan-open-day`. It lays the whole day out as a chain of calendar blocks — each anchored to the one before it — sized against real free hours, and replaces that day's 2+1 rather than sitting beside it. |

## Rolling Reviews (folded into the evening)

The old weekly, monthly, and quarterly ritual check-ins are gone. Their review work is now a **rolling ledger** (`data/review-ledger.ndjson`). Each item carries a `cadence_days` and a `last_done`; it becomes due once `today − last_done ≥ cadence_days`.

- **The evening drip.** The evening check-in surfaces at most **2** due items per night — only ones that both are due AND have something to act on — pointing at each item's owning skill (`/pfc-revive`, `/pfc-focus`, `/pfc-insights`, `/pfc-analyze-trends`, life-wheel rating, etc.). A no-review night stays fast. Engaging with an item stamps its `last_done` to today; ignoring it lets it re-surface on cadence.
- **One at a time, as a form.** `/pfc-review` runs one due review as a short form, applies the answers, and offers the next; keep saying "next" to clear a backlog. The web UI's `/review` page shows the same review (`automations/scripts/review_forms.py` picks it: never done first, then most overdue, skipping one with nothing to ask), and its Save button sends the answers to `/pfc-review` in the chat drawer. The home page's "What needs you" card names it.

The former weekly items (stale-task triage, tasks-missing-area, focus accuracy, vision relevance, habit rates, values alignment, day-trend peek), monthly items (life wheel, project progress, vision activation, monthly habits, insights review, trend analysis, revive outcomes, usage audit — the "is the system being used" check: data freshness, possibly-unused surfaces, logging gaps), and quarterly items (Focus re-pick, vision brainstorm, strengths refresh) all live in the ledger. The nightly gate logic and owning-skill map are in the `pfc-evening-checkin` skill; the one-at-a-time pick and each review's form are in `automations/scripts/review_forms.py`.

## Quarterly

| Activity | When | What happens |
|---|---|---|
| Current Focus re-pick | Start of each quarter | Run `/pfc-focus` (re-pick), the deliberate swap: for each 🎯 Active Pursuit keep, park, retire, or graduate to a 🧱 Foundation (the light is derived from the vehicle habit, never hand-set); confirm foundations; build or refresh each pursuit's **landing** anchor-first against the calendar + `0-me/schedule-patterns.md`; bump the `quarter` tag. Respect the hard cap of 6 pursuits. |
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
