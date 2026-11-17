#!/usr/bin/env python3
"""Log habits whose reps already sit on the calendar, so nobody has to tap them.

Same reasoning as derive_sleep_habit.py: a rep the system can already see
should not depend on memory, because a hole in the log reads as a miss at
compute time. Good fits: a class, a standing appointment, a recurring session
you only ever put on the calendar when it happens.

Which habits: any habit in config/habit_schema.yaml (daily or monthly) with
`auto_derived: true` and a `calendar:` block. The habit-to-event mapping lives
there, never in this script:

    - id: yoga-class
      auto_derived: true
      calendar:
        match: "^Yoga\\b"     # regex, case-insensitive, searched in the event title
        exclude: "MISSED"      # optional regex; a matching title is not a rep

A date gets ONE completed row when at least one matching event started on it
(local date) and has already started by now. Two sessions back to back are one
rep; tonight's class is not a rep at 5 AM (tomorrow's run logs it as yesterday).
A cancelled event never counts. No event, no row: absence already reads as a
miss (7-habits/AGENTS.md), so nothing writes `completed: false`.

Source: data/calendar-cache.json, which the Calendar-fetching render paths
(pfc-render-trello, the evening check-in) write after they fetch events
(docs/data-model.md). An optional `from` stamp says the first date the fetch
covered; without it only the fetch day counts as covered. Scripts cannot reach
the Calendar connector, so the cache is the only feed. `--events FILE` reads
another feed of the same shape (a JSON array, or an object with `events` and
optional `from`), used for a one-time backfill.

Idempotent and conservative:
  - a row for the habit and date from any other source (chat, Trello) is a
    deliberate log and always wins; the derived row is never written beside it;
  - derived rows are rewritten only inside the dates the feed covers (`from`
    through today, capped at the cache's 7-day horizon), so a renamed-to-MISSED
    or deleted event drops its row, and history older than the feed stays.

Usage: python3 automations/scripts/derive_calendar_habits.py [--dry-run] [--events FILE]
"""
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = "calendar-derived"
LOG_FILES = {"daily": "7-habits/_data/habits-daily.ndjson",
             "monthly": "7-habits/_data/habits-monthly.ndjson"}
CACHE_HORIZON_DAYS = 7  # the cache holds at most today plus the next 7 days


def _tz():
    return ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))


def compile_rule(cal):
    """(match, exclude) compiled regexes from a habit's `calendar:` block."""
    match = re.compile(cal["match"], re.IGNORECASE)
    exclude = re.compile(cal["exclude"], re.IGNORECASE) if cal.get("exclude") else None
    return match, exclude


def load_habits(schema):
    """Active auto_derived habits with a calendar rule: [{id, cadence, match}]."""
    out = []
    for cadence in ("daily", "monthly"):
        for h in (schema or {}).get(f"{cadence}_habits") or []:
            if not isinstance(h, dict) or h.get("active") is False:
                continue
            if h.get("auto_derived") is True and isinstance(h.get("calendar"), dict):
                out.append({"id": h["id"], "cadence": cadence, "match": compile_rule(h["calendar"])})
    return out


def _event_day(ev, now):
    """(local date, started) for an event, or None when it has no usable start."""
    start = ev.get("start") or {}
    if start.get("dateTime"):
        t = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=now.tzinfo)
        return t.astimezone(now.tzinfo).date().isoformat(), t <= now
    if start.get("date"):
        day = start["date"][:10]
        return day, day <= now.date().isoformat()
    return None


def derived_rows(habit, events, now):
    """One completed row per date with a matching event that has started."""
    match, exclude = habit["match"]
    days = set()
    for ev in events:
        if ev.get("status") == "cancelled":
            continue
        title = ev.get("summary") or ""
        if not match.search(title) or (exclude and exclude.search(title)):
            continue
        when = _event_day(ev, now)
        if when and when[1]:
            days.add(when[0])
    return [{"habit_id": habit["id"], "date": d, "completed": True, "source": SOURCE}
            for d in sorted(days)]


def covered_dates(blob, today):
    """Dates the feed speaks for: `from` through today, within the cache's horizon."""
    fetched = str(blob.get("fetched_at") or "")[:10] or None
    first = blob.get("from") or fetched or today
    last = today
    if fetched:
        horizon = (date.fromisoformat(fetched) + timedelta(days=CACHE_HORIZON_DAYS - 1)).isoformat()
        last = min(last, horizon)
    out, d = set(), date.fromisoformat(first)
    while d.isoformat() <= last:
        out.add(d.isoformat())
        d += timedelta(days=1)
    return out


def merge(existing, habit_id, rows, covered):
    """Rewrite this habit's derived rows inside `covered`; leave everything else alone."""
    new = {r["date"]: r for r in rows}
    manual = {r.get("date") for r in existing
              if r.get("habit_id") == habit_id and r.get("source") != SOURCE}
    out, seen = [], set()
    for row in existing:
        if row.get("habit_id") != habit_id or row.get("source") != SOURCE:
            out.append(row)
            continue
        day = row.get("date")
        if day in manual or day in seen:
            continue  # a hand-logged row wins; a duplicate derived row falls out
        if day in new:
            out.append(new[day])
            seen.add(day)
        elif day not in covered:
            out.append(row)  # older than the feed: keep
            seen.add(day)
        # inside the feed with no event any more: drop
    out.extend(r for d, r in sorted(new.items()) if d not in seen and d not in manual)
    return out


def _read_ndjson(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _key(record):
    return json.dumps(record, sort_keys=True)


def _write_ndjson(path, records):
    """Untouched rows keep their exact line text; new rows are compact, like `jq -c`."""
    original = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                original.setdefault(_key(json.loads(line)), line)
    lines = [original.get(_key(r)) or json.dumps(r, separators=(",", ":")) for r in records]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(l + "\n" for l in lines))
    tmp.replace(path)


def _read_feed(path):
    if not path.exists():
        return None
    blob = json.loads(path.read_text())
    return {"events": blob} if isinstance(blob, list) else blob


def run(repo, now=None, events_path=None, dry_run=False):
    """Derive every calendar habit; returns the log files it changed (relative paths)."""
    repo = Path(repo)
    now = now or datetime.now(_tz())
    today = now.date().isoformat()
    habits = load_habits(yaml.safe_load((repo / "config/habit_schema.yaml").read_text()))
    feed = _read_feed(Path(events_path) if events_path else repo / "data/calendar-cache.json")
    if not habits or feed is None:
        print("calendar habits: no habits or no calendar feed; nothing to do.")
        return []
    events = feed.get("events") or []
    covered = covered_dates(feed, today)

    changed = []
    for cadence, rel in LOG_FILES.items():
        mine = [h for h in habits if h["cadence"] == cadence]
        if not mine:
            continue
        path = repo / rel
        existing = _read_ndjson(path)
        merged = existing
        for h in mine:
            rows = derived_rows(h, events, now)
            merged = merge(merged, h["id"], rows, covered)
            print(f"{h['id']}: {len(rows)} dates with a calendar rep in the feed")
        if merged != existing:
            changed.append(rel)
            if not dry_run:
                _write_ndjson(path, merged)
            print(f"{'would write' if dry_run else 'wrote'} {rel} ({len(merged) - len(existing):+d} rows)")
    if not changed:
        print("no change.")
    return changed


def main(argv):
    events = argv[argv.index("--events") + 1] if "--events" in argv else None
    run(REPO_ROOT, events_path=events, dry_run="--dry-run" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
