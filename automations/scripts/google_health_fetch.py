#!/usr/bin/env python3
"""
Fetch one day of health data from the Google Health API (v4).

Prints the canonical **flat** `health` schema — the same shape
`google_health_backfill.fetch_health()` writes onto a `day-tracking.ndjson`
record, and the same field names the `pfc-log-day` / `pfc-analyze-trends`
skills read. Sleep, resting heart rate, Active Zone Minutes, tracked workouts,
and the daily recovery metrics (heart-rate variability, blood oxygen, breathing
rate, skin temperature, VO2 max).

Usage:
    python3 automations/scripts/google_health_fetch.py [YYYY-MM-DD]

If no date is given, uses today in $LOCAL_TZ (default America/Denver).
Output: JSON to stdout, errors to stderr.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ── Config ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
# Local timezone: configurable via LOCAL_TZ env var (default America/Denver).
LOCAL_TZ  = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Sleep reduction (awake-gap accounting, awakenings, stage totals) and tracked-workout
# reduction each live in one shared module, imported by this script AND by
# google_health_backfill.py, so the daily path and the history path cannot drift.
from sleep_reduce import reduce_sleep      # noqa: E402
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


# ── API calls ─────────────────────────────────────────────────────────────────

def api_get(data_type, access_token, filter_str=None):
    """Single-page fetch. Fine for daily-summary and sleep types, which return one point."""
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


def api_get_all(data_type, access_token, filter_str):
    """Every dataPoint for a filter, following nextPageToken. Returns (points, ok).

    REQUIRED for interval-stream types (`active-zone-minutes`, `exercise`): they emit
    one point per segment and DO paginate, so a single-page `api_get` silently
    truncates the day and understates any total summed from them.
    Mirrors `google_health_backfill.api_get_all` — keep the two in sync."""
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
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError:
            return points, False
        points.extend(data.get("dataPoints", []))
        token = data.get("nextPageToken")
        if not token:
            return points, True


def next_day(date_str):
    return (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")


# ── Data parsers ──────────────────────────────────────────────────────────────

def fetch_sleep(access_token, date_str):
    """Canonical flat sleep schema (matches google_health_backfill.fetch_sleep)."""
    filter_str = (f'sleep.interval.civil_end_time >= "{date_str}" AND '
                  f'sleep.interval.civil_end_time < "{next_day(date_str)}"')
    data = api_get("sleep", access_token, filter_str)
    if "error" in data:
        return data

    reduced = reduce_sleep(data.get("dataPoints", []), LOCAL_TZ)
    if reduced is None:
        # No sleep dataPoints at all — return the all-None shape.
        return {
            "sleep_minutes":       None, "sleep_hours":        None,
            "awake_minutes":       None, "awake_intrasession_minutes": None,
            "sleep_awake_gap_minutes": None, "sleep_sessions":  None,
            "sleep_continuity":    None,
            "sleep_deep_minutes":  None, "sleep_rem_minutes":  None,
            "sleep_light_minutes": None,
            "sleep_bedtime":       None, "sleep_wake_time":    None,
            "awakenings":          None, "awakenings_count":   None,
        }
    return reduced


def fetch_resting_hr(access_token, date_str):
    """Returns {'resting_hr_bpm': int|None}."""
    filter_str = (f'daily_resting_heart_rate.date >= "{date_str}" AND '
                  f'daily_resting_heart_rate.date < "{next_day(date_str)}"')
    data = api_get("daily-resting-heart-rate", access_token, filter_str)
    if "error" in data:
        return data

    points = data.get("dataPoints", [])
    if not points:
        return {"resting_hr_bpm": None}
    bpm = points[-1].get("dailyRestingHeartRate", {}).get("beatsPerMinute")
    return {"resting_hr_bpm": round(float(bpm)) if bpm is not None else None}


def fetch_exercise_points(access_token, date_str):
    """Raw `exercise` dataPoints for the local day, or None if the call failed.
    None and [] differ: None = unknown, [] = no tracked workouts.
    Mirrors google_health_backfill.fetch_exercise_points — keep in sync."""
    filter_str = (f'exercise.interval.civil_start_time >= "{date_str}" AND '
                  f'exercise.interval.civil_start_time < "{next_day(date_str)}"')
    points, ok = api_get_all("exercise", access_token, filter_str)
    return points if ok else None


def fetch_active_zone_minutes(access_token, date_str, exercise_points=None):
    """Returns {'active_zone_minutes': int|None} — passive AZM PLUS the AZM earned
    inside tracked workouts.

    The active-zone-minutes endpoint returns only passively-measured AZM; a logged
    workout carries its own `metricsSummary.activeZoneMinutes` on the exercise
    endpoint. The device's daily total counts both, so both are summed here.
    Mirrors google_health_backfill.fetch_azm — keep in sync."""
    filter_str = (f'active_zone_minutes.interval.civil_start_time >= "{date_str}" AND '
                  f'active_zone_minutes.interval.civil_start_time < "{next_day(date_str)}"')
    passive_points, ok = api_get_all("active-zone-minutes", access_token, filter_str)
    if not ok and not passive_points:
        return {"error": "active-zone-minutes fetch failed"}

    total = 0
    for p in passive_points:
        azm = p.get("activeZoneMinutes", {})
        total += int(azm.get("activeZoneMinutes", 0) or 0)

    if exercise_points is None:
        exercise_points = fetch_exercise_points(access_token, date_str) or []
    for p in exercise_points:
        total += int((p.get("exercise", {}).get("metricsSummary", {}) or {}).get("activeZoneMinutes", 0) or 0)

    return {"active_zone_minutes": total or None}


def _daily_point(access_token, dt, date_str):
    """Inner payload dict of a daily-summary data type on date_str, else None.
    Inner key = camelCase of the dataType id (daily-vo2-max -> dailyVo2Max).
    Mirrors google_health_backfill._daily_point — keep in sync."""
    snake = dt.replace("-", "_")
    f = f'{snake}.date >= "{date_str}" AND {snake}.date < "{next_day(date_str)}"'
    data = api_get(dt, access_token, f)
    if "error" in data:
        return None
    pts = data.get("dataPoints", [])
    if not pts:
        return None
    parts = snake.split("_")
    return pts[-1].get(parts[0] + "".join(p.capitalize() for p in parts[1:]), {})


def _num(v, ndigits=1):
    return round(float(v), ndigits) if v is not None else None


def fetch_daily_metrics(access_token, date_str):
    """Daily recovery metrics: heart-rate variability, blood oxygen, breathing rate,
    skin-temperature deviation, VO2 max. Each is one value per day (no pagination).
    Fields are None on days the device recorded nothing.

    `daily-heart-rate-zones` is intentionally excluded — it carries only the zone
    threshold heart rates, not time spent in each zone, so it has no trend value.
    Activity totals (steps, distance, calories) are interval-based and live in the
    raw archive (`data/health-raw/`), not here.
    Mirrors google_health_backfill.fetch_daily_metrics — keep in sync."""
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")

    try:
        access_token = get_access_token()
    except FileNotFoundError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    output = {"date": date_str}
    sleep  = fetch_sleep(access_token, date_str)
    rhr    = fetch_resting_hr(access_token, date_str)
    ex_pts = fetch_exercise_points(access_token, date_str)
    azm    = fetch_active_zone_minutes(access_token, date_str, ex_pts)
    daily  = fetch_daily_metrics(access_token, date_str)
    for d in (sleep, rhr, azm, daily):
        if isinstance(d, dict) and "error" not in d:
            output.update(d)
    output.update(exercise_fields(ex_pts, output.get("active_zone_minutes")))

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
