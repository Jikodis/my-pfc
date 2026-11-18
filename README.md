> Generated from modular-pfc commit `3b13d2d` on 2026-11-17.

# PFC — Personal Productivity System

A modular file-based productivity system designed for people with ADHD, autism, alexithymia, or other prefrontal-cortex / executive-function challenges. Optimized for use with Claude Code (also works with Codex and any agent that reads `AGENTS.md`).

## What is PFC?

PFC = Prefrontal Cortex. The system externalizes everything an executive function would normally hold internally: tasks, focus, habits, day ratings, projects, areas of life, values, visions, insights. The git repo is canonical; chat-based agents (Claude Code, etc.) read and write to it.

The bias is toward **less surface for new users on day one** — you don't need to learn it all to get value. There are 30+ slash-command skills, but most users only touch ~7 in their first week.

## The system is yours — edit anything

**This is the most important thing to know on day one.** PFC is a starter kit, not a fixed product. The shipped skills, schemas, area folders, and rules are *defaults* — every one of them is meant to be edited.

Examples of things you can ask your agent to do:

- "Edit `pfc-evening-checkin` to also ask about water intake."
- "Add a new skill that pulls weather and tells me if it's a good outdoor-walking day."
- "Delete the `legal` area — I don't track regulatory work."
- "Change the daily-focus model from 2+1 to 3+0 — I don't want the bonus slot."
- "Add a new field `caffeine_mg` to the day-tracker schema and prompt me for it during evening-checkin."

The system is built to be modified, not just consumed. When something doesn't fit your life, **change it.** Don't work around it. Run `/pfc-onboarding meta/system-is-editable` for the longer pitch.

For the full philosophy of how the system thinks, see [`AGENTS.md`](AGENTS.md).

## Quick start (5 minutes)

1. **Use this template** (top-right green button on github.com).
2. Clone your fork locally.
3. Open in Claude Code (`claude` CLI) or any agent that reads `AGENTS.md`.
4. Run `/pfc-onboarding`. The skill walks you through the system one feature at a time, paced to weeks/months instead of minutes.

That's it for Tier 1. The system works with markdown alone — no Python venv, no cron, no API tokens.

## Advanced installs

Everything past Tier 1 is optional. Each row works on its own, except where a row names the tier it builds on. Tier 2 runs on your own machine; Tier 3 needs the VPS.

| Tier | What you get | Setup time | Doc |
|---|---|---|---|
| 1 | Markdown system + slash commands | 5 min | This README |
| 2: Local automations (optional) | Auto-fetched sleep and Active Zone Minutes, scheduled jobs | 30 min | [`docs/install/local-automations.md`](docs/install/local-automations.md) |
| 2: Google Health (optional) | The health data the local automations fetch: sleep, heart rate, activity, recovery metrics | 30 min | [`docs/install/google-health.md`](docs/install/google-health.md) |
| 2: Connectors (optional) | Google Calendar + Gmail integration | 15 min | [`docs/install/connectors.md`](docs/install/connectors.md) |
| 2: Trello dashboard (optional, recommended) | Visual phone-glance view + mobile capture widget | 20 min | [`docs/install/trello.md`](docs/install/trello.md) |
| 2: Web UI (optional) | A local home page at `http://127.0.0.1:4323` with buttons for the daily loop and a Claude Code chat panel | See doc | [`docs/install/web-ui.md`](docs/install/web-ui.md) |
| 2: Daily sync (optional) | A Mac launch agent that pulls Trello ticks, labeled emails and the calendar into the repo each morning | See doc | [`docs/install/daily-sync.md`](docs/install/daily-sync.md) |
| 3: VPS (optional) | 24/7 background automation | 30 min | [`docs/install/vps.md`](docs/install/vps.md) |
| 3: Remote access (optional) | Drive the VPS from your phone (Termius + tmux + Claude Code Remote Control) | 20 min | [`docs/install/remote-access.md`](docs/install/remote-access.md) |
| 3: TRMNL e-ink screen (optional) | An ambient wall screen showing today's 2+1, habits, focuses and more; the polling endpoint runs on the VPS | See doc | [`docs/install/trmnl-endpoint.md`](docs/install/trmnl-endpoint.md), [`docs/trmnl-plugins.md`](docs/trmnl-plugins.md) |
| 3: reMarkable pages (optional) | The home page, the due review and the task list as pages on a reMarkable tablet that you write on; a server timer reads the ink | See doc | [`docs/remarkable.md`](docs/remarkable.md) |
| 3: AI News (optional) | Posts from the AI blogs you follow, filtered by your criteria, as reMarkable EPUBs and a private podcast feed | See doc | [`docs/ai-news.md`](docs/ai-news.md) |

Trello is highly recommended for the visualization benefit: externalizing the system into a glanceable visual layer is especially valuable for the target audience. Power-Ups are free.

## Where you see the system

The repo holds all the state. Every other place you see the system only shows it, and every job they do also has a chat skill, so none of them is required.

| Surface | Used for | Doc |
|---|---|---|
| Claude Code chat | Where the work happens: every `/pfc-*` skill | [`AGENTS.md`](AGENTS.md) |
| Web UI | The daily loop with buttons, on your own machine | [`docs/install/web-ui.md`](docs/install/web-ui.md) |
| Trello board | A phone glance, ticks from the home-screen widget, and the `📥 Inbox` list for quick captures (optionally processed unattended every 10 minutes) | [`docs/trello-dashboard.md`](docs/trello-dashboard.md) |
| TRMNL screen | An ambient, read-only screen in the room | [`docs/trmnl-plugins.md`](docs/trmnl-plugins.md) |
| reMarkable pages | Pages you carry and write on | [`docs/remarkable.md`](docs/remarkable.md) |
| Claude Duet | A cloud thread that operates the system from the Trello board and a fresh clone | [`docs/duet/pfc-operator/SKILL.md`](docs/duet/pfc-operator/SKILL.md) |

## What's in the box

The system follows a **VAVFPTH** model: Values → Areas → Visions → Focus → Projects → Tasks → Habits.

| Folder | What it holds |
|---|---|
| `0-me/` | Who you are: profile, working-with-me, schedule patterns |
| `1-values/` | Your values list (start with the menu of 30 in `values.md`) |
| `2-areas/` | Areas of life (career, health, finances, relationships, etc.), each with an area statement and optional area items that light it green, yellow or red |
| `3-visions/` | Long-term direction tied to an area (no deadlines) |
| `4-focus/` | Current Focus — the capped, traffic-lit set of what you're on this quarter |
| `5-projects/` | Short-term projects (1-3 months; backstop of 12 active) |
| `6-tasks/` | Tasks, daily focus picks, event log |
| `7-habits/` | Daily + monthly habit tracking |
| `data/` | Day tracking, insights, hypotheses, findings, supplements, Front-of-Mind anchors, the rolling-review ledger, the AI News log |
| `config/` | Schemas + integration config |
| `docs/` | System documentation (start with `docs/system-map.md`) |
| `notes/` | Generated reports (daily and yearly summaries) |
| `automations/` | Python scripts for auto-fetched data, the shared writer the surfaces use, systemd timers for a VPS and macOS launch agents |
| `scripts/` | Validation, session hooks, the daily sync and unattended inbox jobs |
| `web/` | Optional local web UI (an Astro app) |
| `trmnl/` | Optional TRMNL e-ink dashboard plugins |
| `.agents/skills/` | Skill definitions (read by Codex and most other agents) |
| `.claude/skills/` | Symlink mirror for Claude Code |

## Working with other agents

The only instruction file is `AGENTS.md`, read natively by Claude Code (v2.1.277 and later), Codex, and most other agents that follow the AGENTS.md convention. There is no `CLAUDE.md`; don't add one, because a `CLAUDE.md` switches off Claude Code's native `AGENTS.md` reading. The skills work with any agent that has a Skill-equivalent invocation pattern; the slash commands work natively in Claude Code. To run the system from Claude Duet, see the operator guide in [`docs/duet/pfc-operator/SKILL.md`](docs/duet/pfc-operator/SKILL.md) and the "Claude Duet threads" section of `AGENTS.md`.

## Pulling upstream template updates (optional)

The PFC template keeps evolving — new skills, scrubs, install-doc improvements, refined defaults. Your fork is its own thing; you don't have to stay in lockstep. If you want to pull selected upstream updates into your fork later, the `/pfc-pull-template-updates` skill walks each upstream commit one at a time and lets you accept or reject per commit.

**Three things to know before you pull updates:**

1. **The maintainer tailors the template to his own workflows.** Some updates will fit you; some won't. The system was always meant to be edited — the same applies to incoming changes. Pick the refinements you actually want, drop the rest.
2. **Upstream changes can clash with your modifications.** Heavily-customized skills, areas, or schemas may produce merge conflicts. Your modifications take priority — pull updates only when you genuinely want the upstream behavior.
3. **Pulling is opt-in.** A fork that never re-syncs with upstream is entirely valid. Pull when you're curious or when a specific upstream change interests you, not because you "should" stay current.

If a default doesn't fit your life, **modify it locally** rather than fighting upstream commits forever. That's the spirit of the original `meta/system-is-editable` lesson — and it applies just as much to upstream-tracking as it does to day-one edits.

## License

MIT. See [`LICENSE`](LICENSE) for the full text.
