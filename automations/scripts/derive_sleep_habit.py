#!/usr/bin/env python3
"""Derive the `sleep-on-time` habit log from wearable sleep data.

The watch already knows whether you were asleep on time, so the evening
check-in should not have to ask. The bar is NOT redefined here:
`qqrt.timing` in day-tracking.ndjson is already "asleep at or before the
target time" (qqrt.py, `timing_asleep_by_min` in its config). This script only
mirrors that field into the habit log so the Current Focus light, the habit
rates and the Trello card all read the same number. A self-reported habit log
has holes, and a hole is indistinguishable from a miss at compute time.

Idempotent: re-running rewrites the derived rows in place and never touches a
row from another source. Nights with no sleep data get no row at all — absence
already reads as a miss (7-habits/AGENTS.md), and inventing a `false` for a
night the watch was on the charger would be a fabricated miss.

Usage: python3 automations/scripts/derive_sleep_habit.py [--dry-run]
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DAY_TRACKING = REPO_ROOT / "data" / "day-tracking.ndjson"
HABITS_DAILY = REPO_ROOT / "7-habits" / "_data" / "habits-daily.ndjson"
HABIT_SCHEMA = REPO_ROOT / "config" / "habit_schema.yaml"

HABIT_ID = "sleep-on-time"
SOURCE = "fitbit-derived"


def derived_rows(day_records):
    """One habit row per night whose sleep timing is actually known."""
    rows = []
    for rec in day_records:
        timing = (rec.get("qqrt") or {}).get("timing")
        if timing is None:
            continue
        rows.append({"habit_id": HABIT_ID, "date": rec["date"],
                     "completed": bool(timing), "source": SOURCE})
    return rows


def merge(existing, rows):
    """Replace this habit's derived rows, leave every other row untouched.

    Keyed on (habit_id, date) so a re-run after a health re-fetch corrects a
    night rather than appending a second, contradictory row for it.
    """
    by_date = {r["date"]: r for r in rows}
    out, seen = [], set()
    for row in existing:
        if row.get("habit_id") != HABIT_ID:
            out.append(row)
            continue
        if row.get("source") != SOURCE:
            # A hand-logged row for this habit is a deliberate override; keep it
            # and drop the derived one for that date rather than fighting over it.
            out.append(row)
            seen.add(row.get("date"))
            continue
        replacement = by_date.get(row.get("date"))
        if replacement is not None and row.get("date") not in seen:
            out.append(replacement)
            seen.add(row["date"])
        # a derived row whose night lost its data falls out entirely
    out.extend(r for d, r in sorted(by_date.items()) if d not in seen)
    return out


def _read_ndjson(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _write_ndjson(path, records):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(r) + "\n" for r in records))
    tmp.replace(path)


def habit_declared(schema_path=HABIT_SCHEMA, habit_id=HABIT_ID):
    """True when habit_schema.yaml declares the habit this script writes.

    A repo that renamed or removed the habit gets no derived rows, so the
    validator never sees an undeclared habit_id. Rename HABIT_ID above to
    point the script at your own sleep-timing habit.
    """
    if not schema_path.exists():
        return False
    return any(line.strip() in (f"- id: {habit_id}", f'- id: "{habit_id}"')
               for line in schema_path.read_text().splitlines())


def main(argv):
    if not habit_declared():
        print(f"{HABIT_ID}: not declared in config/habit_schema.yaml; nothing to derive.")
        return 0
    days = _read_ndjson(DAY_TRACKING)
    rows = derived_rows(days)
    existing = _read_ndjson(HABITS_DAILY)
    merged = merge(existing, rows)

    added = len(merged) - len(existing)
    on_target = sum(1 for r in rows if r["completed"])
    print(f"{HABIT_ID}: {len(rows)} nights with known timing, "
          f"{on_target} on target ({round(100 * on_target / len(rows)) if rows else 0}%)")
    if "--dry-run" in argv:
        print(f"(dry run — would write {len(merged)} rows, {added:+d} vs current)")
        return 0
    if merged == existing:
        print("no change.")
        return 0
    _write_ndjson(HABITS_DAILY, merged)
    print(f"wrote {len(merged)} rows ({added:+d}).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
