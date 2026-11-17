#!/usr/bin/env python3
"""Log workout habits from the exercise sessions Google Health already recorded.

The watch records the session, the health fetch already stores it in
`health.workouts` on the day's record in data/day-tracking.ndjson, and a rep
that is already recorded should not depend on remembering to tap it
(docs/habit-mechanics.md § "Habits that log themselves").

Which habits: any active daily habit in config/habit_schema.yaml with a
`workout: {types: [...], min_minutes: N}` block, for example

    - id: morning-walk
      workout: {types: [WALKING], min_minutes: 20}

A date gets ONE completed row (source "health-derived") when at least one
session that day has a listed `exerciseType` and, when `min_minutes` is set,
lasted at least that long, however many sessions there are.

How this differs from the sleep deriver: these habits are NOT `auto_derived`.
A workout done without starting the watch still counts, so hand logging (chat,
the Trello card) stays. The deriver only fills in what the watch saw.

Rules:
  - A session's length is its heart-rate-derived `real_minutes`
    (row_duration.py), because the watch timer overruns when Stop is forgotten;
    the timer's `minutes` is used only when no derived length exists.
  - Leave `min_minutes` off (0) for session types that do not hold the heart
    rate up, such as strength training: `real_minutes` can read 1 to 4 minutes on
    a real 45-minute lifting session, so the session type alone decides.
  - A row from any other source for that habit and date wins, whatever it says
    (done, missed or skipped). The deriver never writes beside it.
  - `health.workouts` null or absent means the exercise fetch failed or never
    ran for that day: nothing is written and an existing derived row is kept.
  - A day whose sessions are known and no longer include a match (a
    mis-started session was deleted) loses its derived row.
  - No session never writes a miss. Absence already reads as a miss
    (7-habits/AGENTS.md), and a `false` for a day trained without the watch
    would be a fabricated miss.
  - Sessions dated before the habit's `started` are ignored.

Idempotent: every run sweeps all days, so a session that syncs late and a
first-time backfill use the same path. Run by auto_fetch_health.py on every
fetch that changes the day record.

Usage: python3 automations/scripts/derive_workout_habits.py [--dry-run]
"""
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = "health-derived"
SCHEMA = "config/habit_schema.yaml"
DAY_TRACKING = "data/day-tracking.ndjson"
HABITS_DAILY = "7-habits/_data/habits-daily.ndjson"


def load_habits(schema):
    """Active daily habits with a workout rule: [{id, types, min_minutes, started}]."""
    out = []
    for h in (schema or {}).get("daily_habits") or []:
        if not isinstance(h, dict) or h.get("active") is False:
            continue
        rule = h.get("workout")
        types = set(rule.get("types") or []) if isinstance(rule, dict) else set()
        if types:
            out.append({"id": h["id"], "types": types, "min_minutes": rule.get("min_minutes") or 0,
                        "started": str(h.get("started") or "")})
    return out


def session_minutes(workout):
    """A session's length: the heart-rate-derived minutes, else the watch timer's."""
    real = workout.get("real_minutes")
    return real if real is not None else (workout.get("minutes") or 0)


def counts(habit, workout):
    """True when this session is a rep of the habit."""
    workout = workout or {}
    return (workout.get("type") in habit["types"]
            and session_minutes(workout) >= habit.get("min_minutes", 0))


def session_dates(habit, day_records):
    """(dates with a matching session, dates whose sessions are known)."""
    hit, known = set(), set()
    for rec in day_records:
        day = rec.get("date")
        workouts = (rec.get("health") or {}).get("workouts")
        if not day or not isinstance(workouts, list) or day < habit["started"]:
            continue
        known.add(day)
        if any(counts(habit, w) for w in workouts):
            hit.add(day)
    return hit, known


def merge(existing, habit_id, hit, known):
    """Rewrite this habit's derived rows; leave every other row alone."""
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
        if day in hit or day not in known:
            out.append(row)  # still backed by a session, or no evidence either way
            seen.add(day)
        # sessions known and no match any more: drop
    out.extend({"habit_id": habit_id, "date": d, "completed": True, "source": SOURCE}
               for d in sorted(hit) if d not in seen and d not in manual)
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
    for line in path.read_text().splitlines() if path.exists() else []:
        if line.strip():
            original.setdefault(_key(json.loads(line)), line)
    lines = [original.get(_key(r)) or json.dumps(r, separators=(",", ":")) for r in records]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(l + "\n" for l in lines))
    tmp.replace(path)


def run(repo, dry_run=False):
    """Derive every workout habit. Returns True when the habit log changed (or would)."""
    repo = Path(repo)
    habits = load_habits(yaml.safe_load((repo / SCHEMA).read_text()))
    if not habits:
        print("workout habits: no habit has a workout rule; nothing to do.")
        return False
    days = _read_ndjson(repo / DAY_TRACKING)
    path = repo / HABITS_DAILY
    existing = _read_ndjson(path)
    merged = existing
    for h in habits:
        hit, known = session_dates(h, days)
        before = merged
        merged = merge(merged, h["id"], hit, known)
        added = sorted({r["date"] for r in merged if r.get("habit_id") == h["id"] and r.get("source") == SOURCE}
                       - {r["date"] for r in before if r.get("habit_id") == h["id"] and r.get("source") == SOURCE})
        print(f"{h['id']}: {len(hit)} days with a tracked session"
              + (f", new: {', '.join(added)}" if added else ""))
    if merged == existing:
        print("no change.")
        return False
    if not dry_run:
        _write_ndjson(path, merged)
    print(f"{'would write' if dry_run else 'wrote'} {HABITS_DAILY} ({len(merged) - len(existing):+d} rows)")
    return True


def main(argv):
    run(REPO_ROOT, dry_run="--dry-run" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
