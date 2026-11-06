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

The repo may be shared with another clone (a laptop and a VPS, say), so the run
levels with origin before it reads the files and again before it pushes
(`repo_sync.py`). A conflict keeps the commit local and exits non-zero so the
journal shows it; nothing piles up silently.

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

import repo_sync  # noqa: E402
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


def _git(*args):
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True,
                          timeout=120, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


def sync_before_write():
    """Level with origin so this run edits the newest day-tracking file.
    Returns False when the repo cannot be written at all (a rebase in progress)."""
    if repo_sync.rebase_in_progress(_git, REPO_ROOT):
        print("  a git rebase is in progress in the repo; skipping this run (the next one fetches again).",
              file=sys.stderr)
        return False
    ok, detail = repo_sync.sync_with_upstream(_git, REPO_ROOT)
    if not ok:
        print(f"  repo sync before write failed; continuing on the local copy: {detail}", file=sys.stderr)
    return True


def git_commit_and_push(date_str, raw_path=None):
    add = ["add", "data/day-tracking.ndjson"]
    if raw_path is not None:
        add.append(str(raw_path.relative_to(REPO_ROOT)))
    for args in (add, ["commit", "-m", f"track: auto-fetch health {date_str}"]):
        r = _git(*args)
        if r.returncode != 0:
            print(f"git {' '.join(args)} failed: {r.stderr}", file=sys.stderr)
            sys.exit(1)
    # Level with origin, then push. Another clone may push between the two; one more
    # pass covers that. A conflict keeps the commit local and ends the run non-zero.
    for attempt in (1, 2):
        ok, detail = repo_sync.sync_with_upstream(_git, REPO_ROOT)
        if not ok:
            print(f"REPO SYNC FAILED — commit kept locally, not pushed: {detail}", file=sys.stderr)
            sys.exit(1)
        r = _git("push")
        if r.returncode == 0:
            return
        if attempt == 2:
            print(f"git push failed: {r.stderr}", file=sys.stderr)
            sys.exit(1)


def main():
    date_str = target_date()
    print(f"Fetching health for {date_str}")
    if not sync_before_write():
        return

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
