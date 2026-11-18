#!/usr/bin/env python3
"""
Trello dashboard write-back: detect cards marked complete in interactive
lists, log/archive in repo, archive the Trello card.

Usage:
    python3 automations/scripts/trello_writeback.py [poll | sync]

Standalone CLI; the pfc-sync-trello skill and the daily sync job run `sync`.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from trello_helper import (
    list_lists, list_cards_on_board, update_card, archive_card, load_env,
    list_board_actions, get_card,
)
from trello_render import (
    parse_pfc_frontmatter, INBOX_LIST_NAME, BODY_LIST, HABITS_LIST, PICKS_LIST, TASKS_LIST,
    RATE_PREFIX, rating_answers,
)
import ndjson_file
from pfc_writes import complete_task, drop_pick, log_habit, rate_day, set_picks

REPO_ROOT = SCRIPT_DIR.parents[1]
LOCAL_TZ = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))

# The lists whose cards the user ticks. Within them only task and habit cards are acted on;
# the read-only cards around the picks (Why, What needs you) are skipped.
INTERACTIVE_LISTS = {PICKS_LIST, TASKS_LIST, HABITS_LIST}
HABIT_TYPES = {"habit-daily", "habit-monthly"}


def _today_mt() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")


def _local_date_from_iso(iso) -> "str | None":
    """Convert a Trello UTC timestamp (`dateCompleted`) to a local-timezone date.

    Everything in the repo is dated in local time, but Trello stamps UTC. A card
    checked at 11:56 PM local lands on the *next* UTC day, so converting is what
    keeps the log on the day the thing was actually done.

    Returns None when the timestamp is absent or unparseable so callers fall back
    to sync-time today.
    """
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(LOCAL_TZ).strftime("%Y-%m-%d")


def _this_month_mt() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m")


def poll_completed_cards(api_key, token, board_id):
    """Return cards in interactive lists with dueComplete=true and a valid pfc-id.

    Each entry: {"pfc_id", "pfc_type", "list_name", "trello_card_id", "card_name",
    "date_completed"}. `date_completed` is Trello's UTC check timestamp; handlers
    convert it to a local date so a late-night check is not dated to the next day.
    """
    lists = list_lists(api_key, token, board_id, filter_="open")
    list_id_to_name = {l["id"]: l["name"] for l in lists}
    raw_cards = list_cards_on_board(api_key, token, board_id, filter_="open")
    out = []
    for c in raw_cards:
        if not c.get("dueComplete"):
            continue
        list_name = list_id_to_name.get(c.get("idList"))
        if list_name not in INTERACTIVE_LISTS:
            continue
        if list_name == INBOX_LIST_NAME:
            continue
        fm = parse_pfc_frontmatter(c.get("desc", ""))
        if not fm["pfc-id"]:
            continue
        out.append({
            "pfc_id": fm["pfc-id"],
            "pfc_type": fm["pfc-type"],
            "list_name": list_name,
            "trello_card_id": c["id"],
            "card_name": c.get("name", ""),
            "date_completed": c.get("dateCompleted"),
        })
    return out


def _read_ndjson(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def _write_ndjson(path, records):
    """Line-preserving, atomic rewrite: an unchanged record keeps its exact bytes."""
    ndjson_file.rewrite(path, records)


def _append_ndjson(path, record):
    ndjson_file.append(path, record)


def complete_task_from_card(api_key, token, card, tasks_path=None, events_path=None, log_date=None,
                            focus_path=None):
    """Mark the task done in tasks.ndjson, log event, tick the 2+1, archive the Trello card.

    The completion date comes from *when the card was checked*, not when this sync
    runs; see `log_habit_from_card` for why. The same date picks the daily-focus
    record: a 2+1 task checked last night ticks last night's record.

    Returns:
      'completed' — task was open, now marked done; archive triggered.
      'already_done' — task was already done; archive triggered (cleans up Trello state).
      'unknown' — task id not found in tasks.ndjson; no changes; no archive.
    """
    tasks_path = tasks_path or REPO_ROOT / "6-tasks/_data/tasks.ndjson"
    events_path = events_path or REPO_ROOT / "6-tasks/_data/task_events.ndjson"
    focus_path = focus_path or REPO_ROOT / "6-tasks/_data/daily-focus.ndjson"
    log_date = log_date or _local_date_from_iso(card.get("date_completed")) or _today_mt()

    tasks = _read_ndjson(tasks_path)
    focus = _read_ndjson(focus_path)
    # New event rows only: the events file is appended to, never rewritten.
    new_events = []
    status, info = complete_task(tasks, new_events, focus, card["pfc_id"], log_date, "trello",
                                 focus_date=log_date)
    if status == "unknown":
        return "unknown"

    if status == "completed":
        _write_ndjson(tasks_path, tasks)
        for event in new_events:
            _append_ndjson(events_path, event)
        if info["focus_updated"]:
            _write_ndjson(focus_path, focus)

    archive_card(api_key, token, card["trello_card_id"])
    return status


def log_habit_from_card(api_key, token, card, daily_path=None, monthly_path=None, log_date=None):
    """Log a habit completion from a Trello card. Daily and monthly handled differently.

    The log is dated from *when the card was checked*, not when this sync runs. Dating
    from sync time corrupts the record whenever the two straddle local midnight: the
    render checks a card the moment the habit is logged for that day, and the midnight
    rollover render is what unchecks it. Any writeback that fires in between — the git
    post-commit hook, for instance, which renders *with* writeback — would otherwise
    read yesterday's still-checked card as a fresh completion and stamp it today.

    Returns 'logged', 'updated', or 'already_logged'. 'updated' means the day already
    had a missed or skipped row, now marked done in place. Card is NOT archived:
    habits cycle on next render.
    """
    daily_path = daily_path or REPO_ROOT / "7-habits/_data/habits-daily.ndjson"
    monthly_path = monthly_path or REPO_ROOT / "7-habits/_data/habits-monthly.ndjson"
    log_date = log_date or _local_date_from_iso(card.get("date_completed")) or _today_mt()

    pfc_id = card["pfc_id"]
    if pfc_id.startswith("habit-daily-"):
        habit_id = pfc_id[len("habit-daily-"):]
        log_path = daily_path
    elif pfc_id.startswith("habit-monthly-"):
        habit_id = pfc_id[len("habit-monthly-"):]
        log_path = monthly_path
    else:
        return "unknown"

    existing = _read_ndjson(log_path)
    # One row per habit and date. A new row is appended; a missed row changed in
    # place means the file is rewritten.
    status = log_habit(existing, habit_id, log_date, "trello")
    if status == "logged":
        _append_ndjson(log_path, existing[-1])
    elif status == "updated":
        _write_ndjson(log_path, existing)
    return status


class GitCommitter:
    """Commits the one data file a new sync step just wrote, then pushes.

    The rating card, a dropped pick and the auto-pick write wherever the sync runs:
    the morning daily sync job, a server timer, a render after a web write. A change left
    uncommitted there blocks the web writer (it refuses a dirty file) and stops the
    VPS clone's fast-forward, so each of these steps commits its own file, by path,
    and pushes the way the daily sync does (web_write.push). It writes only when the
    clone is on the write branch and that file has no uncommitted edits of someone
    else's; otherwise the step waits for a later run.
    """

    def __init__(self, repo=None):
        self.repo = Path(repo or REPO_ROOT)

    def _git(self, *args):
        env = {**os.environ, "PFC_SKIP_TRELLO_RENDER": "1"}
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, timeout=90, env=env)

    def ready(self, path) -> bool:
        branch = self._git("symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
        if branch != os.environ.get("PFC_WRITE_BRANCH", "main"):
            return False
        return self._git("status", "--porcelain", "--", str(path)).stdout.strip() == ""

    def commit(self, path, message) -> None:
        self._git("add", "--", str(path))
        done = self._git("commit", "-q", "-m", message, "-m", "Written by the Trello sync.", "--", str(path))
        if done.returncode != 0:
            print(f"   🟡 commit refused ({(done.stderr or done.stdout).strip()[:200]}); restoring {path}",
                  file=sys.stderr)
            self._git("checkout", "HEAD", "--", str(path))
            return
        try:
            import web_write
            ok, detail = web_write.push()
            if not ok:
                print(f"   🟡 committed, not pushed yet: {detail}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 — the commit stands; the next writer pushes it
            print(f"   🟡 committed, not pushed yet: {exc}", file=sys.stderr)


def sync_rating(api_key, token, board_id, today=None, days_path=None, committer=None):
    """Save the day rated on the rating card in 🦸 Body first, once each of its three lists
    has exactly one tick.

    The day comes from the card's id (`rate-day-<date>`), and only today or yesterday
    is saved, the same two days the web's rate-day accepts. The rating itself is
    pfc_writes.rate_day, the web's writer: rating derived from the three,
    hyperfocused left unasked. Nothing is written for a
    card with a list unticked ('waiting') or a list ticked twice ('ambiguous'; the
    render says which on the card), nor for a day already rated.

    Returns 'added' | 'updated' | 'already_rated' | 'waiting' | 'ambiguous' |
    'out_of_window' | 'no_card'.
    """
    days_path = days_path or REPO_ROOT / "data/day-tracking.ndjson"
    today = today or _today_mt()
    yesterday = (datetime.fromisoformat(today) - timedelta(days=1)).strftime("%Y-%m-%d")

    list_ids = {l["id"] for l in list_lists(api_key, token, board_id, filter_="open")
                if l["name"] == BODY_LIST}
    raw = list_cards_on_board(api_key, token, board_id, filter_="open", include_checklists=True)
    card = None
    for c in raw:
        if c.get("idList") not in list_ids:
            continue
        fm = parse_pfc_frontmatter(c.get("desc", ""))
        if fm["pfc-type"] == "rate-day" and (fm["pfc-id"] or "").startswith(RATE_PREFIX):
            card = (fm["pfc-id"][len(RATE_PREFIX):], c)
            break
    if card is None:
        return "no_card"
    day, c = card
    if day not in (today, yesterday):
        return "out_of_window"
    lists = {}
    for cl in c.get("checklists") or []:
        items = sorted(cl.get("checkItems") or [], key=lambda x: x.get("pos", 0))
        lists.setdefault(cl.get("name"), [(it.get("name"), it.get("state") == "complete") for it in items])
    answers = rating_answers(lists)
    if answers["ambiguous"]:
        return "ambiguous"
    if not answers["complete"]:
        return "waiting"
    v = answers["values"]
    committer = committer or GitCommitter()
    if not committer.ready(days_path):
        return "not_ready"
    days = _read_ndjson(days_path)
    status = rate_day(days, day, v["Energy"], v["Mood"], v["Focus"], None)
    if status == "added":
        _append_ndjson(days_path, days[-1])
    elif status == "updated":
        _write_ndjson(days_path, days)
    if status in ("added", "updated"):
        committer.commit(days_path, f"track: log day {day}")
    return status


TWO_PLUS_ONE_LIST = PICKS_LIST


def _local_midnight_utc(today: str) -> str:
    """Local midnight of `today`, as a UTC ISO timestamp (Trello's `since`)."""
    start = datetime.fromisoformat(today).replace(tzinfo=LOCAL_TZ)
    return start.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def sync_dropped_picks(api_key, token, board_id, today=None, focus_path=None, tasks_path=None, committer=None):
    """Archiving a ✅ The 2+1 card in Trello drops that pick from today's 2+1; the task
    stays open in the backlog (pfc_writes.drop_pick).

    Read from the board's archive actions since local midnight. Only an archive a
    person made in a Trello client counts: those carry no `appCreator`, while every
    archive made through the API (the render, this sync, --rebuild, --reset-list)
    carries one with authType `appKeyToken`, so the board's own clean-up is never read
    as a drop. Only an open task that is still an undone pick today is dropped.
    Returns the dropped task ids.
    """
    focus_path = focus_path or REPO_ROOT / "6-tasks/_data/daily-focus.ndjson"
    tasks_path = tasks_path or REPO_ROOT / "6-tasks/_data/tasks.ndjson"
    today = today or _today_mt()
    actions = list_board_actions(api_key, token, board_id, "updateCard:closed",
                                 since=_local_midnight_utc(today))
    card_ids = []
    for a in actions or []:
        data = a.get("data") or {}
        if a.get("appCreator"):
            continue
        if (data.get("list") or {}).get("name") != TWO_PLUS_ONE_LIST:
            continue
        if not (data.get("card") or {}).get("closed"):
            continue
        card_ids.append(data["card"]["id"])
    if not card_ids:
        return []
    committer = committer or GitCommitter()
    if not committer.ready(focus_path):
        return []
    open_ids = {t.get("id") for t in _read_ndjson(tasks_path) if t.get("status") == "open"}
    focus = _read_ndjson(focus_path)
    dropped = []
    for cid in dict.fromkeys(card_ids):
        pfc_id = parse_pfc_frontmatter(get_card(api_key, token, cid, fields="desc").get("desc", ""))["pfc-id"]
        if pfc_id in open_ids and drop_pick(focus, today, pfc_id) == "dropped":
            dropped.append(pfc_id)
    if dropped:
        _write_ndjson(focus_path, focus)
        committer.commit(focus_path, f"focus: set {today} (dropped on Trello)")
    return dropped


def auto_pick_today(now=None, focus_path=None, committer=None):
    """Set today's 2+1 from the home page's suggester when the user has set none
    (home_data.auto_picks), through pfc_writes.set_picks with `source: "auto"`.

    Idempotent: a record that already holds picks, the user's or the system's, is left
    alone, and so is a day trimmed on Trello. Nothing happens from the evening
    hour, when the suggestions card sets tomorrow. The change is committed and pushed
    (GitCommitter); off the write branch or with the file already dirty, nothing is
    written ('not_ready'). Returns 'picked' | 'kept' | 'evening' | 'not_ready'.
    """
    import home_data
    focus_path = focus_path or REPO_ROOT / "6-tasks/_data/daily-focus.ndjson"
    now = now or datetime.now(LOCAL_TZ).replace(tzinfo=None)
    if now.hour >= home_data.EVENING_HOUR:
        return "evening"
    today = now.date().isoformat()
    focus = _read_ndjson(focus_path)
    record = next((r for r in focus if r.get("date") == today), None)
    # Cheap check first: the suggester reads the whole repo, so it runs only on a day
    # that could still be picked.
    if home_data.auto_picks({"evening": False, "suggested": [{"id": "-"}]}, record) is None:
        return "kept"
    committer = committer or GitCommitter()
    if not committer.ready(focus_path):
        return "not_ready"
    plan = home_data.auto_picks(home_data.build_home({}, now), record)
    if plan is None:
        return "kept"
    critical, bonus = plan
    set_picks(focus, today, critical, bonus, source="auto")
    _write_ndjson(focus_path, focus)
    committer.commit(focus_path, f"focus: set {today} (auto-pick)")
    return "picked"


def sync_completed(api_key, token, board_id):
    """Poll completed cards and dispatch each to the right handler. Returns counters."""
    completed = poll_completed_cards(api_key, token, board_id)
    counters = {"tasks_completed": 0, "tasks_already_done": 0, "tasks_unknown": 0,
                "habits_logged": 0, "habits_already_logged": 0, "skipped": 0}
    for c in completed:
        if c["pfc_type"] == "task":
            r = complete_task_from_card(api_key, token, c)
            if r == "completed":
                counters["tasks_completed"] += 1
            elif r == "already_done":
                counters["tasks_already_done"] += 1
            elif r == "unknown":
                counters["tasks_unknown"] += 1
        elif c["pfc_type"] in HABIT_TYPES:
            r = log_habit_from_card(api_key, token, c)
            # A missed row marked done is a write too, so the board renders after it.
            if r in ("logged", "updated"):
                counters["habits_logged"] += 1
            elif r == "already_logged":
                counters["habits_already_logged"] += 1
        else:
            counters["skipped"] += 1
    # Each step below is fail-safe: the completions above are already saved.
    try:
        counters["picks_dropped"] = len(sync_dropped_picks(api_key, token, board_id))
    except Exception as exc:  # noqa: BLE001
        print(f"   🟡 dropped-pick sync failed: {exc}", file=sys.stderr)
        counters["picks_dropped"] = 0
    try:
        rated = sync_rating(api_key, token, board_id)
    except Exception as exc:  # noqa: BLE001
        print(f"   🟡 day rating sync failed: {exc}", file=sys.stderr)
        rated = None
    counters["days_rated"] = 1 if rated in ("added", "updated") else 0
    try:
        counters["picks_auto_set"] = 1 if auto_pick_today() == "picked" else 0
    except Exception as exc:  # noqa: BLE001
        print(f"   🟡 auto-pick failed: {exc}", file=sys.stderr)
        counters["picks_auto_set"] = 0
    # When this machine last pulled Trello into the repo: the 🤖 Brief card's last line.
    try:
        (REPO_ROOT / "data" / ".trello-last-sync").write_text(datetime.now(LOCAL_TZ).isoformat())
    except OSError:
        pass
    return counters


def main(argv):
    env = load_env()
    KEY = env.get("TRELLO_API_KEY") or os.environ.get("TRELLO_API_KEY")
    TOK = env.get("TRELLO_API_TOKEN") or os.environ.get("TRELLO_API_TOKEN")
    BOARD = env.get("TRELLO_DASHBOARD_BOARD_ID") or os.environ.get("TRELLO_DASHBOARD_BOARD_ID")

    if not (KEY and TOK and BOARD):
        print("Missing TRELLO env vars. See .env.example.", file=sys.stderr)
        return 1

    if not argv:
        print("Usage: trello_writeback.py {poll | sync}", file=sys.stderr)
        return 1

    cmd = argv[0]
    if cmd == "poll":
        completed = poll_completed_cards(KEY, TOK, BOARD)
        for c in completed:
            print(json.dumps(c))
        return 0

    if cmd == "sync":
        counters = sync_completed(KEY, TOK, BOARD)
        print(json.dumps(counters, indent=2))
        return 0

    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
