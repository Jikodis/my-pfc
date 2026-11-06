#!/usr/bin/env python3
"""The one program that writes this repo on the web UI's behalf.

    python3 automations/scripts/web_write.py [--dry-run] [--no-render] complete-task <task_id>
    python3 automations/scripts/web_write.py [--dry-run] [--no-render] drop-task <task_id>
    python3 automations/scripts/web_write.py [--dry-run] [--no-render] log-habit <habit_id> [YYYY-MM-DD]
    python3 automations/scripts/web_write.py [--dry-run] [--no-render] park-focus <focus_id> on|off
    python3 automations/scripts/web_write.py [--dry-run] [--no-render] rate-day <YYYY-MM-DD> <energy> <mood> <focus> [hyper:yes|no]
    python3 automations/scripts/web_write.py [--dry-run] [--no-render] set-picks <YYYY-MM-DD> <task_id>... [bonus:<task_id>]
    python3 automations/scripts/web_write.py [--dry-run] [--no-render] stamp-review <review_id>
    python3 automations/scripts/web_write.py [--dry-run] [--no-render] skip-suggestion <YYYY-MM-DD> <task_id>
    python3 automations/scripts/web_write.py [--dry-run] [--no-render] set-area <area_key> green|yellow|red [note:<text>]
    python3 automations/scripts/web_write.py [--dry-run] [--no-render] set-room <room_key> green|yellow|red [note:<text>]
    python3 automations/scripts/web_write.py [--dry-run] [--no-render] retire-anchor <ground_id>
    python3 automations/scripts/web_write.py [--dry-run] [--no-render] set-project <proj_id> active|parked

`web/src/lib/write.ts` spawns it with an argv array and reads the one JSON object it
prints on stdout. It refuses unless the repo is on `PFC_WRITE_BRANCH` (default
`main`). Then, all under one exclusive lock on `data/.web-write.lock`:

1. bring the branch level with origin (`repo_sync.py`: a rebase on a clean tree, a
   fast-forward when there are uncommitted edits, never a stash; a failure is logged
   and the write goes on with the copy it has), then read the files the action needs;
2. change the records through `pfc_writes.py`, the same functions the Trello sync uses;
3. write only the files that changed, each through `ndjson_file.NdjsonFile`, which
   refuses when the file changed on disk after it was read;
4. `git add` those paths and commit only those paths. The repo's pre-commit hook
   runs `scripts/validate.sh`; this script does not run it a second time. When the
   commit fails, the files are put back from HEAD;
5. level with origin again, then push. Another clone of the repo (a laptop and a
   server, say) may have pushed in between; a conflict aborts the rebase, keeps the commit local, and is reported
   as the push error;
6. start the Trello render in the background (not with --no-render) and return
   without waiting for it.

The commit runs with PFC_SKIP_TRELLO_RENDER=1, so the post-commit hook does not
render inside the request. The render is `PFC_TRELLO_RENDER` when set (tests name a
fake), otherwise `trello_render.py`; its output is appended to `PFC_WEB_LOG`
(default `/tmp/pfc-web.log`).

Exit codes, which write.ts maps to HTTP statuses:

    0  saved, or nothing to change ("changed": false); a failed push is still 0,
       and so is SIGTERM after the commit exists (reported as not pushed)
    2  bad request, unknown id, or a refused change ("reason" says which)
    3  busy: the lock is held, the repo is on another branch, the pre-commit hook
       is not installed, a file this change needs has uncommitted edits, or it
       changed while this ran
    4  the commit failed (the pre-commit validator's first failure line) or ran past
       its time; the files were restored
    1  anything else, including SIGTERM before the commit (details on stderr)

Every program it starts runs in a session of its own with a time limit (the commit
with its hook 60 seconds, `PFC_WRITE_COMMIT_TIMEOUT` overrides; push 30), and is
stopped with everything it started when the limit passes or when this script gets
SIGTERM: first SIGTERM, so git removes its lock files, then SIGKILL. SIGTERM, which
`write.ts` sends when its own time runs out, raises inside the script. Before the
commit exists the files are restored from git; after it exists the saved commit is
reported with "pushed": false. Either way the lock is released before it exits.

Dates come from `today_local(load_env())`, never from the browser. The repo is
`PFC_REPO_ROOT` when set (tests point it at a throwaway git repo), otherwise the
repo this script lives in.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import repo_sync  # noqa: E402
from ndjson_file import ChangedUnderneath, NdjsonFile as _NdjsonFile  # noqa: E402
from pfc_writes import (LOG_WINDOW_DAYS, complete_task, drop_task, log_habit, rate_day, retire_anchor,  # noqa: E402
                        set_parked, set_picks, set_project, set_rating, skip_suggestion, stamp_review)
from trmnl_push import load_env, today_local  # noqa: E402
from home_data import _label  # noqa: E402
from web_data import habit_title  # noqa: E402

REPO = Path(os.environ.get("PFC_REPO_ROOT") or SCRIPT_DIR.parents[1]).resolve()

TASKS = "6-tasks/_data/tasks.ndjson"
ARCHIVE = "6-tasks/_data/tasks-archive.ndjson"
EVENTS = "6-tasks/_data/task_events.ndjson"
DAILY_FOCUS = "6-tasks/_data/daily-focus.ndjson"
HABITS_DAILY = "7-habits/_data/habits-daily.ndjson"
HABITS_MONTHLY = "7-habits/_data/habits-monthly.ndjson"
FOCUS = "4-focus/_data/focus.ndjson"
HABIT_SCHEMA = "config/habit_schema.yaml"
DAY_TRACKING = "data/day-tracking.ndjson"
REVIEW_LEDGER = "data/review-ledger.ndjson"
LIFE_WHEEL = "2-areas/_data/life-wheel.ndjson"
HOUSEHOLD = "2-areas/_data/household-status.ndjson"
GROUNDING = "data/grounding.ndjson"
PROJECTS = "5-projects/_data/projects.ndjson"
LOCK = "data/.web-write.lock"

TASK_ID = re.compile(r"^task-\d{8}-\d{3}$")
HABIT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$")
FOCUS_ID = re.compile(r"^focus-\d{8}-\d{3}$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
GROUND_ID = re.compile(r"^ground-\d{8}-\d{3}$")
PROJECT_ID = re.compile(r"^proj-\d{8}-\d{3}$")
RATING_KEY = re.compile(r"^[a-z][a-z_]{0,31}$")
LIGHTS = ("green", "yellow", "red")
NOTE_PREFIX = "note:"
NOTE_LIMIT = 300
# Ids a set-picks call may carry: the picks already done that day travel with the new
# ones, so this bounds the argument list only. The cap of two open picks is checked
# against the day's record in plan_set_picks.
MAX_PICK_IDS = 8
OPEN_PICKS = 2

SOURCE = "web"
CHANGED_UNDERNEATH = "A file this change needs was changed by something else while it was being saved; nothing was changed. Try again."
# Set once the commit exists, so a SIGTERM after it reports the saved change.
COMMITTED = False
SAVED: dict = {}
# True while this script's own sync (a git pull --rebase) runs, so a SIGTERM that
# lands inside it can abort that rebase on the way out instead of leaving it behind.
SYNCING = False
SYNC_INTERRUPTED = False
PUSH_STOPPED = "The push timed out; the commit is saved and will push next time."
BODY = "Written by the web UI."
TRAILER = "Co-Authored-By: PFC web UI <noreply@localhost>"
PUSH_TIMEOUT_SECONDS = 30
COMMIT_TIMEOUT_SECONDS = float(os.environ.get("PFC_WRITE_COMMIT_TIMEOUT") or 60)
GIT_TIMEOUT_SECONDS = 60
STOP_GRACE_SECONDS = 2
WRITE_BRANCH = os.environ.get("PFC_WRITE_BRANCH") or "main"
RENDER = Path(os.environ.get("PFC_TRELLO_RENDER") or SCRIPT_DIR / "trello_render.py")
WEB_LOG = Path(os.environ.get("PFC_WEB_LOG") or "/tmp/pfc-web.log")
USAGE = ("Usage: web_write.py [--dry-run] [--no-render] complete-task <id> | drop-task <id> | log-habit <id> [YYYY-MM-DD] "
         "| park-focus <id> on|off | rate-day <YYYY-MM-DD> <energy 1-5> <mood 1-5> <focus 1-5> [hyper:yes|no] "
         "| set-picks <YYYY-MM-DD> <task_id>... [bonus:<task_id>] | stamp-review <review_id> "
         "| skip-suggestion <YYYY-MM-DD> <task_id> | set-area <key> green|yellow|red [note:<text>] "
         "| set-room <key> green|yellow|red [note:<text>] | retire-anchor <ground_id> | set-project <proj_id> active|parked")


class Stop(Exception):
    """An expected refusal: printed as JSON, exits with its code."""

    def __init__(self, code: int, reason: str, error: str):
        super().__init__(error)
        self.code, self.reason, self.error = code, reason, error


# ---------------------------------------------------------------- NDJSON files

class Terminated(Exception):
    """SIGTERM arrived. Raised from the signal handler so the restore path runs."""


# The process group of the program run_bounded is waiting on, if any.
CURRENT_GROUP: int | None = None


def _on_sigterm(signum, frame):
    # The child runs in a session of its own, so the signal that reached this script
    # did not reach it. Pass it on first; run_bounded then waits and sends SIGKILL.
    global SYNC_INTERRUPTED
    SYNC_INTERRUPTED = SYNCING
    if CURRENT_GROUP is not None:
        _signal_group(CURRENT_GROUP, signal.SIGTERM)
    raise Terminated()


def NdjsonFile(rel: str) -> _NdjsonFile:
    """The file at `rel` under the repo, labeled with `rel`."""
    f = _NdjsonFile(REPO / rel, rel)
    f.rel = rel
    return f


# ---------------------------------------------------------------- the actions

def plan_complete_task(task_id: str, today: str) -> dict:
    tasks, events, focus = NdjsonFile(TASKS), NdjsonFile(EVENTS), NdjsonFile(DAILY_FOCUS)
    status, info = complete_task(tasks.records, events.records, focus.records, task_id, today, SOURCE,
                                 focus_date=today)
    if status == "unknown":
        raise Stop(2, "not_found", "No open task with that id.")
    return {
        "files": [tasks, events, focus],
        "title": info["title"],
        "email_linked": info["email_linked"],
        "subject": f"task: complete {_one_line(info['title'])}",
        "unchanged": "Already done." if status == "already_done" else None,
        "saved": "Saved.",
    }


def plan_drop_task(task_id: str, today: str) -> dict:
    tasks, events, focus = NdjsonFile(TASKS), NdjsonFile(EVENTS), NdjsonFile(DAILY_FOCUS)
    status, info = drop_task(tasks.records, events.records, task_id, today, SOURCE, focus.records)
    if status == "unknown":
        raise Stop(2, "not_found", "No open task with that id.")
    if status == "not_open":
        raise Stop(2, "refused", "That task is already done.")
    tasks.remove_at(info["index"])
    archive = NdjsonFile(ARCHIVE)
    if info["archive"] is not None:
        archive.records.append(info["archive"])
    return {
        "files": [tasks, events, archive],
        "title": info["title"],
        "email_linked": info["email_linked"],
        "subject": f"task: drop {_one_line(info['title'])}",
        "unchanged": None,
        "saved": "Dropped.",
    }


def _habit_cadence(habit_id: str) -> str:
    """'daily' or 'monthly' for an active habit; refuses unknown, inactive, and derived ones."""
    schema = yaml.safe_load((REPO / HABIT_SCHEMA).read_text(encoding="utf-8")) or {}
    for cadence in ("daily", "monthly"):
        for habit in schema.get(f"{cadence}_habits") or []:
            if not isinstance(habit, dict) or habit.get("id") != habit_id:
                continue
            if habit.get("active") is False:
                break
            if habit.get("auto_derived") is True:
                raise Stop(2, "refused", "That habit is logged automatically from your watch data; there is nothing to click.")
            return cadence
    raise Stop(2, "not_found", "No active habit with that id.")


def _log_day(today: str, asked: str | None) -> str:
    """The day a habit log is for: today, or a day named in the last LOG_WINDOW_DAYS."""
    if asked is None:
        return today
    try:
        day = date.fromisoformat(asked)
    except ValueError:
        raise Stop(2, "bad_request", "That is not a valid date.") from None
    back = (date.fromisoformat(today) - day).days
    if back < 0:
        raise Stop(2, "refused", "That day has not happened yet.")
    if back > LOG_WINDOW_DAYS:
        raise Stop(2, "refused", f"That day is more than {LOG_WINDOW_DAYS} days back; log it in chat.")
    return day.isoformat()


def plan_log_habit(habit_id: str, today: str, asked: str | None = None) -> dict:
    day = _log_day(today, asked)
    cadence = _habit_cadence(habit_id)
    logs = NdjsonFile(HABITS_DAILY if cadence == "daily" else HABITS_MONTHLY)
    status = log_habit(logs.records, habit_id, day, SOURCE)
    already = "Already logged today." if day == today else "Already logged for that day."
    return {
        "files": [logs],
        "title": habit_title(habit_id),
        "email_linked": False,
        "subject": f"habit: log {day}",
        "unchanged": already if status == "already_logged" else None,
        "saved": "Marked done (it was logged as missed)." if status == "updated" else "Saved.",
    }


def plan_park_focus(focus_id: str, parked: bool) -> dict:
    focus = NdjsonFile(FOCUS)
    record = next((r for r in focus.records if r.get("id") == focus_id), None)
    if record is None:
        raise Stop(2, "not_found", "No focus with that id.")
    if record.get("retired_date"):
        raise Stop(2, "refused", "That focus is retired.")
    status, info = set_parked(focus.records, focus_id, parked)
    if status == "unknown":
        raise Stop(2, "not_found", "No focus with that id.")
    verb = "park" if parked else "unpark"
    return {
        "files": [focus],
        "title": info["title"],
        "email_linked": False,
        "subject": f"focus: {verb} {_one_line(info['title'])}",
        "unchanged": ("Already parked." if parked else "Already active.") if status == "unchanged" else None,
        "saved": "Saved.",
    }


def _asked_day(asked: str, allowed: tuple[str, ...], refusal: str) -> str:
    """`asked` when it is one of `allowed` (local dates); otherwise a refusal."""
    if asked not in allowed:
        raise Stop(2, "refused", refusal)
    return asked


def plan_rate_day(day: str, energy: int, mood: int, focus: int, hyper: bool | None, today: str) -> dict:
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    _asked_day(day, (today, yesterday), "Only today or yesterday can be rated here; use chat for an older day.")
    days, habits = NdjsonFile(DAY_TRACKING), NdjsonFile(HABITS_DAILY)
    status = rate_day(days.records, habits.records, day, energy, mood, focus, hyper)
    return {
        "files": [days],
        "title": day,
        "email_linked": False,
        "subject": f"track: log day {day}",
        "unchanged": "That day is already rated." if status == "already_rated" else None,
        "saved": "Saved.",
    }


def plan_set_picks(day: str, critical: list[str], bonus: str | None, today: str) -> dict:
    tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
    _asked_day(day, (today, tomorrow), "Picks can be set for today or tomorrow only.")
    tasks, daily = NdjsonFile(TASKS), NdjsonFile(DAILY_FOCUS)
    by_id = {t.get("id"): t for t in tasks.records}
    record = next((r for r in daily.records if r.get("date") == day), None) or {}
    # A pick already done that day stays a pick, so pulling in more work keeps it.
    done = set(record.get("completed") or []) & set(record.get("critical") or [])
    if sum(1 for t in critical if t not in done) > OPEN_PICKS:
        raise Stop(2, "refused", "Two picks are still open; finish or drop one before pulling in another.")
    for task_id in [*(t for t in critical if t not in done), *([bonus] if bonus else [])]:
        task = by_id.get(task_id)
        if task is None or task.get("status") != "open":
            raise Stop(2, "not_found", "Every pick must be an open task.")
        if task.get("agent_doable") == "yes":
            raise Stop(2, "refused", "An agent can finish that task; hand it off instead of picking it.")
        if task.get("deferred"):
            raise Stop(2, "refused", "That task is parked (deferred); un-park it in chat before picking it.")
    status = set_picks(daily.records, day, critical, bonus)
    return {
        "files": [daily],
        "title": day,
        "email_linked": False,
        "subject": f"focus: set {day}",
        "unchanged": "Those are already the picks." if status == "unchanged" else None,
        "saved": "Saved.",
    }


def plan_stamp_review(review_id: str, today: str) -> dict:
    ledger = NdjsonFile(REVIEW_LEDGER)
    status = stamp_review(ledger.records, review_id, today)
    if status == "unknown":
        raise Stop(2, "not_found", "No review with that id.")
    label = next(r.get("label") or review_id for r in ledger.records if r.get("id") == review_id)
    return {
        "files": [ledger],
        "title": label,
        "email_linked": False,
        "subject": f"review: stamp {_one_line(label)}",
        "unchanged": "Already stamped today." if status == "unchanged" else None,
        "saved": "Saved.",
    }


def plan_skip_suggestion(day: str, task_id: str, today: str) -> dict:
    tomorrow = (date.fromisoformat(today) + timedelta(days=1)).isoformat()
    _asked_day(day, (today, tomorrow), "A suggestion can be skipped for today or tomorrow only.")
    tasks, daily = NdjsonFile(TASKS), NdjsonFile(DAILY_FOCUS)
    task = next((t for t in tasks.records if t.get("id") == task_id), None)
    if task is None or task.get("status") != "open":
        raise Stop(2, "not_found", "No open task with that id.")
    status = skip_suggestion(daily.records, day, task_id)
    title = task.get("description") or ""
    return {
        "files": [daily],
        "title": title,
        "email_linked": False,
        "subject": f"focus: skip {_one_line(title)}",
        "unchanged": "Already skipped for that day." if status == "unchanged" else None,
        "saved": "Skipped.",
    }


def now_local(env: dict) -> tuple[str, str]:
    """(local date, `logged_at`) from one reading of the clock, so the two never straddle midnight.
    `logged_at` is the local time with a colon offset, like the existing rating rows."""
    now = datetime.now(ZoneInfo(env.get("LOCAL_TZ", "America/Denver")))
    return now.strftime("%Y-%m-%d"), now.isoformat(timespec="seconds")


def plan_set_rating(rel: str, kind: str, key: str, light: str, note: str | None, today: str, now: str) -> dict:
    """`kind` is 'area' or 'room'; `note` is None to keep the note, '' to clear it."""
    snapshots = NdjsonFile(rel)
    status = set_rating(snapshots.records, key, light, note, today, now)
    if status == "unknown":
        raise Stop(2, "not_found", f"No {kind} with that name.")
    label = _label(key)
    return {
        "files": [snapshots],
        "title": label,
        "email_linked": False,
        "subject": f"review: {kind} {label} {light}",
        "unchanged": "Already set." if status == "unchanged" else None,
        "saved": "Saved.",
    }


def plan_retire_anchor(anchor_id: str, today: str) -> dict:
    grounding = NdjsonFile(GROUNDING)
    status = retire_anchor(grounding.records, anchor_id, today)
    if status == "unknown":
        raise Stop(2, "not_found", "No anchor with that id.")
    title = next(r.get("title") or anchor_id for r in grounding.records if r.get("id") == anchor_id)
    return {
        "files": [grounding],
        "title": title,
        "email_linked": False,
        "subject": f"grounding: retire {_one_line(title)}",
        "unchanged": "Already retired." if status == "unchanged" else None,
        "saved": "Retired.",
    }


def plan_set_project(project_id: str, active: bool) -> dict:
    projects = NdjsonFile(PROJECTS)
    status = set_project(projects.records, project_id, active)
    if status == "unknown":
        raise Stop(2, "not_found", "No project with that id.")
    if status == "closed":
        raise Stop(2, "refused", "That project is done or dropped; it cannot be switched here.")
    name = next(r.get("name") or project_id for r in projects.records if r.get("id") == project_id)
    return {
        "files": [projects],
        "title": name,
        "email_linked": False,
        "subject": f"project: {'activate' if active else 'park'} {_one_line(name)}",
        "unchanged": ("Already active." if active else "Already parked.") if status == "unchanged" else None,
        "saved": "Saved.",
    }


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


# ---------------------------------------------------------------- arguments

def _rating(text: str, what: str) -> int:
    if not re.fullmatch(r"[1-5]", text):
        raise Stop(2, "bad_request", f"{what} is a whole number from 1 to 5.")
    return int(text)


def _check_rate_day(args: list[str]) -> None:
    if not 4 <= len(args) <= 5:
        raise Stop(2, "bad_request", USAGE)
    for value, what in zip(args[1:4], ("Energy", "Mood", "Focus")):
        _rating(value, what)
    seen = set()
    for extra in args[4:]:
        key, _, value = extra.partition(":")
        if key in seen or not (key == "hyper" and value in ("yes", "no")):
            raise Stop(2, "bad_request", USAGE)
        seen.add(key)


def _check_set_picks(args: list[str]) -> None:
    ids = [a for a in args[1:] if not a.startswith("bonus:")]
    bonus = [a[len("bonus:"):] for a in args[1:] if a.startswith("bonus:")]
    if len(args) < 2 or not 1 <= len(ids) <= MAX_PICK_IDS or len(bonus) > 1:
        raise Stop(2, "bad_request", f"Set one to {MAX_PICK_IDS} critical picks and at most one bonus.")
    if not all(TASK_ID.fullmatch(i) for i in [*ids, *bonus]):
        raise Stop(2, "bad_request", "That is not a valid id.")
    if len(set([*ids, *bonus])) != len(ids) + len(bonus):
        raise Stop(2, "bad_request", "A task can be picked only once.")


def _check_skip_suggestion(args: list[str]) -> None:
    if len(args) != 2:
        raise Stop(2, "bad_request", USAGE)
    if not TASK_ID.fullmatch(args[1]):
        raise Stop(2, "bad_request", "That is not a valid id.")


def _check_note(arg: str) -> None:
    """`note:<text>`: one line, at most NOTE_LIMIT characters; empty text clears the note."""
    if not arg.startswith(NOTE_PREFIX):
        raise Stop(2, "bad_request", USAGE)
    text = arg[len(NOTE_PREFIX):]
    if len(text) > NOTE_LIMIT:
        raise Stop(2, "bad_request", f"A note is at most {NOTE_LIMIT} characters.")
    # Control characters and the line separators str.splitlines() splits on (U+0085, U+2028,
    # U+2029) would break the record's line when the file is read back.
    if any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in text):
        raise Stop(2, "bad_request", "A note is one line of plain text.")


def _check_set_rating(args: list[str]) -> None:
    if not 2 <= len(args) <= 3:
        raise Stop(2, "bad_request", USAGE)
    if args[1] not in LIGHTS:
        raise Stop(2, "bad_request", "The light is green, yellow, or red.")
    if len(args) == 3:
        _check_note(args[2])


def parse(argv: list[str]) -> tuple[dict, str, str, list[str]]:
    flags = {"dry_run": False, "no_render": False}
    rest = []
    for arg in argv:
        if arg == "--dry-run":
            flags["dry_run"] = True
        elif arg == "--no-render":
            flags["no_render"] = True
        else:
            rest.append(arg)
    if not rest:
        raise Stop(2, "bad_request", USAGE)
    action, args = rest[0], rest[1:]
    shapes = {"complete-task": (TASK_ID, 1), "drop-task": (TASK_ID, 1), "log-habit": (HABIT_ID, 1), "park-focus": (FOCUS_ID, 2),
              "rate-day": (DAY, None), "set-picks": (DAY, None), "stamp-review": (HABIT_ID, 1),
              "skip-suggestion": (DAY, None), "set-area": (RATING_KEY, None), "set-room": (RATING_KEY, None),
              "retire-anchor": (GROUND_ID, 1), "set-project": (PROJECT_ID, 2)}
    if action not in shapes:
        raise Stop(2, "bad_request", USAGE)
    pattern, count = shapes[action]
    if action == "rate-day":
        _check_rate_day(args)
    elif action == "set-picks":
        _check_set_picks(args)
    elif action == "skip-suggestion":
        _check_skip_suggestion(args)
    elif action in ("set-area", "set-room"):
        _check_set_rating(args)
    # A habit log may name its day as one more argument.
    elif len(args) != count and not (action == "log-habit" and len(args) == 2):
        raise Stop(2, "bad_request", USAGE)
    if not args or not pattern.fullmatch(args[0]):
        raise Stop(2, "bad_request", "That is not a valid date." if pattern is DAY else "That is not a valid id.")
    if action == "log-habit" and len(args) == 2 and not DAY.fullmatch(args[1]):
        raise Stop(2, "bad_request", "That is not a valid date.")
    if action == "park-focus" and args[1] not in ("on", "off"):
        raise Stop(2, "bad_request", "Park takes on or off.")
    if action == "set-project" and args[1] not in ("active", "parked"):
        raise Stop(2, "bad_request", "A project is switched to active or parked.")
    if pattern is DAY:
        try:
            date.fromisoformat(args[0])
        except ValueError:
            raise Stop(2, "bad_request", "That is not a valid date.") from None
    return flags, action, args[0], args[1:]


# ---------------------------------------------------------------- git

def run_bounded(argv: list[str], timeout: float, env: dict | None = None,
                check: bool = False) -> subprocess.CompletedProcess:
    """Run a program in a session of its own; on a timeout or any exception (SIGTERM
    included) stop it and everything it started, then re-raise.

    Its own session means a grandchild that holds the output pipes (a hook, a sleep
    in the validator) is stopped with it instead of keeping this script waiting.
    SIGTERM goes first so a git that is stopped mid-commit removes its index lock;
    whatever is left after the grace period gets SIGKILL.
    """
    global CURRENT_GROUP
    proc = subprocess.Popen(argv, cwd=REPO, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env, start_new_session=True)
    CURRENT_GROUP = proc.pid
    try:
        out, err = proc.communicate(timeout=timeout)
    except BaseException:
        _signal_group(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=STOP_GRACE_SECONDS)
        except Exception:
            pass
        _signal_group(proc.pid, signal.SIGKILL)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        raise
    finally:
        CURRENT_GROUP = None
    if check and proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, argv, out, err)
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)


def _signal_group(pgid: int, sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def git(*args: str, env: dict | None = None, timeout: float = GIT_TIMEOUT_SECONDS, check: bool = True):
    return run_bounded(["git", *args], timeout, env=env, check=check)


def check_branch() -> None:
    # Mid-rebase, HEAD is detached; say so instead of "no branch", and never abort a
    # rebase that is someone else's work in progress.
    if repo_sync.rebase_in_progress(_sync_runner(), REPO):
        raise Stop(3, "rebase_in_progress",
                   "A git rebase is in progress in the repo; finish or abort it, then try again.")
    proc = git("symbolic-ref", "--short", "-q", "HEAD", check=False)
    branch = proc.stdout.strip()
    if proc.returncode != 0 or not branch:
        raise Stop(3, "wrong_branch", "The repo has no branch checked out.")
    if branch != WRITE_BRANCH:
        raise Stop(3, "wrong_branch", f"The repo is on branch {branch}, not {WRITE_BRANCH}; nothing was changed.")


NO_PRECOMMIT_HOOK = "The repo's pre-commit hook is not installed; see docs/install/web-ui.md."


def check_precommit_hook() -> None:
    """The writer leaves validation to the pre-commit hook (it runs scripts/validate.sh,
    the only place some rules live, such as the active-pursuit cap). Without the hook
    a commit would skip them, so no hook means no write."""
    proc = git("rev-parse", "--git-path", "hooks/pre-commit", check=False)
    rel = proc.stdout.strip()
    hook = (REPO / rel) if rel else None
    if proc.returncode != 0 or hook is None or not hook.is_file() or not os.access(hook, os.X_OK):
        raise Stop(3, "no_precommit_hook", NO_PRECOMMIT_HOOK)


def clear_stale_locks(since: float) -> None:
    """Remove the lock files a git commit stopped mid-way leaves behind, so the restore
    can run. Only locks made after `since` (this run's start) are this run's; an older
    one belongs to someone else and stays."""
    git_dir = Path(git("rev-parse", "--absolute-git-dir").stdout.strip())
    for lock in [git_dir / "index.lock", *git_dir.glob("next-index-*.lock")]:
        try:
            if lock.stat().st_mtime >= since:
                lock.unlink()
                sys.stderr.write(f"[web_write] removed {lock.name} left by the stopped commit\n")
        except FileNotFoundError:
            pass


def restore(files: list[_NdjsonFile]) -> None:
    """Put each file back the way HEAD has it. A file that did not exist before goes away."""
    tracked = [f.rel for f in files if f.existed]
    if tracked:
        git("checkout", "HEAD", "--", *tracked)
    for f in files:
        if not f.existed:
            git("rm", "--cached", "-q", "--ignore-unmatch", "--", f.rel, check=False)
            f.path.unlink(missing_ok=True)


def first_failure(output: str) -> str:
    """The pre-commit validator's first failure line, or its last line when it names none.

    Failures are printed as `  ✗ <what>`; the last line only says validation failed.
    """
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    found = next((line.lstrip("✗").strip() for line in lines if line.startswith("✗")), None)
    # The page shows this line, and the page uses no em or en dashes.
    return (found or (lines[-1] if lines else "The validator failed.")).replace(" — ", ": ").replace("—", "-").replace("–", "-")


def head_sha() -> str:
    return git("rev-parse", "HEAD").stdout.strip()


def commit(subject: str, paths: list[str], written: list, started: float) -> None:
    """Commit only `paths`. The pre-commit hook validates; when it refuses or the
    commit runs past its time, put the files back and raise Stop(4)."""
    # The render runs after the push, detached, so the hook must not run it here.
    env = {**os.environ, "PFC_SKIP_TRELLO_RENDER": "1"}
    # Paths after `--` make this an --only commit: anything else already staged
    # stays staged and out of this commit.
    argv = ["commit", "-q", "-m", subject, "-m", BODY, "-m", TRAILER, "--", *paths]
    try:
        proc = git(*argv, env=env, timeout=COMMIT_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        clear_stale_locks(started)
        restore(written)
        raise Stop(4, "invalid",
                   f"The commit and its validator did not finish in {COMMIT_TIMEOUT_SECONDS:g} seconds.") from None
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        clear_stale_locks(started)
        restore(written)
        # git sends a hook's output to stderr, so the failure lines are there.
        raise Stop(4, "invalid", first_failure(proc.stderr + "\n" + proc.stdout))


NO_GH = "gh is not on PATH; cannot read the push token."


def _askpass_script(user: str, gh: str) -> str:
    """A one-shot GIT_ASKPASS helper: the user name, then the token read from the gh
    keyring at the moment git asks. The token is never written anywhere."""
    return ("#!/bin/sh\n"
            "case \"$1\" in\n"
            f"  Username*) printf '%s\\n' {shlex.quote(user)} ;;\n"
            f"  Password*) exec {shlex.quote(gh)} auth token --user {shlex.quote(user)} ;;\n"
            "esac\n")


@contextlib.contextmanager
def network_git():
    """The environment and leading git arguments for every call that reaches origin
    (the sync's fetch or pull, and the push), as `(env, prefix)`.

    With PFC_PUSH_GH_USER set, git's credential helpers are turned off and a temporary
    askpass helper hands git that gh account's token, so the calls do not depend on
    which gh account is active. When that is asked for but gh is not on PATH, yields
    `(None, None)` and the caller reports it."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    user = os.environ.get("PFC_PUSH_GH_USER", "").strip()
    if not user:
        yield env, ()
        return
    gh = shutil.which("gh", path=env.get("PATH"))
    if not gh:
        yield None, None
        return
    fd, helper = tempfile.mkstemp(prefix="pfc-askpass-")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(_askpass_script(user, gh))
        os.chmod(helper, 0o700)
        env["GIT_ASKPASS"] = helper
        yield env, ("-c", "credential.helper=")
    finally:
        try:
            os.unlink(helper)
        except OSError:
            pass


def _sync_runner(env: dict | None = None, prefix: tuple[str, ...] = ()):
    """What repo_sync drives: each git call bounded like a push, never raising on a
    non-zero exit (the sync reads the exit code)."""
    def run(*args: str) -> subprocess.CompletedProcess:
        return git(*prefix, *args, env=env, timeout=PUSH_TIMEOUT_SECONDS, check=False)
    return run


def sync(env: dict, prefix: tuple[str, ...]) -> tuple[bool, str]:
    global SYNCING
    SYNCING = True
    try:
        return repo_sync.sync_with_upstream(_sync_runner(env, prefix), REPO)
    finally:
        SYNCING = False


def sync_before_write() -> None:
    """Level with origin so the change edits the newest copy of each file. A failure
    goes to stderr and the write goes on with the copy it has; if origin still has
    something this clone lacks at push time, the sync there reports it."""
    with network_git() as (env, prefix):
        if env is None:
            return
        ok, detail = sync(env, prefix)
    if not ok:
        sys.stderr.write(f"[web_write] sync before write: {detail}\n")


def push() -> tuple[bool, str | None]:
    """Level with origin, then push the write branch. A sync that cannot complete (a
    conflict with what the other clone pushed, uncommitted edits in the way, no
    network) keeps the commit local and is reported as the push error."""
    with network_git() as (env, prefix):
        if env is None:
            return False, NO_GH
        ok, detail = sync(env, prefix)
        if not ok:
            return False, f"Not pushed: {detail}"
        if prefix:
            return _run_push((*prefix, "push", "origin", WRITE_BRANCH), env)
        return _run_push(("push",), env)


def _run_push(args: tuple[str, ...], env: dict) -> tuple[bool, str | None]:
    try:
        proc = git(*args, env=env, timeout=PUSH_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        return False, f"git push timed out after {PUSH_TIMEOUT_SECONDS} seconds."
    if proc.returncode == 0:
        return True, None
    first = next((line.strip() for line in proc.stderr.splitlines() if line.strip()), "git push failed.")
    return False, first


def start_render() -> None:
    """Start the Trello render in its own session and do not wait for it.

    A failed render is written to the log and never reaches the page: the change is
    already committed, and the next render catches the board up.
    """
    argv = [sys.executable, str(RENDER)] if RENDER.suffix == ".py" else [str(RENDER)]
    try:
        with open(WEB_LOG, "a") as log:
            log.write(f"[pfc-write] starting Trello render: {RENDER.name}\n")
            log.flush()
            subprocess.Popen(argv, cwd=REPO, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             start_new_session=True)
    except OSError as err:
        sys.stderr.write(f"[web_write] could not start the Trello render: {err}\n")


# ---------------------------------------------------------------- main

def run(argv: list[str]) -> tuple[int, dict]:
    flags, action, record_id, extra = parse(argv)
    env = load_env()
    today = today_local(env)

    def plan() -> dict:
        if action == "complete-task":
            return plan_complete_task(record_id, today)
        if action == "drop-task":
            return plan_drop_task(record_id, today)
        if action == "log-habit":
            return plan_log_habit(record_id, today, extra[0] if extra else None)
        if action == "rate-day":
            opts = dict(e.split(":", 1) for e in extra[3:])
            hyper = {"yes": True, "no": False}.get(opts.get("hyper"))
            return plan_rate_day(record_id, int(extra[0]), int(extra[1]), int(extra[2]), hyper, today)
        if action == "set-picks":
            bonus = next((e[len("bonus:"):] for e in extra if e.startswith("bonus:")), None)
            return plan_set_picks(record_id, [e for e in extra if not e.startswith("bonus:")], bonus, today)
        if action == "stamp-review":
            return plan_stamp_review(record_id, today)
        if action == "skip-suggestion":
            return plan_skip_suggestion(record_id, extra[0], today)
        if action in ("set-area", "set-room"):
            note = extra[1][len(NOTE_PREFIX):] if len(extra) > 1 else None
            kind, rel = ("area", LIFE_WHEEL) if action == "set-area" else ("room", HOUSEHOLD)
            day, logged_at = now_local(env)
            return plan_set_rating(rel, kind, record_id, extra[0], note, day, logged_at)
        if action == "retire-anchor":
            return plan_retire_anchor(record_id, today)
        if action == "set-project":
            return plan_set_project(record_id, extra[0] == "active")
        return plan_park_focus(record_id, extra[0] == "on")

    base = {"action": action, "id": record_id}
    if not flags["dry_run"]:
        check_branch()
        check_precommit_hook()

    if flags["dry_run"]:
        result = plan()
        changed = [f for f in result["files"] if f.changed()]
        return 0, {"ok": True, "dry_run": True, **base, "title": result["title"],
                   "changed": bool(changed), "files": sorted(f.rel for f in changed),
                   "message": result["unchanged"] or f"Would commit: {result['subject']}",
                   "email_linked": result["email_linked"]}

    lock_path = REPO / LOCK
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop(3, "busy", "Another change is still being saved.") from None

        sync_before_write()
        result = plan()
        changed = [f for f in result["files"] if f.changed()]
        out = {"ok": True, **base, "title": result["title"], "email_linked": result["email_linked"],
               "commit": None, "pushed": False, "push_error": None}
        if not changed:
            return 0, {**out, "changed": False, "message": result["unchanged"] or "Nothing to change."}

        paths = sorted(f.rel for f in changed)
        # A skill's edit that is not committed yet would be swept into this commit, or
        # thrown away by a restore. Refuse rather than touch it.
        dirty = git("status", "--porcelain", "--", *paths).stdout.strip()
        if dirty:
            raise Stop(3, "dirty", "A file this change needs has edits that are not committed yet.")

        if not all(f.unchanged_on_disk() for f in changed):
            raise Stop(3, "changed_underneath", CHANGED_UNDERNEATH)
        global COMMITTED
        started = time.time()
        before = head_sha()
        written: list = []
        try:
            for f in changed:
                f.write()
                written.append(f)
            git("add", "--", *paths)
            commit(result["subject"], paths, written, started)
        except Stop:
            raise
        except ChangedUnderneath:
            restore(written)
            raise Stop(3, "changed_underneath", CHANGED_UNDERNEATH) from None
        except BaseException:
            # SIGTERM can land after git wrote the commit but before it returned.
            if _head_moved(before):
                COMMITTED = True
                SAVED.update({**out, "changed": True, "message": "Saved. Not pushed yet."})
            else:
                clear_stale_locks(started)
                restore(written)
            raise
        COMMITTED = True
        SAVED.update({**out, "changed": True, "message": "Saved. Not pushed yet."})

        SAVED["commit"] = git("rev-parse", "--short", "HEAD").stdout.strip()
        pushed, push_error = push()
        # The sync inside push() may have replayed the commit onto what origin had, so
        # the sha the page shows is read after it.
        SAVED["commit"] = git("rev-parse", "--short", "HEAD").stdout.strip()
        SAVED.update({"pushed": pushed, "push_error": push_error, "push_done": True,
                      "message": result["saved"] if pushed else "Saved. Not pushed yet."})
        if not flags["no_render"]:
            start_render()
        return 0, {k: v for k, v in SAVED.items() if k != "push_done"}


def _head_moved(before: str) -> bool:
    try:
        return head_sha() != before
    except BaseException:
        return False


def saved_after_sigterm() -> dict:
    """What a SIGTERM after the commit reports: the change is saved, the push is not."""
    payload = {k: v for k, v in SAVED.items() if k != "push_done"}
    if not payload.get("commit"):
        try:
            payload["commit"] = git("rev-parse", "--short", "HEAD").stdout.strip()
        except BaseException:
            payload["commit"] = None
    if not SAVED.get("push_done"):
        payload.update({"pushed": False, "push_error": PUSH_STOPPED, "message": "Saved. Not pushed yet."})
    return payload


def main(argv: list[str]) -> int:
    signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        code, payload = run(argv)
    except Terminated:
        sys.stderr.write("[web_write] stopped by SIGTERM\n")
        if SYNC_INTERRUPTED:
            # The signal landed inside this script's own pull --rebase; put the clone
            # back on its branch rather than leave a half-done rebase for the next write.
            try:
                if repo_sync.rebase_in_progress(_sync_runner(), REPO):
                    git("rebase", "--abort", timeout=10, check=False)
            except BaseException:
                pass
        if COMMITTED:
            # The change is saved; only the push is missing, and the next push sends it.
            code, payload = 0, saved_after_sigterm()
        else:
            code, payload = 1, {"ok": False, "reason": "stopped",
                                "error": "The change was stopped before it was saved."}
    except Stop as stop:
        code, payload = stop.code, {"ok": False, "reason": stop.reason, "error": stop.error}
    except subprocess.CalledProcessError as err:
        sys.stderr.write(f"[web_write] {' '.join(err.cmd)} failed ({err.returncode}):\n{err.stderr or ''}\n")
        code, payload = 1, {"ok": False, "reason": "error", "error": "The change could not be saved."}
    except Exception:
        traceback.print_exc()
        code, payload = 1, {"ok": False, "reason": "error", "error": "The change could not be saved."}
    print(json.dumps(payload, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
