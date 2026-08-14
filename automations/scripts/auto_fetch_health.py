#!/usr/bin/env python3
"""
Auto-fetch daily health data into day-tracking.ndjson + the raw per-day archive.

Two layers, both written here:

  1. **Derived day-level metrics** → `day-tracking.ndjson` → `health` (sleep,
     resting heart rate, Active Zone Minutes, tracked workouts, heart-rate
     variability, blood oxygen, breathing rate, skin temperature, VO2 max).
     Creates the row if missing, replaces the `health` field if present, and
     preserves every user-entered field on that row.
  2. **Comprehensive raw streams** → `data/health-raw/YYYY-MM-DD.json.gz`
     (per-minute heart rate, intraday variability / blood oxygen, sleep stages,
     interval streams) via `google_health_raw`. Best-effort: a raw failure never
     blocks the day-tracking commit.

Then it recomputes the QQRT sleep composite (`backfill_qqrt`) so `qqrt` never
lags the health data, and commits + pushes.

Idempotent: with unchanged data it writes nothing, commits nothing, and pushes
nothing — which is what makes it safe to run on a retry loop (see the
`pfc-health-fetch-morning` timer).

Usage:
    python3 automations/scripts/auto_fetch_health.py [YYYY-MM-DD]

With no argument, defaults to YESTERDAY in $LOCAL_TZ.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from google_health_backfill import fetch_health, get_access_token  # noqa: E402
import google_health_raw  # noqa: E402

REPO_ROOT    = SCRIPT_DIR.parents[1]
# Local timezone: configurable via LOCAL_TZ env var (default America/Denver).
LOCAL_TZ     = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))
DAY_TRACKING = REPO_ROOT / "data/day-tracking.ndjson"


def target_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return (datetime.now(LOCAL_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")


def load_records():
    if not DAY_TRACKING.exists():
        return []
    return [json.loads(l) for l in DAY_TRACKING.read_text().splitlines() if l.strip()]


def write_records(records):
    DAY_TRACKING.write_text(
        "\n".join(json.dumps(r, separators=(",", ":")) for r in records) + "\n"
    )


def capture_raw(date_str):
    """Best-effort raw archive write. Never raises — a raw failure must not block
    the day-tracking commit. Returns the written path, or None when nothing changed."""
    try:
        path, wrote = google_health_raw.write_day(date_str)
        return path if wrote else None
    except Exception as e:  # noqa: BLE001 — intentionally swallowed; raw is supplementary
        print(f"  raw capture failed (non-blocking): {e}", file=sys.stderr)
        return None


def recompute_qqrt():
    """Refresh the QQRT sleep composite on every record. Non-blocking.

    Regularity and sleep debt look only at *prior* nights, so a newly fetched night
    never rewrites an earlier night's score."""
    try:
        import backfill_qqrt
        qres = backfill_qqrt.recompute()
        print(f"  qqrt recomputed ({qres['changed']} changed).")
    except Exception as e:  # noqa: BLE001
        print(f"  qqrt recompute failed (non-blocking): {e}", file=sys.stderr)


def git_commit_and_push(date_str, raw_path=None):
    add = ["git", "-C", str(REPO_ROOT), "add", "data/day-tracking.ndjson"]
    if raw_path is not None:
        add.append(str(raw_path.relative_to(REPO_ROOT)))
    for args in (
        add,
        ["git", "-C", str(REPO_ROOT), "commit", "-m", f"track: auto-fetch health {date_str}"],
        ["git", "-C", str(REPO_ROOT), "push"],
    ):
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"{' '.join(args)} failed: {r.stderr}", file=sys.stderr)
            sys.exit(1)


def main():
    date_str = target_date()
    print(f"Fetching health for {date_str}")

    access_token = get_access_token()
    health = fetch_health(access_token, date_str)
    if health is None:
        print("  No data returned from Google Health — nothing to log.")
        return

    print(f"  sleep={health.get('sleep_hours')}h  "
          f"rhr={health.get('resting_hr_bpm')}  "
          f"azm={health.get('active_zone_minutes')}  "
          f"workouts={health.get('workout_count')}")

    records = load_records()
    existing = next((r for r in records if r.get("date") == date_str), None)

    if existing is not None and existing.get("health") == health:
        # Derived metrics unchanged — but the raw archive may still be a partial
        # mid-day snapshot (google_health_raw finalizes a day only once a capture
        # lands after local midnight). Give it that chance, then stop.
        print("  health field already matches — no change.")
        raw_path = capture_raw(date_str)
        if raw_path is not None:
            git_commit_and_push(date_str, raw_path)
            print("  Raw archive refreshed, committed and pushed.")
        return

    if existing is not None:
        existing["health"] = health
        action = "updated"
    else:
        records.append({"date": date_str, "health": health})
        records.sort(key=lambda r: r.get("date", ""))
        action = "created"

    write_records(records)
    print(f"  day-tracking row {action} for {date_str}.")

    recompute_qqrt()
    raw_path = capture_raw(date_str)
    git_commit_and_push(date_str, raw_path)
    print("  Committed and pushed.")


if __name__ == "__main__":
    main()
