#!/usr/bin/env python3
"""
Trello dashboard write-back: detect cards marked complete in interactive
lists, log/archive in repo, archive the Trello card.

Usage:
    python3 automations/scripts/trello_writeback.py [poll | sync | move-2plus1 | move-back-uncompleted]

Standalone CLI; the pfc-sync-trello skill orchestrates all subcommands.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from trello_helper import (
    list_lists, list_cards_on_board, update_card, archive_card, load_env,
)
from trello_render import (
    parse_pfc_frontmatter, INBOX_LIST_NAME,
)

REPO_ROOT = SCRIPT_DIR.parents[1]
LOCAL_TZ = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))

INTERACTIVE_LISTS = {"✅ 2+1", "✅ Actions", "☀️ Daily Habits", "🌙 Monthly Habits"}
TASK_LISTS = {"✅ 2+1", "✅ Actions"}
HABIT_DAILY_LIST = "☀️ Daily Habits"
HABIT_MONTHLY_LIST = "🌙 Monthly Habits"


def _today_mt() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")


def _this_month_mt() -> str:
    return datetime.now(LOCAL_TZ).strftime("%Y-%m")


def poll_completed_cards(api_key, token, board_id):
    """Return cards in interactive lists with dueComplete=true and a valid pfc-id.

    Each entry: {"pfc_id", "pfc_type", "list_name", "trello_card_id", "card_name"}.
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
        })
    return out


def _read_ndjson(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def _write_ndjson(path, records):
    p = Path(path)
    p.write_text("".join(json.dumps(r) + "\n" for r in records))


def _append_ndjson(path, record):
    p = Path(path)
    with p.open("a") as f:
        f.write(json.dumps(record) + "\n")


def complete_task_from_card(api_key, token, card, tasks_path=None, events_path=None, today=None):
    """Mark the task done in tasks.ndjson, log event, archive the Trello card.

    Returns:
      'completed' — task was open, now marked done; archive triggered.
      'already_done' — task was already done; archive triggered (cleans up Trello state).
      'unknown' — task id not found in tasks.ndjson; no changes; no archive.
    """
    tasks_path = tasks_path or REPO_ROOT / "5-actions/_data/tasks.ndjson"
    events_path = events_path or REPO_ROOT / "5-actions/_data/task_events.ndjson"
    today = today or _today_mt()

    tasks = _read_ndjson(tasks_path)
    task_idx = next((i for i, t in enumerate(tasks) if t.get("id") == card["pfc_id"]), None)
    if task_idx is None:
        return "unknown"

    task = tasks[task_idx]
    if task.get("status") == "done":
        archive_card(api_key, token, card["trello_card_id"])
        return "already_done"

    # Update in place
    task["status"] = "done"
    task["completed"] = today
    tasks[task_idx] = task
    _write_ndjson(tasks_path, tasks)

    # Log event
    _append_ndjson(events_path, {
        "task_id": card["pfc_id"],
        "event": "completed",
        "timestamp": today,
        "source": "trello",
    })

    archive_card(api_key, token, card["trello_card_id"])
    return "completed"


def log_habit_from_card(api_key, token, card, daily_path=None, monthly_path=None, today=None):
    """Log a habit completion from a Trello card. Daily and monthly handled differently.

    Returns 'logged' or 'already_logged'. Card is NOT archived — habits cycle on next render.
    """
    daily_path = daily_path or REPO_ROOT / "6-habits/_data/habits-daily.ndjson"
    monthly_path = monthly_path or REPO_ROOT / "6-habits/_data/habits-monthly.ndjson"
    today = today or _today_mt()

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
    # Idempotency: same habit + same date already logged?
    for r in existing:
        if r.get("habit_id") == habit_id and r.get("date") == today and r.get("completed"):
            return "already_logged"

    _append_ndjson(log_path, {
        "habit_id": habit_id,
        "date": today,
        "completed": True,
        "source": "trello",
    })
    return "logged"


def move_2plus1_from_actions(api_key, token, board_id, focus_task_ids):
    """Move cards with given pfc_ids from ✅ Actions to ✅ 2+1. Returns count moved."""
    if not focus_task_ids:
        return 0
    target_ids = set(focus_task_ids)
    lists = list_lists(api_key, token, board_id, filter_="open")
    list_id_to_name = {l["id"]: l["name"] for l in lists}
    name_to_id = {v: k for k, v in list_id_to_name.items()}
    if "✅ 2+1" not in name_to_id or "✅ Actions" not in name_to_id:
        return 0

    twoplus1_id = name_to_id["✅ 2+1"]
    actions_id = name_to_id["✅ Actions"]

    raw_cards = list_cards_on_board(api_key, token, board_id, filter_="open")
    moved = 0
    for c in raw_cards:
        if c.get("idList") != actions_id:
            continue
        fm = parse_pfc_frontmatter(c.get("desc", ""))
        if fm["pfc-id"] in target_ids:
            update_card(api_key, token, c["id"], idList=twoplus1_id)
            moved += 1
    return moved


def move_back_uncompleted(api_key, token, board_id):
    """At evening, move any card still in ✅ 2+1 (and not completed) back to ✅ Actions. Returns count."""
    lists = list_lists(api_key, token, board_id, filter_="open")
    list_id_to_name = {l["id"]: l["name"] for l in lists}
    name_to_id = {v: k for k, v in list_id_to_name.items()}
    if "✅ 2+1" not in name_to_id or "✅ Actions" not in name_to_id:
        return 0
    twoplus1_id = name_to_id["✅ 2+1"]
    actions_id = name_to_id["✅ Actions"]

    raw_cards = list_cards_on_board(api_key, token, board_id, filter_="open")
    moved = 0
    for c in raw_cards:
        if c.get("idList") != twoplus1_id:
            continue
        if c.get("dueComplete"):
            continue
        update_card(api_key, token, c["id"], idList=actions_id)
        moved += 1
    return moved


def sync_completed(api_key, token, board_id):
    """Poll completed cards and dispatch each to the right handler. Returns counters."""
    completed = poll_completed_cards(api_key, token, board_id)
    counters = {"tasks_completed": 0, "tasks_already_done": 0, "tasks_unknown": 0,
                "habits_logged": 0, "habits_already_logged": 0, "skipped": 0}
    for c in completed:
        if c["list_name"] in TASK_LISTS:
            r = complete_task_from_card(api_key, token, c)
            if r == "completed":
                counters["tasks_completed"] += 1
            elif r == "already_done":
                counters["tasks_already_done"] += 1
            elif r == "unknown":
                counters["tasks_unknown"] += 1
        elif c["list_name"] in {HABIT_DAILY_LIST, HABIT_MONTHLY_LIST}:
            r = log_habit_from_card(api_key, token, c)
            if r == "logged":
                counters["habits_logged"] += 1
            elif r == "already_logged":
                counters["habits_already_logged"] += 1
        else:
            counters["skipped"] += 1
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
        print("Usage: trello_writeback.py {poll | sync | move-2plus1 <task-id>... | move-back-uncompleted}", file=sys.stderr)
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

    if cmd == "move-2plus1":
        focus_ids = argv[1:]
        moved = move_2plus1_from_actions(KEY, TOK, BOARD, focus_ids)
        print(f"Moved {moved} cards Actions → ✅ 2+1")
        return 0

    if cmd == "move-back-uncompleted":
        moved = move_back_uncompleted(KEY, TOK, BOARD)
        print(f"Moved {moved} cards ✅ 2+1 → Actions")
        return 0

    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
