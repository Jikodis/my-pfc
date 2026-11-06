#!/usr/bin/env python3
"""The home page data as JSON for the web UI (web/src/lib/computed.ts), plus the habit
rows and titles home_data.py and web_write.py share.

    python3 automations/scripts/web_data.py --home [--today YYYY-MM-DD]

The rules live elsewhere: habit rates and lights in focus_status.py, everything else
the page shows in home_data.py. This script only shapes habit rows and names habits.
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from focus_status import WINDOW_DAYS, habit_rate, light  # noqa: E402
from trmnl_push import load_env  # noqa: E402

LIGHT_ORDER = {"red": 0, "yellow": 1, "green": 2}


# capitalize() lowercases everything after the first letter, which reads wrong for
# initialisms, units, and clock times: `Ai course unit`, `Hydration 2l`,
# `Asleep before 11pm`. Each key is the lowercase form as it appears in an id; the
# entries containing a space are phrases and are applied before the word pass. Add
# your own as your habit ids need them.
TITLE_CASING = {
    "ai": "AI",
    "hiit": "HIIT",
    "2l": "2L",
    "11pm": "11 PM",
    "1030pm": "10:30 PM",
}


def habit_title(habit_id):
    """The short display name, derived from the id.

    Descriptions run a paragraph long, so no surface shows them as a name. Nothing is
    clipped here: the web UI has room that an e-ink row does not, which is also why
    this does not share trmnl_push._habit_title.
    """
    title = habit_id.replace("-", " ").capitalize()
    for phrase, display in TITLE_CASING.items():
        if " " not in phrase:
            continue
        start = title.lower().find(phrase)
        if start >= 0:
            title = title[:start] + display + title[start + len(phrase):]
    return " ".join(TITLE_CASING.get(w.lower(), w) for w in title.split(" "))


def _last_log_per_date(logs, habit_id):
    """One entry per date for this habit, the latest written winning.

    The habit files are append-only, so a day re-logged later has two
    lines and the later one is the answer.
    """
    by_date = {}
    for entry in logs:
        if entry.get("habit_id") == habit_id:
            by_date[entry.get("date")] = entry
    return by_date


def _daily_run(by_date, started, end_date):
    day = date.fromisoformat(end_date)
    # Today has not happened yet, so an unlogged today leaves the run standing.
    if end_date not in by_date:
        day -= timedelta(days=1)
    run = 0
    while True:
        iso = day.isoformat()
        if started and iso < started:
            break
        entry = by_date.get(iso)
        if entry is None:
            break
        if entry.get("skipped"):
            # A skipped day is a day the habit could not land, so it neither ends
            # the run nor counts as a rep (7-habits/AGENTS.md, structurally-unavailable days).
            day -= timedelta(days=1)
            continue
        if entry.get("completed") is not True:
            break
        run += 1
        day -= timedelta(days=1)
    return run


def _month_before(month):
    year, mon = (int(part) for part in month.split("-"))
    return f"{year - 1}-12" if mon == 1 else f"{year}-{mon - 1:02d}"


def _monthly_run(by_date, started, end_date, frequency):
    kept = {}
    for iso, entry in by_date.items():
        if entry.get("completed") is True and not entry.get("skipped"):
            kept[iso[:7]] = kept.get(iso[:7], 0) + 1
    def reached(month):
        return kept.get(month, 0) >= frequency

    month = end_date[:7]
    # The month in progress still has days left to reach its frequency, so a short
    # current month leaves the run standing and the count starts at the month before.
    if not reached(month):
        month = _month_before(month)
    run = 0
    while reached(month) and not (started and month < started[:7]):
        run += 1
        month = _month_before(month)
    return run


def current_run(logs, habit_id, started, end_date, cadence, frequency):
    """How long the habit's present streak is, in days or in whole months.

    Daily: consecutive days with a completed log, walking back from today. Today
    counts when it is logged and is skipped over when it is not, because the day is
    not finished. Monthly: consecutive calendar months whose completed logs reached
    the habit's frequency, ending with this month or the one before it.
    """
    by_date = _last_log_per_date(logs, habit_id)
    if cadence == "monthly":
        return _monthly_run(by_date, started, end_date, frequency)
    return _daily_run(by_date, started, end_date)


def run_label(run, cadence):
    """The run and its unit as one phrase: `1 day`, `3 days`, `2 months`, `none yet`.

    The number and the word belong together, so every surface prints the same phrase
    instead of each one deciding when to drop the s.
    """
    if run == 0:
        return "none yet"
    unit = "day" if cadence == "daily" else "month"
    return f"{run} {unit}" if run == 1 else f"{run} {unit}s"


def habit_rows(schema, daily_logs, monthly_logs, end_date, window_days=WINDOW_DAYS):
    start = (date.fromisoformat(end_date) - timedelta(days=window_days - 1)).isoformat()
    yesterday = (date.fromisoformat(end_date) - timedelta(days=1)).isoformat()
    rows = []
    for block, cadence, logs in (
        ("daily_habits", "daily", daily_logs),
        ("monthly_habits", "monthly", monthly_logs),
    ):
        for h in schema.get(block) or []:
            if not h.get("active", True):
                continue
            r = habit_rate(logs, h["id"], start, end_date, h["frequency"], cadence)
            run = current_run(logs, h["id"], h.get("started"), end_date, cadence, h["frequency"])
            by_date = _last_log_per_date(logs, h["id"])
            started = h.get("started")
            rows.append({
                "id": h["id"],
                "cadence": cadence,
                "title": habit_title(h["id"]),
                "description": h.get("description", ""),
                "area": h.get("area"),
                "frequency": h["frequency"],
                "started": h.get("started"),
                "completed": r["completed"],
                "target": r["target"],
                "rate_pct": round(r["rate"] * 100),
                "light": light(r["rate"]),
                "current_run": run,
                "run_unit": "days" if cadence == "daily" else "months",
                "run_label": run_label(run, cadence),
                # A habit a script logs is never logged by hand, so no page offers to.
                "auto_derived": bool(h.get("auto_derived", False)),
                # True when today's latest row says done, so a page hides Log today.
                "logged_today": by_date.get(end_date, {}).get("completed") is True,
                # The same for yesterday, so a page hides Log yesterday. A habit that
                # had not started yesterday has nothing to log there, so it reads True.
                "logged_yesterday": (by_date.get(yesterday, {}).get("completed") is True
                                     or bool(started and started > yesterday)),
            })
    rows.sort(key=lambda r: (LIGHT_ORDER[r["light"]], r["rate_pct"]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today")
    ap.add_argument("--home", action="store_true", required=True,
                    help="print the home page data (home_data.build_home)")
    args = ap.parse_args()
    env = load_env()
    import home_data
    tz = ZoneInfo(env.get("LOCAL_TZ", "America/Denver"))
    now = datetime.now(tz).replace(tzinfo=None)
    if args.today:  # a pinned day: evening-hour logic keeps the real clock time
        now = datetime.combine(date.fromisoformat(args.today), now.time())
    json.dump(home_data.build_home(env, now), sys.stdout)


if __name__ == "__main__":
    main()
