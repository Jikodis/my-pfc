#!/usr/bin/env python3
"""
Backfill Google Health data into `data/day-tracking.ndjson`.

Writes the canonical flat `health` block on each record: sleep (duration, stages,
timing, continuity, awakenings), resting heart rate, Active Zone Minutes, tracked
workouts, and the daily recovery metrics (heart-rate variability, blood oxygen,
breathing rate, skin temperature, VO2 max).

Usage:
    python3 automations/scripts/google_health_backfill.py [--all]

By default, only updates records whose `health` is null/absent.
Pass `--all` to re-fetch and overwrite existing health data too — which is also
how you re-derive history after a parsing fix (e.g. the fragmented-night awake-gap
accounting in `sleep_reduce.py`).
"""

import json
import sys
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT  = Path(__file__).resolve().parents[2]
LOCAL_TZ   = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))
TOKEN_URI  = "https://oauth2.googleapis.com/token"
API_BASE   = "https://health.googleapis.com/v4/users/me/dataTypes"

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Sleep reduction (awake-gap accounting, awakenings, stage totals) is defined once in
# sleep_reduce.py, and tracked-workout reduction once in exercise_reduce.py. Both are
# shared with google_health_fetch.py so the daily path and the history path agree.
from sleep_reduce import reduce_sleep        # noqa: E402
from exercise_reduce import exercise_fields  # noqa: E402


def load_env():
    env = {}
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip()
                # Values may be quoted so bash `source` survives shell
                # metacharacters (an unquoted & would otherwise break the bin/
                # scripts that source this file).
                env[k.strip()] = v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"" else v
    return env


ENV = load_env()
CLIENT_ID     = ENV.get("GOOGLE_HEALTH_CLIENT_ID")
CLIENT_SECRET = ENV.get("GOOGLE_HEALTH_CLIENT_SECRET")
TOKEN_FILE    = Path(ENV.get("GOOGLE_HEALTH_TOKEN_FILE", REPO_ROOT / "config/google_health_tokens.json"))
DAY_TRACKING  = REPO_ROOT / "data/day-tracking.ndjson"


def get_access_token():
    if not CLIENT_ID or not CLIENT_SECRET:
        sys.exit("GOOGLE_HEALTH_CLIENT_ID / GOOGLE_HEALTH_CLIENT_SECRET not set in .env — see docs/install/google-health.md")
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


def api_get_all(data_type, access_token, filter_str):
    """Every dataPoint for a filter, following nextPageToken. Returns (points, ok).

    REQUIRED for interval-stream types (`active-zone-minutes`, `exercise`): they
    return one dataPoint per segment and DO paginate, so a single-page `api_get`
    silently truncates the day and understates any total summed from them.
    Daily-summary and sleep types return a single point and don't need this.
    """
    points, token = [], None
    while True:
        params = {"filter": filter_str, "pageSize": "1000"}
        if token:
            params["pageToken"] = token
        url = f"{API_BASE}/{data_type}/dataPoints?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {access_token}")
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            print(f"  ⚠️  Google Health API {data_type} error — HTTP {e.code}: "
                  f"{e.read().decode()[:200]}", file=sys.stderr)
            return points, False
        points.extend(data.get("dataPoints", []))
        token = data.get("nextPageToken")
        if not token:
            return points, True


def next_day(date_str):
    return (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")


def fetch_sleep(access_token, date_str):
    f = (f'sleep.interval.civil_end_time >= "{date_str}" AND '
         f'sleep.interval.civil_end_time < "{next_day(date_str)}"')
    data = api_get("sleep", access_token, f)
    if "error" in data:
        return None
    reduced = reduce_sleep(data.get("dataPoints", []), LOCAL_TZ)
    if reduced is None or not reduced.get("sleep_minutes"):
        return None
    return reduced


def fetch_resting_hr(access_token, date_str):
    f = (f'daily_resting_heart_rate.date >= "{date_str}" AND '
         f'daily_resting_heart_rate.date < "{next_day(date_str)}"')
    data = api_get("daily-resting-heart-rate", access_token, f)
    if "error" in data:
        return None
    points = data.get("dataPoints", [])
    if not points:
        return None
    bpm = points[-1].get("dailyRestingHeartRate", {}).get("beatsPerMinute")
    return round(float(bpm)) if bpm else None


def fetch_exercise_points(access_token, date_str):
    """Raw `exercise` dataPoints for the local day, or None if the call failed.
    None and [] mean different things: None = unknown, [] = no tracked workouts."""
    f = (f'exercise.interval.civil_start_time >= "{date_str}" AND '
         f'exercise.interval.civil_start_time < "{next_day(date_str)}"')
    points, ok = api_get_all("exercise", access_token, f)
    return points if ok else None


def fetch_azm(access_token, date_str, exercise_points=None):
    """Total AZM = passive (between workouts) + AZM earned inside logged workouts.

    The active-zone-minutes endpoint returns only passively-measured AZM. Logged
    workouts live on the exercise endpoint with their own
    `metricsSummary.activeZoneMinutes`. The device's daily total includes both, so
    both are summed here. Pass `exercise_points` to reuse an already-fetched
    exercise response instead of calling that endpoint twice."""
    f1 = (f'active_zone_minutes.interval.civil_start_time >= "{date_str}" AND '
          f'active_zone_minutes.interval.civil_start_time < "{next_day(date_str)}"')
    passive_points, _ = api_get_all("active-zone-minutes", access_token, f1)
    passive_total = 0
    for p in passive_points:
        passive_total += int(p.get("activeZoneMinutes", {}).get("activeZoneMinutes", 0) or 0)

    if exercise_points is None:
        exercise_points = fetch_exercise_points(access_token, date_str) or []
    exercise_total = 0
    for p in exercise_points:
        exercise_total += int(p.get("exercise", {}).get("metricsSummary", {}).get("activeZoneMinutes", 0) or 0)

    total = passive_total + exercise_total
    return total if total > 0 else None


def _daily_point(access_token, dt, date_str):
    """Inner payload dict of a daily-summary data type on date_str, else None.
    The inner key is the camelCase of the dataType id (daily-vo2-max → dailyVo2Max)."""
    snake = dt.replace("-", "_")
    f = f'{snake}.date >= "{date_str}" AND {snake}.date < "{next_day(date_str)}"'
    data = api_get(dt, access_token, f)
    if "error" in data:
        return None
    pts = data.get("dataPoints", [])
    if not pts:
        return None
    parts = snake.split("_")
    inner_key = parts[0] + "".join(p.capitalize() for p in parts[1:])
    return pts[-1].get(inner_key, {})


def _num(v, ndigits=1):
    return round(float(v), ndigits) if v is not None else None


def fetch_daily_metrics(access_token, date_str):
    """Daily recovery metrics: heart-rate variability, blood oxygen, breathing rate,
    skin-temperature deviation, VO2 max. Each is a single daily value (no pagination).
    Returns a flat dict; fields are None on days the device recorded no value.

    `daily-heart-rate-zones` is intentionally excluded — it carries only zone threshold
    heart rates, not time in zone, so it has no trend value. Activity totals (steps,
    distance, calories) are interval-based and live in the raw archive
    (`data/health-raw/`), not here."""
    out = {
        "hrv_ms": None,
        "spo2_avg_pct": None, "spo2_lower_pct": None, "spo2_upper_pct": None,
        "respiratory_rate_bpm": None,
        "skin_temp_nightly_c": None, "skin_temp_baseline_c": None,
        "vo2max": None, "cardio_fitness_level": None,
    }
    hrv = _daily_point(access_token, "daily-heart-rate-variability", date_str)
    if hrv:
        out["hrv_ms"] = _num(hrv.get("averageHeartRateVariabilityMilliseconds"))
    spo2 = _daily_point(access_token, "daily-oxygen-saturation", date_str)
    if spo2:
        out["spo2_avg_pct"]   = _num(spo2.get("averagePercentage"))
        out["spo2_lower_pct"] = _num(spo2.get("lowerBoundPercentage"))
        out["spo2_upper_pct"] = _num(spo2.get("upperBoundPercentage"))
    rr = _daily_point(access_token, "daily-respiratory-rate", date_str)
    if rr:
        out["respiratory_rate_bpm"] = _num(rr.get("breathsPerMinute"))
    temp = _daily_point(access_token, "daily-sleep-temperature-derivations", date_str)
    if temp:
        out["skin_temp_nightly_c"]  = _num(temp.get("nightlyTemperatureCelsius"), 2)
        out["skin_temp_baseline_c"] = _num(temp.get("baselineTemperatureCelsius"), 2)
    vo2 = _daily_point(access_token, "daily-vo2-max", date_str)
    if vo2:
        out["vo2max"]               = _num(vo2.get("vo2Max"))
        out["cardio_fitness_level"] = vo2.get("cardioFitnessLevel")
    return out


def fetch_health(access_token, date_str):
    """The whole flat `health` block for one day, or None when nothing was recorded."""
    sleep     = fetch_sleep(access_token, date_str)
    hr        = fetch_resting_hr(access_token, date_str)
    ex_pts    = fetch_exercise_points(access_token, date_str)
    azm       = fetch_azm(access_token, date_str, ex_pts)
    daily     = fetch_daily_metrics(access_token, date_str)
    has_daily = any(v is not None for v in daily.values())
    if sleep is None and hr is None and azm is None and not has_daily and not ex_pts:
        return None
    result = sleep or {}
    result["resting_hr_bpm"]      = hr
    result["active_zone_minutes"] = azm
    result.update(daily)
    result.update(exercise_fields(ex_pts, azm))
    return result


def main():
    overwrite = "--all" in sys.argv

    records = [json.loads(l) for l in DAY_TRACKING.read_text().splitlines() if l.strip()]
    dates_to_fetch = [r["date"] for r in records if overwrite or not r.get("health")]

    if not dates_to_fetch:
        print("All records already have health data. Use --all to re-fetch.")
        return

    print(f"Fetching health data for {len(dates_to_fetch)} dates...")
    access_token = get_access_token()

    health_by_date = {}
    for date_str in dates_to_fetch:
        health = fetch_health(access_token, date_str)
        status = (
            f"{health.get('sleep_hours')}h sleep, {health.get('active_zone_minutes')} AZM, "
            f"{health.get('workout_count')} workouts"
        ) if health else "no data"
        print(f"  {date_str}: {status}")
        health_by_date[date_str] = health

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

    # Recompute the QQRT sleep composite so `qqrt` never lags a health rewrite.
    try:
        import backfill_qqrt
        qres = backfill_qqrt.recompute()
        print(f"QQRT recomputed ({qres['changed']} of {qres['records']} records changed).")
    except Exception as e:  # noqa: BLE001 — non-blocking; health data is already written
        print(f"QQRT recompute failed (non-blocking): {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
