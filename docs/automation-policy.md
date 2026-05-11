# Automation Policy

## Principles

- Automations are defined in repo files and executed by scripts
- Automated changes follow the commit policy in CLAUDE.md
- Important automated changes must be legible and understandable

See `CLAUDE.md` for the canonical commit-policy lists. This doc mirrors them for quick reference.

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
- CLAUDE.md changes
- Large planning or reorganization sessions

## Execution on VPS

- **systemd timers** for scheduled automations (daily check-in prompts, weekly reviews)
- **systemd services** for long-running processes if needed
- Scripts may invoke Claude Code CLI with `claude -p` for automated workflows

## Safety rules

- Never commit secrets
- Avoid commit loops (no automation that triggers itself)
- Skip empty commits
- Prefer append-only writes for automated data
- Use locks or serialization for concurrent automation jobs

## Future automation targets

- Daily check-in prompt (systemd timer, morning)
- Weekly review prompt (systemd timer, end of week)
- Task archival (when `5-actions/_data/tasks.ndjson` exceeds ~200 lines)
- Report generation (on demand or scheduled)
