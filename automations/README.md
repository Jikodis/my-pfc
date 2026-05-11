# Automations

Automation scripts and scheduling configurations for the productivity system.

## Directory structure

- `scripts/` — Python scripts for automated workflows
- `systemd/` — systemd service and timer unit files for VPS scheduling
- `templates/prompts/` — Reusable prompt templates for Claude Code CLI automation
- `templates/messages/` — Notification message templates

## How automations work

Scripts in `scripts/` run via systemd user timers on the VPS. Some scripts invoke the Google Health API directly; others may invoke Claude Code CLI with `claude -p` for AI-assisted workflows.

See `docs/automation-policy.md` for the commit policy and safety rules.

---

## Active automations

### `pfc-habit-autolog` — Daily habit logging from Google Health

**Script:** `scripts/auto_log_habits.py`
**Units:** `systemd/pfc-habit-autolog.service.template` + `systemd/pfc-habit-autolog.timer.template`

Runs twice daily in your local timezone (`$LOCAL_TZ`, default `America/Denver`):
- **Morning run** — checks last night's sleep session; logs your bedtime habit if you hit your target
- **Late-evening run** — checks full day's activity; logs `active-zone-minutes` if AZM ≥ 20

Edit the systemd `OnCalendar=` lines and the schedule's `__LOCAL_TZ__` substitution to match your day; the 8 AM / 10:30 PM defaults are illustrative.

Safe to run multiple times — skips habits already logged for the date.
Auto-commits and pushes to GitHub when habits are logged.

### `pfc-trello-daily-render` — Daily Trello dashboard render at local midnight

**Script:** `scripts/trello_render.py`
**Units:** `systemd/pfc-trello-daily-render.service.template` + `systemd/pfc-trello-daily-render.timer.template`

Runs once daily at **12:05 AM in your local timezone** (`$LOCAL_TZ`, default `America/Denver`). Re-renders all dashboard lists so daily-habit cards uncheck for the new day (the render reads today's habit logs; with no logs yet for the new day, all habit cards render unchecked). Without this, habit cards stay visually checked until the first render-firing skill runs (e.g. morning-checkin) — which could be hours into the day. Edit the `.timer.template` `OnCalendar=` line if you want a different fire time.

The render is idempotent: a no-change render is a 0-diff no-op. Calendar + Email lists skip 🟡 since this runs without MCP data; cadence checkins still refresh those.

---

## Scripts

| Script | Purpose |
|---|---|
| `google_health_auth.py` | One-time OAuth2 authorization for Google Health API |
| `google_health_fetch.py` | Fetch health data for a single date (sleep, HR, AZM) |
| `google_health_backfill.py` | Backfill historical health data into day-tracking.ndjson |
| `auto_log_habits.py` | Auto-log habits from Google Health data |
| `auto_fetch_health.py` | Write raw health data (sleep, HR, AZM) into day-tracking.ndjson — runs nightly via `pfc-habit-autolog` after `auto_log_habits.py` |
| `analyze_day_trends.py` | Analyze day tracking data for statistical patterns |

---

## Installing systemd units

Run once from the VPS as the `claude` user:

```bash
bash automations/systemd/install.sh
```

This will:
1. Copy unit files to `~/.config/systemd/user/`
2. Enable linger (so units run without an active login session)
3. Reload the user daemon
4. Enable and start the timer

### Verify installation

```bash
# Check timer status and next fire time
systemctl --user status pfc-habit-autolog.timer
systemctl --user list-timers pfc-habit-autolog.timer

# Watch live logs
journalctl --user -u pfc-habit-autolog.service -f

# Review past runs
journalctl --user -u pfc-habit-autolog.service --since today
journalctl --user -u pfc-habit-autolog.service --since "7 days ago"
```

### Updating units after repo changes

If you edit the `.service.template` or `.timer.template` files in `systemd/`, re-run install:

```bash
bash automations/systemd/install.sh
```

Or manually (install.sh substitutes `__REPO_ROOT__`/`__REPO_URL__` from the `.template` sources):

```bash
bash automations/systemd/install.sh
systemctl --user restart pfc-habit-autolog.timer
```

### Manual test run

```bash
# Run for today
python3 automations/scripts/auto_log_habits.py

# Run for a specific date
python3 automations/scripts/auto_log_habits.py 2026-04-12
```

---

## Future automation targets

- Task archival (when `5-actions/_data/tasks.ndjson` exceeds ~200 lines)
