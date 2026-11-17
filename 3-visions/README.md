# Visions

Visions sit between **Areas** and **Focus** in the system (V → A → **V** → F → P → A → H, "VAVFPTH"). They're the layer that lets you express direction without forcing a SMART goal or deadline.

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

## Where visions sit relative to Focus

A vision is a **years** horizon and may rest dormant for long stretches — that's a valid state, not failure. The layer one hop below it, [`4-focus/`](../4-focus/README.md), is the **quarter** horizon: the capped, traffic-lit list of what you're actually on right now. A focus may link up to its vision (`link: {type: "vision", ref: "<slug>"}`) when the connection is real. Most visions won't have a live focus under them at any given moment, and that's fine — you can only push a few things per quarter.

## File layout

- One vision per markdown file: `3-visions/<slug>.md`
- Use `_template.md` as the starting point.
- `_data/vision-brainstorm.ndjson` lives here too — the brainstorm that feeds vision creation (see below).

## Adding a vision

Use `/pfc-add-vision`. The skill covers every required part — statement, area, why, fulfilled state, locus of control, leading indicators. It is **draft-first**: it pre-fills every field from your values, area statement, and existing brainstorm records, then shows you the draft and asks only for edits. Writing a vision statement from a blank page is much harder than reacting to a draft that's already 80% right.

## Vision brainstorm

The brainstorm is the generative exercise that *feeds* visions (and focuses, projects, tasks, habits). It's one record per idea in `_data/vision-brainstorm.ndjson`, so each item carries a lifecycle and a lineage.

**The exercise:** Given 5 minutes, with no judging and no limits, dump everything you want to become, do, see, or have happen. Then sort, categorize, and pick a couple worth pursuing.

**Capture stays frictionless** — you dump free-form (chat or `/pfc-vision-brainstorm`); the skill writes the records. You never hand-author JSON.

**Each record:** `{id, text, created, area, status, became, note}`
- `status`: `raw` (un-acted) · `promoted` (became a vision/focus/project/task/habit) · `done` (already true) · `dropped` (not wanted)
- `became`: `null`, or `{type, ref}` pointing at the vision slug / focus id / project id it graduated into

See what's still latent (un-acted ideas):

```bash
jq -c 'select(.status=="raw")' 3-visions/_data/vision-brainstorm.ndjson
```

Run it quarterly, annually, or whenever the system feels stagnant.

## Maintenance

- **Relevance check** (weekly cadence) — look at an active vision alongside its linked projects, focuses, and habits, and ask only whether it still represents where you want to go. If not → `paused` or `abandoned`. A zero-link vision is *not* by itself drift: with a 3-project cap and a 6-pursuit cap against a larger set of visions, most visions won't have a live leading indicator at any moment.
- **Activation review** (monthly cadence) — list every active vision with its current projects, focuses, and habits so the bare ones stand out, then take a deliberate decision per vision: lean in (start a leading-indicator project or focus, within the caps), let rest, or leave as-is. A dormant vision with nothing under it is a valid state.
- A vision with no progress for a long stretch isn't necessarily failing. The only real drift is a vision that no longer represents where you want to go — caught by relevance, not by counting links.

## Why this exists — the design rationale

ADHD and autism (and many other executive-function variants) make multi-year planning hard to reason with. SMART goals and "by [date] I will X" tend to actively backfire for the target audience — they create deadline anxiety without producing the work. The fix is to express direction differently: values + area statements outrank everything, and visions bridge values to concrete project/habit work *without the deadline scaffolding*.

If deadlines work well for you, you may not need this layer — visions are optional. Skip the folder entirely or run with one or two and treat them lightly. The system tolerates whichever cadence fits you.

Full reasoning lives in [`../0-me/working-with-me.md`](../0-me/working-with-me.md) § Long-term vision.

## Agent operations

If you're an agent reading or writing vision files, see [`AGENTS.md`](AGENTS.md) at this level for the enforcement rules (no deadline field, 0–2 per area cap, brainstorm write rules).
