#!/usr/bin/env python3
"""Data for the one-page web UI home (web/src/lib/computed.ts).

    python3 automations/scripts/web_data.py --home [--today YYYY-MM-DD]

Every rule behind a number on the home page lives here or in the script it calls
(focus_status.py for traffic lights), never in TypeScript. `build_home` returns one
dict; later tasks add keys to it.
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
from pfc_writes import EXERCISE_HABIT_ID, EXERCISE_LABEL  # noqa: E402

REPO = SCRIPT_DIR.parents[1]

EVENING_HOUR = 18  # from this hour on, "rate your day" means today, not yesterday
BROKEN_AWAKE_MINUTES = 60  # this much awake time breaks a night
BROKEN_EFFICIENCY_PCT = 85  # sleep efficiency below this also breaks a night
ROTATION_EPOCH = date(2026, 1, 1)
FOCUS_ORDER = {"red": 0, "yellow": 1, "green": 2}

SYNC_STALE_HOURS = 30  # the job runs daily at 5:00 AM; a day and a few hours late is a miss
DEFAULT_SYNC_LOG = "/tmp/pfc-daily-sync.log"
SYNC_DONE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) DONE ok=(\d+) fail=(\d+)\s*$")

MAX_NEEDS_YOU = 2
DEADLINE_WINDOW_DAYS = 2
EMAIL_PRIORITIES = ("AA", "AB", "BA")
SUGGESTED_COUNT = 3
HANDOFF_COUNT = 3
LETTER = {"high": "A", "medium": "B", "low": "C"}

# Owning skill or action per rolling-review id (the rolling-review gates `/pfc-review` runs)
REVIEW_SKILLS = {
    'stale-task-triage': '`/pfc-revive` — walk the slipped watchlist',
    'tasks-missing-area': 'assign an area to the flagged open tasks (edit `tasks.ndjson` / `/pfc-add-task` shape)',
    'focus-accuracy': '`/pfc-focus` — eyeball traffic-lights + landings',
    'vision-relevance': 'open one file in `3-visions/` and sanity-check it still fits',
    'habit-rate': 'show trailing-7 completion per habit (from `7-habits/_data/habits-daily.ndjson`)',
    'values-alignment': 'add `values` to the flagged active project(s) in `projects.ndjson`',
    'day-trend-peek': 'quick eyeball of the last 7 day ratings (light `/pfc-analyze-trends`)',
    'life-wheel': 'rate the life areas (updates `2-areas/_data/life-wheel.ndjson`)',
    'project-progress': '`/pfc-summarize-project` per active project',
    'vision-activation': '`/pfc-focus` — lean-in / let-rest per vision',
    'monthly-habits': 'show monthly-habit completion (`7-habits/_data/habits-monthly.ndjson`)',
    'insights-review': '`/pfc-insights` — triage active insights',
    'household-status': 'rate the household rooms (updates `2-areas/_data/household-status.ndjson`)',
    'findings-alignment': 'check that active projects and habits still agree with `data/findings.ndjson`',
    'hypotheses-review': 'review active hypotheses in `data/hypotheses.ndjson` — update `last_reviewed`; graduate to a finding if the bar is met (n≥30/\\|r\\|≥0.3/p<0.01, or a clear lived-experience pattern). **Never auto-archive** — surface for a look, the user decides',
    'trend-analysis': '`/pfc-analyze-trends` — full statistical pass',
    'revive-outcomes': '`/pfc-revive` — review outcomes of revived items ≥30d old',
    'usage-audit': '`/pfc-usage-audit` — is the system being used: data freshness, logging gaps, unused surfaces',
    'focus-repick': '`/pfc-focus` — quarterly re-pick',
    'vision-brainstorm': '`/pfc-vision-brainstorm`',
    'strengths-refresh': 'quarterly strengths and profile refresh (`0-me/profile.md`)',
}


def _ndjson(rel):
    p = REPO / rel
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def rotate(items, day):
    """Stable daily pick: index = days since 2026-01-01 mod len. None when empty."""
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
    # Numbered lines only, so a bulleted suggestion menu is skipped. `[ \t]` and not
    # `\s`: an empty numbered line ("2." on its own) must not reach across the line
    # break and take the next line as its value.
    # Bold markers are dropped, so "1. **Health**" reads as Health.
    return [m.group(1).replace("**", "").strip()
            for m in re.finditer(r"^[ \t]*\d+\.[ \t]+(\S.*)$", path.read_text(), re.M)]


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
    """Active visions, sorted by slug. Skips `_`-prefixed files (the template) and the README and AGENTS files."""
    out = []
    for p in sorted((REPO / "3-visions").glob("*.md")):
        if p.name.startswith("_") or p.name in ("README.md", "AGENTS.md", "CLAUDE.md"):
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
    row = next((r for r in _ndjson("data/day-tracking.ndjson") if r.get("date") == today), {})
    health = row.get("health") or {}
    sleep, awake = health.get("sleep_hours"), health.get("awake_minutes")
    eff = qqrt.efficiency(sleep, awake)
    broken = bool(
        (awake is not None and awake >= BROKEN_AWAKE_MINUTES)
        or (eff is not None and eff < BROKEN_EFFICIENCY_PCT)
    )
    logs = _ndjson("7-habits/_data/habits-daily.ndjson")
    exercised = any(
        r.get("habit_id") == EXERCISE_HABIT_ID and r.get("date") == today and r.get("completed") is True
        for r in logs
    )
    days = _window(today)
    exercised_days = len({r["date"] for r in logs
                          if r.get("habit_id") == EXERCISE_HABIT_ID and r.get("completed") is True
                          and r.get("date") in days})
    return {"sleep_hours": sleep, "awake_minutes": awake, "broken_night": broken, "exercised": exercised,
            "exercise_label": EXERCISE_LABEL, "exercised_days": exercised_days,
            "exercise_light": _exercise_light(exercised_days), "window": TREND_DAYS}


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


def _due_review(today):
    """Never done first, then most overdue."""
    due = []
    for r in _ndjson("data/review-ledger.ndjson"):
        if not r.get("last_done"):
            due.append((None, r))
            continue
        overdue = (date.fromisoformat(today) - date.fromisoformat(r["last_done"])).days - r["cadence_days"]
        if overdue >= 0:
            due.append((overdue, r))
    if not due:
        return None
    due.sort(key=lambda x: (x[0] is not None, -(x[0] or 0)))
    r = due[0][1]
    return {"id": r["id"], "label": r["label"], "skill": REVIEW_SKILLS.get(r["id"])}


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
    return [{k: r[k] for k in HABIT_KEYS} for r in rows]


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


def _projects(projects, ready):
    """Active projects (flag set, not done, dropped or parked) and the rest (not done or dropped), on-deck first, parked last."""
    def row(p):
        total = p.get("total_parts") or 0
        task = next((t for t in ready if t.get("project") == p["id"]), None)
        return {"id": p["id"], "name": p.get("name") or p["id"], "area": p.get("area"),
                "status": p.get("status") or ("active" if p.get("active") else "on-deck"),
                "pct": round(100 * (p.get("completed_parts") or 0) / total) if total else 0,
                "next_task": {"id": task["id"], "title": task["description"]} if task else None}
    active = _active_projects(projects)
    rest = [p for p in projects if p not in active and p.get("status") not in ("done", "dropped")]
    rest.sort(key=lambda p: 1 if p.get("status") == "parked" else 0)
    return {"active": [row(p) for p in active], "other": [row(p) for p in rest]}


TREND_DAYS = 30
STALLED_PROJECT_DAYS = 14
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
    return pulse


RATING_TRENDS = [("rating", "Day rating"), ("energy", "Energy"), ("mood", "Mood"), ("focus", "Focus")]


def _trends(today):
    """How the last 30 days turned out, red first: the day rating, energy, mood and
    focus averages, and picks done. Sleep and exercise are inputs, so they live in
    Body first (`_pulse`, `_body`), not here."""
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


def _exercise_light(days_done):
    """Green at the habit's weekly frequency pace over the window, yellow at half of it."""
    import yaml
    schema = yaml.safe_load((REPO / "config/habit_schema.yaml").read_text()) if (REPO / "config/habit_schema.yaml").exists() else {}
    freq = next((h.get("frequency") for h in (schema or {}).get("daily_habits") or []
                 if h.get("id") == EXERCISE_HABIT_ID), None)
    # A habit with no weekly frequency is a daily one: seven days a week.
    target = (freq if isinstance(freq, (int, float)) else 7) * TREND_DAYS / 7
    return "green" if days_done >= target else "yellow" if days_done >= target / 2 else "red"


def _week(today):
    """The next 7 days from data/calendar-cache.json, filtered like the TRMNL week screen.
    Multi-day all-day events appear on every day they cover (their end date is exclusive)."""
    import trello_render
    path = REPO / "data/calendar-cache.json"
    if not path.exists():
        return []
    try:
        events = json.loads(path.read_text()).get("events") or []
    except (OSError, ValueError):
        return []
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
    """The one thing the tour asks you to look at: stale life wheel, else a red live focus,
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
    focus = sorted(status_rows(REPO, today), key=lambda r: FOCUS_ORDER.get(r["status"], 3))
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
    # The day the picks step sets: tomorrow from EVENING_HOUR on, else today.
    pick_date = tomorrow if evening else today
    needs_you = _needs_you(open_tasks, focus, today)

    def suggest(day, count):
        """Ready tasks an agent cannot finish, minus the ids that day's record already
        holds (`skipped`, the picks and the bonus)."""
        held = _not_offered(day)
        return [_row(t, ctx) for t in ready
                if t.get("agent_doable") != "yes" and t["id"] not in held][:count]

    areas = _lights("2-areas/_data/life-wheel.ndjson", today)
    body = _body(today)
    # Today's body says a one-pick day; tomorrow's body is not known yet.
    single_pick = pick_date == today and bool(body["broken_night"] or not body["exercised"])
    focus = [{**f, "projects": _focus_projects(f["focus_id"], focus_links.get(f["focus_id"]), projects, visions)} for f in focus]
    return {
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
        "household": _lights("2-areas/_data/household-status.ndjson", today),
        "projects": _projects(list(projects.values()), ready),
        "habits": _habits(today),
        "needs_you": needs_you,
        "due_review": None if needs_you else _due_review(today),
        "pick_date": pick_date,
        # Today's record all day, so its Done buttons stay through the evening.
        "picks": _picks(today, by_id, ctx),
        # Tomorrow's record, from EVENING_HOUR on only: what the picks step shows then.
        "tomorrow_picks": _picks(tomorrow, by_id, ctx) if evening else None,
        # Every critical pick for today is done, so the page offers more work for today.
        "all_picks_done": _all_picks_done(today),
        # Suggestions for pick_date, kept filled once today's picks are all done. A
        # one-pick day offers one suggestion, not three.
        "suggested": suggest(pick_date, 1 if single_pick else SUGGESTED_COUNT),
        "handoffs": [_row(t, ctx) for t in ready if t.get("agent_doable") == "yes"][:HANDOFF_COUNT],
        "single_pick": single_pick,
        "offer_open_day": evening and now.weekday() in (4, 5),
        "rate_target": {"date": target, "unrated": target_row.get("rating") is None},
        "welcome_back": _welcome_back(today),
        "anchors": [{"id": g["id"], "title": g["title"]} for g in anchors],
        "daily_sync": daily_sync(env, now),
        "pulse": _pulse(today),
        "trends": _trends(today),
        "week": _week(today),
        "tour_look": _tour_look(areas, focus, _active_projects(list(projects.values())), tasks, today),
    }
