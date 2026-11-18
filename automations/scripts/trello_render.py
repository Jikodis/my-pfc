#!/usr/bin/env python3
"""
Trello dashboard render — diff repo state against board state, apply minimum changes.

Usage:
    python3 automations/scripts/trello_render.py [--rebuild] [--reset-list <name>]

Reads TRELLO_DASHBOARD_BOARD_ID from .env. Loads PFC repo state, computes
desired card set, fetches current card set, applies diff (creates/updates/archives).

The Inbox list (📥 Inbox) is never touched — owned by pfc-trello-inbox.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

REPO_ROOT = SCRIPT_DIR.parents[1]


# ── Frontmatter ───────────────────────────────────────────────────────────────

FRONTMATTER_DELIM = "---"


def parse_pfc_frontmatter(desc: str) -> dict:
    """Extract pfc-id, pfc-type, and body from a card description.

    Returns dict with keys 'pfc-id', 'pfc-type', 'body'. If frontmatter is
    missing or malformed, pfc-id and pfc-type are None and body is the
    full original string.
    """
    if not desc:
        return {"pfc-id": None, "pfc-type": None, "body": ""}

    lines = desc.split("\n")
    if len(lines) < 3 or lines[0] != FRONTMATTER_DELIM:
        return {"pfc-id": None, "pfc-type": None, "body": desc}

    # Find closing delimiter
    closing_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line == FRONTMATTER_DELIM:
            closing_idx = i
            break

    if closing_idx is None:
        return {"pfc-id": None, "pfc-type": None, "body": desc}

    fm_lines = lines[1:closing_idx]
    fields = {}
    for line in fm_lines:
        if ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip()

    pfc_id = fields.get("pfc-id")
    pfc_type = fields.get("pfc-type")

    if not pfc_id:
        return {"pfc-id": None, "pfc-type": None, "body": desc}

    # Body is everything after the closing delim, minus one optional blank line
    body_lines = lines[closing_idx + 1:]
    if body_lines and body_lines[0] == "":
        body_lines = body_lines[1:]
    body = "\n".join(body_lines)

    return {"pfc-id": pfc_id, "pfc-type": pfc_type, "body": body}


def serialize_pfc_frontmatter(pfc_id: str, pfc_type: str, body: str) -> str:
    """Build a card description with frontmatter prefix."""
    return f"{FRONTMATTER_DELIM}\npfc-id: {pfc_id}\npfc-type: {pfc_type}\n{FRONTMATTER_DELIM}\n\n{body}"


# ── Card dataclass ────────────────────────────────────────────────────────────

@dataclass
class Card:
    """Render-target representation of a card. Compared by all fields for diff.

    `due_complete` is tri-state:
      - True  → repo asserts the card is complete; render should force the check on Trello.
      - False → repo asserts the card is not complete; render should force the check off.
      - None  → user-owned; render must NOT touch the dueComplete field. Used for
               interactive cards (tasks, focus, habits) where the user manipulates
               the checkbox from the widget before sync has ingested the action.
    """
    pfc_id: str
    pfc_type: str
    list_name: str
    name: str
    body: str
    label_names: list = field(default_factory=list)
    due: Optional[str] = None
    due_complete: Optional[bool] = None
    # Optional checklist for Project cards: list of (name, checked) pairs
    checklist: Optional[list] = None
    # Position in its list (Trello `pos`). None leaves the card wherever it is; a
    # number is set on create and enforced on update, so a red-first order holds
    # after a light changes, not only on a fresh render.
    pos: Optional[float] = None
    # Checklists created once, with the card, and never touched again: the ticks are
    # the user's (the rating card in 🦸 Body first). [(checklist name, [item names])].
    seed_checklists: Optional[list] = None
    # Read back from the board by fetch_current_state: {checklist name: [(item, checked)]}.
    # Never compared; the render reads it to word a card's body (annotate_rate_card).
    checklist_state: Optional[dict] = None


# ── Diff engine ───────────────────────────────────────────────────────────────

def _cards_equal(a: Card, b: Card) -> bool:
    """Compare on the fields the render manages. Excludes pfc_id (key) and pfc_type (immutable).

    `due_complete` uses None as a wildcard: if either side is None, the field is
    considered equal (the renderer is not asserting a desired value).
    """
    due_complete_match = (
        a.due_complete is None
        or b.due_complete is None
        or a.due_complete == b.due_complete
    )
    return (
        a.list_name == b.list_name and
        a.name == b.name and
        a.body == b.body and
        sorted(a.label_names) == sorted(b.label_names) and
        a.due == b.due and
        due_complete_match and
        (a.pos is None or b.pos is None or a.pos == b.pos) and
        (a.checklist or []) == (b.checklist or [])
    )


def compute_diff(desired, current):
    """
    Compute create/update/archive operations.

    desired: list[Card] — what we want the board to look like.
    current: list[tuple[Card, str]] — (card, trello_card_id) pairs from current board state.

    Cards in current with pfc_id=None (user-added without frontmatter) are archived.

    Returns dict:
      {"creates": [Card],
       "updates": [{"card_id": str, "desired": Card, "current": Card}],
       "archives": [str]}
    """
    desired_by_id = {c.pfc_id: c for c in desired}
    current_by_id = {}
    archives = []

    for card, tcid in current:
        if card.pfc_id is None:
            archives.append(tcid)
        else:
            current_by_id[card.pfc_id] = (card, tcid)

    creates = []
    updates = []

    for pfc_id, desired_card in desired_by_id.items():
        if pfc_id not in current_by_id:
            creates.append(desired_card)
        else:
            current_card, tcid = current_by_id[pfc_id]
            if not _cards_equal(desired_card, current_card):
                updates.append({"card_id": tcid, "desired": desired_card, "current": current_card})

    for pfc_id, (current_card, tcid) in current_by_id.items():
        if pfc_id not in desired_by_id:
            archives.append(tcid)

    return {"creates": creates, "updates": updates, "archives": archives}


# ── Reconciliation ────────────────────────────────────────────────────────────

# Import the helper functions we depend on.
from trello_helper import (
    list_lists, create_list, update_list,
    list_labels, create_label,
    list_cards_on_board,
    create_card, update_card, archive_card,
    list_checklists, create_checklist, delete_checklist,
    add_checkitem, update_checkitem, delete_checkitem,
    load_env,
)


# 9 impact×urgency tiers collapse to 5 priority colors. The 9-tier distinction
# stays visible in card titles ("AA (M) - desc"); the label is just the 5-bucket
# priority severity. Labels are plain (unnamed) Trello labels — color-only.
# Tasks a browser agent can run start to finish get 🤖 in the title, so the
# hand-off batch is visible at a glance on the phone. Only "yes" is marked —
# "partly" and "no" carry nothing, because a second marker would need a legend
# and a legend that lives off-screen is no help on the phone.
AGENT_MARK = " 🤖"


def _agent_mark(task) -> str:
    return AGENT_MARK if task.get("agent_doable") == "yes" else ""


TIER_PRIORITY_COLOR = {
    "AA": "red",
    "AB": "orange", "BA": "orange",
    "AC": "yellow", "BB": "yellow", "CA": "yellow",
    "BC": "green",  "CB": "green",
    "CC": "purple",
}
# Order chosen so emoji codepoints sort red → orange → yellow → green → purple
# in Trello's "Sort by card name". Avoid ⚫ (U+26AB) or ⬛ (U+2B1B) — both sort
# BEFORE 🔴 (U+1F534) and broke the Tasks list ordering.
PRIORITY_COLORS = ("red", "orange", "yellow", "green", "purple")


# ── The board's lists ─────────────────────────────────────────────────────────
#
# The board follows the web home page (`web/src/pages/index.astro`): 📥 Inbox, then
# the Today group (Body first, The 2+1, Habits, Week), This quarter (Focuses,
# Projects, Trends), Always (Areas with the household folded in, Values, Visions,
# Front of mind), then the web's other page, Tasks. Every render
# puts the lists in this order right after 📥 Inbox.

INBOX_LIST_NAME = "📥 Inbox"
BODY_LIST = "🦸 Body first"
PICKS_LIST = "✅ The 2+1"
HABITS_LIST = "☀️ Habits"
WEEK_LIST = "🗓️ Week"
FOCUS_LIST = "🎯 Focuses"
PROJECTS_LIST = "🛠️ Projects"
TRENDS_LIST = "📈 Trends"
AREAS_LIST = "🧭 Areas"
VALUES_LIST = "💎 Values"
VISIONS_LIST = "🔭 Visions"
ANCHORS_LIST = "🧠 Front of mind"
TASKS_LIST = "✅ Tasks"

ALL_LIST_NAMES = [
    BODY_LIST, PICKS_LIST, HABITS_LIST, WEEK_LIST,
    FOCUS_LIST, PROJECTS_LIST, TRENDS_LIST,
    AREAS_LIST, VALUES_LIST, VISIONS_LIST, ANCHORS_LIST,
    TASKS_LIST,
]
LIST_POS_STEP = 65536


def ensure_lists(api_key, token, board_id, list_names):
    """Ensure each name in list_names exists, in that order, right after 📥 Inbox.
    Returns {name: list_id}. A missing list is created in its place; when the order
    is off, each list is moved into place. Lists the render does not name stay put."""
    lists = list_lists(api_key, token, board_id, filter_="open")
    existing = {l["name"]: l for l in lists}
    inbox = existing.get(INBOX_LIST_NAME)
    base = (inbox.get("pos") or 0) if inbox else 0
    ours = [existing.get(n) for n in list_names]
    positions = [l.get("pos") for l in ours if l is not None]
    in_order = (None not in ours and None not in positions
                and all(a < b for a, b in zip([base] + positions, positions)))
    result = {}
    for i, name in enumerate(list_names):
        pos = base + (i + 1) * LIST_POS_STEP
        if name not in existing:
            result[name] = create_list(api_key, token, board_id, name, pos=pos)["id"]
            continue
        result[name] = existing[name]["id"]
        if not in_order and existing[name].get("pos") != pos:
            update_list(api_key, token, existing[name]["id"], pos=pos)
    return result


# Life-wheel color buckets (score 1-10 → label color)
LIFEWHEEL_COLOR_BUCKETS = [
    ((1, 2), "red"),
    ((3, 4), "orange"),
    ((5, 6), "yellow"),
    ((7, 8), "lime"),
    ((9, 10), "green"),
]

VALID_TRELLO_COLORS = {
    "red", "orange", "yellow", "lime", "green",
    "pink", "sky", "purple", "blue", "black",
}


def _lifewheel_color(score):
    """Map a life-wheel score to a Trello color name.

    Two input shapes:
    - String color name (e.g. 'green', 'red', 'yellow') → use directly if valid.
    - Numeric 1-10 score → bucketed via LIFEWHEEL_COLOR_BUCKETS.
    Returns None if score is missing / invalid.
    """
    if score is None:
        return None
    if isinstance(score, str):
        s = score.strip().lower()
        return s if s in VALID_TRELLO_COLORS else None
    try:
        n = int(score)
    except (TypeError, ValueError):
        return None
    for (lo, hi), color in LIFEWHEEL_COLOR_BUCKETS:
        if lo <= n <= hi:
            return color
    return None


def ensure_plain_color_labels(api_key, token, board_id, colors):
    """Ensure an unnamed (name='') label exists for each color. Returns {color: label_id}.
    Distinct from named priority labels — this gives color-only labels the user can
    apply to cards without surfacing a name."""
    existing = list_labels(api_key, token, board_id)
    plain_by_color = {}
    for l in existing:
        if not (l.get("name") or "").strip():  # name is empty / None / whitespace
            color = l.get("color")
            if color and color not in plain_by_color:
                plain_by_color[color] = l["id"]
    result = {}
    for color in colors:
        if color in plain_by_color:
            result[color] = plain_by_color[color]
        else:
            new_label = create_label(api_key, token, board_id, "", color)
            result[color] = new_label["id"]
    return result


# ── Repo state loaders ────────────────────────────────────────────────────────

def _read_ndjson(path):
    p = REPO_ROOT / path
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def _safe_focus_status():
    """Derived focus rates, or [] if the computation fails. Never blocks a render."""
    try:
        # The web's own call (home_data.build_home uses status_rows too). It reads the
        # raw habit schema; _load_habit_schema's renamed shape left every focus unknown.
        from focus_status import status_rows
        return status_rows(REPO_ROOT, _today_mt())
    except Exception as exc:  # noqa: BLE001 — render must never hard-fail here
        print(f"   🟡 focus rates unavailable ({exc}) — cards render without them")
        return []


def _safe_home():
    """home_data.build_home for now, the dict the web page and TRMNL read, or None if it
    fails. Never blocks a render."""
    try:
        import home_data
        tz = _ZoneInfo(_os.environ.get("LOCAL_TZ", "America/Denver"))
        return home_data.build_home({}, _dt.datetime.now(tz).replace(tzinfo=None))
    except Exception as exc:  # noqa: BLE001 — render must never hard-fail here
        print(f"   🟡 web home data unavailable ({exc}) — the lists that mirror it are left as they are")
        return None


def load_repo_state():
    """Load all repo state needed by the renderers into a dict."""
    return {
        "values": (REPO_ROOT / "1-values" / "values.md").read_text() if (REPO_ROOT / "1-values" / "values.md").exists() else "",
        "areas": _load_areas(),
        "visions": _load_visions(),
        "projects": _read_ndjson("5-projects/_data/projects.ndjson"),
        "tasks": _read_ndjson("6-tasks/_data/tasks.ndjson"),
        "daily_focus": _read_ndjson("6-tasks/_data/daily-focus.ndjson"),
        "habits_daily": _read_ndjson("7-habits/_data/habits-daily.ndjson"),
        "habits_monthly": _read_ndjson("7-habits/_data/habits-monthly.ndjson"),
        "habit_schema": _load_habit_schema(),
        "life_wheel": _read_ndjson("2-areas/_data/life-wheel.ndjson"),
        # The web home page's data (home_data.build_home), the source of every list that
        # mirrors a web band (trello_home.py). None when it fails; those lists are then
        # left as they are on the board.
        "home": _safe_home(),
        "grounding": _read_ndjson("data/grounding.ndjson"),
        "focus": _read_ndjson("4-focus/_data/focus.ndjson"),
        # Derived focus lights + per-vehicle rates. Degrades to [] on failure
        # rather than killing the whole render.
        "focus_status": _safe_focus_status(),
        "day_tracking": _read_ndjson("data/day-tracking.ndjson"),
    }


def _load_areas():
    """Return list of {name, statement} from 2-areas/<area>/statement.md."""
    areas_root = REPO_ROOT / "2-areas"
    if not areas_root.exists():
        return []
    out = []
    for d in sorted(areas_root.iterdir()):
        if d.is_dir() and d.name != "_data":
            stmt_path = d / "statement.md"
            statement = stmt_path.read_text().strip() if stmt_path.exists() else ""
            out.append({"name": d.name, "statement": statement})
    return out


def _load_visions():
    """Return list of {slug, title, body} for real vision files in 3-visions/.

    A vision file is a per-vision markdown with YAML frontmatter (see
    3-visions/_template.md). Folder docs (README.md, AGENTS.md,
    vision-brainstorm.md) start with a `#` heading, not `---` frontmatter, so
    they are excluded — only frontmatter files render as visions. Without this
    guard every doc in the folder leaks onto the board as a vision card.
    Title comes from the first `# ` heading in the body.
    """
    visions_root = REPO_ROOT / "3-visions"
    if not visions_root.exists():
        return []
    out = []
    for f in sorted(visions_root.glob("*.md")):
        if f.name.lower() == "readme.md":
            continue
        if f.name.startswith("_"):
            continue
        text = f.read_text()
        # Only files with YAML frontmatter are real visions; docs start with `#`.
        if not text.lstrip().startswith("---"):
            continue
        title = _vision_title(text) or f.stem
        out.append({"slug": f.stem, "title": title, "body": text})
    return out


def _vision_title(text):
    """Extract a vision's display title: the first `# ` heading in the body
    (after frontmatter), falling back to the frontmatter `name:` field."""
    lines = text.split("\n")
    fm_name = None
    body_start = 0
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                body_start = i + 1
                break
            if line.startswith("name:"):
                fm_name = line.split(":", 1)[1].strip()
    for line in lines[body_start:]:
        if line.startswith("# "):
            return line.lstrip("# ").strip()
    return fm_name


def _load_habit_schema():
    """Return parsed habit_schema.yaml as a dict normalized to {daily: [...], monthly: [...]}."""
    p = REPO_ROOT / "config" / "habit_schema.yaml"
    if not p.exists():
        return {"daily": [], "monthly": []}
    text = p.read_text()
    try:
        import yaml
        raw = yaml.safe_load(text) or {}
    except ImportError:
        return {"daily": [], "monthly": []}
    # Normalize: schema uses daily_habits/monthly_habits with `description`.
    # Map to daily/monthly with `name` (description) for renderer compatibility.
    def _normalize(items):
        out = []
        for h in items or []:
            out.append({
                "id": h.get("id"),
                "name": h.get("description") or h.get("name") or h.get("id"),
                "short": h.get("short"),
                "frequency": h.get("frequency"),
                "area": h.get("area"),
                "active": h.get("active", True),
                "auto_derived": h.get("auto_derived", False),
            })
        return out
    return {
        "daily": _normalize(raw.get("daily_habits", [])),
        "monthly": _normalize(raw.get("monthly_habits", [])),
    }


# ── Renderers — repo-backed lists ─────────────────────────────────────────────

import datetime as _dt
import os as _os
from zoneinfo import ZoneInfo as _ZoneInfo


def _today_mt() -> str:
    """Return today's date in the local timezone as YYYY-MM-DD.

    Local timezone is read from $LOCAL_TZ (default America/Denver).
    """
    tz = _ZoneInfo(_os.environ.get("LOCAL_TZ", "America/Denver"))
    return _dt.datetime.now(tz).strftime("%Y-%m-%d")


def _deadline_to_due(deadline):
    """Convert YYYY-MM-DD deadline to Trello due ISO 8601 datetime (noon UTC)."""
    if not deadline:
        return None
    return f"{deadline}T12:00:00.000Z"


def render_values(repo_state) -> list:
    """Each numbered value in 1-values/values.md becomes a card."""
    text = repo_state.get("values", "")
    cards = []
    for line in text.splitlines():
        line = line.strip()
        # Match "1. Honesty", "2. Courage", etc.
        if line and line[0].isdigit() and ". " in line:
            rank, _, value = line.partition(". ")
            cards.append(Card(
                pfc_id=f"value-{rank}",
                pfc_type="value",
                list_name=VALUES_LIST,
                name=f"{rank}. {value}",
                body="",
                pos=(len(cards) + 1) * 1024,
            ))
    return cards


COLOR_EMOJI = {
    "red": "🔴", "orange": "🟠", "yellow": "🟡",
    "lime": "🟢", "green": "🟢",
    "sky": "🔵", "blue": "🔵",
    "purple": "🟣", "pink": "🟣",
    "black": "⚫",
}

# 5-level priority emoji for AA..CC tiers. Matches TIER_PRIORITY_COLOR so the
# emoji prefix visually agrees with the plain-color label on the card.
PRIORITY_TIER_EMOJI = {tier: COLOR_EMOJI.get(color, "") for tier, color in TIER_PRIORITY_COLOR.items()}


def _priority_plain_label(tier, plain_color_labels):
    color = TIER_PRIORITY_COLOR.get(tier)
    if color and color in plain_color_labels:
        return [f"_plain:{color}"]
    return []


def _task_priority_tier(t):
    impact = {"high": "A", "medium": "B", "low": "C"}.get(t.get("impact", "low"), "C")
    urgency = {"high": "A", "medium": "B", "low": "C"}.get(t.get("urgency", "low"), "C")
    return f"{impact}{urgency}"


def _task_card(t, list_name, plain_color_labels, project_name=None, pos=None):
    """One interactive task card: `🔴 AA (M) 🤖 - description`, plus ` · <project>`
    for a task in a project. Ticking it on the phone completes the task."""
    tier = _task_priority_tier(t)
    body_lines = [
        f"Impact: {t.get('impact')} · Urgency: {t.get('urgency')} · Size: {t.get('size')}",
        f"Area: {t.get('area', 'none')} · Project: {project_name or 'none'}",
    ]
    if t.get("deadline"):
        body_lines.append(f"Deadline: {t['deadline']}")
    if t.get("notes"):
        body_lines.append(f"Notes: {t['notes']}")
    size = t.get("size", "?")
    tier_emoji = PRIORITY_TIER_EMOJI.get(tier, "")
    # The emoji prefix makes priority visible on Android Trello widgets, which do
    # not render labels.
    head = f"{tier_emoji} {tier}" if tier_emoji else tier
    suffix = f" · {project_name}" if project_name else ""
    return Card(
        pfc_id=t["id"],
        pfc_type="task",
        list_name=list_name,
        name=f"{head} ({size}){_agent_mark(t)} - {t.get('description', '')}{suffix}"[:200],
        body="\n".join(body_lines),
        label_names=_priority_plain_label(tier, plain_color_labels),
        due=_deadline_to_due(t.get("deadline")),
        due_complete=None,
        pos=pos,
    )


def _project_names(repo_state, active_only=False):
    return {p["id"]: p.get("name", p["id"]) for p in repo_state.get("projects", [])
            if p.get("active") or not active_only}


def render_2plus1(repo_state, plain_color_labels=None) -> list:
    """Today's undone 2+1 picks, critical first, then the bonus. Source: today's
    daily-focus row + tasks.ndjson."""
    plain_color_labels = plain_color_labels or {}
    today = _today_mt()
    focus = next((r for r in repo_state.get("daily_focus", []) if r.get("date") == today), None)
    if not focus:
        return []
    tasks_by_id = {t["id"]: t for t in repo_state.get("tasks", [])}
    names = _project_names(repo_state)
    ids = []
    for slot in ("critical", "bonus", "project"):
        v = focus.get(slot)
        if isinstance(v, list):
            ids.extend(v)
        elif isinstance(v, str):
            ids.append(v)
    cards = []
    for tid in dict.fromkeys(ids):
        t = tasks_by_id.get(tid)
        if not t or t.get("status") == "done":
            continue
        cards.append(_task_card(t, PICKS_LIST, plain_color_labels, names.get(t.get("project"))))
    return cards


# Card order in ✅ Tasks: the web Tasks page's default sort (priority code, then file
# order), held by a position built from the code and the task id's date and number, so
# a new task does not shift every card below it.
_TIER_ORDER = [a + b for a in "ABC" for b in "ABC"]


def _task_pos(t):
    digits = "".join(ch for ch in t["id"] if ch.isdigit())[:11] or "0"
    tier = _task_priority_tier(t)
    rank = _TIER_ORDER.index(tier) if tier in _TIER_ORDER else len(_TIER_ORDER)
    return rank * 10 ** 11 + int(digits)


def render_tasks(repo_state, plain_color_labels=None, exclude_2plus1_ids=None) -> list:
    """✅ Tasks, the web Tasks page on the phone: every open task, standalone or in an
    active project, in priority order, except today's 2+1 picks (those sit in
    ✅ The 2+1). Deferred tasks and tasks of a parked or finished project stay off the
    board until they come back into rotation."""
    plain_color_labels = plain_color_labels or {}
    exclude = set(exclude_2plus1_ids or [])
    active = _project_names(repo_state, active_only=True)
    cards = []
    for t in repo_state.get("tasks", []):
        if t.get("status") != "open" or t.get("deferred") or t["id"] in exclude:
            continue
        project = t.get("project") or "none"
        if project != "none" and project not in active:
            continue
        cards.append(_task_card(t, TASKS_LIST, plain_color_labels, active.get(project), pos=_task_pos(t)))
    return cards


def daily_habit_counts(repo_state) -> list:
    """Each tappable daily habit with today's state and its past-7-days count:
    [{id, short, name, frequency, area, done_today, completed, target}].

    The count is the same trailing-7-day window and skip-adjusted target the ramp
    reads (`focus_status.habit_rate`), so the card and the habit's light agree.
    A habit the system measures itself (`auto_derived`, e.g. Fitbit sleep onset)
    is left out: a tap would write a manual row that outranks the measurement.
    """
    from focus_status import habit_rate
    today = _today_mt()
    week_start = (_dt.date.fromisoformat(today) - _dt.timedelta(days=6)).isoformat()
    schema = repo_state.get("habit_schema", {})
    daily = schema.get("daily", []) if isinstance(schema, dict) else []
    logs = repo_state.get("habits_daily", [])
    log_by_id = {r.get("habit_id"): r for r in logs if r.get("date") == today}
    out = []
    for h in daily:
        hid = h.get("id") or h.get("habit_id") or h.get("name")
        if not hid:
            continue
        if h.get("active") is False or h.get("auto_derived"):
            continue
        log = log_by_id.get(hid)
        freq = h.get("frequency") or 7
        r = habit_rate(logs, hid, week_start, today, freq, "daily")
        out.append({"id": hid, "short": h.get("short") or h.get("name", hid), "name": h.get("name", hid),
                    "frequency": freq, "area": h.get("area", ""),
                    "done_today": bool(log and log.get("completed") is True),
                    "completed": r["completed"], "target": r["target"]})
    return out


def render_daily_habits(repo_state) -> list:
    """One tappable card per daily habit, titled `<short name>: <done>/<target> past 7 days`
    (daily_habit_counts)."""
    return [Card(
        pfc_id=f"habit-daily-{h['id']}",
        pfc_type="habit-daily",
        list_name=HABITS_LIST,
        name=f"{h['short']}: {h['completed']}/{h['target']} past 7 days",
        body=f"{h['name']}\nFrequency: {h['frequency']}/week · Area: {h['area']}",
        # False (not None) so render actively unchecks at day rollover. Render runs writeback
        # first by default (see main()), so user widget-clicks get logged before they're wiped.
        due_complete=h["done_today"],
    ) for h in daily_habit_counts(repo_state)]


def render_monthly_habits(repo_state) -> list:
    today = _today_mt()
    month = today[:7]  # YYYY-MM
    schema = repo_state.get("habit_schema", {})
    monthly = schema.get("monthly", []) if isinstance(schema, dict) else []
    month_logs = [r for r in repo_state.get("habits_monthly", []) if r.get("month", "").startswith(month) or r.get("date", "").startswith(month)]
    count_by_id = {}
    logged_today = set()
    for r in month_logs:
        if r.get("completed") is True:
            hid = r.get("habit_id")
            count_by_id[hid] = count_by_id.get(hid, 0) + 1
            if r.get("date") == today:
                logged_today.add(hid)
    cards = []
    for h in monthly:
        hid = h.get("id") or h.get("habit_id") or h.get("name")
        if not hid:
            continue
        # Same rule as the daily cards: a habit the system derives (from the calendar,
        # say) gets no card, because a manual tick would outrank the measurement.
        if h.get("active") is False or h.get("auto_derived"):
            continue
        target = h.get("frequency", 1)
        count = count_by_id.get(hid, 0)
        cards.append(Card(
            pfc_id=f"habit-monthly-{hid}",
            pfc_type="habit-monthly",
            list_name=HABITS_LIST,
            name=f"{h.get('short') or h.get('name', hid)}: {count}/{target} this month",
            body=f"{h.get('name', hid)}\nTarget this month: {target} · Area: {h.get('area', '')}",
            # Per-day check: unchecks overnight like daily habits. Title still shows
            # month-to-date count/target. Each click logs one occurrence; a card that
            # stays checked across days does not re-log.
            due_complete=True if hid in logged_today else False,
        ))
    return cards


GROUNDING_CAP = 10  # soft cap on 🧠 Front of mind anchors; warn (never truncate) if exceeded


def render_grounding(repo_state) -> list:
    """🧠 Front of mind — a small, cycling set of grounding anchors to keep
    front-of-mind right now. Soft-capped: renders ALL active anchors but warns
    if the count exceeds GROUNDING_CAP (truncating would risk hiding something
    important — curation happens by retiring, not by silent cutoff)."""
    cards = []
    active = [g for g in repo_state.get("grounding", []) if g.get("status") == "active"]
    if len(active) > GROUNDING_CAP:
        print(f"   🟡 Front of mind has {len(active)} active topic cards (soft cap {GROUNDING_CAP}) — consider retiring some")
    for g in active:
        # One card per TOPIC: title is the card name, body holds the points.
        # `text` is a legacy single-line fallback for older records.
        title = g.get("title") or g.get("text") or ""
        body = g.get("body") or g.get("text") or ""
        cards.append(Card(
            pfc_id=g["id"],
            pfc_type="grounding",
            list_name=ANCHORS_LIST,
            name=title[:200],
            body=body,
        ))
    return cards


FOCUS_TIER_ORDER = [("foundation", "🧱"), ("pursuit", "🎯"), ("consuming", "🎧")]
FOCUS_STATUS_CIRCLE = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
FOCUS_PURSUIT_CAP = 6  # mirrors config/focus.yaml
FOCUS_PARKED_MARKER = "🅿️"
_FOCUS_LETTER = {"high": "A", "medium": "B", "low": "C"}


def _focus_code(f):
    return _FOCUS_LETTER.get(f.get("impact"), "C") + _FOCUS_LETTER.get(f.get("urgency"), "C")


def render_focus(repo_state) -> list:
    """🎯 Focuses — the capped, traffic-lit set of what's actively being
    pursued this quarter. Renders ALL active (non-retired) focuses grouped by
    tier (🧱 Foundations → 🎯 Active Pursuits → 🎧 Currently Consuming), sorted
    by impact/urgency code within each tier with red first as a tiebreak.

    Title leads with the two-letter code so an alphabetical sort in Trello
    surfaces the most important focuses first; the render's own order groups by
    tier so the list reads correctly either way. Body carries the landing plus
    every vehicle habit's trailing-28-day rate — the primary drives the light,
    but supporting vehicles must stay visible."""
    cards = []
    active = [f for f in repo_state.get("focus", []) if not f.get("retired_date")]

    # Parked focuses are a deliberate stop and do not occupy a pursuit slot.
    # Red now means "not happening" and DOES occupy one.
    pursuits = [f for f in active if f.get("tier") == "pursuit" and not f.get("parked")]
    if len(pursuits) > FOCUS_PURSUIT_CAP:
        print(f"   🟡 Focuses has {len(pursuits)} active pursuits "
              f"(hard cap {FOCUS_PURSUIT_CAP}) — park/retire one")

    rates = {r["focus_id"]: r for r in repo_state.get("focus_status", [])}
    red_first = {"red": 0, "yellow": 1, "green": 2, "parked": 3, "unknown": 4}

    def light(f):
        """The derived light (focus_status.compute, what the web Focuses band shows),
        else the stored one: the stored `status` is only rewritten by a --write run."""
        derived = (rates.get(f["id"]) or {}).get("status")
        return derived if derived in FOCUS_STATUS_CIRCLE else f.get("status", "green")

    for tier, tier_emoji in FOCUS_TIER_ORDER:
        tier_focuses = [x for x in active if x.get("tier") == tier]
        tier_focuses.sort(key=lambda f: (_focus_code(f), red_first.get(light(f), 9)))
        for f in tier_focuses:
            if f.get("parked"):
                marker = FOCUS_PARKED_MARKER
            else:
                marker = FOCUS_STATUS_CIRCLE.get(light(f), "🟢")
            title = (f"{_focus_code(f)} {marker} {tier_emoji} "
                     f"{f.get('title', '')} — {f.get('area', '')}")

            body_parts = []
            if f.get("landing"):
                body_parts.append(f"Landing: {f['landing']}")
            r = rates.get(f["id"])
            if r and r.get("primary"):
                p = r["primary"]
                body_parts.append(
                    f"Rate: {p['completed']} of {p['target']} "
                    f"({round(p['rate'] * 100)}%) via {p['habit_id']}")
                for s in r.get("supporting", []):
                    body_parts.append(
                        f"  also {s['completed']} of {s['target']} "
                        f"({round(s['rate'] * 100)}%) via {s['habit_id']}")
                if r.get("weeks_red", 0) >= 2:
                    body_parts.append(f"⚠ red {r['weeks_red']} weeks running — "
                                      f"re-land / lower / park / retire")
            link = f.get("link")
            if link:
                body_parts.append(f"{link.get('type')}: {link.get('ref')}")

            cards.append(Card(
                pfc_id=f["id"],
                pfc_type="focus",
                list_name=FOCUS_LIST,
                name=title[:200],
                body="\n".join(body_parts),
                pos=(len(cards) + 1) * 1024,
            ))
    return cards


# ── Renderers — external-system-backed ────────────────────────────────────────

def load_calendar_filters() -> dict:
    """Read config/trello_calendar_filters.yaml. Shared by the Trello render and
    the TRMNL pfc-week builder so the two week surfaces filter identically.
    Returns {} when the file is missing or pyyaml isn't installed — the caller
    then shows everything, which is the safe direction to fail."""
    filter_path = REPO_ROOT / "config" / "trello_calendar_filters.yaml"
    if not filter_path.exists():
        return {}
    try:
        import yaml
    except ImportError:
        print("   🟡 pyyaml not installed; calendar filters not applied", file=sys.stderr)
        return {}
    return yaml.safe_load(filter_path.read_text()) or {}


# A cache older than the window it covers has no future events left in it, so
# there is nothing to render. /pfc-render-trello fetches 7 days forward.
CALENDAR_CACHE_MAX_AGE_DAYS = 7


def load_calendar_cache(path=None, today=None):
    """Second source for 🗓️ Week when no live Calendar fetch happened.

    Only a live session can fetch Calendar, because reading it needs the Google
    Calendar MCP connector, so a timer-run render would otherwise skip the list and
    let it go stale between live renders. /pfc-render-trello Step 1, which the
    morning daily sync job runs, commits data/calendar-cache.json for the TRMNL
    pfc-week builder; reading it here means the timer renders a slightly older week
    instead of no week.

    Returns (events, note). events is None whenever the cache can't be used —
    every failure is soft, and the note explains which one so the render can
    print it. Past events are dropped: the cache covers 7 days from its fetch,
    so by the time the timer reads it the front of that window is already gone.
    """
    path = Path(path) if path else REPO_ROOT / "data" / "calendar-cache.json"
    today = today or _today_mt()

    if not path.exists():
        return None, f"no calendar cache at {path.name}"
    try:
        blob = json.loads(path.read_text())
        fetched_at = blob["fetched_at"]
        events = blob["events"]
    except (ValueError, KeyError, TypeError, OSError):
        return None, f"calendar cache unreadable ({path.name})"

    fetched_day = str(fetched_at)[:10]
    try:
        age = (_dt.date.fromisoformat(today)
               - _dt.date.fromisoformat(fetched_day)).days
    except ValueError:
        return None, f"calendar cache unreadable (bad fetched_at {fetched_at!r})"
    if age > CALENDAR_CACHE_MAX_AGE_DAYS:
        return None, f"calendar cache stale ({age}d old, fetched {fetched_day})"

    upcoming = [e for e in events if _event_start_day(e) >= today]
    if not upcoming:
        return None, f"calendar cache has no upcoming events (fetched {fetched_day})"
    return upcoming, f"calendar cache from {fetched_day} ({age}d old, {len(upcoming)} upcoming)"


def _event_start_day(evt) -> str:
    """YYYY-MM-DD an event starts on, for timed and all-day events alike.
    Unparseable starts sort last so a malformed event is never silently dropped.
    """
    start = evt.get("start", {}) or {}
    raw = start.get("dateTime") or start.get("date") or ""
    return str(raw)[:10] or "9999-12-31"


def calendar_event_excluded(evt, filters) -> bool:
    """Shared show/hide test for one Calendar event, applied by both week
    surfaces. See config/trello_calendar_filters.yaml for the four lists and
    why they exist.

    The load-bearing one is `exclude_titles_when_recurring`: a fixed weekly
    pattern (a standing family arrangement, an office day) is already known
    and costs a row for nothing, but a ONE-OFF carrying that same title is the
    exception worth seeing. So recurrence decides only for those titles, which
    is why the fetch must preserve `recurringEventId`.
    """
    def _lower(key):
        return [str(x).lower() for x in (filters.get(key) or [])]

    title = (evt.get("summary") or "").lower()
    cal_name = ((evt.get("organizer", {}) or {}).get("displayName")
                or evt.get("calendarName", "") or "").lower()

    if any(title.startswith(p) for p in _lower("exclude_prefixes")):
        return True
    if any(p in title for p in _lower("exclude_titles")):
        return True
    if evt.get("recurringEventId") and any(
            p in title for p in _lower("exclude_titles_when_recurring")):
        return True
    if any(c in cal_name for c in _lower("exclude_calendars")):
        return True
    return False


# ── ⭐ The rating card ────────────────────────────────────────────────────────
#
# The home page's "How was yesterday?" card on the phone, in 🦸 Body first: one card
# naming the day the web asks about (home_data rate_target: yesterday before the
# evening hour, today after), with three checklists of 1-5, shown only while that day
# is unrated (trello_home.render_body). trello_writeback.sync_rating saves the day once
# each list has exactly one tick, through pfc_writes.rate_day (the web's writer). The
# card's id carries the date, so a new day swaps in a fresh card and its old ticks go
# with the archived one.

RATE_GROUPS = ("Energy", "Mood", "Focus")
RATE_ITEMS = ("1", "2", "3", "4", "5")
RATE_PREFIX = "rate-day-"
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
RATE_HOW = ("Tick one number in each list: 1 is low, 5 is high. Once all three have one tick, "
            "the next sync saves the day (every 2 hours in the day, and at 5 AM). "
            "The day rating is the three averaged and rounded.")


def short_day(iso: str) -> str:
    """'2025-01-05' -> 'Sun Jan 5'."""
    d = _dt.date.fromisoformat(iso)
    return f"{_WEEKDAYS[d.weekday()]} {_MONTHS[d.month - 1]} {d.day}"


def _local_now():
    """Local wall-clock time, naive, the shape home_data.build_home takes."""
    tz = _ZoneInfo(_os.environ.get("LOCAL_TZ", "America/Denver"))
    return _dt.datetime.now(tz).replace(tzinfo=None)


def rating_answers(checklists) -> dict:
    """Read the three 1-5 checklists. {checklist name: [(item, checked)]} ->
    {"values": {group: int | None}, "ambiguous": {group: [ticked numbers]}, "complete": bool}.

    A group counts only with exactly one tick. Two or more ticks is ambiguous, never
    resolved by guessing (a guessed rating poisons every trend)."""
    values, ambiguous = {}, {}
    for group in RATE_GROUPS:
        ticked = []
        for item, checked in (checklists or {}).get(group) or []:
            digits = "".join(ch for ch in str(item) if ch.isdigit())
            if checked and digits and 1 <= int(digits) <= 5:
                ticked.append(int(digits))
        values[group] = ticked[0] if len(ticked) == 1 else None
        if len(ticked) > 1:
            ambiguous[group] = sorted(ticked)
    return {"values": values, "ambiguous": ambiguous,
            "complete": all(v is not None for v in values.values())}


def rate_status_lines(answers) -> list:
    """What the card's body says about the ticks so far."""
    vals = answers["values"]
    lines = ["Answered: " + " · ".join(f"{g} {vals[g] if vals[g] is not None else '—'}" for g in RATE_GROUPS)]
    for group, ticked in answers["ambiguous"].items():
        lines.append(f"⚠ {group} has {len(ticked)} ticks ({', '.join(map(str, ticked))}): "
                     f"untick one so the rating can save.")
    return lines


def annotate_rate_card(desired, current):
    """Add the answered-so-far lines to the desired rate-day card from the ticks on the
    board's card with the same id (none yet: nothing answered)."""
    by_id = {c.pfc_id: c for c, _ in current}
    for card in desired:
        if card.pfc_type != "rate-day":
            continue
        on_board = by_id.get(card.pfc_id)
        answers = rating_answers(on_board.checklist_state if on_board else None)
        card.body = RATE_HOW + "\n\n" + "\n".join(rate_status_lines(answers))


# ── Trello state reader ───────────────────────────────────────────────────────

def fetch_current_state(api_key, token, board_id, list_name_to_id, label_id_to_name, exclude_lists=None):
    """Fetch all open cards on board, parse frontmatter, return list[(Card, trello_card_id)].
    Side-loads checklists so projects can be diffed without extra round-trips.

    label_id_to_name should map all label IDs to a synthetic key — including
    plain-color labels keyed as '_plain:<color>'.
    """
    exclude = set(exclude_lists or [])
    list_id_to_name = {v: k for k, v in list_name_to_id.items()}

    raw_cards = list_cards_on_board(api_key, token, board_id, filter_="open", include_checklists=True)
    out = []
    for rc in raw_cards:
        list_name = list_id_to_name.get(rc.get("idList"))
        if list_name is None or list_name in exclude:
            continue
        fm = parse_pfc_frontmatter(rc.get("desc", ""))
        # Every checklist's ticks; the Progress one (projects) is also diffed.
        state = {}
        for cl in rc.get("checklists", []) or []:
            items = sorted(cl.get("checkItems", []) or [], key=lambda x: x.get("pos", 0))
            state.setdefault(cl.get("name"), [(it.get("name"), it.get("state") == "complete") for it in items])
        checklist = state.get("Progress")
        resolved_label_names = []
        for lid in rc.get("idLabels", []):
            n = label_id_to_name.get(lid)
            if n:
                resolved_label_names.append(n)
        c = Card(
            pfc_id=fm["pfc-id"],
            pfc_type=fm["pfc-type"] or "",
            list_name=list_name,
            name=rc.get("name", ""),
            body=fm["body"],
            label_names=sorted(resolved_label_names),
            due=rc.get("due"),
            due_complete=rc.get("dueComplete", False),
            checklist=checklist,
            pos=rc.get("pos"),
            checklist_state=state,
        )
        out.append((c, rc["id"]))
    return out


# ── Apply engine ──────────────────────────────────────────────────────────────

def apply_creates(api_key, token, creates, list_name_to_id, label_name_to_id):
    for desired in creates:
        list_id = list_name_to_id.get(desired.list_name)
        if list_id is None:
            continue  # list not present; should not happen post-ensure_lists
        desc = serialize_pfc_frontmatter(desired.pfc_id, desired.pfc_type, desired.body)
        id_labels = [label_name_to_id[n] for n in desired.label_names if n in label_name_to_id]
        new_card = create_card(api_key, token, list_id, name=desired.name, desc=desc, id_labels=id_labels,
                               pos=desired.pos)
        new_id = new_card["id"]
        # Apply due / dueComplete if set
        update_kwargs = {}
        if desired.due:
            update_kwargs["due"] = desired.due
        if desired.due_complete:
            update_kwargs["dueComplete"] = True
        if update_kwargs:
            update_card(api_key, token, new_id, **update_kwargs)
        # Apply checklist if present
        if desired.checklist:
            cl = create_checklist(api_key, token, new_id, "Progress")
            for (item_name, checked) in desired.checklist:
                add_checkitem(api_key, token, cl["id"], item_name, checked=checked)
        for (cl_name, items) in desired.seed_checklists or []:
            cl = create_checklist(api_key, token, new_id, cl_name)
            for item_name in items:
                add_checkitem(api_key, token, cl["id"], item_name)


def apply_updates(api_key, token, updates, list_name_to_id, label_name_to_id):
    for op in updates:
        desired = op["desired"]
        card_id = op["card_id"]
        kwargs = {
            "name": desired.name,
            "desc": serialize_pfc_frontmatter(desired.pfc_id, desired.pfc_type, desired.body),
        }
        # List move
        target_list_id = list_name_to_id.get(desired.list_name)
        if target_list_id:
            kwargs["idList"] = target_list_id
        # Labels
        kwargs["idLabels"] = [label_name_to_id[n] for n in desired.label_names if n in label_name_to_id]
        # Due fields
        if desired.due:
            kwargs["due"] = desired.due
        else:
            # Clear due field by sending empty string. Trello quirk: empty=clear.
            kwargs["due"] = ""
        # dueComplete: only push when desired is concrete (True/False). None means
        # "user-owned" — leave whatever Trello has. Prevents post-commit re-renders
        # from wiping a check the user just made on the widget before sync ran.
        if desired.due_complete is not None:
            kwargs["dueComplete"] = desired.due_complete
        if desired.pos is not None:
            kwargs["pos"] = desired.pos
        update_card(api_key, token, card_id, **kwargs)
        # Checklist normalization
        if desired.checklist is not None:
            _normalize_checklist(api_key, token, card_id, desired.checklist)


def _normalize_checklist(api_key, token, card_id, desired_items):
    """Make the card's 'Progress' checklist match desired_items exactly."""
    existing = list_checklists(api_key, token, card_id)
    progress = next((cl for cl in existing if cl.get("name") == "Progress"), None)

    if progress is None:
        if not desired_items:
            return
        progress = create_checklist(api_key, token, card_id, "Progress")
        for (n, checked) in desired_items:
            add_checkitem(api_key, token, progress["id"], n, checked=checked)
        return

    # Reconcile items
    current_items = progress.get("checkItems", [])
    # Sort by position to match user-perceived order
    current_items = sorted(current_items, key=lambda x: x.get("pos", 0))

    # Strategy: if lengths or names differ, rebuild from scratch (delete + recreate)
    needs_rebuild = (
        len(current_items) != len(desired_items)
        or any(ci.get("name") != desired_items[i][0] for i, ci in enumerate(current_items))
    )

    if needs_rebuild:
        delete_checklist(api_key, token, progress["id"])
        new_cl = create_checklist(api_key, token, card_id, "Progress")
        for (n, checked) in desired_items:
            add_checkitem(api_key, token, new_cl["id"], n, checked=checked)
        return

    # Names match; just update states
    for i, (ci) in enumerate(current_items):
        desired_state = "complete" if desired_items[i][1] else "incomplete"
        current_state = ci.get("state", "incomplete")
        if current_state != desired_state:
            update_checkitem(api_key, token, card_id, ci["id"], state=desired_state)


def apply_archives(api_key, token, archives):
    for tcid in archives:
        archive_card(api_key, token, tcid)


# ── Orchestrator ──────────────────────────────────────────────────────────────

def reset_list(api_key, token, board_id, list_name, confirmed=False):
    """Archive all cards on a single named list. Returns count archived,
    or -1 if the list isn't found, or 0 if confirmed=False or list_name == Inbox."""
    if list_name == INBOX_LIST_NAME:
        return 0
    if not confirmed:
        return 0
    lists = list_lists(api_key, token, board_id, filter_="open")
    target_id = next((l["id"] for l in lists if l["name"] == list_name), None)
    if target_id is None:
        return -1
    raw_cards = list_cards_on_board(api_key, token, board_id, filter_="open")
    archived = 0
    for c in raw_cards:
        if c.get("idList") == target_id:
            archive_card(api_key, token, c["id"])
            archived += 1
    return archived


def rebuild_board(api_key, token, board_id, confirmed=False):
    """Archive every non-Inbox card on the board. Returns count archived.

    confirmed=False is a no-op safety guard. The CLI confirmation prompt
    must succeed before this is called with confirmed=True.
    """
    if not confirmed:
        return 0

    # Map list ids → names so we can identify the Inbox list.
    lists = list_lists(api_key, token, board_id, filter_="open")
    list_id_to_name = {l["id"]: l["name"] for l in lists}

    raw_cards = list_cards_on_board(api_key, token, board_id, filter_="open")
    archived = 0
    for c in raw_cards:
        list_name = list_id_to_name.get(c.get("idList"), "")
        if list_name == INBOX_LIST_NAME:
            continue
        archive_card(api_key, token, c["id"])
        archived += 1
    return archived


def render(api_key, token, board_id, calendar_events=None, calendar_filters=None):
    """Run a single full render. Returns counters dict.

    calendar_events: list of Google Calendar event dicts, or None to leave the
    🗓️ Week cards as they are. calendar_filters is accepted for the CLI's sake; the
    week is filtered by home_data with config/trello_calendar_filters.yaml.
    """
    import home_data
    import trello_home

    print("📋 Loading repo state...")
    state = load_repo_state()

    print("🔧 Reconciling lists and labels...")
    list_map = ensure_lists(api_key, token, board_id, ALL_LIST_NAMES)
    # All labels are plain (unnamed) Trello labels: 5 priority colors for tier
    # cards (tasks/projects/2+1) + life-wheel colors for area cards.
    needed_colors = sorted(set(
        list(PRIORITY_COLORS)
        + [c for _, c in LIFEWHEEL_COLOR_BUCKETS]
    ))
    plain_color_label_map = ensure_plain_color_labels(api_key, token, board_id, needed_colors)
    # Card.label_names uses synthetic keys '_plain:<color>' for plain labels.
    plain_label_name_to_id = {f"_plain:{color}": lid for color, lid in plain_color_label_map.items()}

    print("🎨 Rendering desired card sets...")
    twoplus1 = render_2plus1(state, plain_color_labels=plain_color_label_map)
    today_focus_ids = {c.pfc_id for c in twoplus1}
    values = render_values(state)

    # Card types left as they are on the board this run (not updated, not archived):
    # the home_data cards when build_home fails, the week when no calendar data came.
    kept_types = set()
    desired = []
    home = state.get("home")
    if home is not None:
        sync_stamp = REPO_ROOT / "data" / ".trello-last-sync"
        now = _local_now()
        desired.append(trello_home.render_brief(
            home, daily_habit_counts(state), state.get("day_tracking", []), now,
            sync_stamp.read_text().strip() if sync_stamp.exists() else None,
            review=trello_home.current_review(home), overdue=trello_home.due_reviews(home),
            focus_rows=state.get("focus", []), features=trello_home.feature_scorecard(home)))
        desired += trello_home.render_body(home)
        desired += trello_home.render_picks(home, twoplus1)
        desired += trello_home.render_projects(home, state.get("projects", []),
                                               plain_color_labels=plain_color_label_map)
        desired += trello_home.render_trends(home)
        desired += trello_home.render_areas(home, {a["name"]: a["statement"] for a in state.get("areas", [])},
                                            plain_color_labels=plain_color_label_map)
        desired += trello_home.render_values(home, values)
        desired += trello_home.render_visions(home, state.get("focus", []), state.get("projects", []),
                                              state.get("visions", []))
    else:
        kept_types |= trello_home.HOME_TYPES
        desired += trello_home.positioned(twoplus1, start=2)
        desired += values
    desired += trello_home.positioned(render_daily_habits(state) + render_monthly_habits(state))
    if calendar_events is not None:
        desired += trello_home.render_week(home_data.week_days(calendar_events, _today_mt()), _today_mt())
    else:
        kept_types.add("week-day")
        print(f"   🟡 Calendar data not provided; leaving {WEEK_LIST} as it is")
    desired += render_focus(state)
    desired += render_grounding(state)
    desired += render_tasks(state, plain_color_labels=plain_color_label_map, exclude_2plus1_ids=today_focus_ids)
    print(f"   {len(desired)} desired cards across {len(set(c.list_name for c in desired))} lists")

    print("🔍 Fetching current Trello state...")
    # id→name map: plain labels keyed as '_plain:<color>'.
    label_id_to_name = {v: k for k, v in plain_label_name_to_id.items()}
    current = fetch_current_state(api_key, token, board_id, list_map, label_id_to_name,
                                  exclude_lists={INBOX_LIST_NAME})
    current = [(c, tcid) for c, tcid in current if c.pfc_type not in kept_types]
    print(f"   {len(current)} current cards on dashboard (excluding {INBOX_LIST_NAME}"
          + (f" and kept types {sorted(kept_types)})" if kept_types else ")"))

    annotate_rate_card(desired, current)
    ops = compute_diff(desired, current)
    print(f"📐 Diff: {len(ops['creates'])} creates, {len(ops['updates'])} updates, {len(ops['archives'])} archives")

    print("✏️  Applying creates...")
    apply_creates(api_key, token, ops["creates"], list_map, plain_label_name_to_id)
    print("✏️  Applying updates...")
    apply_updates(api_key, token, ops["updates"], list_map, plain_label_name_to_id)
    print("✏️  Applying archives...")
    apply_archives(api_key, token, ops["archives"])

    # Write last-render timestamp
    stamp = REPO_ROOT / "data" / ".trello-last-render"
    stamp.write_text(_dt.datetime.now(_ZoneInfo(_os.environ.get("LOCAL_TZ", "America/Denver"))).isoformat())

    return {
        "creates": len(ops["creates"]),
        "updates": len(ops["updates"]),
        "archives": len(ops["archives"]),
        "desired_total": len(desired),
        "current_total": len(current),
    }


def main(argv):
    # Local-only mode — no Trello creds needed. Prints the Superman-pulse 7-day trend
    # for pfc-daily-summary's Superman Pulse. Optional integer arg = window size.
    if "--pulse-history" in argv:
        i = argv.index("--pulse-history")
        n = 7
        if i + 1 < len(argv) and argv[i + 1].isdigit():
            n = int(argv[i + 1])
        from pulse import print_pulse_history
        print_pulse_history(_read_ndjson("data/day-tracking.ndjson"), n)
        return 0

    env = load_env()
    import os
    KEY = env.get("TRELLO_API_KEY") or os.environ.get("TRELLO_API_KEY")
    TOK = env.get("TRELLO_API_TOKEN") or os.environ.get("TRELLO_API_TOKEN")
    BOARD = env.get("TRELLO_DASHBOARD_BOARD_ID") or os.environ.get("TRELLO_DASHBOARD_BOARD_ID")

    if not (KEY and TOK and BOARD):
        print("Missing one of: TRELLO_API_KEY, TRELLO_API_TOKEN, TRELLO_DASHBOARD_BOARD_ID. See .env.example.", file=sys.stderr)
        return 1

    # Optional external-data flags
    calendar_events = None
    calendar_filters = {}

    if "--rebuild" in argv:
        # Count what would be archived first
        lists = list_lists(KEY, TOK, BOARD, filter_="open")
        list_id_to_name = {l["id"]: l["name"] for l in lists}
        raw_cards = list_cards_on_board(KEY, TOK, BOARD, filter_="open")
        target_count = sum(1 for c in raw_cards if list_id_to_name.get(c.get("idList")) != INBOX_LIST_NAME)

        print(f"🔴 DESTRUCTIVE: --rebuild will archive {target_count} cards (excluding 📥 Inbox).")
        print(f"   Then re-render from repo. Existing card IDs will be replaced with new ones.")
        print(f"   Type 'yes' to proceed: ", end="", flush=True)
        try:
            response = input().strip()
        except EOFError:
            print("\n🟡 No input received — aborting rebuild.")
            return 1
        if response != "yes":
            print(f"🟡 Rebuild aborted (response was {response!r}).")
            return 0
        archived = rebuild_board(KEY, TOK, BOARD, confirmed=True)
        print(f"✅ Archived {archived} cards. Now running normal render to repopulate.")
        # Fall through to render below

    if "--reset-list" in argv:
        i = argv.index("--reset-list")
        if i + 1 >= len(argv):
            print("Usage: trello_render.py --reset-list <list-name>", file=sys.stderr)
            return 1
        target_name = argv[i + 1]
        if target_name == INBOX_LIST_NAME:
            print(f"🔴 Cannot reset {INBOX_LIST_NAME} — it's owned by pfc-trello-inbox.", file=sys.stderr)
            return 1
        # Probe count
        lists = list_lists(KEY, TOK, BOARD, filter_="open")
        target_id = next((l["id"] for l in lists if l["name"] == target_name), None)
        if target_id is None:
            print(f"🔴 List {target_name!r} not found on board. Available: {[l['name'] for l in lists]}", file=sys.stderr)
            return 1
        raw_cards = list_cards_on_board(KEY, TOK, BOARD, filter_="open")
        count = sum(1 for c in raw_cards if c.get("idList") == target_id)
        print(f"🟡 DESTRUCTIVE: --reset-list {target_name!r} will archive {count} cards.")
        print(f"   Type 'yes' to proceed: ", end="", flush=True)
        try:
            response = input().strip()
        except EOFError:
            print("\n🟡 No input received — aborting.")
            return 1
        if response != "yes":
            print(f"🟡 Reset aborted (response was {response!r}).")
            return 0
        archived = reset_list(KEY, TOK, BOARD, target_name, confirmed=True)
        print(f"✅ Archived {archived} cards in {target_name}. Running render to repopulate.")
        # Fall through to render

    if "--calendar-events" in argv:
        i = argv.index("--calendar-events")
        if i + 1 < len(argv):
            with open(argv[i + 1]) as f:
                calendar_events = json.load(f)

    # No live fetch (the nightly timer, the post-commit hook — neither can reach
    # the Calendar MCP connector): fall back to the cache the daily sync job
    # commits each morning (/pfc-render-trello Step 1). A slightly older week beats a blank list that nothing reports.
    # --no-calendar-cache opts out and restores the old skip-the-list behavior.
    if calendar_events is None and "--no-calendar-cache" not in argv:
        cached, note = load_calendar_cache()
        if cached is None:
            print(f"   🟡 Calendar not fetched and {note}; {WEEK_LIST} will be left as it is")
        else:
            print(f"   🟡 Calendar not fetched; falling back to {note}")
            calendar_events = cached

    # Always load filters; harmless if no calendar data provided.
    calendar_filters = load_calendar_filters()

    # Writeback first so user widget-clicks land in repo logs before render reads them.
    # Skip with --no-writeback for the midnight rollover service: at 12:05 AM, writeback
    # would log yesterday's still-checked cards under today's date, which is incorrect.
    if "--no-writeback" not in argv:
        try:
            from trello_writeback import sync_completed
            print("🔁 Writeback: syncing user-checked cards to repo...")
            counters = sync_completed(KEY, TOK, BOARD)
            interesting = ", ".join(f"{k}={v}" for k, v in counters.items() if v)
            print(f"   {interesting or '(nothing to sync)'}")
        except Exception as e:
            print(f"   🟡 Writeback failed (continuing to render): {e}", file=sys.stderr)

    result = render(KEY, TOK, BOARD,
                    calendar_events=calendar_events,
                    calendar_filters=calendar_filters)
    print(f"\n🟢 Render complete. Created: {result['creates']} · Updated: {result['updates']} · Archived: {result['archives']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
