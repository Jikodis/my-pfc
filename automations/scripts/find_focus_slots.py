#!/usr/bin/env python3
"""Find calendar slots for today's focus tasks.

Pure scheduler. Reads a JSON payload on stdin, writes a JSON result on stdout.
See docs/calendar-scheduling.md
for the contract.
"""

import json
import os
import sys
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

# Local timezone: configurable via LOCAL_TZ env var (default America/Denver).
LOCAL_TZ_NAME = os.environ.get("LOCAL_TZ", "America/Denver")
MOUNTAIN = ZoneInfo(LOCAL_TZ_NAME)

SIZE_MINUTES = {"XS": 5, "S": 15, "M": 30, "L": 60, "XL": 120}
DEFAULT_SIZE_MINUTES = 30  # null/unknown size → M
MIN_SLOT_MINUTES = 15      # floor: even XS tasks get a 15-min calendar block

# Local-time window boundaries: (start_hour, end_hour) pairs.
WEEKDAY_WINDOWS = [(8, 9), (12, 13), (17, 21)]
WEEKEND_WINDOWS = [(8, 21)]


def _parse_iso(s):
    return datetime.fromisoformat(s)


def _windows_for(date):
    is_weekend = date.weekday() >= 5
    hours = WEEKEND_WINDOWS if is_weekend else WEEKDAY_WINDOWS
    out = []
    for sh, eh in hours:
        start = datetime.combine(date, time(sh, 0), tzinfo=MOUNTAIN)
        end   = datetime.combine(date, time(eh, 0), tzinfo=MOUNTAIN)
        out.append((start, end))
    return out


def _subtract_busy(windows, busy):
    busy = sorted(busy, key=lambda b: b[0])
    free = []
    for w_start, w_end in windows:
        cur = w_start
        for b_start, b_end in busy:
            if b_end <= cur or b_start >= w_end:
                continue
            if b_start > cur:
                free.append((cur, min(b_start, w_end)))
            cur = max(cur, b_end)
            if cur >= w_end:
                break
        if cur < w_end:
            free.append((cur, w_end))
    return free


def _ceil_quarter(dt):
    """Round dt up to the next 15-minute boundary (seconds/microseconds zeroed)."""
    dt = dt.replace(second=0, microsecond=0)
    remainder = dt.minute % 15
    if remainder == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt
    return dt + timedelta(minutes=(15 - remainder))


def _clip_to_now(free, now):
    out = []
    for fs, fe in free:
        if fe <= now:
            continue
        if fs < now:
            fs = now
        if fs < fe:
            out.append((fs, fe))
    return out


def _duration_for(size):
    if size is None:
        minutes = DEFAULT_SIZE_MINUTES
    else:
        minutes = SIZE_MINUTES.get(size, DEFAULT_SIZE_MINUTES)
    return timedelta(minutes=max(MIN_SLOT_MINUTES, minutes))


def schedule(date_str, busy_events, tasks, now=None):
    date = datetime.strptime(date_str, "%Y-%m-%d").date()
    busy = [(_parse_iso(e["start"]), _parse_iso(e["end"])) for e in busy_events]
    windows = _windows_for(date)
    free = _subtract_busy(windows, busy)
    if now is not None:
        free = _clip_to_now(free, _ceil_quarter(_parse_iso(now)))

    placements = []
    unscheduled = []
    for t in tasks:
        duration = _duration_for(t.get("size"))
        placed = False
        for i, (fs, fe) in enumerate(free):
            if fe - fs >= duration:
                start = fs
                end = fs + duration
                placements.append({
                    "task_id": t["id"],
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                })
                free[i] = (end, fe)
                placed = True
                break
        if not placed:
            unscheduled.append(t["id"])
    return {"placements": placements, "unscheduled": unscheduled}


def main():
    payload = json.load(sys.stdin)
    result = schedule(
        payload["date"],
        payload.get("busy_events", []),
        payload.get("tasks", []),
        now=payload.get("now"),
    )
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
