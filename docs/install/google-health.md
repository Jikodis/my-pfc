# Google Health install guide

Set up the Google Health API integration that powers `automations/scripts/auto_fetch_health.py` and `auto_log_habits.py`. Required if you want auto-fetched sleep, resting HR, and Active Zone Minutes flowing into `data/day-tracking.ndjson` and `6-habits/_data/habits-daily.ndjson`.

If you don't want those features, skip this — the system degrades gracefully (the `health` field on day-tracking rows just stays absent).

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

Should print sleep hours, resting HR, and AZM for that date. If it prints `None` for everything, your wearable hadn't synced data for that date by the time you ran it — try a date a few days back.

## Step 8 — Schedule (optional)

For continuous auto-fetch:

- **Local with cron:** add a twice-daily job around 8 AM and 10:30 PM local time (the defaults below; edit to suit your sleep schedule):
  ```
  0 8,22 * * * cd /path/to/your/pfc && /usr/bin/python3 automations/scripts/auto_log_habits.py >> /tmp/pfc-habit-autolog.log 2>&1
  30 22 * * * cd /path/to/your/pfc && /usr/bin/python3 automations/scripts/auto_fetch_health.py >> /tmp/pfc-fetch-health.log 2>&1
  ```
- **VPS with systemd:** see [`docs/install/vps.md`](vps.md). The `automations/systemd/install.sh` script wires up `pfc-habit-autolog.timer`.

## Troubleshooting

- **`invalid_grant` on first auth.** Token request older than ~10 min — restart the auth script.
- **`access_denied` in the browser.** Your account isn't on the test-users list (Step 3.5). Add it.
- **`HTTP 403` from fetch.** Scopes weren't approved. Re-run `google_health_auth.py` with `prompt=consent` (already the default) — you'll see the consent screen again.
- **Token refresh fails after ~6 months.** Apps in "Testing" status have a 7-day refresh-token lifetime in some Google rollouts and a longer one in others. If your token dies, just re-run `google_health_auth.py`. Five-minute fix.
- **No data for recent dates.** Wearable sync lag. Most data is fully synced ~11 AM the next day. Don't fetch today's data before evening.

## Operational notes

- The token file (`config/google_health_tokens.json`) is gitignored. Don't commit it.
- The `.env` file is gitignored. Don't commit it.
- Both files have to be regenerated per machine. Tokens are per-OAuth-client-per-account; cloning the repo to a second machine means a second `google_health_auth.py` run.
- If you rotate the client secret in Cloud Console, all existing tokens stop working — re-run auth on every machine.
