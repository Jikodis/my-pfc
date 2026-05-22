# 4 · Focus

The **Focus** layer of VAVFPAH — the quarter-horizon band between **Vision** (years) and **Habit** (a day). It holds the scarce, capped, traffic-lit set of what you're actively pursuing *right now*.

Visions answer *where am I headed*. Habits answer *what's today's rep*. Neither answers *what am I actually on this season* — that's this folder.

- Data: [`_data/focus.ndjson`](_data/focus.ndjson) — one record per active or retired focus. Ships empty; fill it with `/pfc-focus`.
- Managed by `/pfc-focus` (view · add · park · graduate · retire · quarterly re-pick).
- Surfaced in the daily check-in as a read-only trickle, and rendered to the `🎯 Current Focus` Trello list if you use the dashboard.
- Schema: [`../config/focus_schema.yaml`](../config/focus_schema.yaml). Tier caps: [`../config/focus.yaml`](../config/focus.yaml).

## The three tiers

| Tier | What it holds | Cap |
|---|---|---|
| 🧱 Foundations | Always-on keystones — the things that have become automatic and hold everything else up | soft ~4 |
| 🎯 Active Pursuits | This quarter's push — the deliberate, effortful set | **hard 6** |
| 🎧 Currently Consuming | What you're reading / listening to right now | book 1 · podcast 3 · audiobook 1 |

The hard cap of 6 pursuits is the feature, not a limitation. A list of 20 "focuses" is a list of zero. When a 7th thing wants in, something has to be retired, parked, or graduated to a Foundation first.

## Traffic light

Every focus carries a `status` that is **derived, never hand-typed**: `automations/scripts/focus_status.py` computes it from the primary vehicle habit's trailing-28-day completion rate — 🟢 ≥70% · 🟡 40–69% · 🔴 <40%. Red means **not happening**. A deliberate stop is `parked: true` (renders 🅿️): parked focuses stay on the list, free a pursuit slot, and are exempt from the two-red-weeks forcing function. Deleting is what makes something silently disappear and then resurface six months later as guilt; parking keeps it honest.

Every active foundation and pursuit also declares `habits: [...]` — its **vehicle habits** from `config/habit_schema.yaml`, first one primary. The vehicle is what makes the focus measurable; a focus with no vehicle displays green forever while nothing happens. See [`../docs/habit-mechanics.md`](../docs/habit-mechanics.md).

## Landing — when and where it actually happens

The `landing` field is the *when / where / trigger* for a pursuit: the running state it bends out of, the place, and the ritual that starts it ("after the morning walk, at the kitchen table, headphones on"). Anchor it to something already running rather than a bare clock time — an anchored slot survives a day that runs late; a clock slot doesn't. See [`../docs/calendar-scheduling.md`](../docs/calendar-scheduling.md) § The anchor rule.

**A pursuit with no landing is a wish.** The reviews flag it.

## Graduation and retirement

- A pursuit that has become automatic → move `tier` to `foundation`. This frees a pursuit slot, which is the reward for making something stick.
- Finished or abandoned → set `retired_date`. The record stays in the file as history but drops out of the render and the caps.

## Record shape

Two examples of the shape (both generic — your file starts empty):

```json
{"id":"focus-20250101-001","tier":"pursuit","area":"learning","title":"Learn Spanish","medium":null,"link":{"type":"vision","ref":"conversational-in-a-second-language"},"status":"green","quarter":"2025-Q1","landing":"After the morning walk, at the kitchen table — 20 min of the app, headphones on","habits":["study-spanish"],"impact":"medium","urgency":"medium","parked":false,"created":"2025-01-01","retired_date":null,"notes":null}
{"id":"focus-20250101-002","tier":"consuming","area":"learning","title":"Deep Work","medium":"book","link":null,"status":"green","quarter":"2025-Q1","landing":"Ten pages before bed","habits":[],"impact":"low","urgency":"low","parked":false,"created":"2025-01-01","retired_date":null,"notes":null}
```

Every focus names exactly one `area` matching a folder under `2-areas/` — that's the backbone, and nothing floats. The `link` to a vision, habit, or project is optional: record it only when it's real, one hop up, never invented.

## Cadence

| When | What |
|---|---|
| Daily | Read-only surfacing in the check-in — keeps the list in perception so a pursuit can't quietly go invisible |
| Weekly | Drift check: did anything silently die? Any pursuit missing a landing? |
| Monthly | Shown next to the vision review so the two altitudes are visible together. Informational — no forced swaps |
| Quarterly | The re-pick: keep / ease / pause / retire / graduate each pursuit, refresh landings, bump the `quarter` tag |

## Agent operations

See [`AGENTS.md`](AGENTS.md) at this level for the write rules (jq-only, atomic temp file, cap enforcement, date stamping).
