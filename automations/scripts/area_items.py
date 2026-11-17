#!/usr/bin/env python3
"""Area items: the things each life area carries, their lights, the area rollup,
and the plate (how much of the week's waking hours the items commit).

    python3 automations/scripts/area_items.py [--today YYYY-MM-DD]

prints every area with its items and the plate as JSON. Every rule lives here:
the `/pfc-review` area check-in and any dashboard only read what this returns.
Schema: config/area_item_schema.yaml.

Item lights:
  question           the newest answer in area-checkins.ndjson: good / okay / rough
                     -> green / yellow / red; older than STALE_DAYS shows as stale
  fitbit:sleep       the worse of the "Sleep hours" and "Continuity (awake)" pulse
                     levers over their 30-night window (never sleep hours alone)
  habit:<id>         days done in the last WINDOW_DAYS against the habit's weekly pace
  calendar:<name>    hours only (timed events on the calendar named <name> in the
                     next 7 days, from data/calendar-cache.json); no light

Area light: weighted average of the item lights that have data (green 2, yellow 1,
red 0); green at >= 75% of the maximum, yellow at >= 40%, else red; a red on a
weight-3 item caps the area at yellow. No items, or no item with data: the area's
manual life-wheel light.

Plate: free waking hours = 168 - the sleep item's hours; committed = the active
time items' hours this week (sleep left out, Upkeep converted to per week, ended
Seasons dropped); green up to 90% of free hours, yellow up to 100%, red over.
"""

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

ITEMS_FILE = "2-areas/_data/area-items.ndjson"
CHECKINS_FILE = "2-areas/_data/area-checkins.ndjson"
WHEEL_FILE = "2-areas/_data/life-wheel.ndjson"

LIGHT_SCORE = {"green": 2, "yellow": 1, "red": 0}
LIGHT_ORDER = {"red": 0, "yellow": 1, "green": 2}
GREEN_SHARE = 0.75
YELLOW_SHARE = 0.40
CAP_WEIGHT = 3  # a red on an item this heavy caps the area at yellow
ANSWER_LIGHT = {"good": "green", "okay": "yellow", "rough": "red"}
PER_WEEK = {"week": 1.0, "month": 12 / 52, "quarter": 4 / 52, "year": 1 / 52}
WEEK_HOURS = 168
PLATE_GREEN = 0.90
PLATE_YELLOW = 1.00
EPSILON = 1e-9
WINDOW_DAYS = 30  # habit and sleep windows
STALE_DAYS = 31  # the life wheel's staleness rule
WEEK_DAYS = 7
SLEEP_SOURCE = "fitbit:sleep"
CALENDAR_PREFIX = "calendar:"
SLEEP_LEVERS = (("hours", "sleep hours on target"), ("continuity", "unbroken"))
WINDOW_LIGHT = {"\U0001F7E2": "green", "\U0001F7E1": "yellow", "\U0001F534": "red"}


def _ndjson(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


# ── small rules ───────────────────────────────────────────────────────────────


def pace_light(done, frequency, window_days):
    """Green at the habit's weekly-frequency pace over the window, yellow at half of it."""
    target = frequency * window_days / 7
    return "green" if done >= target else "yellow" if done >= target / 2 else "red"


def rollup(items):
    """Weighted area light from [{light, weight}]; None when no item has a light."""
    lit = [i for i in items if i.get("light") in LIGHT_SCORE]
    if not lit:
        return None
    top = sum(2 * i["weight"] for i in lit)
    share = sum(LIGHT_SCORE[i["light"]] * i["weight"] for i in lit) / top
    light = "green" if share >= GREEN_SHARE - EPSILON else "yellow" if share >= YELLOW_SHARE - EPSILON else "red"
    if light == "green" and any(i["light"] == "red" and i["weight"] >= CAP_WEIGHT for i in lit):
        light = "yellow"
    return light


def _ended(item, today):
    return bool(item.get("ends")) and item["ends"] < today


def calendar_name(item):
    """The calendar a `calendar:<name>` source names, else None."""
    source = item.get("source") or ""
    return source[len(CALENDAR_PREFIX):] if source.startswith(CALENDAR_PREFIX) else None


def weekly_hours(item, calendar_hours):
    """Hours per week this week; None for a status item. `calendar_hours` is
    {calendar name: hours}, used by calendar-sourced items."""
    if item.get("kind") != "time":
        return None
    cal = calendar_name(item)
    if cal is not None:
        return float((calendar_hours or {}).get(cal, 0))
    hours = item.get("hours") or 0
    return hours * PER_WEEK.get(item.get("every") or "week", 1.0)


def _week(today):
    first = date.fromisoformat(today)
    return [(first + timedelta(days=i)).isoformat() for i in range(WEEK_DAYS)]


def calendar_hours(events, today, name):
    """Hours of timed events on the calendar named `name` in the 7 days from today.
    An event's calendar is its organizer's displayName in the calendar cache."""
    days = set(_week(today))
    total = 0.0
    for ev in events or []:
        start, end = (ev.get("start") or {}).get("dateTime"), (ev.get("end") or {}).get("dateTime")
        cal = (ev.get("organizer") or {}).get("displayName") or ""
        if not (start and end and cal == name and start[:10] in days):
            continue
        total += (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 3600
    return round(total, 2)


def latest_answers(checkins):
    """{item_id: newest row}: newest date, then the later line."""
    out = {}
    for row in checkins:
        iid = row.get("item_id")
        if iid and (iid not in out or (row.get("date") or "") >= (out[iid].get("date") or "")):
            out[iid] = row
    return out


def habit_light(habit_id, logs, schema, today):
    """(light, why) for a habit over the last WINDOW_DAYS; (None, why) for an unknown habit."""
    habits = list((schema or {}).get("daily_habits") or []) + list((schema or {}).get("monthly_habits") or [])
    h = next((x for x in habits if x.get("id") == habit_id), None)
    if not h or not h.get("frequency"):
        return None, "habit not found in config/habit_schema.yaml"
    end = date.fromisoformat(today)
    window = {(end - timedelta(days=i)).isoformat() for i in range(WINDOW_DAYS)}
    done = len({r["date"] for r in logs
                if r.get("habit_id") == habit_id and r.get("completed") is True and r.get("date") in window})
    pace = h["frequency"] * WINDOW_DAYS / 7
    return pace_light(done, h["frequency"], WINDOW_DAYS), f"done {done} of the last {WINDOW_DAYS} days, pace is {round(pace)}"


def sleep_light(day_rows):
    """(light, why): the worse of the Sleep hours and Continuity levers' 30-night windows."""
    from pulse import pulse_history, pulse_window_status
    hist = pulse_history(day_rows, WINDOW_DAYS)
    if hist is None:
        return None, "no sleep data"
    n = len(hist["dates"])
    lights, parts = [], []
    for lid, words in SLEEP_LEVERS:
        statuses = hist["series"].get(lid, {}).get("statuses") or []
        lights.append(WINDOW_LIGHT.get(pulse_window_status(statuses)))
        parts.append(f"{words} {sum(1 for s in statuses if s == chr(0x1F7E2))} of {n}")
    known = [x for x in lights if x]
    light = min(known, key=lambda x: LIGHT_ORDER[x]) if known else None
    return light, ", ".join(parts) + " nights"


def wheel_snapshot(path, today):
    """The newest life-wheel row as {date, stale, rows: [{key, label, light, note}]}."""
    rows = _ndjson(path)
    if not rows:
        return {"date": None, "stale": True, "rows": []}
    latest = max(enumerate(rows), key=lambda p: (p[1].get("date") or "", p[0]))[1]
    age = (date.fromisoformat(today) - date.fromisoformat(latest["date"])).days
    notes = latest.get("notes") or {}
    out = [{"key": k, "label": k.replace("_", " ").capitalize(), "light": v, "note": notes.get(k) or None}
           for k, v in (latest.get("ratings") or {}).items()]
    return {"date": latest["date"], "stale": age > STALE_DAYS, "rows": out}


# ── the whole set ─────────────────────────────────────────────────────────────


def _item_light(item, answers, today, sleep, habits):
    """(light, why, stale) for one active item that has not ended."""
    source = item.get("source")
    if source == SLEEP_SOURCE:
        return sleep[0], sleep[1], False
    cal = calendar_name(item)
    if cal is not None:
        return None, f"hours from the {cal} calendar", False
    if source and source.startswith("habit:"):
        light, why = habits.get(source[len("habit:"):], (None, "habit not found in config/habit_schema.yaml"))
        return light, why, False
    a = answers.get(item["id"])
    if not a:
        return None, "no answer yet", False
    age = (date.fromisoformat(today) - date.fromisoformat(a["date"])).days
    word = (a.get("answer") or "").capitalize()
    why = f"{word} on {a['date']}" + (f": {a['note']}" if a.get("note") else "")
    return ANSWER_LIGHT.get(a.get("answer")), why, age > STALE_DAYS


def _round(x):
    return None if x is None else round(x, 1)


def compute(items, checkins, wheel, today, *, events, sleep, habits):
    """Area rows (red first, no light last) with their items, the plate, and the
    newest check-in date. `wheel` is `wheel_snapshot(...)`; `sleep` is
    `sleep_light(...)`; `habits` is {habit_id: (light, why)}."""
    active = [i for i in items if i.get("active") is True]
    known_ids = {i["id"] for i in items}
    answers = latest_answers([c for c in checkins if c.get("item_id") in known_ids])
    cals = {calendar_name(i) for i in active if calendar_name(i) is not None}
    cal_hours = {c: calendar_hours(events, today, c) for c in cals}

    by_area = {}
    for item in active:
        ended = _ended(item, today)
        light, why, stale = (None, f"ended {item['ends']}: retire it at the next check-in", False) if ended \
            else _item_light(item, answers, today, sleep, habits)
        hours = weekly_hours(item, cal_hours)
        if ended and hours is not None:
            hours = 0.0  # an ended Season drops out of the hours
        by_area.setdefault(item["area"], []).append({
            "id": item["id"], "title": item["title"], "kind": item["kind"], "weight": item["weight"],
            "hours": _round(hours), "_hours": hours or 0.0, "light": light, "why": why, "stale": stale,
            "ended": ended, "source": item.get("source"),
        })

    wheel_rows = {r["key"]: r for r in wheel.get("rows") or []}
    keys = list(wheel_rows) + [k for k in by_area if k not in wheel_rows]
    rows = []
    for key in keys:
        w = wheel_rows.get(key) or {"key": key, "label": key.replace("_", " ").capitalize(), "light": None, "note": None}
        its = by_area.get(key, [])
        computed = rollup([i for i in its if not i["ended"]])
        committed = [i["_hours"] for i in its if i["kind"] == "time" and i["source"] != SLEEP_SOURCE]
        for i in its:
            del i["_hours"]
        rows.append({"key": key, "label": w["label"], "light": computed or w.get("light"), "manual": w.get("light"),
                     "note": w.get("note"), "source": "items" if computed else "manual",
                     "hours": _round(sum(committed)) if committed else None, "items": its})
    rows.sort(key=lambda r: LIGHT_ORDER.get(r["light"], 3))

    plate = None
    if active:
        sleep_item = next((i for i in active if i.get("source") == SLEEP_SOURCE), None)
        free = WEEK_HOURS - ((sleep_item or {}).get("hours") or 0)
        committed = sum(weekly_hours(i, cal_hours) or 0 for i in active
                        if i.get("kind") == "time" and i.get("source") != SLEEP_SOURCE and not _ended(i, today))
        ratio = committed / free if free else float("inf")
        light = "green" if ratio <= PLATE_GREEN + EPSILON else "yellow" if ratio <= PLATE_YELLOW + EPSILON else "red"
        plate = {"free": _round(free), "committed": _round(committed), "pct": round(100 * ratio) if free else None,
                 "light": light}

    checked = max((c["date"] for c in checkins if c.get("item_id") in known_ids and c.get("date")), default=None)
    return {"rows": rows, "plate": plate, "checked": checked}


def build(repo, today, wheel=None):
    """`compute` over the repo's files. `wheel` defaults to the newest life-wheel row."""
    import yaml
    repo = Path(repo)
    if wheel is None:
        wheel = wheel_snapshot(repo / WHEEL_FILE, today)
    items = _ndjson(repo / ITEMS_FILE)
    schema_path = repo / "config/habit_schema.yaml"
    schema = yaml.safe_load(schema_path.read_text()) if schema_path.exists() else {}
    logs = _ndjson(repo / "7-habits/_data/habits-daily.ndjson")
    habit_ids = {i["source"][len("habit:"):] for i in items if (i.get("source") or "").startswith("habit:")}
    habits = {h: habit_light(h, logs, schema, today) for h in habit_ids}
    needs_sleep = any(i.get("source") == SLEEP_SOURCE for i in items)
    sleep = sleep_light(_ndjson(repo / "data/day-tracking.ndjson")) if needs_sleep else (None, "no sleep data")
    events = None
    cache = repo / "data/calendar-cache.json"
    if cache.exists():
        try:
            events = json.loads(cache.read_text()).get("events") or []
        except (OSError, ValueError):
            events = None
    return compute(items, _ndjson(repo / CHECKINS_FILE), wheel, today, events=events, sleep=sleep, habits=habits)


def main(argv):
    today = argv[argv.index("--today") + 1] if "--today" in argv else None
    if not today:
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))).date().isoformat()
    print(json.dumps(build(REPO, today), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
