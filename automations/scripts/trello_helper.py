#!/usr/bin/env python3
"""
Trello helper. Subcommands: list, delete.

Auth via env vars: TRELLO_API_KEY, TRELLO_API_TOKEN, TRELLO_INBOX_LIST_ID.

Usage:
    python3 automations/scripts/trello_helper.py list
    python3 automations/scripts/trello_helper.py delete <card_id>

list:    GET inbox cards -> JSONL of {id, name} on stdout, exit 0.
delete:  DELETE card by id -> exit 0 on 200 or 404 (already gone), 1 otherwise.

Errors and HTTP failures go to stderr with exit code 1.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = "https://api.trello.com/1"
TIMEOUT_SECONDS = 15

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_env():
    """Load .env into a dict. Stdlib-only. Matches google_health_fetch.py shape."""
    env = {}
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def _resolve_env():
    """Merge .env values with os.environ. os.environ wins."""
    env = load_env()
    env.update({k: v for k, v in os.environ.items() if v})
    return env


def _request(url, method="GET"):
    """Make HTTP request with retry on 429 (one-shot) and URLError (3x backoff)."""
    rate_limited_retried = False
    backoffs = [1, 2, 4]
    network_retry_idx = 0
    while True:
        try:
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                return json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            if e.code == 429 and not rate_limited_retried:
                rate_limited_retried = True
                time.sleep(10)
                continue
            raise
        except urllib.error.URLError:
            if network_retry_idx < len(backoffs):
                time.sleep(backoffs[network_retry_idx])
                network_retry_idx += 1
                continue
            raise


def list_cards(api_key, token, list_id):
    """Return list of {id, name} for cards in the inbox list."""
    qs = urllib.parse.urlencode({"fields": "name", "key": api_key, "token": token})
    url = f"{API_BASE}/lists/{list_id}/cards?{qs}"
    return _request(url, method="GET")


def delete_card(api_key, token, card_id):
    """Delete a card. Returns True on 200 or 404, raises on other errors."""
    qs = urllib.parse.urlencode({"key": api_key, "token": token})
    url = f"{API_BASE}/cards/{card_id}?{qs}"
    try:
        _request(url, method="DELETE")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return True
        raise


def list_boards(api_key, token, fields="name"):
    """Return all boards visible to this token."""
    qs = urllib.parse.urlencode({"fields": fields, "key": api_key, "token": token})
    return _request(f"{API_BASE}/members/me/boards?{qs}", "GET")


def list_lists(api_key, token, board_id, filter_="open", fields="name,closed,pos"):
    """Return lists on a board. filter_ is 'open', 'closed', or 'all'."""
    qs = urllib.parse.urlencode({
        "filter": filter_, "fields": fields, "key": api_key, "token": token
    })
    return _request(f"{API_BASE}/boards/{board_id}/lists?{qs}", "GET")


def list_cards_on_board(api_key, token, board_id, filter_="open", include_checklists=False):
    """Return every card on a board across all lists. filter_ matches Trello's filter param.
    If include_checklists is True, each card record also has a 'checklists' array (Trello
    side-loads them via the checklists=all parameter)."""
    params = {
        "filter": filter_,
        "fields": "name,idList,desc,due,dueComplete,closed,idLabels",
        "key": api_key, "token": token,
    }
    if include_checklists:
        params["checklists"] = "all"
        params["checklist_fields"] = "name"
    qs = urllib.parse.urlencode(params)
    return _request(f"{API_BASE}/boards/{board_id}/cards?{qs}", "GET")


def create_card(api_key, token, list_id, name, desc=None, id_labels=None):
    """Create a new card on a list. id_labels is a list of label ids (optional)."""
    params = {"idList": list_id, "name": name, "key": api_key, "token": token}
    if desc is not None:
        params["desc"] = desc
    if id_labels:
        params["idLabels"] = ",".join(id_labels)
    qs = urllib.parse.urlencode(params)
    return _request(f"{API_BASE}/cards?{qs}", "POST")


def update_card(api_key, token, card_id, **fields):
    """Update one or more card fields. Supported: name, desc, idList, idLabels (list),
    dueComplete, closed."""
    params = {"key": api_key, "token": token}
    for k, v in fields.items():
        if k == "idLabels" and isinstance(v, list):
            params["idLabels"] = ",".join(v)
        elif k in ("dueComplete", "closed"):
            params[k] = "true" if v else "false"
        elif v is not None:
            params[k] = v
    qs = urllib.parse.urlencode(params)
    return _request(f"{API_BASE}/cards/{card_id}?{qs}", "PUT")


def archive_card(api_key, token, card_id):
    """Archive a card (closed=true). Distinct from delete_card which is permanent."""
    return update_card(api_key, token, card_id, closed=True)


def create_list(api_key, token, board_id, name, pos="bottom"):
    """Create a new list on a board. pos is 'top', 'bottom', or a numeric position."""
    params = {"idBoard": board_id, "name": name, "pos": pos, "key": api_key, "token": token}
    qs = urllib.parse.urlencode(params)
    return _request(f"{API_BASE}/lists?{qs}", "POST")


def archive_list(api_key, token, list_id):
    """Archive a list (closed=true). Reversible via PUT closed=false."""
    qs = urllib.parse.urlencode({"value": "true", "key": api_key, "token": token})
    return _request(f"{API_BASE}/lists/{list_id}/closed?{qs}", "PUT")


def list_labels(api_key, token, board_id):
    """Return all labels on a board."""
    qs = urllib.parse.urlencode({"key": api_key, "token": token})
    return _request(f"{API_BASE}/boards/{board_id}/labels?{qs}", "GET")


def create_label(api_key, token, board_id, name, color):
    """Create a label on a board. color is one of Trello's named colors:
    yellow, purple, blue, red, green, orange, black, sky, pink, lime, or null for no color."""
    params = {"idBoard": board_id, "name": name, "color": color, "key": api_key, "token": token}
    qs = urllib.parse.urlencode(params)
    return _request(f"{API_BASE}/labels?{qs}", "POST")


# ── Checklists ────────────────────────────────────────────────────────────────

def list_checklists(api_key, token, card_id):
    """Return all checklists on a card."""
    qs = urllib.parse.urlencode({"key": api_key, "token": token})
    return _request(f"{API_BASE}/cards/{card_id}/checklists?{qs}", "GET")


def create_checklist(api_key, token, card_id, name):
    """Create a checklist on a card. Returns the new checklist record."""
    qs = urllib.parse.urlencode({"idCard": card_id, "name": name, "key": api_key, "token": token})
    return _request(f"{API_BASE}/checklists?{qs}", "POST")


def delete_checklist(api_key, token, checklist_id):
    """Permanently delete a checklist."""
    qs = urllib.parse.urlencode({"key": api_key, "token": token})
    return _request(f"{API_BASE}/checklists/{checklist_id}?{qs}", "DELETE")


def add_checkitem(api_key, token, checklist_id, name, checked=False):
    """Add an item to a checklist. checked=True creates it already complete."""
    params = {
        "name": name,
        "checked": "true" if checked else "false",
        "key": api_key, "token": token,
    }
    qs = urllib.parse.urlencode(params)
    return _request(f"{API_BASE}/checklists/{checklist_id}/checkItems?{qs}", "POST")


def update_checkitem(api_key, token, card_id, checkitem_id, state):
    """Update checkitem state. state is 'complete' or 'incomplete'.
    Note: Trello requires this to go through the *card*, not the checklist."""
    qs = urllib.parse.urlencode({"state": state, "key": api_key, "token": token})
    return _request(f"{API_BASE}/cards/{card_id}/checkItem/{checkitem_id}?{qs}", "PUT")


def delete_checkitem(api_key, token, checklist_id, checkitem_id):
    """Permanently remove a checkitem from a checklist."""
    qs = urllib.parse.urlencode({"key": api_key, "token": token})
    return _request(f"{API_BASE}/checklists/{checklist_id}/checkItems/{checkitem_id}?{qs}", "DELETE")


def _need_env(env):
    missing = [k for k in ("TRELLO_API_KEY", "TRELLO_API_TOKEN", "TRELLO_INBOX_LIST_ID")
               if not env.get(k)]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}. See .env.example.",
              file=sys.stderr)
        return False
    return True


def main(argv):
    env = _resolve_env()
    if not argv:
        print("Usage: trello_helper.py {list | delete <card_id>}", file=sys.stderr)
        return 1

    cmd = argv[0]
    if cmd == "list":
        if not _need_env(env):
            return 1
        try:
            cards = list_cards(
                env["TRELLO_API_KEY"],
                env["TRELLO_API_TOKEN"],
                env["TRELLO_INBOX_LIST_ID"],
            )
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print("Trello credentials invalid (401).", file=sys.stderr)
            else:
                print(f"Trello list failed: HTTP {e.code}", file=sys.stderr)
            return 1
        except urllib.error.URLError as e:
            print(f"Trello list failed: network error: {e.reason}", file=sys.stderr)
            return 1
        for card in cards:
            print(json.dumps({"id": card["id"], "name": card["name"]}))
        return 0

    if cmd == "delete":
        if len(argv) < 2:
            print("Usage: trello_helper.py delete <card_id>", file=sys.stderr)
            return 1
        if not _need_env(env):
            return 1
        card_id = argv[1]
        try:
            delete_card(
                env["TRELLO_API_KEY"],
                env["TRELLO_API_TOKEN"],
                card_id,
            )
            return 0
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print("Trello credentials invalid (401).", file=sys.stderr)
            else:
                print(f"Trello delete failed: HTTP {e.code}", file=sys.stderr)
            return 1
        except urllib.error.URLError as e:
            print(f"Trello delete failed: network error: {e.reason}", file=sys.stderr)
            return 1

    if cmd == "boards":
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            boards = list_boards(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"])
        except urllib.error.HTTPError as e:
            print(f"Trello boards failed: HTTP {e.code}", file=sys.stderr); return 1
        except urllib.error.URLError as e:
            print(f"Trello boards failed: {e.reason}", file=sys.stderr); return 1
        for b in boards:
            print(json.dumps({"id": b["id"], "name": b.get("name")}))
        return 0

    if cmd == "lists":
        if len(argv) < 2:
            print("Usage: trello_helper.py lists <board_id>", file=sys.stderr); return 1
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            lists = list_lists(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], argv[1])
        except urllib.error.HTTPError as e:
            print(f"Trello lists failed: HTTP {e.code}", file=sys.stderr); return 1
        for l in lists:
            print(json.dumps({"id": l["id"], "name": l.get("name"), "pos": l.get("pos"), "closed": l.get("closed")}))
        return 0

    if cmd == "cards-on-board":
        if len(argv) < 2:
            print("Usage: trello_helper.py cards-on-board <board_id> [--filter open|closed|all]", file=sys.stderr); return 1
        board_id = argv[1]
        filter_ = "open"
        if "--filter" in argv:
            i = argv.index("--filter")
            if i + 1 < len(argv): filter_ = argv[i+1]
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            cards = list_cards_on_board(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], board_id, filter_)
        except urllib.error.HTTPError as e:
            print(f"Trello cards-on-board failed: HTTP {e.code}", file=sys.stderr); return 1
        for c in cards:
            print(json.dumps(c))
        return 0

    if cmd == "card-create":
        # card-create <list_id> --name "..." [--desc "..."] [--idLabels "id1,id2"]
        if len(argv) < 4 or "--name" not in argv:
            print("Usage: trello_helper.py card-create <list_id> --name <n> [--desc D] [--idLabels A,B]", file=sys.stderr); return 1
        list_id = argv[1]
        def _arg(flag):
            if flag in argv:
                i = argv.index(flag)
                if i+1 < len(argv): return argv[i+1]
            return None
        name = _arg("--name")
        desc = _arg("--desc")
        labels_csv = _arg("--idLabels")
        id_labels = labels_csv.split(",") if labels_csv else None
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            card = create_card(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], list_id, name=name, desc=desc, id_labels=id_labels)
        except urllib.error.HTTPError as e:
            print(f"card-create failed: HTTP {e.code}", file=sys.stderr); return 1
        print(json.dumps({"id": card["id"], "name": card.get("name")}))
        return 0

    if cmd == "card-update":
        # card-update <card_id> [--name N --desc D --idList L --idLabels A,B --dueComplete true|false]
        if len(argv) < 2:
            print("Usage: trello_helper.py card-update <card_id> [--name --desc --idList --idLabels --dueComplete]", file=sys.stderr); return 1
        card_id = argv[1]
        env = _resolve_env()
        if not _need_env(env): return 1
        kwargs = {}
        for flag, key in [("--name","name"), ("--desc","desc"), ("--idList","idList"), ("--idLabels","idLabels")]:
            if flag in argv:
                i = argv.index(flag)
                if i+1 < len(argv):
                    val = argv[i+1]
                    kwargs[key] = val.split(",") if key == "idLabels" else val
        if "--dueComplete" in argv:
            i = argv.index("--dueComplete")
            if i+1 < len(argv):
                kwargs["dueComplete"] = (argv[i+1].lower() == "true")
        if not kwargs:
            print("card-update requires at least one field flag", file=sys.stderr); return 1
        try:
            card = update_card(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], card_id, **kwargs)
        except urllib.error.HTTPError as e:
            print(f"card-update failed: HTTP {e.code}", file=sys.stderr); return 1
        print(json.dumps({"id": card["id"]}))
        return 0

    if cmd == "card-archive":
        if len(argv) < 2:
            print("Usage: trello_helper.py card-archive <card_id>", file=sys.stderr); return 1
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            archive_card(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], argv[1])
        except urllib.error.HTTPError as e:
            print(f"card-archive failed: HTTP {e.code}", file=sys.stderr); return 1
        return 0

    if cmd == "list-create":
        if len(argv) < 4 or "--name" not in argv:
            print("Usage: trello_helper.py list-create <board_id> --name <n> [--pos POS]", file=sys.stderr); return 1
        board_id = argv[1]
        i = argv.index("--name"); name = argv[i+1] if i+1 < len(argv) else None
        pos = "bottom"
        if "--pos" in argv:
            j = argv.index("--pos"); pos = argv[j+1] if j+1 < len(argv) else "bottom"
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            lst = create_list(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], board_id, name=name, pos=pos)
        except urllib.error.HTTPError as e:
            print(f"list-create failed: HTTP {e.code}", file=sys.stderr); return 1
        print(json.dumps({"id": lst["id"], "name": lst.get("name")}))
        return 0

    if cmd == "list-archive":
        if len(argv) < 2:
            print("Usage: trello_helper.py list-archive <list_id>", file=sys.stderr); return 1
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            archive_list(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], argv[1])
        except urllib.error.HTTPError as e:
            print(f"list-archive failed: HTTP {e.code}", file=sys.stderr); return 1
        return 0

    if cmd == "labels":
        if len(argv) < 2:
            print("Usage: trello_helper.py labels <board_id>", file=sys.stderr); return 1
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            labels = list_labels(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], argv[1])
        except urllib.error.HTTPError as e:
            print(f"labels failed: HTTP {e.code}", file=sys.stderr); return 1
        for l in labels:
            print(json.dumps({"id": l["id"], "name": l.get("name"), "color": l.get("color")}))
        return 0

    if cmd == "label-create":
        if len(argv) < 6 or "--name" not in argv or "--color" not in argv:
            print("Usage: trello_helper.py label-create <board_id> --name <n> --color <c>", file=sys.stderr); return 1
        board_id = argv[1]
        i = argv.index("--name"); name = argv[i+1]
        j = argv.index("--color"); color = argv[j+1]
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            lab = create_label(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], board_id, name=name, color=color)
        except urllib.error.HTTPError as e:
            print(f"label-create failed: HTTP {e.code}", file=sys.stderr); return 1
        print(json.dumps({"id": lab["id"], "name": lab.get("name"), "color": lab.get("color")}))
        return 0

    if cmd == "checklists":
        if len(argv) < 2:
            print("Usage: trello_helper.py checklists <card_id>", file=sys.stderr); return 1
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            cls = list_checklists(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], argv[1])
        except urllib.error.HTTPError as e:
            print(f"checklists failed: HTTP {e.code}", file=sys.stderr); return 1
        for c in cls:
            print(json.dumps({"id": c["id"], "name": c.get("name"), "items": len(c.get("checkItems", []))}))
        return 0

    if cmd == "checklist-create":
        if len(argv) < 4 or "--name" not in argv:
            print("Usage: trello_helper.py checklist-create <card_id> --name <n>", file=sys.stderr); return 1
        i = argv.index("--name"); name = argv[i+1]
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            cl = create_checklist(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], argv[1], name)
        except urllib.error.HTTPError as e:
            print(f"checklist-create failed: HTTP {e.code}", file=sys.stderr); return 1
        print(json.dumps({"id": cl["id"]}))
        return 0

    if cmd == "checklist-delete":
        if len(argv) < 2:
            print("Usage: trello_helper.py checklist-delete <checklist_id>", file=sys.stderr); return 1
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            delete_checklist(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], argv[1])
        except urllib.error.HTTPError as e:
            print(f"checklist-delete failed: HTTP {e.code}", file=sys.stderr); return 1
        return 0

    if cmd == "checkitem-add":
        if len(argv) < 4 or "--name" not in argv:
            print("Usage: trello_helper.py checkitem-add <checklist_id> --name <n> [--checked]", file=sys.stderr); return 1
        i = argv.index("--name"); name = argv[i+1]
        checked = "--checked" in argv
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            it = add_checkitem(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], argv[1], name, checked=checked)
        except urllib.error.HTTPError as e:
            print(f"checkitem-add failed: HTTP {e.code}", file=sys.stderr); return 1
        print(json.dumps({"id": it["id"]}))
        return 0

    if cmd == "checkitem-update":
        if len(argv) < 5 or "--state" not in argv:
            print("Usage: trello_helper.py checkitem-update <card_id> <checkitem_id> --state complete|incomplete", file=sys.stderr); return 1
        i = argv.index("--state"); state = argv[i+1]
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            it = update_checkitem(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], argv[1], argv[2], state)
        except urllib.error.HTTPError as e:
            print(f"checkitem-update failed: HTTP {e.code}", file=sys.stderr); return 1
        print(json.dumps({"id": it["id"], "state": it.get("state")}))
        return 0

    if cmd == "checkitem-delete":
        if len(argv) < 3:
            print("Usage: trello_helper.py checkitem-delete <checklist_id> <checkitem_id>", file=sys.stderr); return 1
        env = _resolve_env()
        if not _need_env(env): return 1
        try:
            delete_checkitem(env["TRELLO_API_KEY"], env["TRELLO_API_TOKEN"], argv[1], argv[2])
        except urllib.error.HTTPError as e:
            print(f"checkitem-delete failed: HTTP {e.code}", file=sys.stderr); return 1
        return 0

    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
