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
    list_lists, create_list, archive_list,
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
# and a legend that isn't on the screen is a legend the reader doesn't have.
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


def ensure_lists(api_key, token, board_id, list_names):
    """Ensure each name in list_names exists on the board. Returns {name: list_id}."""
    existing = {l["name"]: l["id"] for l in list_lists(api_key, token, board_id, filter_="open")}
    result = {}
    for name in list_names:
        if name in existing:
            result[name] = existing[name]
        else:
            new_list = create_list(api_key, token, board_id, name, pos="bottom")
            result[name] = new_list["id"]
    return result


# ── Per-active-project lists ──────────────────────────────────────────────────
#
# Each active project (projects.ndjson `active: true`) gets its own list
# `🎯 <project name>` so the project backlog doesn't drown the standalone
# Tasks list on the mobile dashboard. When a project flips inactive, its list
# is archived on the next render. Tasks belonging to inactive projects don't
# render to Trello at all — they remain in NDJSON until the project reactivates.

PROJECT_LIST_PREFIX = "🎯 "
FOCUS_LIST_NAME = "🎯 Current Focus"  # shares the 🎯 prefix but is NOT a per-project list
PROJECT_LIST_NAME_MAX = 50  # Trello list-name character cap (safer than 100 for mobile)


def _project_list_name(project_name: str) -> str:
    return f"{PROJECT_LIST_PREFIX}{project_name.strip()}"[:PROJECT_LIST_NAME_MAX]


def _is_project_list_name(name: str) -> bool:
    return name.startswith(PROJECT_LIST_PREFIX) and name != FOCUS_LIST_NAME


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
        from focus_status import compute
        return compute(
            _read_ndjson("4-focus/_data/focus.ndjson"),
            _read_ndjson("7-habits/_data/habits-daily.ndjson"),
            _read_ndjson("7-habits/_data/habits-monthly.ndjson"),
            _load_habit_schema_raw(),
            _today_mt(),
        )
    except Exception as exc:  # noqa: BLE001 — render must never hard-fail here
        print(f"   🟡 focus rates unavailable ({exc}) — cards render without them")
        return []


def _load_habit_schema_raw():
    """habit_schema.yaml as raw dict (daily_habits/monthly_habits keys) — the
    shape focus_status.compute expects, distinct from _load_habit_schema's
    normalized {daily, monthly} shape."""
    import yaml
    p = REPO_ROOT / "config" / "habit_schema.yaml"
    return yaml.safe_load(p.read_text()) if p.exists() else {}


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
        "grounding": _read_ndjson("data/grounding.ndjson"),
        "focus": _read_ndjson("4-focus/_data/focus.ndjson"),
        # Derived focus lights + per-vehicle rates. Degrades to [] on failure
        # rather than killing the whole render.
        "focus_status": _safe_focus_status(),
        "insights": _read_ndjson("data/insights.ndjson"),
        "findings": _read_ndjson("data/findings.ndjson"),
        "hypotheses": _read_ndjson("data/hypotheses.ndjson"),
        "supplements": _read_ndjson("data/supplements.ndjson"),
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
    3-visions/_template.md). Folder docs (README.md, AGENTS.md, CLAUDE.md,
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
                "frequency": h.get("frequency"),
                "area": h.get("area"),
                "active": h.get("active", True),
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
        # Match "1. Love", "2. Faith", etc.
        if line and line[0].isdigit() and ". " in line:
            rank, _, value = line.partition(". ")
            cards.append(Card(
                pfc_id=f"value-{rank}",
                pfc_type="value",
                list_name="💎 Values",
                name=f"{rank}. {value}",
                body="",
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


def render_areas(repo_state, plain_color_labels=None) -> list:
    """Render Area cards with life-wheel context.

    Body structure:
        Life Wheel: <emoji> <score>          (or 'Life Wheel: 🟢 green' for string colors)
        Why: <per-area note from latest life-wheel record>   (only if note exists)

        <area statement>

    If plain_color_labels is provided, attach a plain-color label keyed to the
    area's life-wheel score (1-2 red, 3-4 orange, 5-6 yellow, 7-8 lime,
    9-10 green; or the string color name directly).
    """
    plain_color_labels = plain_color_labels or {}
    wheel_rows = repo_state.get("life_wheel", [])
    latest_scores = {}
    latest_notes = {}
    if wheel_rows:
        latest = wheel_rows[-1]
        latest_scores = latest.get("scores") or latest.get("ratings") or {}
        latest_notes = latest.get("notes") or {}
    cards = []
    for area in repo_state.get("areas", []):
        name = area["name"]
        score = latest_scores.get(name)
        note = latest_notes.get(name)
        color = _lifewheel_color(score)
        label_names = []
        if color and color in plain_color_labels:
            label_names = [f"_plain:{color}"]
        # Build header lines (life-wheel rating + reason note)
        header_lines = []
        if score is not None and score != "":
            emoji = COLOR_EMOJI.get(color, "")
            if isinstance(score, str):
                rating_str = f"Life Wheel: {emoji} {score}".strip()
            else:
                rating_str = f"Life Wheel: {emoji} {score}/10".strip()
            header_lines.append(rating_str)
        if note:
            header_lines.append(f"Why: {note}")
        statement = area["statement"][:1000]
        body_parts = []
        if header_lines:
            body_parts.append("\n".join(header_lines))
        body_parts.append(statement)
        body = "\n\n".join(body_parts)
        title_emoji = COLOR_EMOJI.get(color, "")
        card_name = f"{title_emoji} {name.capitalize()}".strip() if title_emoji else name.capitalize()
        cards.append(Card(
            pfc_id=f"area-{name}",
            pfc_type="area",
            list_name="🧭 Areas",
            name=card_name,
            body=body,
            label_names=label_names,
        ))
    return cards


def render_visions(repo_state) -> list:
    cards = []
    for v in repo_state.get("visions", []):
        cards.append(Card(
            pfc_id=f"vision-{v['slug']}",
            pfc_type="vision",
            list_name="🔭 Visions",
            name=v["title"],
            body=v["body"][:1000],
        ))
    return cards


def render_projects(repo_state, plain_color_labels=None) -> list:
    plain_color_labels = plain_color_labels or {}
    cards = []
    for p in repo_state.get("projects", []):
        if not p.get("active"):
            continue
        if p.get("status") == "done":
            continue
        total = p.get("total_parts", 0) or 0
        completed = p.get("completed_parts", 0) or 0
        pct = int(round((completed / total * 100) if total else 0))
        impact = (p.get("impact", "low")[:1] or "C").upper()
        urgency = (p.get("urgency", "low")[:1] or "C").upper()
        impact_letter = {"H": "A", "M": "B", "L": "C"}.get(impact, "C")
        urgency_letter = {"H": "A", "M": "B", "L": "C"}.get(urgency, "C")
        tier = f"{impact_letter}{urgency_letter}"
        body_lines = [
            f"Area: {p.get('area', '')} · Values: {', '.join(p.get('values', []))}",
            f"Impact: {p.get('impact')} · Urgency: {p.get('urgency')} · Excitement: {p.get('excitement')}",
            f"Parts: {completed}/{total} ({pct}%)",
        ]
        if p.get("deadline"):
            body_lines.append(f"Deadline: {p['deadline']}")
        # Build the Progress checklist
        checklist = [(f"Part {i+1}", i < completed) for i in range(total)]
        tier_emoji = PRIORITY_TIER_EMOJI.get(tier, "")
        project_title = f"{tier_emoji} [{pct}%] {p['name']}".strip() if tier_emoji else f"[{pct}%] {p['name']}"
        cards.append(Card(
            pfc_id=p["id"],
            pfc_type="project",
            list_name="🛠️ Projects",
            name=project_title,
            body="\n".join(body_lines),
            label_names=_priority_plain_label(tier, plain_color_labels),
            due=_deadline_to_due(p.get("deadline")),
            due_complete=False,
            checklist=checklist if total > 0 else None,
        ))
    return cards


def _task_priority_tier(t):
    impact = {"high": "A", "medium": "B", "low": "C"}.get(t.get("impact", "low"), "C")
    urgency = {"high": "A", "medium": "B", "low": "C"}.get(t.get("urgency", "low"), "C")
    return f"{impact}{urgency}"


def render_2plus1(repo_state, plain_color_labels=None) -> list:
    """Render today's 2+1 focus cards. Source: today's daily-focus row + tasks.ndjson."""
    plain_color_labels = plain_color_labels or {}
    today = _today_mt()
    focus = next((r for r in repo_state.get("daily_focus", []) if r.get("date") == today), None)
    if not focus:
        return []
    tasks_by_id = {t["id"]: t for t in repo_state.get("tasks", [])}
    ids = []
    for slot in ("critical", "bonus", "project"):
        v = focus.get(slot)
        if isinstance(v, list):
            ids.extend(v)
        elif isinstance(v, str):
            ids.append(v)
    cards = []
    for tid in ids:
        t = tasks_by_id.get(tid)
        if not t or t.get("status") == "done":
            continue
        tier = _task_priority_tier(t)
        body_lines = [
            f"Impact: {t.get('impact')} · Urgency: {t.get('urgency')} · Size: {t.get('size')}",
            f"Area: {t.get('area', 'none')} · Project: {t.get('project', 'none')}",
        ]
        if t.get("deadline"):
            body_lines.append(f"Deadline: {t['deadline']}")
        if t.get("notes"):
            body_lines.append(f"Notes: {t['notes']}")
        size = t.get("size", "?")
        desc_text = t.get("description", "")
        tier_emoji = PRIORITY_TIER_EMOJI.get(tier, "")
        # Title format: "🔴 AA (M) - description" — emoji prefix makes priority
        # visible on Android Trello widgets where labels are not rendered.
        bot = _agent_mark(t)
        formatted_name = (f"{tier_emoji} {tier} ({size}){bot} - {desc_text}"
                          if tier_emoji else f"{tier} ({size}){bot} - {desc_text}")[:200]
        cards.append(Card(
            pfc_id=t["id"],
            pfc_type="task",
            list_name="✅ 2+1",
            name=formatted_name,
            body="\n".join(body_lines),
            label_names=_priority_plain_label(tier, plain_color_labels),
            due=_deadline_to_due(t.get("deadline")),
            due_complete=None,
        ))
    return cards


def render_tasks(repo_state, plain_color_labels=None, exclude_2plus1_ids=None) -> list:
    """Render open standalone tasks (no project) except those in today's 2+1.
    Project-linked tasks render via render_project_tasks instead."""
    plain_color_labels = plain_color_labels or {}
    exclude = set(exclude_2plus1_ids or [])
    cards = []
    for t in repo_state.get("tasks", []):
        if t.get("status") != "open":
            continue
        if t.get("deferred"):
            continue  # parked by the user — out of rotation, off the board
        if t["id"] in exclude:
            continue
        if (t.get("project") or "none") != "none":
            continue
        tier = _task_priority_tier(t)
        body_lines = [
            f"Impact: {t.get('impact')} · Urgency: {t.get('urgency')} · Size: {t.get('size')}",
            f"Area: {t.get('area', 'none')} · Project: {t.get('project', 'none')}",
        ]
        if t.get("deadline"):
            body_lines.append(f"Deadline: {t['deadline']}")
        if t.get("notes"):
            body_lines.append(f"Notes: {t['notes']}")
        size = t.get("size", "?")
        desc_text = t.get("description", "")
        tier_emoji = PRIORITY_TIER_EMOJI.get(tier, "")
        bot = _agent_mark(t)
        formatted_name = (f"{tier_emoji} {tier} ({size}){bot} - {desc_text}"
                          if tier_emoji else f"{tier} ({size}){bot} - {desc_text}")[:200]
        cards.append(Card(
            pfc_id=t["id"],
            pfc_type="task",
            list_name="✅ Tasks",
            name=formatted_name,
            body="\n".join(body_lines),
            label_names=_priority_plain_label(tier, plain_color_labels),
            due=_deadline_to_due(t.get("deadline")),
            due_complete=None,
        ))
    return cards


def render_project_tasks(repo_state, plain_color_labels=None, exclude_2plus1_ids=None) -> list:
    """Render open tasks for each active project to that project's dedicated list.
    Tasks belonging to inactive/done/missing projects are NOT rendered to Trello —
    they remain in NDJSON until the project reactivates."""
    plain_color_labels = plain_color_labels or {}
    exclude = set(exclude_2plus1_ids or [])
    active_projects = {
        p["id"]: p
        for p in repo_state.get("projects", [])
        if p.get("active")
    }
    cards = []
    for t in repo_state.get("tasks", []):
        if t.get("status") != "open":
            continue
        if t.get("deferred"):
            continue  # parked by the user — out of rotation, off the board
        if t["id"] in exclude:
            continue
        proj_id = t.get("project") or "none"
        project = active_projects.get(proj_id)
        if project is None:
            continue
        tier = _task_priority_tier(t)
        body_lines = [
            f"Impact: {t.get('impact')} · Urgency: {t.get('urgency')} · Size: {t.get('size')}",
            f"Area: {t.get('area', 'none')} · Project: {project['name']}",
        ]
        if t.get("deadline"):
            body_lines.append(f"Deadline: {t['deadline']}")
        if t.get("notes"):
            body_lines.append(f"Notes: {t['notes']}")
        size = t.get("size", "?")
        desc_text = t.get("description", "")
        tier_emoji = PRIORITY_TIER_EMOJI.get(tier, "")
        bot = _agent_mark(t)
        formatted_name = (f"{tier_emoji} {tier} ({size}){bot} - {desc_text}"
                          if tier_emoji else f"{tier} ({size}){bot} - {desc_text}")[:200]
        cards.append(Card(
            pfc_id=t["id"],
            pfc_type="task",
            list_name=_project_list_name(project["name"]),
            name=formatted_name,
            body="\n".join(body_lines),
            label_names=_priority_plain_label(tier, plain_color_labels),
            due=_deadline_to_due(t.get("deadline")),
            due_complete=None,
        ))
    return cards


def render_daily_habits(repo_state) -> list:
    today = _today_mt()
    schema = repo_state.get("habit_schema", {})
    daily = schema.get("daily", []) if isinstance(schema, dict) else []
    today_logs = [r for r in repo_state.get("habits_daily", []) if r.get("date") == today]
    log_by_id = {r.get("habit_id"): r for r in today_logs}
    cards = []
    for h in daily:
        hid = h.get("id") or h.get("habit_id") or h.get("name")
        if not hid:
            continue
        if h.get("active") is False:
            continue
        log = log_by_id.get(hid)
        completed = log and log.get("completed") is True
        # No ✓ title marker: the card's own checkbox already shows completion, and
        # a name that changes daily forces a pointless update on every render.
        cards.append(Card(
            pfc_id=f"habit-daily-{hid}",
            pfc_type="habit-daily",
            list_name="☀️ Daily Habits",
            name=f"{h.get('name', hid)}",
            body=f"Frequency: {h.get('frequency', '?')}/week · Area: {h.get('area', '')}",
            # False (not None) so render actively unchecks at day rollover. Render runs writeback
            # first by default (see main()), so user widget-clicks get logged before they're wiped.
            due_complete=True if completed else False,
        ))
    return cards


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
        if h.get("active") is False:
            continue
        target = h.get("frequency", 1)
        count = count_by_id.get(hid, 0)
        cards.append(Card(
            pfc_id=f"habit-monthly-{hid}",
            pfc_type="habit-monthly",
            list_name="🌙 Monthly Habits",
            name=f"{h.get('name', hid)}: {count}/{target}",
            body=f"Target this month: {target} · Area: {h.get('area', '')}",
            # Per-day check: unchecks overnight like daily habits. Title still shows
            # month-to-date count/target. Each click logs one occurrence; a card that
            # stays checked across days does not re-log.
            due_complete=True if hid in logged_today else False,
        ))
    return cards


def render_life_wheel(repo_state) -> list:
    rows = repo_state.get("life_wheel", [])
    if not rows:
        return []
    latest = rows[-1]
    cards = []
    # Schema variants: numeric scores (e.g. {"career": 7}) or color ratings (e.g. {"career": "green"}).
    scores = latest.get("scores") or {}
    ratings = latest.get("ratings") or {}
    if scores:
        for area, score in scores.items():
            cards.append(Card(
                pfc_id=f"lifewheel-{area}",
                pfc_type="life-wheel",
                list_name="🎡 Life Wheel",
                name=f"{area.capitalize()}: {score}/10",
                body=f"As of {latest.get('date', 'unknown')}",
            ))
    elif ratings:
        for area, rating in ratings.items():
            note = (latest.get("notes") or {}).get(area, "")
            body = f"As of {latest.get('date', 'unknown')}"
            if note:
                body += f"\n\n{note}"
            cards.append(Card(
                pfc_id=f"lifewheel-{area}",
                pfc_type="life-wheel",
                list_name="🎡 Life Wheel",
                name=f"{area.capitalize()}: {rating}",
                body=body,
            ))
    return cards


GROUNDING_CAP = 10  # soft cap on 🧠 Front of Mind anchors; warn (never truncate) if exceeded


def render_grounding(repo_state) -> list:
    """🧠 Front of Mind — a small, cycling set of grounding anchors to keep
    front-of-mind right now. One card per TOPIC (not per bullet): `title` is the
    card name, `body` holds the points, so a heavy theme stays one scannable card.

    Soft-capped: renders ALL active anchors but warns when the count exceeds
    GROUNDING_CAP. Truncating would risk hiding something important — curation
    happens by retiring an anchor, not by a silent cutoff.
    """
    cards = []
    active = [g for g in repo_state.get("grounding", []) if g.get("status") == "active"]
    if len(active) > GROUNDING_CAP:
        print(f"   🟡 Front of Mind has {len(active)} active topic cards (soft cap {GROUNDING_CAP}) — consider retiring some")
    for g in active:
        # `text` is a single-line fallback for records that have no title/body split.
        title = g.get("title") or g.get("text") or ""
        body = g.get("body") or g.get("text") or ""
        cards.append(Card(
            pfc_id=g["id"],
            pfc_type="grounding",
            list_name="🧠 Front of Mind",
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
    """🎯 Current Focus — the capped, traffic-lit set of what's actively being
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
    # Red means "not happening" and DOES occupy one.
    pursuits = [f for f in active if f.get("tier") == "pursuit" and not f.get("parked")]
    if len(pursuits) > FOCUS_PURSUIT_CAP:
        print(f"   🟡 Current Focus has {len(pursuits)} active pursuits "
              f"(hard cap {FOCUS_PURSUIT_CAP}) — park/retire one")

    rates = {r["focus_id"]: r for r in repo_state.get("focus_status", [])}
    red_first = {"red": 0, "yellow": 1, "green": 2, "parked": 3, "unknown": 4}

    for tier, tier_emoji in FOCUS_TIER_ORDER:
        tier_focuses = [x for x in active if x.get("tier") == tier]
        tier_focuses.sort(key=lambda f: (_focus_code(f),
                                         red_first.get(f.get("status", "green"), 9)))
        for f in tier_focuses:
            if f.get("parked"):
                marker = FOCUS_PARKED_MARKER
            else:
                marker = FOCUS_STATUS_CIRCLE.get(f.get("status", "green"), "🟢")
            title = (f"{_focus_code(f)} {marker} {tier_emoji} "
                     f"{f.get('title', '')} — {f.get('area', '')}")

            body_parts = []
            if f.get("landing"):
                body_parts.append(f"Landing: {f['landing']}")
            r = rates.get(f["id"])
            if r and r.get("primary"):
                pr = r["primary"]
                body_parts.append(
                    f"Rate: {pr['completed']} of {pr['target']} "
                    f"({round(pr['rate'] * 100)}%) via {pr['habit_id']}")
                for sup in r.get("supporting", []):
                    body_parts.append(
                        f"  also {sup['completed']} of {sup['target']} "
                        f"({round(sup['rate'] * 100)}%) via {sup['habit_id']}")
                if r.get("weeks_red", 0) >= 2:
                    body_parts.append(f"⚠ red {r['weeks_red']} weeks running — "
                                      f"re-land / lower / park / retire")
            link = f.get("link")
            if link:
                body_parts.append(f"{link.get('type')}: {link.get('ref')}")

            cards.append(Card(
                pfc_id=f["id"],
                pfc_type="focus",
                list_name=FOCUS_LIST_NAME,
                name=title[:200],
                body="\n".join(body_parts),
            ))
    return cards


def render_insights(repo_state) -> list:
    cards = []
    for ins in repo_state.get("insights", []):
        if ins.get("status") != "active":
            continue
        snippet = (ins.get("insight") or "")[:200]
        cards.append(Card(
            pfc_id=ins["id"],
            pfc_type="insight",
            list_name="💡 Insights",
            name=snippet,
            body=(ins.get("insight") or "") + (f"\n\nCategory: {ins['category']}" if ins.get("category") else ""),
        ))
    return cards


def render_findings(repo_state) -> list:
    cards = []
    for f in repo_state.get("findings", []):
        body = (f.get("finding") or f.get("statement") or "")
        cards.append(Card(
            pfc_id=f["id"],
            pfc_type="finding",
            list_name="📜 Findings",
            name=body[:200],
            body=body,
        ))
    return cards


def render_hypotheses(repo_state) -> list:
    cards = []
    for h in repo_state.get("hypotheses", []):
        if h.get("status") != "active":
            continue
        snippet = (h.get("hypothesis") or "")[:200]
        cards.append(Card(
            pfc_id=h["id"],
            pfc_type="hypothesis",
            list_name="🧪 Hypothesis",
            name=snippet,
            body=f"Domain: {h.get('domain', '')}\n\n{h.get('hypothesis', '')}",
        ))
    return cards


# Time-of-day → numeric prefix + display label, ordered through the day.
TIME_OF_DAY_ORDER = {
    "morning": (1, "Morning"),
    "afternoon": (2, "Afternoon"),
    "evening": (3, "Evening"),
    "bedtime": (4, "Bedtime"),
    "with meals": (5, "With Meals"),
}


def render_supplements(repo_state) -> list:
    """Render currently-active supplements. Title format:
        '<rank>. <Time labels> - <name> <dose>'
    where rank is 1=Morning..5=With Meals (uses earliest time when multi).
    Sorted alphabetically by Trello, the prefix gives natural time-of-day order."""
    today = _today_mt()
    cards = []
    for s in repo_state.get("supplements", []):
        started = s.get("started")
        stopped = s.get("stopped")
        if not started:
            continue
        if started > today:
            continue
        if stopped and stopped <= today:
            continue
        name = s.get("name", "?")
        dose = s.get("dose", "")
        times = s.get("times") or []
        # Determine numeric prefix (earliest time slot) and joined display labels.
        time_pairs = sorted(
            (TIME_OF_DAY_ORDER.get(t, (99, t.title())) for t in times),
            key=lambda p: p[0],
        )
        if time_pairs:
            rank = time_pairs[0][0]
            time_label = ", ".join(label for _, label in time_pairs)
            title = f"{rank}. {time_label} - {name} {dose}".strip()
        else:
            # Schema requires non-empty times, but be defensive.
            title = f"9. {name} {dose}".strip()
        body_lines = [f"Started: {started}"]
        food = s.get("food_requirement")
        if food:
            food_label = {
                "empty_stomach": "Take: empty stomach",
                "with_food": "Take: with food",
                "with_fat": "Take: with fat",
                "either": "Take: any time",
            }.get(food, f"Take: {food}")
            body_lines.append(food_label)
        if s.get("purpose"):
            body_lines.append(f"Purpose: {s['purpose']}")
        if s.get("notes"):
            body_lines.append(f"Notes: {s['notes']}")
        cards.append(Card(
            pfc_id=s["id"],
            pfc_type="supplement",
            list_name="💊 Supplements",
            name=title,
            body="\n".join(body_lines),
        ))
    return cards


def render_last_7_days(repo_state) -> list:
    rows = repo_state.get("day_tracking", [])
    last7 = sorted(rows, key=lambda r: r.get("date", ""))[-7:]
    cards = []
    for r in last7:
        date = r.get("date", "")
        try:
            dt = _dt.datetime.strptime(date, "%Y-%m-%d")
            day = dt.strftime("%a")
        except Exception:
            day = "?"
        rating = r.get("rating", "?")
        mood = r.get("mood", "?")
        energy = r.get("energy", "?")
        focus = r.get("focus", "?")
        body_lines = []
        if r.get("hyperfocused"):
            body_lines.append("⚠ hyperfocused")
        if r.get("notes"):
            body_lines.append(f"Notes: {r['notes']}")
        cards.append(Card(
            pfc_id=f"day-{date}",
            pfc_type="day-tracking",
            list_name="⬅ Last 7 Days",
            name=f"{date} {day} · ⭐ {rating}/5 · 😊 {mood} · ⚡ {energy} · 🎯 {focus}",
            body="\n".join(body_lines) if body_lines else "(no flags)",
        ))
    return cards


# ── 🦸 Superman Pulse ─────────────────────────────────────────────────────────
#
# An at-a-glance status board for the levers that drive your best days: one card
# per lever, plus a verdict card that reads the CRITICAL levers together.
#
# The thresholds, verdict, remediations, and trend math all live in
# `pulse.py` — that module is the single source of truth and every surface
# imports from it. This file only turns those tuples into Trello cards. Do NOT
# re-derive a band here; two copies of a threshold drift the moment one is tuned.
#
# The default lever set there is a generic starting point. Replace it with the
# levers your own `/pfc-analyze-trends` surfaces: a metric that does not separate
# your good days from your average ones does not earn a card.
SUPERMAN_PULSE_LIST = "🦸 Superman Pulse"


def render_superman_pulse(repo_state) -> list:
    """One card per lever plus a verdict card, sorted red-first (red → yellow →
    green) with tier only breaking ties inside a colour, so what's off is what
    you see first."""
    from pulse import pulse_snapshot

    snap = pulse_snapshot(repo_state.get("day_tracking", []))
    if snap is None:
        return []
    levers = snap["levers"]
    crit = [lv for lv in levers if lv[1] == "CRITICAL"]
    crit_green = sum(1 for lv in crit if lv[6] == "🟢")

    status_rank = {"🔴": 0, "🟡": 1, "🟢": 2, "⚪": 3}
    cards = [Card(
        pfc_id="pulse-verdict",
        pfc_type="superman-pulse",
        list_name=SUPERMAN_PULSE_LIST,
        name=f"⭐ VERDICT — {snap['verdict']['status']} {snap['verdict']['text']}",
        body=(f"For {snap['date']} — last night's sleep plus where recovery stands now.\n\n"
              f"Critical levers green: {crit_green}/{len(crit)}.\n\n"
              f"Tonight's move: {snap['move']}\n\n"
              "Thresholds live in automations/scripts/pulse.py — tune them to "
              "what /pfc-analyze-trends finds in your own data."),
    )]
    # Red first, then yellow, then green — worst at the top so the thing to fix
    # is the thing read first. Tier only breaks ties within a colour.
    for lid, tier, trank, label, disp, target, status in sorted(
            levers, key=lambda x: (status_rank.get(x[6], 9), x[2])):
        cards.append(Card(
            pfc_id=f"pulse-{lid}",
            pfc_type="superman-pulse",
            list_name=SUPERMAN_PULSE_LIST,
            name=f"{status} [{tier}] {label}: {disp} (target {target})",
            body=f"Tier: {tier}. Now: {disp}. Target: {target}. Status: {status}.",
        ))
    return cards


# ── Renderers — external-system-backed ────────────────────────────────────────

def _format_event_time(start, end):
    """Convert a Calendar event start/end to '<Day> <12hr time>' string. Handles all-day events."""
    if "dateTime" in start:
        # Datetime event
        try:
            dt = _dt.datetime.fromisoformat(start["dateTime"])
            day = dt.strftime("%a %m/%d")
            time = dt.strftime("%I:%M %p").lstrip("0")
            return f"{day} {time}"
        except Exception:
            return start["dateTime"]
    else:
        # All-day event. Some sources give a clean YYYY-MM-DD; others (Google
        # Calendar API via MCP) return an ISO timestamp like '2026-05-08T00:00:00Z'.
        raw = start.get("date", "?")
        try:
            # Try parsing as datetime first (handles ISO timestamps)
            dt = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            day = dt.strftime("%a %m/%d")
            return f"{day} (all day)"
        except (ValueError, AttributeError):
            # Fall back to plain string (handles 'YYYY-MM-DD')
            return f"{raw} (all day)"


def _event_sort_key(evt):
    """Sortable key for a calendar event — uses the start time/date."""
    start = evt.get("start", {}) or {}
    if "dateTime" in start:
        return start["dateTime"]
    if "date" in start:
        # All-day events: date string sorts naturally; pad to make it sort BEFORE
        # any timed event on the same day if both exist (date-only events conventionally start at 00:00).
        return start["date"] + "T00:00:00"
    return ""


def _event_to_due(start):
    """Convert a calendar event start to a Trello due ISO 8601 timestamp (UTC).
    Lets users sort the Week-at-a-Glance list by Due Date in Trello.
    All-day events anchor to noon UTC of the date (matches task convention)."""
    if "dateTime" in start:
        raw = start["dateTime"]
        try:
            dt = _dt.datetime.fromisoformat(raw)
            dt_utc = dt.astimezone(_dt.timezone.utc)
            return dt_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        except Exception:
            return None
    if "date" in start:
        raw = start["date"]
        try:
            dt = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%dT12:00:00.000Z")
        except (ValueError, AttributeError):
            return f"{raw}T12:00:00.000Z"
    return None


# A cache older than the window it covers has no future events left in it, so
# there is nothing to render. /pfc-render-trello fetches 7 days forward.
CALENDAR_CACHE_MAX_AGE_DAYS = 7


def load_calendar_cache(path=None, today=None):
    """Second source for 🗓️ Week at a Glance when no live Calendar fetch happened.

    Only a live session can fetch Calendar, because reading it needs the Google
    Calendar MCP connector. A scheduled render (a systemd timer, the post-commit
    hook) would otherwise skip the list entirely, so it silently goes stale between
    live renders. /pfc-render-trello Step 1, which the daily sync job runs every
    morning, commits data/calendar-cache.json for the TRMNL pfc-week builder;
    reading it here means a scheduled render shows a slightly older week instead
    of no week.

    Returns (events, note). events is None whenever the cache can't be used —
    every failure is soft, and the note explains which one so the render can
    print it. Past events are dropped: the cache covers 7 days from its fetch,
    so by the time a scheduled render reads it the front of that window is gone.
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


def render_calendar(events, filters) -> list:
    """Render Calendar events to cards, applying the title and calendar filters
    from config/trello_calendar_filters.yaml. Output is sorted chronologically
    so cards land on Trello in time order.

    Recurring events are NOT dropped wholesale. They were once, and the week
    surface came out nearly blank as a result — most real commitments (standing
    lunches, classes, therapy, an in-office day) are recurring series, and
    those are exactly the ones that must not be missed. The line that matters
    is real commitments vs. PFC scaffolding, which is a title question, not a
    recurrence question. See the filter file's header for the full rule.
    """
    # Sort events chronologically before rendering so the resulting card list
    # is in time order.
    events_sorted = sorted(events, key=_event_sort_key)
    cards = []
    for evt in events_sorted:
        if calendar_event_excluded(evt, filters):
            continue
        title = evt.get("summary") or "(no title)"
        cal_name = (evt.get("organizer", {}) or {}).get("displayName") or evt.get("calendarName", "")
        time_part = _format_event_time(evt.get("start", {}), evt.get("end", {}))
        body_lines = [f"Calendar: {cal_name}"]
        if evt.get("location"):
            body_lines.append(f"Location: {evt['location']}")
        if evt.get("end", {}).get("dateTime"):
            body_lines.append(f"End: {evt['end']['dateTime']}")
        cards.append(Card(
            pfc_id=f"gcal-{evt['id']}",
            pfc_type="calendar-event",
            list_name="🗓️ Week at a Glance",
            name=f"{time_part} · {title}"[:200],
            body="\n".join(body_lines),
            due=_event_to_due(evt.get("start", {})),
        ))
    return cards


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
        # Extract Progress checklist if present (used for projects).
        checklist = None
        for cl in rc.get("checklists", []) or []:
            if cl.get("name") == "Progress":
                items = sorted(cl.get("checkItems", []) or [], key=lambda x: x.get("pos", 0))
                checklist = [(it.get("name"), it.get("state") == "complete") for it in items]
                break
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
        new_card = create_card(api_key, token, list_id, name=desired.name, desc=desc, id_labels=id_labels)
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

INBOX_LIST_NAME = "📥 Inbox"

ALL_LIST_NAMES = [
    "🧠 Front of Mind",
    "🦸 Superman Pulse",
    "🎯 Current Focus",
    "✅ 2+1",
    "⬅ Last 7 Days",
    "🗓️ Week at a Glance",  # MCP-fed: skipped if Calendar MCP is unavailable
    "💎 Values",
    "🧭 Areas",  # life-wheel state surfaces as a plain-color label here, not a separate list
    "🔭 Visions",
    "🛠️ Projects",
    "✅ Tasks",
    "☀️ Daily Habits",
    "🌙 Monthly Habits",
    "💡 Insights",
    "📜 Findings",
    "🧪 Hypothesis",
    "💊 Supplements",
]


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

    calendar_events: list of Google Calendar event dicts, or None to skip Calendar list.
    calendar_filters: dict from trello_calendar_filters.yaml, or {} for no filtering.

    Email has no dashboard list — labeled inbox emails become tasks via
    `pfc-email-triage`, and those render as normal Action cards.
    """
    print("📋 Loading repo state...")
    state = load_repo_state()

    # Compute per-active-project list names. Each active project gets its own
    # backlog list (`🎯 <name>`); inactive-project lists are archived below.
    active_project_lists = [
        _project_list_name(p["name"])
        for p in state.get("projects", [])
        if p.get("active")
    ]
    all_list_names = list(ALL_LIST_NAMES) + active_project_lists

    print("🔧 Reconciling lists and labels...")
    list_map = ensure_lists(api_key, token, board_id, all_list_names)
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

    desired = []
    desired += render_values(state)
    desired += render_areas(state, plain_color_labels=plain_color_label_map)
    desired += render_visions(state)
    desired += render_projects(state, plain_color_labels=plain_color_label_map)
    desired += twoplus1
    desired += render_tasks(state, plain_color_labels=plain_color_label_map, exclude_2plus1_ids=today_focus_ids)
    desired += render_project_tasks(state, plain_color_labels=plain_color_label_map, exclude_2plus1_ids=today_focus_ids)
    desired += render_daily_habits(state)
    desired += render_monthly_habits(state)
    # Life Wheel list: no longer rendered. Existing cards in that list will be
    # archived because the diff sees no desired cards there.
    desired += render_grounding(state)
    desired += render_focus(state)
    desired += render_insights(state)
    desired += render_findings(state)
    desired += render_hypotheses(state)
    desired += render_supplements(state)
    desired += render_last_7_days(state)
    desired += render_superman_pulse(state)

    # External-system-backed lists. If data is None, the corresponding list is
    # NOT rendered — leaving any existing cards on that list intact (we exclude
    # the list from the diff scope).
    excluded_lists = {INBOX_LIST_NAME}
    if calendar_events is not None:
        desired += render_calendar(calendar_events, calendar_filters or {})
    else:
        excluded_lists.add("🗓️ Week at a Glance")
        print("   🟡 Calendar data not provided; skipping 🗓️ Week at a Glance")

    print(f"   {len(desired)} desired cards across {len(set(c.list_name for c in desired))} lists")

    print("🔍 Fetching current Trello state...")
    # id→name map: plain labels keyed as '_plain:<color>'.
    label_id_to_name = {v: k for k, v in plain_label_name_to_id.items()}
    current = fetch_current_state(api_key, token, board_id, list_map, label_id_to_name, exclude_lists=excluded_lists)
    print(f"   {len(current)} current cards on dashboard (excluding {sorted(excluded_lists)})")

    ops = compute_diff(desired, current)
    print(f"📐 Diff: {len(ops['creates'])} creates, {len(ops['updates'])} updates, {len(ops['archives'])} archives")

    print("✏️  Applying creates...")
    apply_creates(api_key, token, ops["creates"], list_map, plain_label_name_to_id)
    print("✏️  Applying updates...")
    apply_updates(api_key, token, ops["updates"], list_map, plain_label_name_to_id)
    print("✏️  Applying archives...")
    apply_archives(api_key, token, ops["archives"])

    # Archive stale per-project lists. A 🎯-prefixed list on the board whose
    # project is no longer active (or has been deleted from projects.ndjson)
    # gets archived so the dashboard reflects current active-project state.
    active_set = set(active_project_lists)
    stale_lists = [
        l for l in list_lists(api_key, token, board_id, filter_="open")
        if _is_project_list_name(l["name"]) and l["name"] not in active_set
    ]
    for l in stale_lists:
        archive_list(api_key, token, l["id"])
    if stale_lists:
        print(f"   Archived {len(stale_lists)} stale per-project list(s): "
              + ", ".join(l["name"] for l in stale_lists))

    # Write last-render timestamp
    stamp = REPO_ROOT / "data" / ".trello-last-render"
    stamp.write_text(_dt.datetime.now(_ZoneInfo(_os.environ.get("LOCAL_TZ", "America/Denver"))).isoformat())

    return {
        "creates": len(ops["creates"]),
        "updates": len(ops["updates"]),
        "archives": len(ops["archives"]),
        "desired_total": len(desired),
        "current_total": len(current),
        "project_lists_archived": len(stale_lists),
    }


def main(argv):
    # Local-only mode — no Trello credentials needed. Prints the Superman Pulse
    # 7-day trend for pfc-daily-summary's Superman Pulse. Optional integer arg = window size.
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

    # No live fetch (a scheduled render, the post-commit hook — neither can reach
    # the Calendar MCP connector): fall back to the cache the daily sync job
    # commits each morning (/pfc-render-trello Step 1). A slightly older week beats
    # a blank list that nothing reports. --no-calendar-cache opts out and restores
    # the skip-the-list behavior.
    if calendar_events is None and "--no-calendar-cache" not in argv:
        cached, note = load_calendar_cache()
        if cached is None:
            print(f"   🟡 Calendar not fetched and {note}; 🗓️ Week at a Glance will be skipped")
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
