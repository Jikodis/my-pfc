#!/usr/bin/env python3
"""Data for the one-page web UI home (web/src/lib/computed.ts).

    python3 automations/scripts/web_data.py --home [--today YYYY-MM-DD]

Every rule behind a number on the home page lives here or in the script it calls
(focus_status.py for traffic lights), never in TypeScript. `build_home` returns one
dict, and `web/src/lib/computed.ts` types it.
"""

import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import qqrt  # noqa: E402
from focus_status import status_rows  # noqa: E402

REPO = SCRIPT_DIR.parents[1]

EVENING_HOUR = 18  # from this hour on, "rate your day" means today, not yesterday
BROKEN_AWAKE_MINUTES = 60  # this much awake time in the night breaks it
BROKEN_EFFICIENCY_PCT = 85  # sleep efficiency below this also breaks a night
ROTATION_EPOCH = date(2025, 1, 1)
FOCUS_ORDER = {"red": 0, "yellow": 1, "green": 2}
SYNC_STALE_HOURS = 30  # the daily sync runs once a morning; a day and a few hours late is a miss
DEFAULT_SYNC_LOG = "/tmp/pfc-daily-sync.log"
SYNC_DONE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) DONE ok=(\d+) fail=(\d+)\s*$")

MAX_NEEDS_YOU = 2
DEADLINE_WINDOW_DAYS = 2
EMAIL_PRIORITIES = ("AA", "AB", "BA")
SUGGESTED_COUNT = 3
HANDOFF_COUNT = 3
LETTER = {"high": "A", "medium": "B", "low": "C"}

# Owning skill or action per rolling-review id in data/review-ledger.ndjson. The same
# map is the owning-skill table in `.agents/skills/pfc-review/SKILL.md`; change both
# together. The page shows this text, and the page uses no em or en dashes.
REVIEW_SKILLS = {
    'stale-task-triage': '`/pfc-revive`: walk the slipped watchlist',
    'tasks-missing-area': 'assign an area to the flagged open tasks (edit `tasks.ndjson` / `/pfc-add-task` shape)',
    'focus-accuracy': '`/pfc-focus`: eyeball traffic-lights + landings',
    'vision-relevance': 'open one file in `3-visions/` and sanity-check it still fits',
    'habit-rate': 'show trailing-7 completion per habit (from `7-habits/_data/habits-daily.ndjson`)',
    'values-alignment': 'add `values` to the flagged active project(s) in `projects.ndjson`',
    'day-trend-peek': 'quick eyeball of the last 7 day ratings (light `/pfc-analyze-trends`)',
    'hypotheses-review': 'review active hypotheses in `data/hypotheses.ndjson`: update `last_reviewed`; graduate to a finding if the bar is met (n>=30, \\|r\\|>=0.3, p<0.01, or a clear lived-experience pattern). **Never auto-archive**: surface it, the user decides',
    'life-wheel': "the area check-in: each area's item questions, one area at a time (`/pfc-review` § life-wheel; answers append to `2-areas/_data/area-checkins.ndjson`)",
    'household-status': 'rate each house area (`2-areas/_data/household-status.ndjson`); a task for anything red',
    'project-progress': '`/pfc-summarize-project` per active project',
    'vision-activation': '`/pfc-focus`: lean-in / let-rest per vision',
    'monthly-habits': 'show monthly-habit completion (`7-habits/_data/habits-monthly.ndjson`)',
    'insights-review': '`/pfc-insights`: triage active insights',
    'findings-alignment': 'cross-check active findings (`data/findings.ndjson`) against values, projects, and habits; supersede anything life has moved past',
    'trend-analysis': '`/pfc-analyze-trends`: full statistical pass',
    'revive-outcomes': '`/pfc-revive`: review outcomes of revived items 30+ days old',
    'usage-audit': '`/pfc-usage-audit`: the system health report: feature scorecard (use it, change cadence, change feature), then data freshness and logging gaps',
    'focus-repick': '`/pfc-focus`: quarterly re-pick',
    'vision-brainstorm': '`/pfc-vision-brainstorm`',
    'strengths-refresh': 'quarterly strengths refresh (`0-me/profile.md`)',
}


def _ndjson(rel):
    p = REPO / rel
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def rotate(items, day):
    """Stable daily pick: index = days since ROTATION_EPOCH mod len. None when empty."""
    if not items:
        return None
    days = (date.fromisoformat(day) - ROTATION_EPOCH).days
    return items[days % len(items)]


def rate_target_date(now):
    """The day the rating prompt is about: today from EVENING_HOUR on, else yesterday."""
    d = now.date() if now.hour >= EVENING_HOUR else now.date() - timedelta(days=1)
    return d.isoformat()


def _values_list():
    path = REPO / "1-values/values.md"
    if not path.exists():
        return []
    return [m.group(1).strip() for m in re.finditer(r"^[ \t]*\d+\.[ \t]+(\S.*)$", path.read_text(), re.M)]


def _frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    meta = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    return meta


def _vision_value(text, values):
    """First value named in bold under '## Why it matters' (visions carry no values field)."""
    m = re.search(r"^## Why it matters\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        return None
    known = {v.lower(): v for v in values}
    for name in re.findall(r"\*\*([^*]+)\*\*", m.group(1)):
        if name.strip().lower() in known:
            return known[name.strip().lower()]
    return None


def _visions(values):
    """Active visions, sorted by slug. Skips the template, README and AGENTS files."""
    out = []
    for p in sorted((REPO / "3-visions").glob("*.md")):
        if p.name in ("_template.md", "README.md", "AGENTS.md"):
            continue
        text = p.read_text()
        meta = _frontmatter(text)
        if meta.get("status") != "active":
            continue
        title = re.search(r"^# (.+)$", text, re.M)
        out.append({
            "id": p.stem,
            "title": title.group(1).strip() if title else p.stem,
            "area": meta.get("area"),
            "value": _vision_value(text, values),
        })
    return out


def _body(today):
    """Last night's sleep and whether it was a broken night."""
    row = next((r for r in _ndjson("data/day-tracking.ndjson") if r.get("date") == today), {})
    health = row.get("health") or {}
    sleep, awake = health.get("sleep_hours"), health.get("awake_minutes")
    eff = qqrt.efficiency(sleep, awake)
    broken = bool(
        (awake is not None and awake >= BROKEN_AWAKE_MINUTES)
        or (eff is not None and eff < BROKEN_EFFICIENCY_PCT)
    )
    return {"sleep_hours": sleep, "awake_minutes": awake, "broken_night": broken, "window": TREND_DAYS}


def _welcome_back(today):
    """True when the last rating AND the last daily-focus pick are both older than yesterday."""
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    rated = [r["date"] for r in _ndjson("data/day-tracking.ndjson") if r.get("rating") is not None]
    # A record with no critical picks (a skip-only record) is not a pick day.
    picked = [r["date"] for r in _ndjson("6-tasks/_data/daily-focus.ndjson") if r.get("critical")]
    return max(rated, default="") < yesterday and max(picked, default="") < yesterday


def _letter(v):
    v = (v or "").lower()
    return LETTER.get(v, v.upper() or "C")


def _code(task):
    """Ranking code: the stored priority when present, else impact letter + urgency letter."""
    return task.get("priority") or _letter(task.get("impact")) + _letter(task.get("urgency"))


def _rank(task):
    return (_code(task), task.get("deadline") or "9999-99-99", task.get("created") or "")


def _is_blocked(task, open_ids):
    return any(d in open_ids for d in task.get("depends_on") or [])


def _area_title(area):
    """Display name from 2-areas/<area>/statement.md's heading, else the id title-cased."""
    path = REPO / "2-areas" / area / "statement.md"
    if path.exists():
        m = re.search(r"^# (.+)$", path.read_text(), re.M)
        if m:
            return re.split(r"\s+[\u2014-]\s+", m.group(1).strip())[0].strip()
    return area.replace("-", " ").title()


def _area_fallback(task):
    return [_area_title(task["area"])] if task.get("area") else []


def _why_chain(task, projects, focus_rows, visions):
    """[focus title, vision title, value] by following links the records carry:
    task.project -> project.vision -> vision, and the focus whose link is that vision.
    Stops at the first missing link; never invents one (web/AGENTS.md rule 2)."""
    project = projects.get(task.get("project"))
    vision = next((v for v in visions if project and v["id"] == project.get("vision")), None)
    if not vision:
        return _area_fallback(task)
    focus = next((f for f in focus_rows
                  if (f.get("link") or {}).get("type") == "vision" and f["link"].get("ref") == vision["id"]), None)
    chain = [focus["title"]] if focus else []
    chain.append(vision["title"])
    if vision.get("value"):
        chain.append(vision["value"])
    return chain


def _row(task, ctx):
    return {"id": task["id"], "title": task["description"], "why": _why_chain(task, *ctx)}


def _needs_you(open_tasks, focus, today):
    """At most MAX_NEEDS_YOU rows: deadlines in the window (deferred tasks left out),
    then high-priority email tasks, then red focuses. A deadline row carries its ISO
    `date` for the page to format; other rows carry `date: None`."""
    limit = (date.fromisoformat(today) + timedelta(days=DEADLINE_WINDOW_DAYS)).isoformat()
    due = sorted((t for t in open_tasks
                  if not t.get("deferred") and t.get("deadline") and t["deadline"] <= limit),
                 key=lambda t: t["deadline"])
    out = [{"kind": "deadline", "id": t["id"], "title": t["description"],
            "why": "overdue since" if t["deadline"] < today else "due", "date": t["deadline"]} for t in due]
    seen = {t["id"] for t in due}
    out += [{"kind": "email", "id": t["id"], "title": t["description"], "why": f"priority {t['priority']} email",
             "date": None}
            for t in open_tasks
            if t.get("source_email_thread_id") and t.get("priority") in EMAIL_PRIORITIES and t["id"] not in seen]
    out += [{"kind": "focus", "id": f["focus_id"], "title": f["title"],
             "why": f"red for {f['weeks_red']} weeks" if f.get("weeks_red") else "red", "date": None}
            for f in focus if f["status"] == "red"]
    return out[:MAX_NEEDS_YOU]


def _tag_picks(home, open_tasks, today):
    """A task can be one of today's picks and a needs_you row at once. Tag each needs_you
    row with `in_picks` ('critical', 'bonus' or None) and give each of today's picks a
    `flag`: that row's {why, date} when it has one, else None. The page leaves the row
    out and shows the flag on the pick, so one task has one Done. needs_you itself is
    unchanged for every surface."""
    picks = home["picks"]
    which = {}
    if picks:
        which = {tid: "critical" for tid in picks["critical_ids"]}
        if picks["bonus_id"]:
            which[picks["bonus_id"]] = "bonus"
    for n in home["needs_you"]:
        n["in_picks"] = which.get(n["id"]) if n["kind"] != "focus" else None
    if not picks:
        return
    hidden = {n["id"]: n for n in home["needs_you"] if n["in_picks"]}
    for p in picks["critical"] + ([picks["bonus"]] if picks["bonus"] else []):
        n = hidden.get(p["id"])
        p["flag"] = {"why": n["why"], "date": n["date"]} if n and n.get("date") else None


def _due_review(today):
    """Never done first, then most overdue."""
    due = _due_reviews(today)
    if not due:
        return None
    due.sort(key=lambda x: (x[0] is not None, -(x[0] or 0)))
    r = due[0][1]
    return {"id": r["id"], "label": r["label"], "skill": REVIEW_SKILLS.get(r["id"])}


def _due_reviews(today):
    """Every rolling review that is due today: [(days overdue or None if never done, row)]."""
    due = []
    for r in _ndjson("data/review-ledger.ndjson"):
        if not r.get("last_done"):
            due.append((None, r))
            continue
        overdue = (date.fromisoformat(today) - date.fromisoformat(r["last_done"])).days - r["cadence_days"]
        if overdue >= 0:
            due.append((overdue, r))
    return due


def _picks(pick_date, tasks_by_id, ctx):
    """The day's picks, each with `done` from the daily-focus record itself."""
    rec = next((r for r in _ndjson("6-tasks/_data/daily-focus.ndjson") if r.get("date") == pick_date), None)
    if not rec or not rec.get("critical"):  # no record, or one that only lists skips: no picks set
        return None
    completed = set(rec.get("completed") or [])
    def item(tid, done):
        t = tasks_by_id.get(tid)
        return {**_row(t, ctx), "done": done} if t and t.get("agent_doable") != "yes" else None
    critical = [item(tid, tid in completed) for tid in rec.get("critical") or []]
    return {"critical": [i for i in critical if i],
            "bonus": item(rec["bonus"], rec.get("bonus_completed") is True) if rec.get("bonus") else None,
            # The record's ids as stored, so a page adding picks sends every one back.
            "critical_ids": list(rec.get("critical") or []), "bonus_id": rec.get("bonus") or None}


def _live(focus_row):
    """A foundation or pursuit that is not parked: the focuses the page offers as today's."""
    return focus_row.get("tier") in ("foundation", "pursuit") and not focus_row.get("parked")


def _linked_vision(focus_record, visions):
    link = (focus_record or {}).get("link") or {}
    if link.get("type") != "vision":
        return None
    return next((v for v in visions if v["id"] == link.get("ref")), None)


def _focus_projects(focus_id, focus_record, projects, visions):
    """Active projects that name this focus (project.focus) or the vision it links to
    (project.vision), id and name. Only links the records carry; none is invented."""
    vision = _linked_vision(focus_record, visions)
    return [{"id": p["id"], "name": p.get("name") or p["id"]} for p in projects.values()
            if p.get("status") == "active"
            and (p.get("focus") == focus_id or (vision and p.get("vision") == vision["id"]))]


def _focus_of_day(focus, focus_links, visions, today):
    """One live focus per day, rotating in id order, with its linked vision and that vision's value."""
    live = sorted((f for f in focus if _live(f)), key=lambda f: f["focus_id"])
    f = rotate(live, today)
    if not f:
        return None
    vision = _linked_vision(focus_links.get(f["focus_id"]), visions)
    return {"id": f["focus_id"], "title": f["title"],
            "vision": vision["title"] if vision else None, "value": vision.get("value") if vision else None}


HABIT_KEYS = ("id", "title", "description", "auto_derived", "cadence", "logged_today", "logged_yesterday")
STALE_AREA_DAYS = 31
REPICK_PURSUITS = 6
REPICK_RED_WEEKS = 4  # 28 days
PROJECT_CLOSED = ("done", "dropped", "parked")


def _habits(today):
    """Every active daily and monthly habit, in habit_rows order."""
    import yaml
    from web_data import habit_rows

    schema = yaml.safe_load((REPO / "config/habit_schema.yaml").read_text()) or {}
    rows = habit_rows(schema, _ndjson("7-habits/_data/habits-daily.ndjson"),
                      _ndjson("7-habits/_data/habits-monthly.ndjson"), today)
    # title_plain: the page's name, acronyms spelled out (HABIT_PLAIN); `title` stays
    # as it is for the TRMNL and Trello surfaces that read it.
    return [{**{k: r[k] for k in HABIT_KEYS}, "title_plain": _plain_title(r["title"])} for r in rows]


# Acronyms in habit titles that the web page spells out, e.g. {"HIIT": "Interval training"}.
HABIT_PLAIN = {}


def _plain_title(title):
    return " ".join(HABIT_PLAIN.get(w, w) for w in title.split(" "))


def _questions():
    """The numbered lines under '## Current Questions' in 0-me/questions.md."""
    path = REPO / "0-me/questions.md"
    if not path.exists():
        return []
    m = re.search(r"^## Current Questions\n(.*?)(?=^## |\Z)", path.read_text(), re.S | re.M)
    if not m:
        return []
    return [{"n": int(n), "text": t.strip()}
            for n, t in re.findall(r"^(\d+)\.\s+(.+)$", m.group(1), re.M)]


def _label(key):
    return key.replace("_", " ").capitalize()


def _lights(rel, today):
    """The latest row of a ratings file as {date, stale, rows}, red first, then yellow, then green."""
    rows = _ndjson(rel)
    if not rows:
        return {"date": None, "stale": True, "rows": []}
    # Newest date, then the later line: the same row pfc_writes.set_rating copies and edits.
    latest = max(enumerate(rows), key=lambda p: (p[1].get("date") or "", p[0]))[1]
    age = (date.fromisoformat(today) - date.fromisoformat(latest["date"])).days
    notes = latest.get("notes") or {}
    out = [{"key": k, "label": _label(k), "light": v, "note": notes.get(k) or None}
           for k, v in (latest.get("ratings") or {}).items()]
    out.sort(key=lambda r: FOCUS_ORDER.get(r["light"], 3))
    return {"date": latest["date"], "stale": age > STALE_AREA_DAYS, "rows": out}


def _areas(today):
    """The life wheel's areas with their items (area_items.py): each row's light is the
    rollup of its items' lights, or its manual life-wheel light when no item has data.
    The band's date is the newer of the wheel snapshot and the newest check-in, and it
    is stale past STALE_AREA_DAYS like the wheel was. Returns (areas, plate)."""
    import area_items
    wheel = _lights("2-areas/_data/life-wheel.ndjson", today)
    res = area_items.build(REPO, today, wheel)
    newest = max((d for d in (wheel["date"], res["checked"]) if d), default=None)
    stale = newest is None or (date.fromisoformat(today) - date.fromisoformat(newest)).days > STALE_AREA_DAYS
    for row in res["rows"]:
        row["why"] = _area_why(row)
    return {"date": newest, "stale": stale, "rows": res["rows"]}, res["plate"]


def household_parked():
    """True while the household rooms are parked (`household_parked: true` in
    config/automation_config.yaml, for a stretch when nobody tracks the rooms)."""
    try:
        import yaml
        cfg = yaml.safe_load((REPO / "config/automation_config.yaml").read_text()) or {}
    except Exception:  # noqa: BLE001 — a missing or broken config shows the rooms
        return False
    return bool(cfg.get("household_parked"))


def _area_why(row):
    """Why an area is the colour it is, in one line, for every surface (web, Trello,
    TRMNL). An area lit by its items: the items at least as bad as the
    area, worst and heaviest first, each with its own why. A manual light: its note."""
    if row.get("source") != "items":
        return row.get("note") or "set by hand"
    if row.get("light") == "green":
        return "every item on track"
    rank = {"red": 0, "yellow": 1, "green": 2}
    worst = rank.get(row.get("light"), 2)
    drivers = sorted((i for i in row.get("items") or [] if rank.get(i.get("light"), 3) <= worst),
                     key=lambda i: (rank[i["light"]], -(i.get("weight") or 0)))
    return "; ".join(f"{i['title']}: {i['why']}" for i in drivers[:2]) or "from its items"


def _focuses(focus):
    tiers = {"foundation": [], "pursuit": [], "consuming": []}
    for f in focus:
        if f.get("tier") in tiers:
            tiers[f["tier"]].append({**f, "light": f["status"]})
    return tiers


def _repick_nudge(focus):
    """Six live pursuits and any of them red for four weeks or more."""
    live = [f for f in focus if f.get("tier") == "pursuit" and not f.get("parked")]
    if len(live) < REPICK_PURSUITS:
        return False
    return any(f["status"] == "red" and f["weeks_red"] >= REPICK_RED_WEEKS for f in live)


def _active_projects(projects):
    return [p for p in projects if p.get("active") is True and p.get("status") not in PROJECT_CLOSED]


def _projects(projects, ready, tasks=(), events=(), today=None):
    """Active projects (flag set, not done, dropped or parked) and the rest (not done or dropped), on-deck first, parked last.

    Active rows also carry the project gauges from project_gauges.py (the one home of
    both rules): `pace` (parts a week, one decimal), `est_finish`, `days_late` and the
    on-time `light` (None without a deadline), and `days_idle` with `stalled` at
    STALLED_PROJECT_DAYS. The web band shows percent and next task."""
    import project_gauges

    def row(p):
        total = p.get("total_parts") or 0
        task = next((t for t in ready if t.get("project") == p["id"]), None)
        return {"id": p["id"], "name": p.get("name") or p["id"], "area": p.get("area"),
                "status": p.get("status") or ("active" if p.get("active") else "on-deck"),
                "pct": round(100 * (p.get("completed_parts") or 0) / total) if total else 0,
                "next_task": {"id": task["id"], "title": task["description"]} if task else None}

    def gauged(p):
        out = row(p)
        if today is None:
            return out
        day = date.fromisoformat(today)
        v = project_gauges.velocity(p, day)
        idle = project_gauges.days_idle(p, tasks, events, day)
        stalled = idle is not None and idle >= STALLED_PROJECT_DAYS
        out.update({"pace": round(v["parts_per_week"], 1) if v["parts_per_week"] is not None else None,
                    "est_finish": v["estimated_completion"], "days_late": v["days_late"], "light": v["light"],
                    "days_idle": idle, "stalled": stalled,
                    # Stalled for CHRONIC_DAYS more: idle 28 days or more.
                    "chronic": stalled and idle >= STALLED_PROJECT_DAYS + CHRONIC_DAYS})
        return out

    active = _active_projects(projects)
    rest = [p for p in projects if p not in active and p.get("status") not in ("done", "dropped")]
    rest.sort(key=lambda p: 1 if p.get("status") == "parked" else 0)
    rows = [gauged(p) for p in active]
    if today is not None:
        _mark_chronic(rows, lambda p: p["days_idle"])
    return {"active": rows, "other": [row(p) for p in rest]}


TREND_DAYS = 30
STALLED_PROJECT_DAYS = 14
# A red that has held this long is long-running ("chronic"): the page folds those into
# one count line so a red that is new stands out. Two weeks, the same span as the
# stalled-project rule: a focus red 2+ weeks, a project stalled 14 more days (idle 28+),
# a sleep lever red on at least half of the last 14 nights.
CHRONIC_DAYS = 14


def _mark_chronic(rows, worst):
    """Set `chronic_lead` on the worst chronic row (highest `worst(row)`, first in list
    order on a tie) and False on every other row. Rows already carry `chronic`."""
    lead = None
    for r in rows:
        if r["chronic"] and (lead is None or worst(r) > worst(lead)):
            lead = r
    for r in rows:
        r["chronic_lead"] = r is lead
    return rows
TREND_LIGHT_ORDER = {"red": 0, "yellow": 1, "green": 2}


def _window(today):
    end = date.fromisoformat(today)
    return {(end - timedelta(days=i)).isoformat() for i in range(TREND_DAYS)}


def _pulse(today):
    """Last night's levers, each with its nights on target over the last TREND_DAYS
    (`on` of `n`), so Body first carries both today's reading and the 30-day one."""
    import trmnl_push
    pulse = trmnl_push.build_pfc_pulse({}, today)
    month = {lv["label"]: lv for lv in trmnl_push.build_pfc_pulse_trend({}, today)["levers"]}
    for lv in pulse["levers"]:
        m = month.get(lv["label"])
        lv["on"], lv["n"] = (m["on"], m["n"]) if m else (None, None)
    # Red nights over the last CHRONIC_DAYS tracked nights: a lever red last night and on
    # at least half of them is long-running, not new.
    import pulse as pulse_rules
    hist = pulse_rules.pulse_history(_ndjson("data/day-tracking.ndjson"), CHRONIC_DAYS)
    recent = {s["label"]: s["statuses"] for s in (hist or {}).get("series", {}).values()}
    for lv in pulse["levers"]:
        statuses = recent.get(lv["label"]) or []
        lv["red_nights"] = sum(1 for x in statuses if x == "\U0001F534")
        lv["nights"] = len(statuses)
        lv["chronic"] = lv["mark"] == "RED" and bool(statuses) and lv["red_nights"] * 2 >= len(statuses)
    _mark_chronic(pulse["levers"], lambda lv: lv["red_nights"])
    for lv in pulse["levers"]:
        lv["label_plain"] = LEVER_PLAIN.get(lv["label"], lv["label"])
        lv["target_words"] = target_words(lv["target"])
    return pulse


# Lever names the page spells out (acronyms spelled out). The e-ink and Trello keep
# `label`; the web page shows `label_plain`.
LEVER_PLAIN = {"QQRT score": "Sleep score (quantity, quality, timing)", "REM": "Dream sleep (REM)"}


def _amount(text):
    """One e-ink amount as words: '10m' -> '10 min', '7.4h' -> '7.4 hours', '2x' -> '2 times'."""
    m = re.fullmatch(r"([\d.]+)\s*(m|h|x|pt)?", text.strip())
    if not m:
        return text.strip()
    n, unit = m.group(1), m.group(2)
    one = n == "1"
    return {None: n, "m": f"{n} min", "h": f"{n} hour" if one else f"{n} hours",
            "x": f"{n} time" if one else f"{n} times", "pt": f"{n} point" if one else f"{n} points"}[unit]


def target_words(target):
    """A lever's e-ink target ('<=10m, 70m to yellow', trmnl_push._ascii) as plain words
    for the web page: '10 min or less, 70 min short of yellow'. A clock time reads
    'by 6:45 AM'; a count reads 'or fewer'."""
    m = re.fullmatch(r"(<=|>=)?\s*([^,]*?)(?:,\s*(.+?) to (yellow|green))?", (target or "").strip())
    if not m or not m.group(2):
        return (target or "").strip()
    op, amount, gap, tier = m.groups()
    if re.search(r"\b(AM|PM)$", amount):
        words = f"by {amount}" if op == "<=" else f"{amount} or later" if op == ">=" else amount
    else:
        less = "or fewer" if amount.endswith("x") else "or less"
        words = _amount(amount) + (f" {less}" if op == "<=" else " or more" if op == ">=" else "")
    return f"{words}, {_amount(gap)} short of {tier}" if gap else words


RATING_TRENDS = [("rating", "Day rating"), ("energy", "Energy"), ("mood", "Mood"), ("focus", "Focus")]


def _trends(today):
    """How the last 30 days turned out, red first: the day rating, energy, mood and
    focus averages, and picks done. Sleep is an input, so it lives in Body first
    (`_pulse`, `_body`), not here."""
    days = _window(today)
    rows = [r for r in _ndjson("data/day-tracking.ndjson") if r.get("date") in days]
    out = []
    for key, name in RATING_TRENDS:
        vals = [r[key] for r in rows if isinstance(r.get(key), (int, float))]
        if vals:
            avg = sum(vals) / len(vals)
            light = "green" if avg >= 4 else "yellow" if avg >= 3 else "red"
            why = f"avg {round(avg, 1)} over {len(vals)} rated days"
        else:
            light, why = "red", "no rated days in 30"
        out.append({"name": name, "light": light, "why": why})

    recs = [r for r in _ndjson("6-tasks/_data/daily-focus.ndjson") if r.get("date") in days]
    total = sum(len(r.get("critical") or []) for r in recs)
    done = sum(len(set(r.get("critical") or []) & set(r.get("completed") or [])) for r in recs)
    pct = 100 * done / total if total else 0
    out.append({"name": "Picks done", "light": "green" if pct >= 70 else "yellow" if pct >= 40 else "red",
                "why": f"{done} of {total} critical picks done"})

    out.sort(key=lambda t: TREND_LIGHT_ORDER[t["light"]])
    return out


def _week(today):
    """The next 7 days from data/calendar-cache.json (week_days)."""
    path = REPO / "data/calendar-cache.json"
    if not path.exists():
        return []
    try:
        events = json.loads(path.read_text()).get("events") or []
    except (OSError, ValueError):
        return []
    return week_days(events, today)


def week_days(events, today):
    """The next 7 days of `events` (Google Calendar event dicts), filtered like the TRMNL
    week screen: [{date, events: [{start, title}]}], all-day events first in a day.
    Multi-day all-day events appear on every day they cover (their end date is exclusive).
    The web Week band reads the cache through _week."""
    import trello_render
    filters = trello_render.load_calendar_filters()
    first = date.fromisoformat(today)
    days = {(first + timedelta(days=i)).isoformat(): [] for i in range(7)}
    for ev in events:
        if trello_render.calendar_event_excluded(ev, filters):
            continue
        start = ev.get("start") or {}
        title = ev.get("summary") or ""
        if start.get("dateTime"):
            if start["dateTime"][:10] in days:
                days[start["dateTime"][:10]].append({"start": start["dateTime"], "title": title})
        elif start.get("date"):
            begin = date.fromisoformat(start["date"][:10])
            stop = ((ev.get("end") or {}).get("date") or "")[:10]
            last = date.fromisoformat(stop) - timedelta(days=1) if stop else begin
            for i in range(max((last - begin).days, 0) + 1):
                d = (begin + timedelta(days=i)).isoformat()
                if d in days:
                    days[d].append({"start": None, "title": title})
    for evs in days.values():
        evs.sort(key=lambda e: (e["start"] is not None, e["start"] or ""))
    return [{"date": d, "events": evs} for d, evs in days.items()]


def _focus_record(day):
    return next((r for r in _ndjson("6-tasks/_data/daily-focus.ndjson") if r.get("date") == day), {})


def _not_offered(day):
    """Ids the day's record already holds: its skips, its picks and its bonus."""
    rec = _focus_record(day)
    return {*(rec.get("skipped") or []), *(rec.get("critical") or []), *([rec["bonus"]] if rec.get("bonus") else [])}


def _all_picks_done(day):
    """At least one critical pick on that day, and every one of them completed."""
    rec = _focus_record(day)
    critical = rec.get("critical") or []
    return bool(critical) and set(critical) <= set(rec.get("completed") or [])


def _tour_look(areas, focus, active_projects, tasks, today):
    """The one thing the home page asks the user to look at (a row in What needs you): stale life wheel, else a red live focus,
    else an active project idle STALLED_PROJECT_DAYS or more (project_gauges.days_idle)."""
    import project_gauges
    if areas["stale"]:
        return {"kind": "stale_areas", "title": "Life wheel",
                "detail": "last rated" if areas["date"] else "never rated", "date": areas["date"]}
    red = next((f for f in focus if f["status"] == "red" and _live(f)), None)
    if red:
        weeks = red.get("weeks_red")
        return {"kind": "red_focus", "title": red["title"], "detail": f"red for {weeks} weeks" if weeks else "red",
                "date": None}
    events = _ndjson("6-tasks/_data/task_events.ndjson")
    today_d = date.fromisoformat(today)
    for p in active_projects:
        idle = project_gauges.days_idle(p, tasks, events, today_d)
        if idle is not None and idle >= STALLED_PROJECT_DAYS:
            return {"kind": "stalled_project", "title": p.get("name") or p["id"], "detail": f"{idle} days idle",
                    "date": None}
    return None


def auto_picks(home, record):
    """The 2+1 the system sets for today when the user has set none (trello_writeback's
    auto-pick): the home page's suggestions (`suggested`) taken the way the suggestions
    card takes taps, the first two critical and a third the bonus.

    Returns (critical, bonus), or None: in the evening (the suggestions card sets tomorrow
    then), when today's record already holds a pick or a bonus (the user's picks are never
    overwritten), when a pick was dropped today on Trello, once the system has picked
    the day (`source: "auto"`), or with nothing to suggest. `record` is today's
    daily-focus record or None; a record holding only skips still gets picks."""
    record = record or {}
    if home["evening"] or record.get("critical") or record.get("bonus") or record.get("dropped") \
            or record.get("source") == "auto":
        return None
    ids = [t["id"] for t in home["suggested"]]
    if not ids:
        return None
    return ids[:2], (ids[2] if len(ids) > 2 else None)


def daily_sync(env, now):
    """Last finished run of scripts/daily-sync.sh, from the last DONE line of its log.
    `ok` is fail == 0. Stale when there is no DONE line or it is over SYNC_STALE_HOURS old."""
    path = Path(env.get("PFC_DAILY_SYNC_LOG") or os.environ.get("PFC_DAILY_SYNC_LOG") or DEFAULT_SYNC_LOG)
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        lines = []
    for line in reversed(lines):
        m = SYNC_DONE.match(line)
        if m:
            when = datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}")
            return {"last_run": when.isoformat(), "ok": int(m.group(4)) == 0,
                    "stale": now - when > timedelta(hours=SYNC_STALE_HOURS)}
    return {"last_run": None, "ok": None, "stale": True}


def sync_needs_look(sync):
    """The sync needs a look when it failed, has gone stale, or never ran: the same
    states the footer words in red. The home page then lists it under What needs you."""
    return not (sync["ok"] and not sync["stale"])


def build_home(env, now):
    today = now.date().isoformat()
    values = _values_list()
    visions = _visions(values)
    vod = rotate(visions, today)
    target = rate_target_date(now)
    target_row = next((r for r in _ndjson("data/day-tracking.ndjson") if r.get("date") == target), {})
    anchors = [g for g in _ndjson("data/grounding.ndjson")
               if g.get("status") == "active" and not g.get("retired_date")]
    questions = _questions()
    # Impact/urgency code first (AA before AB), red first only as the tiebreak: the
    # Focus list's priority scheme (root AGENTS.md), same order as Trello's render_focus.
    focus = sorted(status_rows(REPO, today),
                   key=lambda r: (r.get("code") or "CC", FOCUS_ORDER.get(r["status"], 3)))
    tasks = _ndjson("6-tasks/_data/tasks.ndjson")
    open_tasks = [t for t in tasks if t.get("status") == "open"]
    open_ids = {t["id"] for t in open_tasks}
    projects = {p["id"]: p for p in _ndjson("5-projects/_data/projects.ndjson")}
    focus_links = {f["id"]: f for f in _ndjson("4-focus/_data/focus.ndjson")}
    focus_rows = [{**focus_links.get(f["focus_id"], {}), "title": f["title"]} for f in focus]
    ctx = (projects, focus_rows, visions)
    by_id = {t["id"]: t for t in tasks + _ndjson("6-tasks/_data/tasks-archive.ndjson")}
    # Deferred tasks are parked out of every pick pool (config/task_schema.yaml `deferred`).
    ready = sorted((t for t in open_tasks if not t.get("deferred") and not _is_blocked(t, open_ids)), key=_rank)
    evening = now.hour >= EVENING_HOUR
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    # The day the suggestions card sets: tomorrow from EVENING_HOUR on, else today.
    pick_date = tomorrow if evening else today
    needs_you = _needs_you(open_tasks, focus, today)

    def suggest(day, count):
        """Ready tasks an agent cannot finish, minus the ids that day's record already
        holds (`skipped`, the picks and the bonus)."""
        held = _not_offered(day)
        return [_row(t, ctx) for t in ready
                if t.get("agent_doable") != "yes" and t["id"] not in held][:count]

    areas, plate = _areas(today)
    body = _body(today)
    focus = [{**f, "projects": _focus_projects(f["focus_id"], focus_links.get(f["focus_id"]), projects, visions),
              # Red CHRONIC_DAYS or more (weeks_red counts whole red weeks, capped at 8).
              "chronic": f["status"] == "red" and not f.get("parked") and f.get("weeks_red", 0) * 7 >= CHRONIC_DAYS}
             for f in focus]
    for tier in {f.get("tier") for f in focus}:
        _mark_chronic([f for f in focus if f.get("tier") == tier], lambda f: f["weeks_red"])
    home = {
        "date": today,
        "evening": evening,
        "values": values,
        "visions": [{k: v[k] for k in ("id", "title", "area")} for v in visions],
        "vision_of_day": {k: vod[k] for k in ("id", "title", "value")} if vod else None,
        "focus": focus,
        "focus_of_day": _focus_of_day(focus, focus_links, visions, today),
        "body": body,
        "focuses": _focuses(focus),
        "repick_nudge": _repick_nudge(focus),
        "questions": questions,
        "question_of_day": rotate(questions, today),
        "areas": areas,
        # Free waking hours against the time items' hours this week (area_items.py), or None without items.
        "plate": plate,
        # None while parked (config/automation_config.yaml household_parked).
        "household": None if household_parked() else _lights("2-areas/_data/household-status.ndjson", today),
        "projects": _projects(list(projects.values()), ready, tasks, _ndjson("6-tasks/_data/task_events.ndjson"), today),
        "habits": _habits(today),
        "needs_you": needs_you,
        "due_review": None if needs_you else _due_review(today),
        # How many rolling reviews are due, the home page's one included.
        "reviews_due": len(_due_reviews(today)),
        "pick_date": pick_date,
        # Today's record all day, so its Done buttons stay through the evening.
        "picks": _picks(today, by_id, ctx),
        # Tomorrow's record, from EVENING_HOUR on only: what the 2+1 band shows then.
        "tomorrow_picks": _picks(tomorrow, by_id, ctx) if evening else None,
        # Every critical pick for today is done, so the page offers more work for today.
        "all_picks_done": _all_picks_done(today),
        # Suggestions for pick_date, kept filled once today's picks are all done, so the
        # page can always offer a full 2+1.
        "suggested": suggest(pick_date, SUGGESTED_COUNT),
        "handoffs": [_row(t, ctx) for t in ready if t.get("agent_doable") == "yes"][:HANDOFF_COUNT],
        "offer_open_day": evening and now.weekday() in (4, 5),
        "rate_target": {"date": target, "unrated": target_row.get("rating") is None},
        "welcome_back": _welcome_back(today),
        "anchors": [{"id": g["id"], "title": g["title"]} for g in anchors],
        "pulse": _pulse(today),
        "trends": _trends(today),
        "week": _week(today),
        "tour_look": _tour_look(areas, focus, _active_projects(list(projects.values())), tasks, today),
        "daily_sync": daily_sync(env, now),
    }
    home["sync_needs_look"] = sync_needs_look(home["daily_sync"])
    _tag_picks(home, open_tasks, today)
    # The one due review is the one every surface shows (review_forms.current_review:
    # never done, then most overdue, skipping one with nothing to ask), so the home
    # card, the /review page and `/pfc-review` in chat always name the same one.
    if home["due_review"] is not None:
        try:
            import review_forms
            r = review_forms.current_review(home, today, repo=REPO)
            home["due_review"] = {"id": r["id"], "label": r["label"], "skill": REVIEW_SKILLS.get(r["id"])} if r else None
        except Exception:  # noqa: BLE001 — the cadence-only pick stands
            pass
    return home
