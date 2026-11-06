# Google Health install guide

Set up the Google Health API integration that powers `automations/scripts/auto_fetch_health.py`. Required if you want auto-fetched health data flowing into `data/day-tracking.ndjson` and the raw archive at `data/health-raw/`.

If you don't want those features, skip this — the system degrades gracefully (the `health` field on day-tracking rows just stays absent).

## What gets fetched

Two layers, both written by the same run:

| Layer | Where | What |
|---|---|---|
| Derived day metrics | `data/day-tracking.ndjson` → `health` | Sleep (duration, stages, timing, continuity, per-night awakenings), resting heart rate, Active Zone Minutes, tracked workout sessions, and daily recovery metrics: heart-rate variability, blood oxygen, breathing rate, skin-temperature deviation, VO2 max |
| Comprehensive raw archive | `data/health-raw/YYYY-MM-DD.json.gz` | The full unflattened API responses — per-minute heart rate, intraday variability and blood oxygen, sleep stages, interval streams. See [`data/health-raw/README.md`](../../data/health-raw/README.md) |

A third derived layer, the QQRT sleep composite, is computed from the above and written back onto each day-tracking record as `qqrt` (see `automations/scripts/qqrt.py`). Its thresholds are generic defaults you tune in `config/automation_config.yaml` under `health.sleep`.

## Prerequisites

- A Google account with health data already syncing to Google Health (Fitbit, Pixel Watch, Wear OS device, etc.).
- Python 3.10+ on the machine that will run the cron / systemd job.
- ~30 minutes the first time. Most of it is Google Cloud Console clicking.

## Step 1 — Create a Google Cloud project

1. Open [console.cloud.google.com](https://console.cloud.google.com).
2. Top bar → project picker → **New Project**.
3. Name it whatever you want (e.g. `pfc-health`). No organization needed.
4. Wait ~30 seconds for creation, then switch into it.

## Step 2 — Enable the Health API

1. Left sidebar → **APIs & Services** → **Library**.
2. Search for `Google Health API` (sometimes listed as `Health Connect API` or `Fitness API` depending on rollout — the one you want exposes the `googlehealth.*.readonly` scopes).
3. Click → **Enable**.

If you only see the older Fitness API, that one also works for sleep/HR/AZM but uses different scope strings. The scripts in this repo target the newer Google Health API; if you fall back to Fitness, you'll need to swap scope strings in `automations/scripts/google_health_auth.py` and the field paths in `google_health_fetch.py`.

## Step 3 — Configure the OAuth consent screen

1. Left sidebar → **APIs & Services** → **OAuth consent screen**.
2. User type → **External**. (Internal requires a Workspace org.)
3. Fill the required fields:
   - App name: anything (`pfc-health`)
   - User support email: yours
   - Developer contact: yours
4. **Scopes** screen → Add scopes → search for and add:
   - `googlehealth.sleep.readonly`
   - `googlehealth.health_metrics_and_measurements.readonly`
   - `googlehealth.activity_and_fitness.readonly`

   All three are needed. Sleep covers sleep sessions and stages; health metrics covers heart-rate variability, blood oxygen, breathing rate, skin temperature and VO2 max; activity covers Active Zone Minutes, steps, distance, energy and the `exercise` (tracked workout) data type. Approving only the first leaves the recovery and workout fields permanently null.
5. **Test users** screen → add your own Google account email. The app stays in "Testing" status indefinitely; that's fine for personal use. Apps in Testing only let allowlisted accounts authorize, which is exactly what you want.
6. Save and exit. Do NOT submit for verification — that's only needed if you're shipping to other users.

## Step 4 — Create OAuth credentials

1. Left sidebar → **APIs & Services** → **Credentials**.
2. **Create Credentials** → **OAuth client ID**.
3. Application type → **Web application** (not Desktop — the auth flow uses a localhost redirect).
4. Authorized redirect URIs → add: `http://localhost:8080/callback`
5. Create. Copy the **Client ID** and **Client secret** that pop up. You won't see the secret again after closing the modal — save it now.

## Step 5 — Configure the repo `.env`

Copy `.env.example` to `.env` (gitignored) and fill in the values from Step 4:

```bash
cp .env.example .env
$EDITOR .env
```

Required:

```
GOOGLE_HEALTH_CLIENT_ID=<from step 4>
GOOGLE_HEALTH_CLIENT_SECRET=<from step 4>
GOOGLE_HEALTH_TOKEN_FILE=<absolute path>/config/google_health_tokens.json
```

`GOOGLE_HEALTH_TOKEN_FILE` is auto-written by the next step; just point it at a writable path inside `config/`.

## Step 6 — Run the OAuth flow

This is a one-time per-machine step. Tokens auto-refresh after this.

### Local machine (laptop with browser)

```bash
python3 automations/scripts/google_health_auth.py
```

The script opens a localhost server on port 8080, prints an authorization URL, and waits. Open the URL in your browser, approve the scopes, and the redirect lands back on localhost. Tokens save to `config/google_health_tokens.json` (mode `0600`).

### VPS / headless

You need to tunnel port 8080 from the VPS back to your laptop so the OAuth callback can reach the script:

```bash
# On your laptop:
ssh -L 8080:localhost:8080 <user>@<vps>

# In that SSH session, on the VPS:
python3 automations/scripts/google_health_auth.py
```

Open the printed URL in your laptop's browser. Approve. The callback hits localhost:8080 on your laptop, gets tunneled to the VPS, and the script saves tokens there. Close the SSH session when done.

## Step 7 — Verify

```bash
python3 automations/scripts/google_health_fetch.py 2026-05-08
```

Should print a flat JSON object with sleep hours, stage minutes, bedtime and wake time, resting heart rate, Active Zone Minutes, workout fields, and the daily recovery metrics for that date. If everything is `None`, your wearable hadn't synced data for that date by the time you ran it — try a date a few days back.

Then check the raw archive path works:

```bash
python3 automations/scripts/google_health_raw.py 2026-05-08
# → data/health-raw/2026-05-08.json.gz, with a per-type point count
```

## Step 8 — Backfill history

```bash
# Fill in records that have no health data yet
python3 automations/scripts/google_health_backfill.py

# Re-derive EVERY record — also the fix-up path after a parsing change
python3 automations/scripts/google_health_backfill.py --all

# Raw archive for a date range (only as far back as the provider still keeps
# intraday data — daily summaries go back further than sleep stages)
python3 automations/scripts/google_health_raw.py --range 2026-04-01 2026-04-30
```

`--all` also recomputes the QQRT composite on every record. Run it once after any upgrade that changes sleep parsing.

## Step 9 — Schedule (optional)

The fetch runs on **three** cadences, because the data lands at three different times.

| When | Unit | Why |
|---|---|---|
| Every 30 min, 6:00–10:30 AM local | `pfc-health-fetch-morning` | Last night's sleep lands whenever your watch syncs to your phone, not on a clock — it can vary by hours from one morning to the next. A single fixed hour either fires too early (no data) or too late (you spend the morning looking at yesterday's numbers). Retrying catches the sync within 30 minutes of whenever it happens. |
| Noon local, two passes | `pfc-health-fetch` | Pass 1 fetches **today** (fresh sleep for a same-day rating in the tour); pass 2 fetches **yesterday**, finalizing its complete full-day activity totals now that the day is over. |

Retries are nearly free: `auto_fetch_health.py` writes nothing, commits nothing, and pushes nothing when the health block is unchanged. Providers also sometimes revise a night's numbers an hour later, so retrying picks up the correction.

- **Local with cron:**
  ```
  # Morning retry loop, every 30 min from 6 AM
  */30 6-10 * * * cd /path/to/your/pfc && /usr/bin/python3 automations/scripts/auto_fetch_health.py "$(date +\%Y-\%m-\%d)" >> /tmp/pfc-health-fetch.log 2>&1
  # Noon two-pass: today, then yesterday
  0 12 * * * cd /path/to/your/pfc && /usr/bin/python3 automations/scripts/auto_fetch_health.py "$(date +\%Y-\%m-\%d)"; cd /path/to/your/pfc && /usr/bin/python3 automations/scripts/auto_fetch_health.py >> /tmp/pfc-health-fetch.log 2>&1
  ```
- **VPS with systemd:** see [`docs/install/vps.md`](vps.md). `automations/systemd/install.sh` wires up `pfc-health-fetch.timer` and `pfc-health-fetch-morning.timer`.

Adjust the morning window to your own wake time — the 6:00–10:30 AM default is illustrative.

## Troubleshooting

- **`invalid_grant` on first auth.** Token request older than ~10 min — restart the auth script.
- **`access_denied` in the browser.** Your account isn't on the test-users list (Step 3.5). Add it.
- **`HTTP 403` from fetch.** Scopes weren't approved. Re-run `google_health_auth.py` with `prompt=consent` (already the default) — you'll see the consent screen again.
- **Token refresh fails after ~6 months.** Apps in "Testing" status have a 7-day refresh-token lifetime in some Google rollouts and a longer one in others. If your token dies, just re-run `google_health_auth.py`. Five-minute fix.
- **No data for recent dates.** Wearable sync lag — the watch has to reach the phone, and the phone the cloud. This is exactly what the morning retry loop exists for; don't tune a single fetch time around it.
- **A total looks too low (Active Zone Minutes, workouts).** These are interval streams: the API returns one point per segment and paginates. A single-page fetch silently truncates the day. Both fetch scripts use `api_get_all`, which follows `nextPageToken` — if you add a new interval-type fetch, use that, not `api_get`.
- **Sleep efficiency looks impossibly good on a night you know was broken.** A fragmented night is logged as several sessions, and the awake time *between* them appears in no session's own count. `sleep_reduce.py` adds those gaps back; `sleep_awake_gap_minutes` and `sleep_continuity` expose the split. Data fetched before that fix needs `google_health_backfill.py --all`.
- **A whole day's raw archive is missing the afternoon.** The file was written mid-day and something marked it final early. Re-capture with `google_health_raw.py <date> --force`.
- **No sleep score.** The provider's own 0–100 sleep score is not exposed by the API — it's app-proprietary. Quality here is computed from raw efficiency and deep-sleep share instead. Don't go looking for the score field.

## Operational notes

- The token file (`config/google_health_tokens.json`) is gitignored. Don't commit it.
- The `.env` file is gitignored. Don't commit it.
- Both files have to be regenerated per machine. Tokens are per-OAuth-client-per-account; cloning the repo to a second machine means a second `google_health_auth.py` run.
- If you rotate the client secret in Cloud Console, all existing tokens stop working — re-run auth on every machine.
