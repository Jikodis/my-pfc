#!/usr/bin/env python3
"""The two project gauges: velocity and days idle.

Projects are one of the three intention layers, and these are the numbers that
say whether one is still moving (root AGENTS.md, "The three intention layers").
Both rules live here so the /pfc-revive watchlist and the web UI's home page read
the same arithmetic instead of each holding a copy.

- velocity: parts a day measured since the project started, projected forward to
  a finish date and compared against the deadline. The rule and the three lights
  are the ones written in 5-projects/AGENTS.md, "Velocity calculation": green on
  track, yellow within 7 days late, red past SIGNAL_A_LATE_DAYS late.
- days idle: days since the newest task event on any of the project's tasks,
  falling back to the project's own start when it has no event yet.

Every function here is pure. Nothing in this module reads a file, so a caller
passes in the rows it already loaded.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Optional

# Velocity turns red past this many days late. /pfc-revive calls that state
# signal A, which is where the name comes from; tune the number here.
SIGNAL_A_LATE_DAYS = 7


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _light(days_late: int) -> str:
    if days_late <= 0:
        return "green"
    return "yellow" if days_late <= SIGNAL_A_LATE_DAYS else "red"


def velocity(project: dict, today: date) -> dict:
    """How fast the project is moving and whether that lands before the deadline.

    Returns parts_per_week, estimated_completion (YYYY-MM-DD), days_late, and
    light. A field is None when the rule cannot reach it: everything is None
    without a start date or without a completed part, and days_late and light
    are None when the project has no deadline to miss.

    Known and deliberate: the start date here is `created`, not the registry's
    `started` field, which is what /pfc-revive's signal A has always measured
    from, so a project whose two dates differ is graded from `created` while
    days_idle() below falls back to `started`.
    """
    empty = {"parts_per_week": None, "estimated_completion": None,
             "days_late": None, "light": None}

    started = _parse_date(project.get("created"))
    if started is None:
        return empty
    completed_parts = int(project.get("completed_parts") or 0)
    if completed_parts <= 0:
        return empty

    days_elapsed = max(1, (today - started).days)
    parts_per_day = completed_parts / days_elapsed
    remaining = max(0, int(project.get("total_parts") or 0) - completed_parts)
    estimated_completion = today + timedelta(days=remaining / parts_per_day)

    out = {"parts_per_week": parts_per_day * 7,
           "estimated_completion": estimated_completion.isoformat(),
           "days_late": None, "light": None}

    deadline = _parse_date(project.get("deadline"))
    if deadline is not None:
        out["days_late"] = (estimated_completion - deadline).days
        out["light"] = _light(out["days_late"])
    return out


def days_idle(
    project: dict,
    tasks: Iterable[dict],
    events: Iterable[dict],
    today: date,
) -> Optional[int]:
    """Days since anything happened on this project.

    The newest task event on any of the project's tasks wins; with no event, the
    project's own `started` (or `created`) stands in. Returns None when there is
    no date to measure from.

    Known and deliberate: events are read by their `timestamp` field only, so the
    26 of 719 rows in task_events.ndjson that carry their date under `ts` or
    `date` do not count here; revive_watchlist.load_events is more tolerant, so signal F and
    this gauge can disagree about the same project by a few days.
    """
    project_id = project.get("id")
    task_ids = {t["id"] for t in tasks if t.get("project") == project_id and t.get("id")}

    newest = ""
    for e in events:
        task_id = e.get("task_id")
        stamp = (e.get("timestamp") or "")[:10]
        if task_id in task_ids and stamp > newest:
            newest = stamp

    stamp = newest or project.get("started") or project.get("created")
    when = _parse_date(stamp)
    return None if when is None else (today - when).days
