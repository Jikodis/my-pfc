#!/usr/bin/env python3
"""
Fetch today's health data from Google Health API (v4).

Returns JSON with sleep, resting heart rate, and active zone minutes.
Usage:
    python3 automations/scripts/google_health_fetch.py [YYYY-MM-DD]

If no date given, uses today in $LOCAL_TZ (default America/Denver).
Output: JSON to stdout, errors to stderr.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ── Config ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
# Local timezone: configurable via LOCAL_TZ env var (default America/Denver).
MOUNTAIN  = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))

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

ENV = load_env()

CLIENT_ID     = ENV.get("GOOGLE_HEALTH_CLIENT_ID")
CLIENT_SECRET = ENV.get("GOOGLE_HEALTH_CLIENT_SECRET")
TOKEN_FILE    = Path(ENV.get("GOOGLE_HEALTH_TOKEN_FILE", REPO_ROOT / "config/google_health_tokens.json"))
TOKEN_URI     = "https://oauth2.googleapis.com/token"
API_BASE      = "https://health.googleapis.com/v4/users/me/dataTypes"

# ── Token management ──────────────────────────────────────────────────────────

def load_tokens():
    if not TOKEN_FILE.exists():
        raise FileNotFoundError(
            f"Token file not found: {TOKEN_FILE}\n"
            "Run google_health_auth.py first."
        )
    return json.loads(TOKEN_FILE.read_text())


def save_tokens(tokens):
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    TOKEN_FILE.chmod(0o600)


def refresh_access_token(tokens):
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
    save_tokens(tokens)
    return tokens


def get_access_token():
    tokens = load_tokens()
    tokens = refresh_access_token(tokens)
    return tokens["access_token"]


# ── API call ──────────────────────────────────────────────────────────────────

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
        body = e.read().decode()
        return {"error": f"HTTP {e.code}: {body}"}


# ── Data parsers ──────────────────────────────────────────────────────────────

def fetch_sleep(access_token, date_str):
    next_date = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    filter_str = f'sleep.interval.civil_end_time >= "{date_str}" AND sleep.interval.civil_end_time < "{next_date}"'
    data = api_get("sleep", access_token, filter_str)

    if "error" in data:
        return data

    points = data.get("dataPoints", [])
    if not points:
        return {"total_minutes": None, "stages_minutes": {}}

    # Use the main sleep session if flagged, otherwise sum all
    main_points = [p for p in points if p.get("sleep", {}).get("metadata", {}).get("main")]
    target = main_points if main_points else points

    total_asleep = 0
    total_awake  = 0
    stages = {"deep": 0, "light": 0, "rem": 0, "wake": 0}

    for point in target:
        summary = point.get("sleep", {}).get("summary", {})

        total_asleep += int(summary.get("minutesAsleep", 0) or 0)
        total_awake  += int(summary.get("minutesAwake",  0) or 0)

        for s in summary.get("stagesSummary", []):
            stype = s.get("type", "").upper()
            mins  = int(s.get("minutes", 0) or 0)
            if stype == "DEEP":
                stages["deep"] += mins
            elif stype == "REM":
                stages["rem"]  += mins
            elif stype == "AWAKE":
                stages["wake"] += mins
            elif stype == "LIGHT":
                stages["light"] += mins

    return {
        "total_minutes":  total_asleep,
        "total_hours":    round(total_asleep / 60, 1),
        "awake_minutes":  total_awake,
        "stages_minutes": stages,
    }


def fetch_resting_hr(access_token, date_str):
    next_date = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    filter_str = f'daily_resting_heart_rate.date >= "{date_str}" AND daily_resting_heart_rate.date < "{next_date}"'
    data = api_get("daily-resting-heart-rate", access_token, filter_str)

    if "error" in data:
        return data

    points = data.get("dataPoints", [])
    if not points:
        return {"bpm": None, "_debug": "no data points returned"}

    point = points[-1]
    hr = point.get("dailyRestingHeartRate", {})
    bpm = hr.get("beatsPerMinute")
    if bpm is None:
        return {"bpm": None, "_debug_raw": point}
    return {"bpm": round(float(bpm))}


def fetch_active_zone_minutes(access_token, date_str):
    next_date = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    filter_str = f'active_zone_minutes.interval.civil_start_time >= "{date_str}" AND active_zone_minutes.interval.civil_start_time < "{next_date}"'
    data = api_get("active-zone-minutes", access_token, filter_str)

    if "error" in data:
        return data

    points = data.get("dataPoints", [])
    if not points:
        return {"total_minutes": None, "_debug": "no data points returned"}

    # Sum all intervals for the day
    total = 0
    for p in points:
        azm = p.get("activeZoneMinutes", {})
        total += int(azm.get("activeZoneMinutes", 0) or 0)

    if total == 0 and points:
        return {"total_minutes": 0, "_debug_raw": points[0]}
    return {"total_minutes": total}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(MOUNTAIN).strftime("%Y-%m-%d")

    try:
        access_token = get_access_token()
    except FileNotFoundError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    output = {
        "date":               date_str,
        "sleep":              fetch_sleep(access_token, date_str),
        "resting_heart_rate": fetch_resting_hr(access_token, date_str),
        "active_zone_minutes": fetch_active_zone_minutes(access_token, date_str),
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
