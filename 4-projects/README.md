# Projects

Short-term efforts (1–3 months) that move you toward a vision or area outcome. The "deliberate work" layer of VAVPAH — bigger than a single task, smaller than a life direction.

## What lives here

- **Registry** (`_data/projects.ndjson`) — one record per project with status, area, optional vision link, percent complete, parts-completed count.
- **Project markdown files** (`<slug>.md` at the top of this folder) — plans, breakdowns, notes for the projects that need more thinking than fits in the NDJSON record. Optional; lightweight projects don't need a markdown file.

## The 3-active rule

You can have at most **3 projects in `active` status at any time.** The cap exists because attention is finite — adding a fourth dilutes the energy on all three you already had. When a fourth project becomes urgent, something else has to move to `paused` or `done`.

The validator enforces this. Trying to mark a fourth project active will fail until you resolve the conflict.

## Lifecycle

| Status | Meaning |
|---|---|
| `active` | Currently being worked. Max 3. |
| `planned` | Scoped but not started. No cap. |
| `paused` | Deliberately set aside with a documented "when to resume" trigger. |
| `done` | Completed. |
| `archived` | Abandoned or superseded — not the same as `done`. |

## Optional vision link

A project may declare a `vision:` field pointing to a vision slug under `3-visions/`. When set, the system can detect drift — a vision with zero linked projects or habits is flagged during weekly check-in as direction-without-leading-indicators.

## Velocity tracking

Projects with `total_parts` and `completed_parts` get an automatically computed completion velocity surfaced in the morning and evening check-ins. The system compares the projected completion date against the project's `deadline` and flags any slippage.

## Key skills

| Skill | What it does |
|---|---|
| `/pfc-add-project` | Register a new project |
| `/pfc-summarize-project` | Status, completion %, velocity, next actions |
| `/pfc-pick-tasks` | Surface project-aligned tasks |
| `/pfc-morning-checkin` | Daily project status block |
| `/pfc-evening-checkin` | End-of-day project velocity update |

## Agent operations

If you're an agent reading or writing project records, see [`AGENTS.md`](AGENTS.md) at this level for the operational rules (jq patterns, velocity math, 3-active enforcement).
