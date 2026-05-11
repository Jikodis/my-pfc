#!/usr/bin/env python3
"""
Auto-fetch daily health data (sleep, resting HR, AZM) into day-tracking.ndjson.

Runs on schedule for yesterday's data (typically fully synced by mid-morning local time).
Creates the day-tracking row if missing, replaces the `health` field if present.
Preserves all user-entered fields. Does NOT touch habits-daily.ndjson.

Usage:
    python3 automations/scripts/auto_fetch_health.py [YYYY-MM-DD]
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from google_health_backfill import fetch_health, get_access_token

REPO_ROOT    = SCRIPT_DIR.parents[1]
# Local timezone: configurable via LOCAL_TZ env var (default America/Denver).
MOUNTAIN     = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))
DAY_TRACKING = REPO_ROOT / "data/day-tracking.ndjson"


def target_date():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return (datetime.now(MOUNTAIN) - timedelta(days=1)).strftime("%Y-%m-%d")


def load_records():
    if not DAY_TRACKING.exists():
        return []
    return [json.loads(l) for l in DAY_TRACKING.read_text().splitlines() if l.strip()]


def write_records(records):
    DAY_TRACKING.write_text(
        "\n".join(json.dumps(r, separators=(",", ":")) for r in records) + "\n"
    )


def git_commit_and_push(date_str):
    for args in (
        ["git", "-C", str(REPO_ROOT), "add", "data/day-tracking.ndjson"],
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
          f"azm={health.get('active_zone_minutes')}")

    records = load_records()
    existing = next((r for r in records if r.get("date") == date_str), None)

    if existing is not None:
        if existing.get("health") == health:
            print("  health field already matches — no change.")
            return
        existing["health"] = health
        action = "updated"
    else:
        records.append({"date": date_str, "health": health})
        records.sort(key=lambda r: r.get("date", ""))
        action = "created"

    write_records(records)
    print(f"  day-tracking row {action} for {date_str}.")
    git_commit_and_push(date_str)
    print("  Committed and pushed.")


if __name__ == "__main__":
    main()
