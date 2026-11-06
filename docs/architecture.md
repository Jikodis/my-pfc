# Architecture

## Overview

The system is a Git repository running on any VPS or local machine, accessed via Claude Code (CLI, IDE, or Remote Control). All inference runs on Anthropic's servers — the VPS just holds the repo and a lightweight process.

## Architecture diagram

```
You (Phone/Laptop)
    │
    ├── Claude App + Remote Control (primary)
    ├── SSH via Termius (fallback)
    └── Local clone (parallel dev)
    │
    ▼
Anthropic API (inference + relay)
    │
    ▼
VPS (any Linux distro; Ubuntu 24.04 recommended). Tested with Hetzner, DigitalOcean, Vultr — any flat-rate $4–6/mo droplet handles the workload.
    ├── Claude Code CLI
    ├── tmux (session persistence)
    └── UFW firewall + SSH key auth
    │
    ▼
Git Repo (this repo)
    │
    ▼
GitHub (private, backup + sync)
```

## Surfaces

Four surfaces render the repo, and none of them owns state: **Claude Code** (where the work happens), the **Trello board** (phone, `trello_render.py`), the **TRMNL e-ink screen** (ambient, `trmnl/`), and the **local web UI** (`web/`, an Astro app at `http://127.0.0.1:4323` with a Claude Code chat panel and buttons that complete a task, log a habit, or park a focus through `web_write.py`; record changes live in `pfc_writes.py`, shared with the Trello sync, and file rewrites go through `ndjson_file.py`). Numbers with a rule behind them are computed once in Python so the four cannot disagree.

## Key decisions

| Decision | Choice | Reasoning |
|---|---|---|
| VPS Provider | any VPS provider (Hetzner, DigitalOcean, Vultr, etc.) | a $4–6/mo flat-rate droplet is plenty for this workload |
| Plan | ~$6/mo (1 vCPU, 1GB, 25GB minimum) | API-bound workload, minimal compute needed |
| Primary Access | Claude App + Remote Control | Native phone experience, no terminal needed |
| Git Strategy | Commit directly to main | Markdown + NDJSON operations, low merge risk |
| Session Persistence | tmux + systemd | Survives SSH drops; auto-restarts on boot |
| Remote Control Mode | `--spawn worktree --capacity N` (tune N to your machine) | Isolated worktrees per session |
| AI Abstraction | Skills (`.claude/skills/`) | All v1 workflows are sequential, single-context |
| Custom Subagents | Deferred to v2+ | Start conversational, automate when patterns emerge |
| Structured Data | NDJSON | Append-only, machine-readable, grep-queryable |
| Networking | Direct SSH (no Tailscale) | VPS has public IP, no NAT traversal needed |

## Persistence & reliability

- **tmux** keeps Claude Code running regardless of connection state
- **Remote Control** auto-reconnects on network drops
- **VPS reboots** create a new session ID; systemd service auto-restarts the process
- **VPS snapshots** provide disaster recovery (~$1.50/mo)

## Future: model routing

Use a faster model for daily ops, a larger model for deep work — see the persona/routing docs in Claude Code.
