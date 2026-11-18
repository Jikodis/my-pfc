# Docs

Cross-cutting system documentation. If you're trying to understand how the PFC system works (rather than how to *use* a specific feature), the docs you want are in here. Per-feature usage lives in the skill files (`.agents/skills/pfc-*/SKILL.md`).

## Top-level docs

| File | What it covers |
|---|---|
| [`system-map.md`](system-map.md) | The one-page picture of the whole system — how the layers nest and when you touch each one. Start here. |
| [`architecture.md`](architecture.md) | How the pieces fit together: the repo, Claude Code, automations, the VPS, and the surfaces that show the repo (web UI, Trello, TRMNL, reMarkable, Claude Duet) |
| [`data-model.md`](data-model.md) | Canonical schemas for every typed record — tasks, habits, projects, day-tracking, insights, hypotheses, findings, supplements |
| [`calendar-scheduling.md`](calendar-scheduling.md) | Hard rules for any agent creating/moving calendar events. Read this before doing any batch scheduling. |
| [`cadences.md`](cadences.md) | The evening spine, rolling reviews, quarterly + yearly rhythms |
| [`conventions.md`](conventions.md) | File-format conventions — NDJSON, schemas, ID formats |
| [`automation-policy.md`](automation-policy.md) | Commit policy and safety rules for automation scripts |
| [`workflows.md`](workflows.md) | Flow diagrams: values to tasks, the evening spine, rolling reviews, hypothesis testing |
| [`trello-dashboard.md`](trello-dashboard.md) | Trello board reference: every list, the render triggers, the card conventions |
| [`trmnl-plugins.md`](trmnl-plugins.md) | TRMNL e-ink dashboard — which repo data feeds which screen, transports, deploy loop |
| [`remarkable.md`](remarkable.md) | Optional reMarkable pages: the home page, the due review and the task list on a tablet, and how the server timer reads the ink |
| [`ai-news.md`](ai-news.md) | Optional AI News: filtered posts from AI blogs as reMarkable EPUBs and a private podcast feed |
| [`habit-mechanics.md`](habit-mechanics.md) | How habits start, recover and retire: the ramp, never miss twice, habits that log themselves |
| [`ideas.md`](ideas.md) | Backlog of ideas for the system itself (skills, automations, surfaces), not life tasks |
| [`duet/pfc-operator/SKILL.md`](duet/pfc-operator/SKILL.md) | Operating guide for running the system from a Claude Duet thread |

## Install guides

The `install/` subfolder holds tier-by-tier setup guides:

| File | Tier | What it sets up |
|---|---|---|
| [`install/connectors.md`](install/connectors.md) | 2 | Google Calendar + Gmail MCP connectors |
| [`install/google-health.md`](install/google-health.md) | 2 | Google Health API for sleep / activity auto-fetch |
| [`install/local-automations.md`](install/local-automations.md) | 2 | Cron-based health fetch on your own machine |
| [`install/trello.md`](install/trello.md) | 2 | Trello dashboard board + widgets + completion sync |
| [`install/web-ui.md`](install/web-ui.md) | 2 | Optional local web UI at `http://127.0.0.1:4323` as a macOS launch agent |
| [`install/daily-sync.md`](install/daily-sync.md) | 2 | Optional Mac launch agent that runs the Trello, inbox and calendar syncs each morning |
| [`install/vps.md`](install/vps.md) | 3 | VPS with systemd timers for 24/7 automation |
| [`install/trmnl-endpoint.md`](install/trmnl-endpoint.md) | 3 | TRMNL polling endpoint on the VPS (optional e-ink dashboard) |
| [`install/remote-access.md`](install/remote-access.md) | 3 | Termius + tmux + Claude Code Remote Control for phone access |

## How to read these docs

- **Just installed?** Follow the README at the repo root → `/pfc-onboarding` → install guides in order of tier you want.
- **Building a skill?** Read `architecture.md` and `data-model.md` first. Then look at an existing skill that does something similar.
- **Touching the calendar?** `calendar-scheduling.md`. Non-negotiable.
- **Adding new typed records?** `data-model.md` for shape; `conventions.md` for naming.

## See also

- Repo-root [`AGENTS.md`](../AGENTS.md) — the master rule file that points at most of these docs.
- [`.agents/skills/`](../.agents/skills/) — per-feature usage.
