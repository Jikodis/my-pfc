# Docs

Cross-cutting system documentation. If you're trying to understand how the PFC system works (rather than how to *use* a specific feature), the docs you want are in here. Per-feature usage lives in the skill files (`.agents/skills/pfc-*/SKILL.md`).

## Top-level docs

| File | What it covers |
|---|---|
| [`architecture.md`](architecture.md) | System architecture — how the pieces fit together (repo, Claude Code, automations, VPS, Trello) |
| [`data-model.md`](data-model.md) | Canonical schemas for every typed record — tasks, habits, projects, day-tracking, insights, hypotheses, findings, supplements |
| [`calendar-scheduling.md`](calendar-scheduling.md) | Hard rules for any agent creating/moving calendar events. Read this before doing any batch scheduling. |
| [`cadences.md`](cadences.md) | The daily / weekly / monthly / quarterly check-in rhythms |
| [`conventions.md`](conventions.md) | File-format conventions — NDJSON, schemas, ID formats |
| [`automation-policy.md`](automation-policy.md) | Commit policy and safety rules for automation scripts |
| [`workflows.md`](workflows.md) | End-to-end workflow examples (typical morning, weekly review, project lifecycle) |

## Install guides

The `install/` subfolder holds tier-by-tier setup guides:

| File | Tier | What it sets up |
|---|---|---|
| [`install/connectors.md`](install/connectors.md) | 2 | Google Calendar + Gmail MCP connectors |
| [`install/google-health.md`](install/google-health.md) | 2 | Google Health API for sleep / activity auto-fetch |
| [`install/local-automations.md`](install/local-automations.md) | 2 | Cron-based local automation scripts |
| [`install/trello.md`](install/trello.md) | 2 | Trello dashboard board + widgets + completion sync |
| [`install/vps.md`](install/vps.md) | 3 | VPS with systemd timers for 24/7 automation |
| [`install/remote-access.md`](install/remote-access.md) | 3 | Termius + tmux + Claude Code Remote Control for phone access |

## How to read these docs

- **Just installed?** Follow the README at the repo root → `/pfc-onboarding` → install guides in order of tier you want.
- **Building a skill?** Read `architecture.md` and `data-model.md` first. Then look at an existing skill that does something similar.
- **Touching the calendar?** `calendar-scheduling.md`. Non-negotiable.
- **Adding new typed records?** `data-model.md` for shape; `conventions.md` for naming.

## See also

- Repo-root [`AGENTS.md`](../AGENTS.md) — the master rule file that points at most of these docs.
- [`.agents/skills/`](../.agents/skills/) — per-feature usage.
