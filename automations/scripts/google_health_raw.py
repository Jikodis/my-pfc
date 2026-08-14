#!/usr/bin/env python3
"""Capture comprehensive RAW Google Health data for one day into a per-day archive file.

Writes `data/health-raw/YYYY-MM-DD.json.gz` holding the full, unflattened API
responses for every available data type — daily summaries, intraday samples
(per-minute heart rate, intraday heart-rate variability / blood oxygen), interval
streams (steps, distance, energy, Active Zone Minutes, exercise), and sleep stages.

This is the **insurance layer**. Derived day-level metrics live in
`day-tracking.ndjson` (via `google_health_backfill.fetch_health`); this store keeps
EVERYTHING ELSE, so a future analysis is never blocked by what you happened to
compute today. Intraday data has a short retention window on the provider's side
(sleep stages age out after roughly a year), so it has to be captured going
forward — it cannot be backfilled indefinitely.

Design decisions
----------------
- **One file per local day, rewritten only while the day is still open.** A file
  captured mid-day is re-fetched by any later run until one lands after local
  midnight; after that the day is final and the file is never touched again.
  Without this, everything logged after the morning run (afternoon workouts, AZM
  accrued through the day) is permanently missing — the file exists, so a later
  pass skips it.
- **Gzipped compact JSON** — lossless, roughly 8× smaller. Per-day files are
  immutable once final, so they get no benefit from git delta compression anyway.
- **Heart rate is downsampled to 1-minute means.** The raw stream arrives at
  ~2-second resolution (~34k points/day ≈ 11 MB/day ≈ 4 GB/yr) — far beyond any
  realistic analysis need and a fast path to GitHub's repo-size limit. One minute
  is the standard "intraday" granularity. EVERY OTHER stream is kept at full
  resolution.
- **Day boundary = local midnight** (`LOCAL_TZ`), converted to whichever UTC or
  civil window each data type expects.

Usage:
    python3 automations/scripts/google_health_raw.py                     # yesterday (local)
    python3 automations/scripts/google_health_raw.py YYYY-MM-DD
    python3 automations/scripts/google_health_raw.py --range START END   # inclusive
    python3 automations/scripts/google_health_raw.py YYYY-MM-DD --force  # overwrite
"""

import gzip
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from google_health_fetch import get_access_token, api_get, API_BASE  # noqa: E402
import urllib.parse, urllib.request, urllib.error  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR   = REPO_ROOT / "data" / "health-raw"
LOCAL_TZ  = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))

# Data type → which time field its list filter uses.
#   daily    : "{snake}.date"                       (local-day keyed)
#   sample   : "{snake}.sample_time.physical_time"  (UTC instant)
#   interval : "{snake}.interval.start_time"        (UTC instant)
#   sleep    : "sleep.interval.civil_end_time"      (local civil — keeps a night on its wake date)
DAILY_TYPES = [
    "daily-heart-rate-variability", "daily-heart-rate-zones", "daily-oxygen-saturation",
    "daily-respiratory-rate", "daily-resting-heart-rate",
    "daily-sleep-temperature-derivations", "daily-vo2-max",
]
SAMPLE_TYPES = [
    "heart-rate", "heart-rate-variability", "oxygen-saturation",
    "respiratory-rate-sleep-summary", "vo2-max", "run-vo2-max", "weight", "body-fat",
]
INTERVAL_TYPES = ["steps", "distance", "active-energy-burned", "active-zone-minutes", "exercise"]
# total-calories is excluded: its list method is unsupported (it requires a daily
# roll-up call); active-energy-burned covers calorie burn at interval resolution.


def _utc_window(date_str):
    """Local-midnight day → (start_utc_z, end_utc_z) ISO strings."""
    y, m, d = (int(x) for x in date_str.split("-"))
    start = datetime(y, m, d, tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)
    fmt = lambda dt: dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    return fmt(start), fmt(end)


def _filter_for(dt, date_str):
    snake = dt.replace("-", "_")
    nd = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    su, eu = _utc_window(date_str)
    if dt in DAILY_TYPES:
        return f'{snake}.date >= "{date_str}" AND {snake}.date < "{nd}"'
    if dt in SAMPLE_TYPES:
        return f'{snake}.sample_time.physical_time >= "{su}" AND {snake}.sample_time.physical_time < "{eu}"'
    if dt in INTERVAL_TYPES:
        # `exercise` only accepts the civil_start_time field (the others take start_time).
        field = "interval.civil_start_time" if dt == "exercise" else "interval.start_time"
        bound = f'"{date_str}"' if dt == "exercise" else f'"{su}"'
        ubound = f'"{nd}"' if dt == "exercise" else f'"{eu}"'
        return f'{snake}.{field} >= {bound} AND {snake}.{field} < {ubound}'
    raise ValueError(dt)


def _get_page(dt, access_token, filter_str, page_token):
    params = {"filter": filter_str, "pageSize": "1000"}
    if page_token:
        params["pageToken"] = page_token
    url = f"{API_BASE}/{dt}/dataPoints?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def fetch_all_pages(dt, access_token, filter_str):
    """Return (points, error). Follows nextPageToken until exhausted — a single page
    silently truncates any high-volume stream."""
    points, token = [], None
    while True:
        try:
            data = _get_page(dt, access_token, filter_str, token)
        except urllib.error.HTTPError as e:
            return points, f"HTTP {e.code}: {e.read().decode()[:160]}"
        points.extend(data.get("dataPoints", []))
        token = data.get("nextPageToken")
        if not token:
            return points, None


def fetch_sleep_raw(access_token, date_str):
    nd = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    f = f'sleep.interval.civil_end_time >= "{date_str}" AND sleep.interval.civil_end_time < "{nd}"'
    data = api_get("sleep", access_token, f)
    if "error" in data:
        return [], data["error"]
    return data.get("dataPoints", []), None


def downsample_hr_1min(points):
    """Collapse raw ~2-second heart-rate samples to 1-minute means.
    Returns [{"t": "YYYY-MM-DDTHH:MM:00Z", "bpm": int, "n": int}] sorted by minute,
    where n is how many raw samples fed the mean."""
    buckets = defaultdict(list)
    for p in points:
        hr = p.get("heartRate", {})
        ts = hr.get("sampleTime", {}).get("physicalTime")
        bpm = hr.get("beatsPerMinute")
        if not ts or bpm is None:
            continue
        try:
            buckets[ts[:16] + ":00Z"].append(float(bpm))   # truncate to UTC minute
        except (ValueError, TypeError):
            continue
    out = [{"t": m, "bpm": round(sum(v) / len(v)), "n": len(v)} for m, v in buckets.items()]
    out.sort(key=lambda x: x["t"])
    return out


def capture_day(access_token, date_str):
    types, counts, errors = {}, {}, {}

    sleep_pts, sleep_err = fetch_sleep_raw(access_token, date_str)
    types["sleep"] = sleep_pts
    counts["sleep"] = len(sleep_pts)
    if sleep_err:
        errors["sleep"] = sleep_err

    for dt in DAILY_TYPES + SAMPLE_TYPES + INTERVAL_TYPES:
        pts, err = fetch_all_pages(dt, access_token, _filter_for(dt, date_str))
        types[dt] = pts
        counts[dt] = len(pts)
        if err:
            errors[dt] = err

    # Heart rate: downsample the 2-second stream to 1-minute means. Keep the raw
    # sample count for the record, but do not store the raw stream (size).
    if "heart-rate" in types:
        raw = types.pop("heart-rate")
        types["heart-rate-1min"] = downsample_hr_1min(raw)
        counts["heart-rate-raw-samples"] = counts.pop("heart-rate", 0)
        counts["heart-rate-1min"] = len(types["heart-rate-1min"])

    return {
        "date": date_str,
        "fetched_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tz": str(LOCAL_TZ),
        "schema_note": "heart-rate downsampled to 1-min means (key 'heart-rate-1min'); all other streams full-resolution",
        "counts": counts,
        "errors": errors,
        "types": types,
    }


def _captured_after_day_end(out_path, date_str):
    """True when the existing archive was fetched after local midnight closed date_str,
    i.e. the day was already complete and the file is final. A file written mid-day is
    a partial snapshot — anything logged later that day is missing from it."""
    y, m, d = (int(x) for x in date_str.split("-"))
    day_end = datetime(y, m, d, tzinfo=LOCAL_TZ) + timedelta(days=1)
    try:
        with gzip.open(out_path, "rt", encoding="utf-8") as f:
            stamp = json.loads(f.readline()).get("fetched_at_utc")
        fetched = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001 — unreadable file: re-fetch rather than trust it
        return False
    return fetched >= day_end


def write_day(date_str, force=False):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{date_str}.json.gz"
    if out_path.exists() and not force:
        if _captured_after_day_end(out_path, date_str):
            print(f"  {date_str}: final (captured after day end; --force to overwrite)")
            return out_path, False
        print(f"  {date_str}: partial snapshot — re-fetching")
    access_token = get_access_token()
    payload = capture_day(access_token, date_str)
    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",", ":")) + "\n")
    nonzero = {k: v for k, v in payload["counts"].items() if v}
    size_kb = out_path.stat().st_size / 1024
    print(f"  {date_str}: {size_kb:.0f} KB gz | " + ", ".join(f"{k}={v}" for k, v in sorted(nonzero.items())))
    if payload["errors"]:
        print(f"    errors: {list(payload['errors'].keys())}")
    return out_path, True


def daterange(start, end):
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    cur = s
    while cur <= e:
        yield cur.strftime("%Y-%m-%d")
        cur += timedelta(days=1)


def main():
    args = sys.argv[1:]
    force = "--force" in args
    args = [a for a in args if a != "--force"]

    if args and args[0] == "--range":
        if len(args) != 3:
            print("usage: google_health_raw.py --range START END", file=sys.stderr)
            sys.exit(2)
        dates = list(daterange(args[1], args[2]))
    elif args:
        dates = [args[0]]
    else:
        dates = [(datetime.now(LOCAL_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")]

    print(f"Capturing raw health data for {len(dates)} day(s) → {RAW_DIR.relative_to(REPO_ROOT)}/")
    for d in dates:
        write_day(d, force=force)


if __name__ == "__main__":
    main()
