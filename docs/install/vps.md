# VPS install guide (Tier 3)

Tier 3 takes the Tier 2 local setup and moves it to a VPS running systemd user services. The result: automations run 24/7 regardless of whether your laptop is open, and you get persistent health-data fetching from any device.

This tier reuses everything from Tier 2 (Python venv, Google Health credentials). If you already have Tier 2 working on your laptop, you're mostly copying that setup to the server and swapping cron for systemd.

---

## Prerequisites

- Tier 2 complete locally (`docs/install/local-automations.md`) — or you intend to skip cron entirely and go straight to systemd on the VPS.
- A VPS you control with:
  - Linux (Debian 12 or Ubuntu 22.04+ recommended)
  - A non-root user account with sudo access
  - SSH key authentication configured (password auth is fine too, but key auth is better practice)
  - Minimum specs: 1 vCPU / 1 GB RAM. The scripts are lightweight; this is well within a $4/month Hetzner or DigitalOcean instance.
- Python 3.10+ on the VPS. Check with `python3 --version`; install with `sudo apt install python3 python3-venv python3-pip` if missing.

---

## Step 1 — Clone the repo on the VPS

SSH into your VPS, then:

```bash
git clone <your fork URL> ~/pfc
cd ~/pfc
python3 -m venv .venv
source .venv/bin/activate
pip install -r automations/requirements.txt
```

Replace `<your fork URL>` with the HTTPS or SSH URL of your personal fork (e.g. `https://github.com/yourname/my-pfc.git`).

Verify the venv installed correctly:

```bash
python3 -c "import google.auth; print('ok')"
```

---

## Step 2 — Set up Google Health on the VPS

The VPS is a headless environment — there's no browser to complete the OAuth callback. The token flow requires a short SSH tunnel to forward the callback to your laptop.

Follow `docs/install/google-health.md` §6 "VPS / headless" for the exact steps. The short version:
1. On the VPS, start the token authorization script — it will print a local callback URL.
2. On your laptop, open an SSH tunnel to forward that port.
3. Open the authorization URL in your laptop browser, complete the Google sign-in, and the token lands on the VPS.

Once the token file exists on the VPS, subsequent runs are non-interactive. The token refreshes automatically.

Set the `GOOGLE_HEALTH_*` env vars in the repo's `.env` file on the VPS — same values as your laptop, but pointing to the credential and token files at their VPS paths.

---

## Step 3 — Install the systemd user units

The `automations/systemd/` directory contains service and timer unit templates. The install script substitutes `__REPO_ROOT__` and `__REPO_URL__` based on the current working directory and configured git remote, then copies the units into `~/.config/systemd/user/` and reloads systemd:

```bash
bash automations/systemd/install.sh
```

Run this from the repo root. The script is idempotent — re-running it after changes to the unit templates applies the updates without manual cleanup.

After the script completes, verify the units are registered:

```bash
systemctl --user list-unit-files 'pfc-*.service' 'pfc-*.timer'
```

You should see `pfc-habit-autolog.service`, `pfc-habit-autolog.timer`, `pfc-health-fetch.service`, and `pfc-health-fetch.timer` listed as `enabled`.

---

## Step 4 — Enable linger

By default, systemd user sessions only run while a user is logged in. "Linger" keeps the user's systemd session alive after logout, so the timers keep firing even when no SSH session is active.

The `install.sh` script enables linger automatically. To verify:

```bash
loginctl show-user $USER | grep Linger
```

Expected output: `Linger=yes`. If it shows `no`, enable it manually:

```bash
sudo loginctl enable-linger $USER
```

---

## Step 5 — Verify the timers

Check that the timers are scheduled and firing:

```bash
# List upcoming timer fire times
systemctl --user list-timers pfc-habit-autolog.timer pfc-health-fetch.timer

# Watch live service output
journalctl --user -u pfc-habit-autolog.service -f
journalctl --user -u pfc-health-fetch.service -f
```

The `list-timers` output shows `NEXT` (when it will next fire) and `LAST` (when it last fired). If `LAST` is blank, the timer hasn't run yet — wait for the next scheduled time or trigger a manual test run (Step 6).

---

## Step 6 — Manual test run

Before relying on the timers, confirm a single run works end-to-end:

```bash
source .venv/bin/activate
python3 automations/scripts/auto_log_habits.py
python3 automations/scripts/auto_fetch_health.py
```

Then inspect the result:

```bash
git diff data/day-tracking.ndjson
git diff 6-habits/_data/habits-daily.ndjson
git log --oneline -3
```

If the scripts write data and commit successfully, the VPS setup is working. If you see auth errors, revisit Step 2 and the VPS / headless section of `docs/install/google-health.md`.

---

## Updating units after repo changes

If you modify the unit templates in `automations/systemd/` (e.g. to change schedule times), re-run the install script to apply the changes:

```bash
bash automations/systemd/install.sh
```

The script is idempotent and safe to re-run at any time. It reloads the systemd daemon and restarts affected services automatically.

---

## Keeping the repo in sync

The VPS runs automations and commits data. Your laptop is where you interact with Claude Code. Both push to the same remote.

To keep them in sync:

- On your laptop: `git pull` before starting a session.
- On the VPS: the automation scripts pull before running (the `install.sh` templating sets this up by default).

If you get merge conflicts between laptop and VPS commits, they'll almost always be in NDJSON data files. NDJSON files are append-mostly; the safe resolution is to keep both appended lines.

---

## Driving the VPS from your phone

If the point of the VPS is "I want to run my PFC system from anywhere," set up the **Termius + tmux + Claude Code Remote Control** stack next. That gives you mobile-friendly SSH, session persistence across drops, and a phone-app chat UI with push notifications for approval prompts.

Full walkthrough: `docs/install/remote-access.md`.
