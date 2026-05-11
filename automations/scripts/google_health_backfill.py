#!/usr/bin/env python3
"""
Backfill Google Health data (sleep + active zone minutes + resting HR)
into existing day-tracking.ndjson records that have no health data.

Usage:
    python3 automations/scripts/google_health_backfill.py [--all]

By default, only updates records where health is null.
Pass --all to re-fetch and overwrite existing health data too.
"""

import json
import sys
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT  = Path(__file__).resolve().parents[2]
LOCAL_TZ   = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))
TOKEN_URI  = "https://oauth2.googleapis.com/token"
API_BASE   = "https://health.googleapis.com/v4/users/me/dataTypes"

def load_env():
    env = {}
    for line in (REPO_ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env

ENV = load_env()
CLIENT_ID     = ENV["GOOGLE_HEALTH_CLIENT_ID"]
CLIENT_SECRET = ENV["GOOGLE_HEALTH_CLIENT_SECRET"]
TOKEN_FILE    = Path(ENV.get("GOOGLE_HEALTH_TOKEN_FILE", REPO_ROOT / "config/google_health_tokens.json"))
DAY_TRACKING  = REPO_ROOT / "data/day-tracking.ndjson"

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
    with urllib.request.urlopen(req) as r:
        new_tokens = json.loads(r.read())
    tokens["access_token"] = new_tokens["access_token"]
    if "refresh_token" in new_tokens:
        tokens["refresh_token"] = new_tokens["refresh_token"]
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    return tokens["access_token"]

def api_get(data_type, access_token, filter_str):
    url = f"{API_BASE}/{data_type}/dataPoints?" + urllib.parse.urlencode({"filter": filter_str})
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        msg = f"HTTP {e.code}: {e.read().decode()[:200]}"
        print(f"  ⚠️  Google Health API {data_type} error — {msg}", file=sys.stderr)
        return {"error": msg}

def next_day(date_str):
    return (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

def fetch_sleep(access_token, date_str):
    nd = next_day(date_str)
    f  = f'sleep.interval.civil_end_time >= "{date_str}" AND sleep.interval.civil_end_time < "{nd}"'
    data = api_get("sleep", access_token, f)
    if "error" in data:
        return None
    points = data.get("dataPoints", [])
    if not points:
        return None
    main_pts = [p for p in points if p.get("sleep", {}).get("metadata", {}).get("main")]
    target = main_pts if main_pts else points
    total_asleep = total_awake = 0
    stages = {"deep": 0, "light": 0, "rem": 0, "wake": 0}
    for point in target:
        summary = point.get("sleep", {}).get("summary", {})
        total_asleep += int(summary.get("minutesAsleep", 0) or 0)
        total_awake  += int(summary.get("minutesAwake",  0) or 0)
        for s in summary.get("stagesSummary", []):
            stype = s.get("type", "").upper()
            mins  = int(s.get("minutes", 0) or 0)
            if   stype == "DEEP":  stages["deep"]  += mins
            elif stype == "REM":   stages["rem"]   += mins
            elif stype == "AWAKE": stages["wake"]  += mins
            elif stype == "LIGHT": stages["light"] += mins
    if total_asleep == 0:
        return None
    return {
        "sleep_minutes":       total_asleep,
        "sleep_hours":         round(total_asleep / 60, 1),
        "awake_minutes":       total_awake,
        "sleep_deep_minutes":  stages["deep"],
        "sleep_rem_minutes":   stages["rem"],
        "sleep_light_minutes": stages["light"],
    }

def fetch_resting_hr(access_token, date_str):
    nd = next_day(date_str)
    f  = f'daily_resting_heart_rate.date >= "{date_str}" AND daily_resting_heart_rate.date < "{nd}"'
    data = api_get("daily-resting-heart-rate", access_token, f)
    if "error" in data:
        return None
    points = data.get("dataPoints", [])
    if not points:
        return None
    bpm = points[-1].get("dailyRestingHeartRate", {}).get("beatsPerMinute")
    return round(float(bpm)) if bpm else None

def fetch_azm(access_token, date_str):
    """Total AZM = passive (between workouts) + exercise (from logged workouts).

    Per Google Health docs, the active-zone-minutes endpoint returns only
    passively-measured AZM. Logged workouts (e.g. hikes, tennis tracked from
    the watch) live on the exercise endpoint with their own metricsSummary.activeZoneMinutes.
    Fitbit's daily AZM total includes both, so we sum across both endpoints.
    """
    nd = next_day(date_str)

    f1 = f'active_zone_minutes.interval.civil_start_time >= "{date_str}" AND active_zone_minutes.interval.civil_start_time < "{nd}"'
    passive_data = api_get("active-zone-minutes", access_token, f1)
    passive_total = 0
    if "error" not in passive_data:
        for p in passive_data.get("dataPoints", []):
            passive_total += int(p.get("activeZoneMinutes", {}).get("activeZoneMinutes", 0) or 0)

    f2 = f'exercise.interval.civil_start_time >= "{date_str}" AND exercise.interval.civil_start_time < "{nd}"'
    exercise_data = api_get("exercise", access_token, f2)
    exercise_total = 0
    if "error" not in exercise_data:
        for p in exercise_data.get("dataPoints", []):
            exercise_total += int(p.get("exercise", {}).get("metricsSummary", {}).get("activeZoneMinutes", 0) or 0)

    total = passive_total + exercise_total
    return total if total > 0 else None

def fetch_health(access_token, date_str):
    sleep = fetch_sleep(access_token, date_str)
    hr    = fetch_resting_hr(access_token, date_str)
    azm   = fetch_azm(access_token, date_str)
    if sleep is None and hr is None and azm is None:
        return None
    result = sleep or {}
    result["resting_hr_bpm"]      = hr
    result["active_zone_minutes"] = azm
    return result

def main():
    overwrite = "--all" in sys.argv

    records = [json.loads(l) for l in DAY_TRACKING.read_text().splitlines() if l.strip()]
    dates_to_fetch = [
        r["date"] for r in records
        if overwrite or not r.get("health")
    ]

    if not dates_to_fetch:
        print("All records already have health data. Use --all to re-fetch.")
        return

    print(f"Fetching health data for {len(dates_to_fetch)} dates...")
    access_token = get_access_token()

    health_by_date = {}
    for date_str in dates_to_fetch:
        health = fetch_health(access_token, date_str)
        status = f"{health['sleep_hours']}h sleep, {health.get('active_zone_minutes')} AZM" if health else "no data"
        print(f"  {date_str}: {status}")
        health_by_date[date_str] = health

    # Update records in place
    updated = []
    changed = 0
    for record in records:
        date_str = record["date"]
        if date_str in health_by_date and health_by_date[date_str] is not None:
            record["health"] = health_by_date[date_str]
            changed += 1
        updated.append(json.dumps(record, separators=(",", ":")))

    DAY_TRACKING.write_text("\n".join(updated) + "\n")
    print(f"\nUpdated {changed} records in day-tracking.ndjson.")

if __name__ == "__main__":
    main()
