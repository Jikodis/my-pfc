# Automation Policy

## Principles

- Automations are defined in repo files and executed by scripts
- Automated changes follow the commit policy in AGENTS.md
- Important automated changes must be legible and understandable

See `AGENTS.md` for the canonical commit-policy lists. This doc mirrors them for quick reference.

## Auto-commit operations (no confirmation needed)

- Task capture (add/complete/move)
- Daily focus picks
- Habit logging
- Day tracking entries
- Daily check-in appends
- Project progress updates
- Automation-generated data (NDJSON appends)
- Generated reports

## Ask-before-commit operations

- Structural repo changes
- Skill or agent definition edits
- AGENTS.md changes
- Large planning or reorganization sessions

## Where automations run

All of them are optional. On a VPS, `automations/systemd/install.sh` installs systemd user units ([`install/vps.md`](install/vps.md)); on a Mac, launch agents in `automations/launchd/` do the jobs that need your own machine.

| Job | Runs as | On by default? |
|---|---|---|
| Health fetch (morning retry loop + noon two-pass) | `pfc-health-fetch-morning.timer`, `pfc-health-fetch.timer` | Yes, once installed |
| Trello render shortly after midnight | `pfc-trello-daily-render.timer` | Yes, once installed |
| Fast-forward the server clone every 5 minutes | `pfc-repo-sync.timer` | Yes, once installed |
| TRMNL polling endpoint | `pfc-trmnl-serve.service` | Only with `TRMNL_SERVE_TOKEN` in `.env` ([`install/trmnl-endpoint.md`](install/trmnl-endpoint.md)) |
| reMarkable pages sync every 10 minutes | `pfc-remarkable-sync.timer` | Only with `PFC_REMARKABLE_SYNC=1` ([`remarkable.md`](remarkable.md)) |
| Unattended Trello inbox every 10 minutes | `pfc-trello-inbox.timer` (`scripts/trello-inbox-auto.sh`) | Only with `PFC_TRELLO_INBOX=1` |
| AI News daily | `pfc-ai-news.timer` | Only with `PFC_AI_NEWS=1` ([`ai-news.md`](ai-news.md)) |
| Daily sync on a Mac | `com.pfc.daily-sync` launch agent (`scripts/daily-sync.sh`) | Only with `PFC_DAILY_SYNC=1` ([`install/daily-sync.md`](install/daily-sync.md)) |
| Pull server commits into a Mac clone | `com.pfc.repo-sync` launch agent | When you install it |
| Local web UI | `com.pfc.web` launch agent | When you install it ([`install/web-ui.md`](install/web-ui.md)) |

The jobs that need judgment run headless Claude Code (`claude -p`), which is why each one is opt-in.

## Safety rules

- Never commit secrets
- Avoid commit loops (no automation that triggers itself)
- Skip empty commits
- Prefer append-only writes for automated data
- Use locks or serialization for concurrent automation jobs. The web writer (`automations/scripts/web_write.py`, used by the web UI and the reMarkable sync) and the daily sync share one lock, `data/.web-write.lock`; the daily sync takes it through `automations/scripts/with_write_lock.py`.

## Future automation targets

- Daily check-in prompt (systemd timer, evening)
- Task archival (when `6-tasks/_data/tasks.ndjson` exceeds ~200 lines)
- Report generation (on demand or scheduled)
