#!/usr/bin/env python3
"""The agent's replies on the reMarkable pages: what happened to what was written there.

Every page carries a small "Agent" strip in its top-right corner: what the sync saved
from that page, how many notes it sent to the inbox, what the unattended inbox job did
with each note sent from it (when PFC_TRELLO_INBOX is on), and any question a headless
review run asked. You answer a question by writing anywhere on the page; that note
reaches the Trello inbox with the page's recent replies in the card's description, so
the agent reading it knows what it answers. See docs/remarkable.md § "Agent replies".

Store: data/.remarkable/replies.ndjson, one {at, page, text} per line (local state,
git-ignored). Writers: remarkable_sync.py (saves, review questions) and
scripts/trello-inbox-auto.sh (`remarkable_replies.py from-inbox` on its output).
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
STORE = SCRIPT_DIR.parents[1] / "data" / ".remarkable" / "replies.ndjson"
TZ = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))
PAGES = ["0 - Inbox", "1 - Today", "2 - This quarter", "3 - Always", "4 - Review", "5 - Tasks"]
KEEP_HOURS = 36


def page_of(label):
    """'Today', '1 - Today' or '5 - Tasks, page 2' → the page's name; None if unknown."""
    label = (label or "").split(",")[0].strip().lower()
    for name in PAGES:
        if label in (name.lower(), name.split(" - ", 1)[1].lower()):
            return name
    return None


def add(page, text, store=STORE, now=None):
    page = page_of(page) or page
    now = now or datetime.now(TZ)
    store = Path(store)
    store.parent.mkdir(parents=True, exist_ok=True)
    with open(store, "a") as f:
        f.write(json.dumps({"at": now.isoformat(timespec="minutes"), "page": page, "text": text.strip()},
                           ensure_ascii=False) + "\n")


def recent(page, store=STORE, now=None, limit=4):
    """The page's replies from the last KEEP_HOURS hours, newest first."""
    now = now or datetime.now(TZ)
    store = Path(store)
    if not store.exists():
        return []
    out = []
    for line in store.read_text().splitlines():
        try:
            r = json.loads(line)
            at = datetime.fromisoformat(r["at"])
        except (ValueError, KeyError):
            continue
        if r.get("page") == page and now - at <= timedelta(hours=KEEP_HOURS):
            out.append(r)
    return list(reversed(out))[:limit]


def stamp(r):
    at = datetime.fromisoformat(r["at"])
    return at.strftime("%a %I:%M %p").replace(" 0", " ")


QROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")


def questions(text):
    """Rows of an open-questions table (`| # | Question | Default |`) in a run's output."""
    return [(int(m.group(1)), m.group(2), m.group(3)) for line in (text or "").splitlines()
            if (m := QROW.match(line.strip()))]


# The page a note came from, as remarkable_sync.py tags it ("From the Today page: …").
FROM = re.compile(r"^(?:\*\*)?From the (.+?) page(?: \([^)]*\))?:\s*(.*)$")

# One per-card line of `/pfc-trello-inbox unattended`: `🟢 <title> → <action>` or
# `🟡 <title> → left (❓ …)`.
LINE = re.compile(r"^\s*(?:-\s*)?(🟢|🟡)\s*\"?(.+?)\"?\s*→\s*(.+)$")


def from_inbox(output, store=STORE, now=None):
    """The inbox job's per-card lines as replies on the page each note came from
    (0 - Inbox when it names none). Returns how many were saved."""
    n = 0
    for line in (output or "").splitlines():
        m = LINE.match(line)
        if not m:
            continue
        mark, title, action = m.groups()
        title = title.strip("*\" ")
        f = FROM.match(title)
        page = page_of(f.group(1)) if f else None
        note = f.group(2) if f else title
        short = note if len(note) <= 60 else note[:57] + "..."
        text = f"\"{short}\" → {action.strip()}" if mark == "🟢" else f"Waiting: \"{short}\" → {action.strip()}"
        add(page or "0 - Inbox", text, store, now)
        n += 1
    return n


def main(argv):
    if argv[:1] == ["from-inbox"]:
        print(f"{from_inbox(sys.stdin.read())} replies saved")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
