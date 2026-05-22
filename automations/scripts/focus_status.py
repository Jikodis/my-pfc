#!/usr/bin/env python3
"""Derive the Current Focus traffic light from habit completion data.

The light is NOT hand-typed. Each focus declares an ordered list of vehicle
habits in 4-focus/_data/focus.ndjson; the FIRST is the primary and drives the
light, the rest are supporting and are reported alongside it.

Rate math follows 7-habits/AGENTS.md rule 1:
  - unlogged days inside the window count as MISSES
  - days logged {skipped: true} drop out of BOTH numerator and denominator

Thresholds: green >= 0.70 · yellow 0.40-0.69 · red < 0.40

Usage:
    python3 automations/scripts/focus_status.py            # print JSON
    python3 automations/scripts/focus_status.py --write     # also rewrite status
"""

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
FOCUS_FILE = REPO / "4-focus/_data/focus.ndjson"
DAILY_FILE = REPO / "7-habits/_data/habits-daily.ndjson"
MONTHLY_FILE = REPO / "7-habits/_data/habits-monthly.ndjson"
SCHEMA_FILE = REPO / "config/habit_schema.yaml"
TMP_FILE = REPO / "data/.jq_update.tmp"

GREEN_FLOOR = 0.70
YELLOW_FLOOR = 0.40
WINDOW_DAYS = 28

_LETTER = {"high": "A", "medium": "B", "low": "C"}


def code(focus):
    """Two-letter impact/urgency code, impact first. high=A, medium=B, low=C."""
    return _LETTER[focus["impact"]] + _LETTER[focus["urgency"]]


def light(rate):
    """Traffic light for a completion rate in [0, 1]."""
    if rate >= GREEN_FLOOR:
        return "green"
    if rate >= YELLOW_FLOOR:
        return "yellow"
    return "red"


def window_target(frequency, cadence, available_days):
    """How many reps the window asks for, given the habit's LIVE frequency.

    daily:   frequency is per week  -> frequency / 7 * available_days
    monthly: frequency is per month -> frequency / 30 * available_days
    Never returns less than 1 — a zero denominator would make every rate
    undefined and every light red.
    """
    per_day = frequency / 7.0 if cadence == "daily" else frequency / 30.0
    return max(1, round(per_day * available_days))


def _in_window(entry, start, end):
    return start <= entry.get("date", "") <= end


def habit_rate(logs, habit_id, start, end, frequency, cadence):
    """Completion rate for one habit over [start, end] inclusive."""
    mine = [e for e in logs
            if e.get("habit_id") == habit_id and _in_window(e, start, end)]
    completed = sum(1 for e in mine if e.get("completed") is True)
    skipped = sum(1 for e in mine if e.get("skipped") is True)

    span = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    available = max(1, span - skipped)
    target = window_target(frequency, cadence, available)
    return {
        "habit_id": habit_id,
        "completed": completed,
        "target": target,
        "skipped": skipped,
        "rate": min(1.0, completed / target),
    }


def consecutive_red_weeks(logs, habit_id, end, frequency, cadence, max_weeks=8,
                          started=None):
    """How many of the most recent 7-day windows were red, counting back.

    Stops at the first non-red window. Capped at max_weeks so a habit that has
    never been logged returns a bounded number instead of walking to epoch.

    `started` is the habit's start date. Weeks that began before the habit
    existed are NOT counted — otherwise a habit created today immediately reads
    "red 8 weeks running" and trips the forcing function on day one, which is
    the exact opposite of what the ramp is for. Only full weeks the habit was
    alive for count.
    """
    end_d = date.fromisoformat(end)
    started_d = date.fromisoformat(started) if started else None
    streak = 0
    for w in range(max_weeks):
        w_end = end_d - timedelta(days=7 * w)
        w_start = w_end - timedelta(days=6)
        if started_d and w_start < started_d:
            break
        r = habit_rate(logs, habit_id, w_start.isoformat(), w_end.isoformat(),
                       frequency, cadence)
        if light(r["rate"]) != "red":
            break
        streak += 1
    return streak


def _habit_index(schema):
    """{habit_id: (frequency, cadence, started)} across both habit blocks."""
    idx = {}
    for block, cadence in (("daily_habits", "daily"), ("monthly_habits", "monthly")):
        for h in schema.get(block) or []:
            idx[h["id"]] = (h["frequency"], cadence, h.get("started"))
    return idx


def compute(focuses, daily_logs, monthly_logs, schema, end_date,
            window_days=WINDOW_DAYS):
    """Per-focus status. Retired focuses are excluded entirely."""
    idx = _habit_index(schema)
    start = (date.fromisoformat(end_date) - timedelta(days=window_days - 1)).isoformat()
    out = []

    for f in focuses:
        if f.get("retired_date"):
            continue

        rates = []
        for hid in f.get("habits") or []:
            if hid not in idx:
                continue
            frequency, cadence, started = idx[hid]
            logs = monthly_logs if cadence == "monthly" else daily_logs
            # A habit's window starts no earlier than the habit itself — days
            # before it existed are not misses.
            h_start = max(start, started) if started else start
            r = habit_rate(logs, hid, h_start, end_date, frequency, cadence)
            r["cadence"] = cadence
            r["light"] = light(r["rate"])
            rates.append(r)

        primary = rates[0] if rates else None

        if f.get("parked"):
            status, weeks_red = "parked", 0
        elif primary is None:
            status, weeks_red = "unknown", 0
        else:
            status = primary["light"]
            frequency, cadence, started = idx[primary["habit_id"]]
            logs = monthly_logs if cadence == "monthly" else daily_logs
            weeks_red = consecutive_red_weeks(
                logs, primary["habit_id"], end_date, frequency, cadence,
                started=started)

        out.append({
            "focus_id": f["id"],
            "title": f.get("title", ""),
            "tier": f.get("tier", ""),
            "code": code(f),
            "impact": f["impact"],
            "urgency": f["urgency"],
            "parked": bool(f.get("parked")),
            "status": status,
            "primary": primary,
            "supporting": rates[1:],
            "weeks_red": weeks_red,
        })
    return out


def _read_ndjson(path):
    if not Path(path).exists():
        return []
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def _write_status(results):
    """Rewrite `status` in focus.ndjson via jq. Parked/unknown keep their
    stored status — only a real derived light is written back."""
    mapping = {r["focus_id"]: r["status"] for r in results
               if r["status"] in ("green", "yellow", "red")}
    if not mapping:
        return
    # NOTE: "--argjson", "m", <value> must be three separate argv elements.
    # Collapsing them into one "--argjson m" string makes jq fail and leaves an
    # empty focus.ndjson behind.
    with TMP_FILE.open("w") as out:
        subprocess.run(
            ["jq", "-c", "--argjson", "m", json.dumps(mapping),
             "if $m[.id] then .status = $m[.id] else . end", str(FOCUS_FILE)],
            stdout=out, check=True)
    TMP_FILE.replace(FOCUS_FILE)


def main():
    today = date.today().isoformat()
    results = compute(
        _read_ndjson(FOCUS_FILE),
        _read_ndjson(DAILY_FILE),
        _read_ndjson(MONTHLY_FILE),
        yaml.safe_load(SCHEMA_FILE.read_text()),
        today,
    )
    if "--write" in sys.argv:
        _write_status(results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
