# Data

Non-VAVPAH state and knowledge — files that don't belong to a specific life-domain folder but are referenced across the whole system.

## What lives here

### Knowledge files — captured observations and durable insights

| File | Purpose | Bar to add |
|---|---|---|
| `insights.ndjson` | Personal observations, revelations, noticings | Low — capture freely throughout the week |
| `hypotheses.ndjson` | Experiments to test against your data | Medium — must be testable, must propose an indicator |
| `findings.ndjson` | Durable, hard-won insights | High — either graduated from a hypothesis (n ≥ 30, statistically supported) or added manually from life experience |

The three files form a maturity ladder: most observations stay as insights, some get formalized into hypotheses worth testing, and a small fraction graduate to findings that shape future decisions.

### State files

| File | Purpose |
|---|---|
| `day-tracking.ndjson` | Daily rating + auto-fetched health data (sleep, AZM, resting HR) |
| `supplements.ndjson` | Baseline supplement / medication registry — what you're currently taking and historical changes |
| `.trello-last-render` | Timestamp of the last Trello dashboard render (used by render-skip logic) |
| `.jq_update.tmp` | Temp file for atomic NDJSON updates — should never persist between runs |

## Key skills

| Skill | What it does |
|---|---|
| `/pfc-add-insight` | Capture an observation |
| `/pfc-add-hypothesis` | Formalize a testable claim |
| `/pfc-insights` | Review insights, decide what to graduate or drop |
| `/pfc-analyze-trends` | Find statistical patterns in `day-tracking.ndjson` |
| `/pfc-log-day` | Add a daily rating entry |
| `/pfc-supplement` | Add/stop/list supplements |

## The insight → hypothesis → finding ladder

This is one of the more deliberate design choices in the system: capture is cheap, validation is expensive, durable knowledge is rare.

- **Insights** flow in casually — anything you noticed, half-thought, or wondered about. No bar.
- **Hypotheses** are insights that you've decided are worth *testing*. They name a pattern and an indicator you can measure.
- **Findings** are hypotheses that have been validated (statistically, or via hard-won lived experience) and now shape future decisions.

The weekly check-in surfaces stale insights for triage. The monthly check-in evaluates hypotheses against accumulated data. Findings rarely move once added.

## Agent operations

If you're an agent reading or writing these files, see [`AGENTS.md`](AGENTS.md) at this level for the operational rules (jq patterns, integrity checks).
