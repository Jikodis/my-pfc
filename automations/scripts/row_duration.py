#!/usr/bin/env python3
"""Derive real workout duration from the per-minute heart-rate stream.

Why this exists
---------------
A watch session timer is not trustworthy: start it, forget to press Stop, and
`activeDuration` can run an hour past the end of the actual effort. Everything
derived from that timer is inflated with it: `calories`, and
`averageHeartRateBeatsPerMinute` (idle minutes drag the average down).

Active zone minutes are immune to the inflation but are the wrong answer for a
different reason: a warm-up below the zone threshold earns little or no zone
credit but is genuinely part of the session. So AZM undercounts the front of the
session about as badly as the timer overcounts the back.

What this does instead: read the per-minute heart rate inside the session
window and find the block where the heart rate was actually elevated. That
block starts when the effort starts (warm-up included) and ends when it stops,
regardless of when the timer was stopped.

Data source is `data/health-raw/YYYY-MM-DD.json.gz` — the raw Google Health
payload, which carries both `exercise` (session windows) and `heart-rate-1min`.

The constants below are starting points. Calibrate ABSOLUTE_FLOOR_BPM against a
few of your own traces (run with no arguments and compare Timer vs Real).

Usage
-----
    python3 automations/scripts/row_duration.py                 # every day with a session
    python3 automations/scripts/row_duration.py 2025-01-01      # one day
    python3 automations/scripts/row_duration.py --type ROWING_MACHINE
    python3 automations/scripts/row_duration.py --write         # stamp day-tracking.ndjson
"""

import argparse
import gzip
import json
import pathlib
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from exercise_reduce import _local_iso  # noqa: E402 — same-dir sibling

REPO = pathlib.Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "health-raw"
TRACKING = REPO / "data" / "day-tracking.ndjson"

# Fraction of the way from resting heart rate to the session peak that counts as
# "working". 0.40 puts the line above a post-workout sitting-around plateau but
# below a warm-up: warm-up counts, sitting on the couch does not.
ELEVATED_FRACTION = 0.40

# Hard floor, in bpm, under which nothing counts as working, regardless of what the
# relative threshold says. The relative threshold alone fails on EASY sessions: when
# the in-window peak is low, 40% of the way up from resting can sit below ordinary
# moving-around-the-house heart rate, so a stopped-late window reads as one long
# workout. Set this between your post-workout ambient plateau and your warm-up
# heart rate, read off a few of your own sessions.
ABSOLUTE_FLOOR_BPM = 100  # placeholder: calibrate to your own sessions

# The effort sometimes starts before the timer does, so look a little earlier than
# the timer window. Kept short: a wider pre-window drags in whatever raised the
# heart rate before the session (stairs, carrying groceries).
PRE_WINDOW_MIN = 5

# Never look PAST the timer. The error runs one way (the timer is left running,
# not stopped early), so the recorded end is a hard upper bound on the session,
# and anything after it is recovery.
POST_WINDOW_MIN = 0

# KNOWN LIMIT: do not keep tuning these constants to chase a remembered number.
# Per-minute heart rate cannot always separate the last minutes of an easy session
# from the first minutes of recovery. The derivation fixes the gross errors (a
# 90-minute timer on a 30-minute session); treat a derived duration as accurate to
# a few minutes, not to the minute, and never present it as exact.

# An interval session dips hard between pieces. Bridge gaps up to this many minutes
# so the recovery valleys do not split one session into six.
MERGE_GAP_MIN = 3

# Never bridge across a hole in the data this long: that is the watch losing
# contact or being taken off, not a recovery valley.
MAX_DATA_GAP_MIN = 6


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load_day(date_str):
    path = RAW / f"{date_str}.json.gz"
    if not path.exists():
        return None
    with gzip.open(path) as fh:
        return json.load(fh)


def resting_hr_for(date_str):
    """Resting heart rate from the day record; None if absent."""
    if not TRACKING.exists():
        return None
    with open(TRACKING) as fh:
        for line in fh:
            rec = json.loads(line)
            if rec.get("date") == date_str:
                return (rec.get("health") or {}).get("resting_hr_bpm")
    return None


def sessions_from(raw):
    """Yield (type, name, start, end) for each tracked exercise session."""
    for point in raw.get("types", {}).get("exercise") or []:
        ex = point.get("exercise") or {}
        interval = ex.get("interval") or {}
        start, end = interval.get("startTime"), interval.get("endTime")
        if not (start and end):
            continue
        yield {
            "type": ex.get("exerciseType"),
            "name": ex.get("displayName"),
            "key": _local_iso(interval),
            "start": parse_ts(start),
            "end": parse_ts(end),
            "timer_minutes": round((parse_ts(end) - parse_ts(start)).total_seconds() / 60),
            "azm": int((ex.get("metricsSummary") or {}).get("activeZoneMinutes") or 0),
        }


def hr_series(raw):
    out = [(parse_ts(s["t"]), s["bpm"]) for s in raw.get("types", {}).get("heart-rate-1min") or []]
    out.sort()
    return out


def derive(session, series, resting):
    """Find the elevated block inside the session window.

    Returns a dict with the derived start/end/minutes, or None when there is not
    enough heart-rate data inside the window to say anything honest.
    """
    lo = session["start"] - timedelta(minutes=PRE_WINDOW_MIN)
    hi = session["end"] + timedelta(minutes=POST_WINDOW_MIN)
    window = [(t, b) for t, b in series if lo <= t <= hi]
    if len(window) < 5:
        return None

    peak = max(b for _, b in window)
    base = resting if resting else min(b for _, b in window)
    threshold = max(ABSOLUTE_FLOOR_BPM, base + ELEVATED_FRACTION * (peak - base))

    # Walk the window, collecting runs of at-or-above-threshold minutes. A short
    # dip below threshold stays inside the run; a long dip, or a hole in the
    # data, closes it.
    runs, current, last_t = [], None, None
    for t, bpm in window:
        gap = (t - last_t).total_seconds() / 60 if last_t else 0
        if current and gap > MAX_DATA_GAP_MIN:
            runs.append(current)
            current = None
        if bpm >= threshold:
            if current is None:
                current = {"start": t, "end": t}
            else:
                if (t - current["end"]).total_seconds() / 60 > MERGE_GAP_MIN:
                    runs.append(current)
                    current = {"start": t, "end": t}
                else:
                    current["end"] = t
        last_t = t
    if current:
        runs.append(current)
    if not runs:
        return None

    best = max(runs, key=lambda r: r["end"] - r["start"])
    minutes = round((best["end"] - best["start"]).total_seconds() / 60) + 1

    # Second number: the hard part, excluding the warm-up ramp. Same idea, higher
    # line — 70% of the way from resting to peak.
    hard_line = base + 0.70 * (peak - base)
    hard = sum(1 for t, b in window if best["start"] <= t <= best["end"] and b >= hard_line)

    return {
        "start": best["start"],
        "end": best["end"],
        "minutes": minutes,
        "hard_minutes": hard,
        "peak": peak,
        "threshold": round(threshold),
        "base": base,
    }


def real_minutes_by_start(date_str, resting=None):
    """{local-iso session start -> {real_minutes, hard_minutes}} for one day.

    Keyed by the same local-time string `exercise_reduce` writes into
    `health.workouts[].start`, so the caller can merge without guessing at order.
    Returns {} when the raw archive for the day is missing — the raw file is
    best-effort, so a missing one must degrade quietly, not raise.
    """
    raw = load_day(date_str)
    if not raw:
        return {}
    series = hr_series(raw)
    if resting is None:
        resting = resting_hr_for(date_str)
    out = {}
    for session in sessions_from(raw):
        if not session["key"]:
            continue
        d = derive(session, series, resting)
        if d:
            out[session["key"]] = {
                "real_minutes": d["minutes"],
                "hard_minutes": d["hard_minutes"],
            }
    return out


def apply_to_health(health, date_str):
    """Stamp `real_minutes` / `hard_minutes` onto each workout, plus the day sum.

    Mutates and returns `health`. A session with no usable heart-rate data gets
    null rather than a guess — null means "could not derive", never "zero".
    """
    workouts = health.get("workouts")
    if not workouts:
        health["workout_real_minutes"] = 0 if workouts == [] else None
        return health
    derived = real_minutes_by_start(date_str, health.get("resting_hr_bpm"))
    total = 0
    for w in workouts:
        d = derived.get(w.get("start"))
        w["real_minutes"] = d["real_minutes"] if d else None
        w["hard_minutes"] = d["hard_minutes"] if d else None
        if d:
            total += d["real_minutes"]
    health["workout_real_minutes"] = total
    return health


def write_all():
    """Backfill every day-tracking record that has a workouts array."""
    records = [json.loads(l) for l in open(TRACKING) if l.strip()]
    changed = 0
    for rec in records:
        health = rec.get("health")
        if not isinstance(health, dict) or health.get("workouts") is None:
            continue
        before = json.dumps(health, sort_keys=True)
        apply_to_health(health, rec["date"])
        if json.dumps(health, sort_keys=True) != before:
            changed += 1
    with open(TRACKING, "w") as fh:
        for rec in records:
            fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
    print(f"Stamped derived duration on {changed} day-tracking record(s).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", help="single YYYY-MM-DD; omit for every day on file")
    ap.add_argument("--type", dest="ex_type", help="filter to one exerciseType, e.g. ROWING_MACHINE")
    ap.add_argument("--write", action="store_true",
                    help="stamp real_minutes/hard_minutes onto day-tracking.ndjson and exit")
    args = ap.parse_args()

    if args.write:
        return write_all()

    dates = [args.date] if args.date else sorted(p.name[:10] for p in RAW.glob("*.json.gz"))
    mt = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))

    rows = []
    for date_str in dates:
        raw = load_day(date_str)
        if not raw:
            continue
        series = hr_series(raw)
        resting = resting_hr_for(date_str)
        for session in sessions_from(raw):
            if args.ex_type and session["type"] != args.ex_type:
                continue
            d = derive(session, series, resting)
            rows.append((date_str, session, d))

    if not rows:
        print("No tracked sessions found.")
        return

    print(f"{'Date':<11}{'Type':<17}{'Start':>8}{'Timer':>7}{'Real':>7}{'Hard':>7}{'AZM':>6}{'Peak':>6}  Verdict")
    print("-" * 88)
    for date_str, s, d in rows:
        start = s["start"].astimezone(mt).strftime("%-I:%M %p")
        if not d:
            print(f"{date_str:<11}{(s['type'] or '?')[:16]:<17}{start:>8}{s['timer_minutes']:>7}{'—':>7}{'—':>7}{s['azm']:>6}{'—':>6}  no heart-rate data")
            continue
        overrun = s["timer_minutes"] - d["minutes"]
        verdict = f"timer long by {overrun} min" if overrun >= 5 else "timer looks honest"
        print(f"{date_str:<11}{(s['type'] or '?')[:16]:<17}{start:>8}{s['timer_minutes']:>7}"
              f"{d['minutes']:>7}{d['hard_minutes']:>7}{s['azm']:>6}{d['peak']:>6}  {verdict}")

    print()
    print("Timer = what the watch recorded.  Real = heart rate actually elevated (warm-up included).")
    print("Hard  = minutes inside that block at 70%+ of the way from resting to peak.")


if __name__ == "__main__":
    sys.exit(main())
