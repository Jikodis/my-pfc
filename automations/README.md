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

### `pfc-health-fetch` + `pfc-health-fetch-morning` — Health data into day-tracking

**Script:** `scripts/auto_fetch_health.py`
**Units:** `systemd/pfc-health-fetch.{service,timer}.template` + `systemd/pfc-health-fetch-morning.{service,timer}.template`

Writes two layers per run: derived day metrics into `data/day-tracking.ndjson` → `health`, and the comprehensive raw streams into `data/health-raw/YYYY-MM-DD.json.gz`. Then recomputes the QQRT sleep composite (`qqrt` on each record) and commits + pushes.

Three cadences, because the data lands at three different times:

- **Morning retry** — every 30 minutes from 6:00 AM local, fetching **today** (last night's sleep). Sleep lands whenever the watch syncs, not on a clock, so one fixed hour is either too early or too late.
- **Noon two-pass** — pass 1 today (fresh sleep beside a same-day rating in the tour), pass 2 yesterday (finalizes complete full-day activity totals).

Idempotent, and that's what makes the retry loop cheap: with unchanged data it writes nothing, commits nothing, and pushes nothing. Full setup in [`docs/install/google-health.md`](../docs/install/google-health.md).

### `pfc-trello-daily-render` — Daily Trello dashboard render at local midnight

**Script:** `scripts/trello_render.py`
**Units:** `systemd/pfc-trello-daily-render.service.template` + `systemd/pfc-trello-daily-render.timer.template`

Runs once daily at **12:05 AM in your local timezone** (`$LOCAL_TZ`, default `America/Denver`). Re-renders all dashboard lists so daily-habit cards uncheck for the new day (the render reads today's habit logs; with no logs yet for the new day, all habit cards render unchecked). Without this, habit cards stay visually checked until the first render-firing skill runs (any `pfc-*` skill that renders, or a web UI write) — which could be hours into the day. Edit the `.timer.template` `OnCalendar=` line if you want a different fire time.

The render is idempotent: a no-change render is a 0-diff no-op. It has no MCP access, so `🗓️ Week at a Glance` falls back to `data/calendar-cache.json` (refreshed each morning by the daily sync job).

---

## Scripts

| Script | Purpose |
|---|---|
| `google_health_auth.py` | One-time OAuth2 authorization for the Google Health API |
| `google_health_fetch.py` | Fetch and print one date's flat `health` block (sleep, heart rate, activity, workouts, recovery metrics) |
| `google_health_backfill.py` | Backfill historical health data into day-tracking.ndjson; `--all` re-derives every record and recomputes QQRT |
| `google_health_raw.py` | Capture the comprehensive RAW streams (per-minute heart rate, intraday variability/blood oxygen, sleep stages) to `data/health-raw/YYYY-MM-DD.json.gz`; `--range START END` to backfill. A file captured mid-day is re-fetched until one lands after local midnight, then it's final |
| `sleep_reduce.py` | Shared sleep parsing — awake-gap accounting for fragmented nights, awakenings, stage totals. Imported by both fetch paths so they cannot drift |
| `exercise_reduce.py` | Shared tracked-workout parsing — session list, intensity, timing, `azm_outside_workouts` |
| `qqrt.py` | Canonical QQRT sleep-composite levers + sleep-debt ledger. Thresholds are generic defaults, tunable via `config/automation_config.yaml` → `health.sleep` |
| `backfill_qqrt.py` | Recompute the `qqrt` object on every day-tracking record (idempotent; runs automatically after any health write) |
| `pulse.py` | Daily Pulse levers, verdict, per-lever fix, and the multi-day trend — the single source of truth every pulse surface imports (Trello render, TRMNL, the daily summary). Bands tunable via `config/automation_config.yaml` → `health.pulse` |
| `auto_fetch_health.py` | Fetch health into day-tracking.ndjson + the raw archive, recompute QQRT, commit and push — runs via `pfc-health-fetch` and `pfc-health-fetch-morning` |
| `repo_sync.py` | Levels a clone with origin before a writer reads and before it pushes (`git pull --rebase` on a clean tree, fast-forward only otherwise); used by `auto_fetch_health.py` and `web_write.py` |
| `pfc_writes.py` · `ndjson_file.py` | The task, habit, focus and day-rating record changes shared by the web writer and the Trello sync, and the line-preserving atomic NDJSON rewrite they write through |
| `web_data.py` · `home_data.py` · `web_write.py` | The web UI's Python side: every number it shows, and the one writer behind its buttons (see `web/AGENTS.md`) |
| `analyze_day_trends.py` | Analyze day-tracking data: correlations, gate/gradient classification, QQRT threshold, sleep debt, trailing-2-night worst night |

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
systemctl --user status pfc-health-fetch.timer
systemctl --user list-timers

# Watch live logs
journalctl --user -u pfc-health-fetch.service -f

# Review past runs
journalctl --user -u pfc-health-fetch.service --since today
journalctl --user -u pfc-health-fetch.service --since "7 days ago"
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
# Fetch health for today
python3 automations/scripts/auto_fetch_health.py

# Fetch health for a specific date
python3 automations/scripts/auto_fetch_health.py 2025-01-12
```

---

## Future automation targets

- Task archival (when `6-tasks/_data/tasks.ndjson` exceeds ~200 lines)
