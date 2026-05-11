# Visions

Visions sit between **Areas** and **Projects** in the system (V → A → **V** → P → A → H, "VAVPAH"). They're the layer that lets you express direction without forcing a SMART goal or deadline.

A vision answers: *what does this look like when it's true, and what habits/projects increase the probability of getting there?*

Examples:
- "Ship a side project"
- "Build a meaningful long-term relationship"
- "Build a home that runs on systems instead of effort"

Anti-pattern: SMART goals like "Be promoted to Staff Engineer by 2027-Q3." Visions don't carry deadlines.

## Properties

- Each vision belongs to **one** area (must match a folder under `2-areas/`).
- **0–2 visions per area** at any time. Most areas have zero. Total kept low.
- Lifecycle: `active` / `paused` / `fulfilled` / `abandoned`. **No deadline field, ever.**
- Projects and habits **may** declare a `vision:` link in their metadata. Optional but encouraged.
- Locus of control matters — outside-control visions only have leading indicators, never deadlines.

## File layout

- One vision per markdown file: `3-visions/<slug>.md`
- Use `_template.md` as the starting point.
- `passion-brainstorm.md` lives here too — annual or on-demand exercise that feeds vision creation.

## Adding a vision

Use `/pfc-add-vision`. The skill walks through every required part — statement, area, why, fulfilled state, locus of control, leading indicators.

## Maintenance

- Reviewed during `/pfc-weekly-checkin` and surfaced by `/pfc-system-health` when an active vision has zero linked projects or habits (a vision with no leading indicators is drifting).
- A vision with no progress for a long stretch isn't necessarily failing — direction without "progress" is a valid state. But absence of *any* leading indicators in linked projects/habits **is** drift.

## Why this exists — the design rationale

ADHD and autism (and many other executive-function variants) make multi-year planning hard to reason with. SMART goals and "by [date] I will X" tend to actively backfire for the target audience — they create deadline anxiety without producing the work. The fix is to express direction differently: values + area statements outrank everything, and visions bridge values to concrete project/habit work *without the deadline scaffolding*.

If deadlines work well for you, you may not need this layer — visions are optional. Skip the folder entirely or run with one or two and treat them lightly. The system tolerates whichever cadence fits you.

Full reasoning lives in [`../0-me/working-with-me.md`](../0-me/working-with-me.md) § Long-term vision.

## Agent operations

If you're an agent reading or writing vision files, see [`AGENTS.md`](AGENTS.md) at this level for the enforcement rules (no deadline field, 0–2 per area cap, drift detection).
