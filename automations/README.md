# Automations

Automation scripts and scheduling configurations for the productivity system.

## Directory structure

- `scripts/` — Python scripts for automated workflows
- `systemd/` — systemd service and timer unit files for VPS scheduling
- `launchd/` — macOS launch agent template for the local web UI (`com.pfc.web.plist`)
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

Writes two layers per run: derived day metrics into `data/day-tracking.ndjson` → `health`, and the comprehensive raw streams into `data/health-raw/YYYY-MM-DD.json.gz`. Then stamps each workout's heart-rate-derived length (`row_duration.py`), recomputes the QQRT sleep composite (`qqrt` on each record), derives the habits the watch can answer (`derive_sleep_habit.py`, `derive_workout_habits.py`) into `7-habits/_data/habits-daily.ndjson`, and commits + pushes both files together. A partial raw snapshot of a day still in progress is not committed on its own.

Three cadences, because the data lands at three different times:

- **Morning retry** — every 30 minutes from 6:00 AM local, fetching **today** (last night's sleep). Sleep lands whenever the watch syncs, not on a clock, so one fixed hour is either too early or too late.
- **Noon two-pass** — pass 1 today (fresh sleep for the same-day evening check-in), pass 2 yesterday (finalizes complete full-day activity totals).
- **On demand** — the evening check-in fetches before reading health data.

Idempotent, and that's what makes the retry loop cheap: with unchanged data it writes nothing, commits nothing, and pushes nothing. Full setup in [`docs/install/google-health.md`](../docs/install/google-health.md).

### `pfc-trello-daily-render` — Daily Trello dashboard render at local midnight

**Script:** `scripts/trello_render.py`
**Units:** `systemd/pfc-trello-daily-render.service.template` + `systemd/pfc-trello-daily-render.timer.template`

Runs once daily at **12:05 AM in your local timezone** (`$LOCAL_TZ`, default `America/Denver`). Re-renders all dashboard lists so daily-habit cards uncheck for the new day (the render reads today's habit logs; with no logs yet for the new day, all habit cards render unchecked). Without this, habit cards stay visually checked until the first render-firing skill runs (e.g. the evening check-in) — which could be hours into the day. Edit the `.timer.template` `OnCalendar=` line if you want a different fire time.

The render is idempotent: a no-change render is a 0-diff no-op. Calendar + Email lists skip 🟡 since this runs without MCP data; cadence checkins still refresh those.

### `com.pfc.web` — the local web UI (optional, macOS)

**Script:** `scripts/run-web.sh`
**Agent:** `launchd/com.pfc.web.plist` (a template: fill in `__REPO_ROOT__`, `__USER__`, `__PATH__`, `__PYTHON__`)

Serves the web UI in `web/` at `http://127.0.0.1:4323`, starting at login and restarting if it stops. It rebuilds by itself when the web source changes and swaps the new build in once no chat reply or save is running. The page reads the repo through `scripts/web_data.py` and writes it through `scripts/web_write.py`. Full setup in [`docs/install/web-ui.md`](../docs/install/web-ui.md).

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
| `pulse.py` | Daily Pulse levers, verdict, per-lever fix, and the multi-day trend — the single source of truth every pulse surface imports (Trello render, check-in). Bands tunable via `config/automation_config.yaml` → `health.pulse` |
| `auto_fetch_health.py` | Fetch health into day-tracking.ndjson + the raw archive, recompute QQRT, commit and push — runs via `pfc-health-fetch` and `pfc-health-fetch-morning` |
| `analyze_day_trends.py` | Analyze day-tracking data: correlations, gate/gradient classification, QQRT threshold, sleep debt, trailing-2-night worst night |
| `row_duration.py` | Heart-rate-derived workout length (`real_minutes`, `hard_minutes`) for sessions whose watch timer ran long. No args prints Timer vs Real per session; `--write` stamps day-tracking.ndjson |
| `derive_sleep_habit.py` | Mirror `qqrt.timing` into the `sleep-on-time` habit log (source `fitbit-derived`); a hand-logged row wins. `--dry-run` |
| `derive_workout_habits.py` | Log habits with a `workout:` rule in `config/habit_schema.yaml` from recorded exercise sessions (source `health-derived`); a hand-logged row wins. `--dry-run` |
| `derive_calendar_habits.py` | Log `auto_derived` habits with a `calendar:` rule from `data/calendar-cache.json` (source `calendar-derived`). `--dry-run`, `--events FILE` for a backfill |
| `area_items.py` | Area item lights, the weighted area rollup, and the plate (committed vs free weekly hours) from `2-areas/_data/area-items.ndjson` + `area-checkins.ndjson`. Prints JSON; `--today YYYY-MM-DD` |
| `ndjson_file.py` | Rewrite an NDJSON file so only changed lines change; atomic replace that refuses when the file changed underneath |
| `web_data.py` | The web UI's reader: `--home` prints the home page data as JSON (`home_data.build_home`); `--review [--id ID]` prints the one due review as a form, or `null`. Also the habit rows and habit titles the page shows |
| `home_data.py` | Every rule behind a number on the web home page: the 2+1 and its suggestions, what needs you, the why-chain, areas, focuses, projects, the pulse, trends, the week |
| `web_write.py` | The one program that writes the repo for the web UI: one action per button, under the lock `data/.web-write.lock`; pulls, writes only the changed lines, commits only those paths, pushes. `--dry-run` changes nothing |
| `pfc_writes.py` | The record changes the web writer and the Trello sync share: complete or drop a task, log a habit, rate a day, set picks, park a focus, stamp a review |
| `repo_sync.py` | Level the branch with its upstream before a write or push: rebase on a clean tree, fast-forward with uncommitted edits, never a stash |
| `review_forms.py` | The one due rolling review as a fill-in form (web `/review` page and `/pfc-review`); `--finish ID --shown IDS` stamps it or records the rows done |
| `project_gauges.py` | Project velocity (pace, finish date, days late, light) and days idle: one home for the rules `/pfc-revive` and the web UI both read |
| `feature_use.py` | Feature scorecard for `/pfc-usage-audit`: real use of each feature over the last 30 days and the 60 before, with a suggested verdict. `--json` |
| `with_write_lock.py` | Run a command under the web writer's lock; a busy lock skips the run (exit 0). For a scheduled job that commits to the repo |
| `run-web.sh` | Serve the web UI and keep its build current (the `com.pfc.web` launch agent) |

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
