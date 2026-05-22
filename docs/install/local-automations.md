# Local automations install guide (Tier 2)

The Tier 1 quickstart (clone → `claude` → `/pfc-onboarding`) gets the core system running with zero dependencies beyond Claude Code itself. This doc covers the next step up: a Python virtual environment and cron jobs that run background automations on your laptop.

You only need this if you want:
- **Auto-fetched health data** — sleep (duration, stages, timing, continuity, awakenings), resting heart rate, Active Zone Minutes, tracked workouts, and daily recovery metrics pulled from Google Health into `data/day-tracking.ndjson`, plus the comprehensive raw streams into `data/health-raw/`.
- **Scheduled background jobs** — automations that run at set times without manual invocation.

If you just want to log data manually during check-ins, stay on Tier 1.

---

## Prerequisites

- Tier 1 quickstart complete (repo cloned, Claude Code running, `/pfc-onboarding` finished or skipped).
- Python 3.10 or later. Check with `python3 --version`.
- macOS or Linux. (Windows users: WSL2 works; native Windows is untested.)

---

## Step 1 — Set up the Python virtual environment

From inside your repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r automations/requirements.txt
```

The venv is gitignored. You'll need to `source .venv/bin/activate` again in any new terminal session before running scripts manually.

To verify the install worked:

```bash
python3 -c "import google.auth; print('ok')"
```

---

## Step 2 — Configure Google Health (optional, but the most useful integration here)

Google Health is what feeds sleep, heart rate, and Active Zone Minutes into the system automatically. Without it, those fields stay blank and the auto-fetch scripts are no-ops.

Follow the full setup in [`docs/install/google-health.md`](google-health.md). That doc covers:
- Creating a Google Cloud project and enabling the Health API
- Configuring the OAuth consent screen and generating credentials
- Running the one-time token authorization flow
- Setting the `GOOGLE_HEALTH_*` env vars in `.env`

If you skip Google Health, the cron jobs below will still run but won't write any data — that's fine if you prefer manual logging.

---

## Step 3 — Set up cron jobs

Add these entries to your crontab with `crontab -e`:

```cron
# PFC — auto-log habits (8 AM and 10:30 PM local time — edit to suit your sleep/wake schedule)
TZ=America/Denver

# PFC — health fetch, morning retry loop (every 30 min, 6:00–10:30 AM local)
*/30 6-10 * * * cd /path/to/your/pfc && .venv/bin/python3 automations/scripts/auto_fetch_health.py "$(date +\%Y-\%m-\%d)" >> /tmp/pfc-auto-fetch-health.log 2>&1

# PFC — health fetch, noon two-pass: today, then yesterday
0 12 * * * cd /path/to/your/pfc && .venv/bin/python3 automations/scripts/auto_fetch_health.py "$(date +\%Y-\%m-\%d)"; cd /path/to/your/pfc && .venv/bin/python3 automations/scripts/auto_fetch_health.py >> /tmp/pfc-auto-fetch-health.log 2>&1
```

Replace `/path/to/your/pfc` with the absolute path to your repo root (e.g. `~/pfc`). Use `pwd` inside the repo to get it. Replace `TZ=America/Denver` with your IANA timezone (e.g. `Europe/London`, `Asia/Tokyo`).

**Why these times.** Edit them to fit your day; the values below are illustrative.

- **Morning retry loop.** Last night's sleep lands whenever your watch syncs to your phone, not on a clock — it can vary by hours from one morning to the next. A single fixed hour therefore either fires too early (no data) or too late (you spend the morning looking at yesterday's numbers). Retrying every 30 minutes catches the sync within half an hour of whenever it happens. The extra firings are nearly free: `auto_fetch_health.py` writes nothing, commits nothing, and pushes nothing when the data is unchanged. Providers also sometimes revise a night's numbers an hour later, so retrying picks up the correction. Set the window to bracket your wake time.
- **Noon two-pass.** Pass 1 fetches **today** so the same-day evening check-in reads fresh sleep. Pass 2 (no date argument, so it defaults to yesterday) finalizes yesterday's **complete** full-day activity totals now that the day is over — overwriting the partial value, losing nothing.

**On macOS:** cron is available but runs less reliably than on Linux. If jobs aren't firing, check `Console.app` for cron errors or use `launchd` instead (not covered here).

---

## Step 4 — Verify it works

Run each script once manually to confirm the setup is correct before relying on the timer:

```bash
# From repo root, with venv active
source .venv/bin/activate

python3 automations/scripts/auto_fetch_health.py
python3 automations/scripts/auto_fetch_health.py
```

After each run, check the output and inspect the resulting change:

```bash
# See what the script wrote
git diff data/day-tracking.ndjson
git diff 7-habits/_data/habits-daily.ndjson

# Or look at the tail of the NDJSON
tail -5 data/day-tracking.ndjson
```

If the script runs without error and you see a new or updated NDJSON line, the integration is working. If you see `No credentials found` or a Google auth error, revisit `docs/install/google-health.md` — the token flow probably needs to be re-run.

Scripts that successfully write data also commit automatically (the commit message will be `track: auto-fetch health YYYY-MM-DD`). This is intentional — the cron job keeps the repo up to date without manual intervention.

---

## Step 5 — Logs and troubleshooting

The crontab entries above redirect output to log files in `/tmp/`:

```bash
tail -50 /tmp/pfc-auto-fetch-health.log
tail -50 /tmp/pfc-auto-log-habits.log
```

On Linux, cron job output also goes to the system log:

```bash
grep CRON /var/log/syslog | tail -20
```

**Common issues.**

| Symptom | Likely cause | Fix |
|---|---|---|
| No log file appears | Cron never fired | Check `crontab -l` matches what you entered; check system cron is running (`systemctl status cron`) |
| `ModuleNotFoundError` | Wrong Python called | Ensure the crontab uses `.venv/bin/python3`, not system `python3` |
| `No credentials found` | Token expired or missing | Re-run token flow per `docs/install/google-health.md` §5 |
| Script runs but NDJSON unchanged | No new data from Google | Check Google Health has data for today (open the app); check scopes in Cloud Console |
| `git commit` fails in cron | No git identity set | Run `git config user.email "you@example.com"` and `git config user.name "Your Name"` in the repo |

---

## Next step

If you want the automations running 24/7 from any device — not just when your laptop is awake — see [`docs/install/vps.md`](vps.md) for the Tier 3 VPS + systemd setup.
