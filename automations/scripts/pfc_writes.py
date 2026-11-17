#!/usr/bin/env python3
"""
The record changes every writer shares: complete a task, log a habit, park a focus.

The Trello sync (`trello_writeback.py`) and the web UI's writer (`web_write.py`)
both call these, so a task completed from the Trello board and one completed from
the browser leave the same rows behind. Each function changes the lists it is handed,
in place, and reads no file and no clock: the caller loads the records, passes the
local date, and writes the result back. Checks that depend on config (a habit's
cadence, `auto_derived`) are the caller's.

The rules mirror the skills: `pfc-complete-task` steps 4 to 6 and `pfc-focus`
PARK / UNPARK.
"""

from __future__ import annotations

import json


def _find(records: list[dict], record_id: str) -> dict | None:
    return next((r for r in records if r.get("id") == record_id), None)


def _mark_focus_done(focus: list[dict], task_id: str, today: str) -> bool:
    """The 2+1 update: `pfc-complete-task` step 6. True when a record changed."""
    changed = False
    for day in focus:
        if day.get("date") != today:
            continue
        if task_id in (day.get("critical") or []):
            done = day.get("completed") or []
            if task_id not in done:
                day["completed"] = [*done, task_id]
                changed = True
        elif day.get("bonus") == task_id and day.get("bonus_completed") is not True:
            day["bonus_completed"] = True
            changed = True
    return changed


def complete_task(tasks: list[dict], events: list[dict], focus: list[dict],
                  task_id: str, today: str, source: str,
                  focus_date: str | None = None) -> tuple[str, dict]:
    """Mark a task done, log the event, and tick it off that day's 2+1.

    `today` dates the completion; `focus_date` is the daily-focus record to tick,
    `today` when not given. Callers pass it: the web writer passes today, the Trello
    sync the local date the card was checked, so a card checked last night and
    synced this morning ticks last night's record.

    Returns ('completed' | 'already_done' | 'unknown', info) where info is
    {"title", "email_linked", "focus_updated"}. `email_linked` tells the caller the
    source email can be archived (`pfc-complete-task` step 7). Only 'completed'
    changes anything.
    """
    task = _find(tasks, task_id)
    if task is None:
        return "unknown", {"title": "", "email_linked": False, "focus_updated": False}

    thread = task.get("source_email_thread_id")
    info = {
        "title": task.get("description") or "",
        "email_linked": isinstance(thread, str) and thread != "",
        "focus_updated": False,
    }
    if task.get("status") == "done":
        return "already_done", info

    task["status"] = "done"
    task["completed"] = today
    events.append({"task_id": task_id, "event": "completed", "timestamp": today, "source": source})
    info["focus_updated"] = _mark_focus_done(focus, task_id, focus_date or today)
    return "completed", info


DROP_NOTE = "Dropped: won't do."


def drop_task(tasks: list[dict], events: list[dict], task_id: str, today: str,
              source: str, focus: list[dict] | None = None) -> tuple[str, dict]:
    """Drop an open task the user decided not to do: log a `deleted` event, the way a drop
    made in chat is logged.

    The record itself is removed by the caller, at `info["index"]`, through its file
    layer (`NdjsonFile.remove_at`), because the line has to go with it. When the
    task was ever a 2+1 pick or a skipped suggestion (named in `focus`), `info["archive"]` is a copy stamped
    `dropped: today` for the caller to append to the task archive: every pick must
    still name a task, and so must every skip (`scripts/validate.sh` step 6b); the 2+1 history keeps its
    title. Returns ('dropped' | 'not_open' | 'unknown', info) where info is
    {"title", "email_linked", "index", "archive"}. Only 'dropped' changes anything.
    """
    index = next((i for i, r in enumerate(tasks) if r.get("id") == task_id), None)
    if index is None:
        return "unknown", {"title": "", "email_linked": False, "index": None, "archive": None}
    task = tasks[index]
    thread = task.get("source_email_thread_id")
    info = {
        "title": task.get("description") or "",
        "email_linked": isinstance(thread, str) and thread != "",
        "index": index,
        "archive": None,
    }
    if task.get("status") != "open":
        return "not_open", info
    picked = any(task_id in (day.get("critical") or []) or day.get("bonus") == task_id
                 or task_id in (day.get("skipped") or []) for day in focus or [])
    if picked:
        info["archive"] = {**task, "dropped": today}
    events.append({"task_id": task_id, "event": "deleted", "timestamp": today, "source": source,
                   "note": DROP_NOTE})
    return "dropped", info


# How many days back a page may still log a habit. Past a week nobody can say from
# memory whether the habit happened, so an older day goes through chat, where the
# day's own records can be read first.
LOG_WINDOW_DAYS = 7


def log_habit(logs: list[dict], habit_id: str, today: str, source: str) -> str:
    """Mark the habit done on the date `today`, keeping one row per habit and date.

    A completed row is left alone ('already_logged'). A row that says missed or
    skipped, which a chat log can write, is updated in place: completed,
    re-sourced, and stripped of its skip fields ('updated'). A second row for the
    same date would count the habit twice and fail `scripts/validate.sh`. With no
    row for the date, one is appended ('logged').
    """
    for row in logs:
        if row.get("habit_id") == habit_id and row.get("date") == today:
            if row.get("completed") is True:
                return "already_logged"
            row["completed"] = True
            row["source"] = source
            row.pop("skipped", None)
            row.pop("skip_reason", None)
            return "updated"
    logs.append({"habit_id": habit_id, "date": today, "completed": True, "source": source})
    return "logged"


def set_parked(focus: list[dict], focus_id: str, parked: bool) -> tuple[str, dict]:
    """Park or unpark a focus. A record with no `parked` field counts as not parked.

    Returns ('updated' | 'unchanged' | 'unknown', {"title"}). A retired focus
    (`retired_date` set) is 'unknown': it is off every list and cannot be parked.
    """
    record = _find(focus, focus_id)
    if record is None or record.get("retired_date"):
        return "unknown", {"title": ""}
    info = {"title": record.get("title") or ""}
    if bool(record.get("parked", False)) == parked:
        return "unchanged", info
    record["parked"] = parked
    return "updated", info


def rate_day(days: list[dict], day: str, energy: int, mood: int, focus: int,
             hyperfocused: bool | None) -> str:
    """Rate a day: the home page's rating card (`rate-day` in `web_write.py`).

    `rating` is round((energy + mood + focus) / 3), never asked (`pfc-log-day`).
    `hyperfocused` is optional: written when given, otherwise left as it is, or null on
    a new row. Fields never asked for here (exercised, sick, notes) stay as they are,
    or null on a new row. A day that already has a rating is left alone
    ('already_rated'). A row without one (the health fetch writes those) is filled in
    place ('updated'); with no row, a new one is appended ('added').
    """
    rating = int((energy + mood + focus) / 3 + 0.5)
    row = next((r for r in days if r.get("date") == day), None)
    if row is not None and row.get("rating") is not None:
        return "already_rated"
    asked = {"rating": rating, "energy": energy, "focus": focus, "mood": mood}
    if hyperfocused is not None:
        asked["hyperfocused"] = hyperfocused
    if row is not None:
        row.update(asked)
        return "updated"
    days.append({"date": day, "rating": rating, "energy": energy, "focus": focus, "mood": mood,
                 "exercised": None, "sick": None, "hyperfocused": hyperfocused, "notes": None})
    return "added"


def set_picks(focus: list[dict], day: str, critical: list[str], bonus: str | None) -> str:
    """Set a day's 2+1. Keeps an existing `project` slot and `skipped` list; `completed`
    keeps only the ids already done that are still picked (so a done pick sent again
    stays done when more work is pulled in), and `bonus_completed` stays only while the
    bonus is the same task. Returns 'added' | 'updated' | 'unchanged'."""
    record = next((r for r in focus if r.get("date") == day), None)
    if record is None:
        focus.append({"date": day, "critical": list(critical), "bonus": bonus, "completed": [],
                      "bonus_completed": False})
        return "added"
    before = json.loads(json.dumps(record))
    done = [t for t in (record.get("completed") or []) if t in critical]
    kept_bonus = bonus is not None and record.get("bonus") == bonus and record.get("bonus_completed") is True
    record["critical"] = list(critical)
    record["bonus"] = bonus
    record["completed"] = done
    record["bonus_completed"] = kept_bonus
    return "unchanged" if record == before else "updated"


def drop_pick(focus: list[dict], day: str, task_id: str) -> str:
    """Take a task out of a day's 2+1 (the reMarkable Today page's swap box). The task
    stays open in the backlog. It is added to `skipped`, so the day's suggestions stop
    offering it, and to `dropped`, so a second drop of it that day changes nothing and
    a later pick of the same task stands. A done pick is left alone.
    Returns 'dropped' | 'unchanged' (dropped once already) | 'unknown'."""
    record = next((r for r in focus if r.get("date") == day), None)
    if record is None:
        return "unknown"
    critical = record.get("critical") or []
    open_critical = task_id in critical and task_id not in (record.get("completed") or [])
    is_bonus = record.get("bonus") == task_id and record.get("bonus_completed") is not True
    is_project = record.get("project") == task_id and record.get("project_completed") is not True
    if not (open_critical or is_bonus or is_project):
        return "unknown"
    if task_id in (record.get("dropped") or []):
        return "unchanged"
    if open_critical:
        record["critical"] = [t for t in critical if t != task_id]
    if is_bonus:
        record["bonus"] = None
        record["bonus_completed"] = False
    if is_project:
        record.pop("project", None)
        record.pop("project_completed", None)
    if task_id not in (record.get("skipped") or []):
        record["skipped"] = [*(record.get("skipped") or []), task_id]
    record["dropped"] = [*(record.get("dropped") or []), task_id]
    return "dropped"


def stamp_review(ledger: list[dict], review_id: str, day: str) -> str:
    """Set a rolling review's `last_done` to `day`. 'stamped' | 'unchanged' | 'unknown'."""
    row = _find(ledger, review_id)
    if row is None:
        return "unknown"
    if row.get("last_done") == day and not row.get("seen"):
        return "unchanged"
    row["last_done"] = day
    row.pop("seen", None)  # a finished review starts its next round from the top
    return "stamped"


def mark_review_seen(ledger: list[dict], review_id: str, rows: list[str]) -> str:
    """Record rows of a review already answered this round, when the review had more rows
    than one form holds: it stays due and its next form starts after them (review_forms).
    'saved' | 'unchanged' | 'unknown'."""
    row = _find(ledger, review_id)
    if row is None:
        return "unknown"
    seen = list(row.get("seen") or [])
    new = [r for r in rows if r not in seen]
    if not new:
        return "unchanged"
    row["seen"] = seen + new
    return "saved"


def skip_suggestion(focus: list[dict], day: str, task_id: str) -> str:
    """Add a task to the day's `skipped` list, so the home page stops suggesting it for
    that day. A day with no record gets one with no picks. 'added' | 'updated' | 'unchanged'."""
    record = next((r for r in focus if r.get("date") == day), None)
    if record is None:
        focus.append({"date": day, "critical": [], "bonus": None, "completed": [], "bonus_completed": False,
                      "skipped": [task_id]})
        return "added"
    skipped = record.get("skipped") or []
    if task_id in skipped:
        return "unchanged"
    record["skipped"] = [*skipped, task_id]
    return "updated"


def set_rating(snapshots: list[dict], key: str, light: str, note: str | None, day: str,
               logged_at: str) -> str:
    """Change one area's (or room's) light in the life-wheel or household-status history.

    The newest snapshot is copied to a new one dated `day` with that key's light changed;
    every other rating and note is kept. `note` None leaves the key's note alone, an empty
    string clears it, any other text sets it. A second change on the same day edits that
    day's snapshot instead of adding a tie for newest. Returns 'added' | 'updated' |
    'unchanged' | 'unknown' (the key is not in the newest snapshot).
    """
    if not snapshots:
        return "unknown"
    latest = max(enumerate(snapshots), key=lambda p: (p[1].get("date") or "", p[0]))[1]
    if key not in (latest.get("ratings") or {}):
        return "unknown"
    ratings = {**latest["ratings"], key: light}
    notes = dict(latest.get("notes") or {})
    if note is not None:
        if note:
            notes[key] = note
        else:
            notes.pop(key, None)
    if ratings == latest["ratings"] and notes == (latest.get("notes") or {}):
        return "unchanged"
    if latest.get("date") == day:
        latest.update({"ratings": ratings, "notes": notes, "logged_at": logged_at})
        return "updated"
    snapshots.append({"date": day, "ratings": ratings, "notes": notes, "logged_at": logged_at})
    return "added"


def retire_anchor(grounding: list[dict], anchor_id: str, today: str) -> str:
    """Retire a front-of-mind anchor (`data/grounding.ndjson`). 'retired' | 'unchanged' (already retired) | 'unknown'."""
    row = _find(grounding, anchor_id)
    if row is None:
        return "unknown"
    if row.get("status") == "retired":
        return "unchanged"
    row["status"] = "retired"
    row["retired_date"] = today
    return "retired"


def set_project(projects: list[dict], project_id: str, active: bool) -> str:
    """Switch a project between active and parked. 'updated' | 'unchanged' | 'unknown' |
    'closed' (a done or dropped project is not switched)."""
    row = _find(projects, project_id)
    if row is None:
        return "unknown"
    if row.get("status") in ("done", "dropped"):
        return "closed"
    status = "active" if active else "parked"
    if row.get("active") is active and row.get("status") == status:
        return "unchanged"
    row["active"] = active
    row["status"] = status
    return "updated"
