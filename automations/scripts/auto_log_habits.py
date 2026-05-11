#!/usr/bin/env python3
"""
Auto-log habits from Google Health API data.

Currently a no-op: no habits in habit_schema.yaml declare an `auto_log:`
block. Add `auto_log:` to a habit definition to enable automatic logging. The helper
check_active_zone_minutes() and the fetch utilities are kept for future
auto-logged habits. Raw AZM is still fetched into day-tracking.health by
automations/scripts/auto_fetch_health.py — that path is unaffected.

Usage:
    python3 automations/scripts/auto_log_habits.py [YYYY-MM-DD]

If no date given, uses today in $LOCAL_TZ (default America/Denver).
Skips habits already logged for the date. Safe to run multiple times.
"""

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ── Config ────────────────────────────────────────────────────────────────────

REPO_ROOT     = Path(__file__).resolve().parents[2]
# Local timezone: configurable via LOCAL_TZ env var (default America/Denver).
MOUNTAIN      = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))
HABITS_FILE   = REPO_ROOT / "data" / "habits-daily.ndjson"
TOKEN_URI     = "https://oauth2.googleapis.com/token"
API_BASE      = "https://health.googleapis.com/v4/users/me/dataTypes"

# ── Env / tokens ──────────────────────────────────────────────────────────────

def load_env():
    env = {}
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

ENV           = load_env()
CLIENT_ID     = ENV.get("GOOGLE_HEALTH_CLIENT_ID")
CLIENT_SECRET = ENV.get("GOOGLE_HEALTH_CLIENT_SECRET")
TOKEN_FILE    = Path(ENV.get("GOOGLE_HEALTH_TOKEN_FILE",
                             str(REPO_ROOT / "config/google_health_tokens.json")))


def get_access_token():
    tokens = json.loads(TOKEN_FILE.read_text())
    data = urllib.parse.urlencode({
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": tokens["refresh_token"],
        "grant_type":    "refresh_token",
    }).encode()
    req = urllib.request.Request(TOKEN_URI, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req) as resp:
        new_tokens = json.loads(resp.read())
    tokens["access_token"] = new_tokens["access_token"]
    if "refresh_token" in new_tokens:
        tokens["refresh_token"] = new_tokens["refresh_token"]
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    TOKEN_FILE.chmod(0o600)
    return tokens["access_token"]


# ── API helpers ───────────────────────────────────────────────────────────────

def api_get(data_type, access_token, filter_str=None):
    url = f"{API_BASE}/{data_type}/dataPoints"
    if filter_str:
        url += "?" + urllib.parse.urlencode({"filter": filter_str})
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode()}"}


# ── Habit checkers ────────────────────────────────────────────────────────────

def check_active_zone_minutes(access_token, date_str, threshold=20):
    """Return True if active zone minutes for `date_str` >= threshold."""
    next_date = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    filter_str = (
        f'active_zone_minutes.interval.civil_start_time >= "{date_str}" AND '
        f'active_zone_minutes.interval.civil_start_time < "{next_date}"'
    )
    data = api_get("active-zone-minutes", access_token, filter_str)
    if "error" in data:
        print(f"  [azm] API error: {data['error']}", file=sys.stderr)
        return False

    points = data.get("dataPoints", [])
    if not points:
        print(f"  [azm] No data points for {date_str}", file=sys.stderr)
        return False

    total = sum(int(p.get("activeZoneMinutes", {}).get("activeZoneMinutes", 0) or 0) for p in points)
    print(f"  [azm] Total active zone minutes: {total}")
    return total >= threshold


# ── Habit log helpers ─────────────────────────────────────────────────────────

def already_logged(date_str, habit_id):
    """Return True if this habit is already logged for this date."""
    if not HABITS_FILE.exists():
        return False
    for line in HABITS_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            if record.get("date") == date_str and record.get("habit_id") == habit_id:
                return True
        except json.JSONDecodeError:
            continue
    return False


def log_habit(date_str, habit_id):
    """Append a habit completion record."""
    record = json.dumps({"date": date_str, "habit_id": habit_id, "completed": True,
                         "source": "google_health_auto"})
    with HABITS_FILE.open("a") as f:
        f.write(record + "\n")
    print(f"  Logged: {habit_id} for {date_str}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(MOUNTAIN).strftime("%Y-%m-%d")
    print(f"Auto-logging habits for {date_str}")

    try:
        access_token = get_access_token()
    except (FileNotFoundError, KeyError) as e:
        print(f"Auth error: {e}\nRun google_health_auth.py first.", file=sys.stderr)
        sys.exit(1)

    logged_any = False

    # No auto-logged habits currently active. Add a new auto-log block here
    # when a habit with `auto_log:` is added to habit_schema.yaml.

    # ── Commit if anything was logged ─────────────────────────────────────────
    if logged_any:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "add", "6-habits/_data/habits-daily.ndjson"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"git add failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "commit", "-m", f"habit: auto-log {date_str}"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"git commit failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "push"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"git push failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        print(f"Committed and pushed habit log for {date_str}.")
    else:
        print("Nothing new to log.")


if __name__ == "__main__":
    main()
