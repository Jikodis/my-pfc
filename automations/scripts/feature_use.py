#!/usr/bin/env python3
"""Feature scorecard: which parts of the PFC system you actually use.

For every feature, counts real use in the last 30 days and in the 60 days before
that (days 31-90), from the repo's own records, against what the feature asks for
in that window. Then suggests one verdict per feature:

    keep             — used (>= 60% of what it asks for in the last 30 days)
    just use it      — it worked before (prior 60 days >= 60%) or is climbing back
    change cadence   — half-used for 90 days: the rhythm asks more than it gets
    change feature   — barely used for 90 days: the feature itself isn't landing

The verdict is a starting point. The skill (`pfc-usage-audit` § Feature scorecard)
overrides it with judgment.

Only the user's own use counts. Rows the system writes itself (watch- and
calendar-derived habits, email-synced tasks) are reported in their own "runs on its
own" section, never as use.

    python3 automations/scripts/feature_use.py            # markdown report
    python3 automations/scripts/feature_use.py --json     # machine-readable
    python3 automations/scripts/feature_use.py --today 2025-01-15
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from focus_status import habit_rate, light  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

USED_FLOOR = 0.60
PARTLY_FLOOR = 0.20
RECENT_DAYS = 30
PRIOR_DAYS = 60  # days 31-90

# Habit rows the system writes itself. Not the user's use.
AUTO_HABIT_SOURCES = {"fitbit-derived", "health-derived", "calendar-derived", "google_health_auto"}
# Task events the system writes itself.
AUTO_TASK_SOURCES = {"email-sync", "email-triage", "calendar-sync", "repo-maintenance"}


# ── helpers ────────────────────────────────────────────────────────────────────

def read_ndjson(rel):
    path = REPO / rel
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def day(value):
    """First 10 chars of a date or timestamp, or None."""
    return value[:10] if isinstance(value, str) and len(value) >= 10 else None


class Window:
    """Inclusive [start, end] date range, as ISO strings."""

    def __init__(self, start: date, end: date):
        self.start, self.end = start, end
        self.days = max(0, (end - start).days + 1)

    def has(self, value) -> bool:
        d = day(value)
        return d is not None and self.start.isoformat() <= d <= self.end.isoformat()

    def clamp(self, since):
        """The part of the window on or after `since` (a feature's start date)."""
        if not since:
            return self
        s = max(self.start, date.fromisoformat(since))
        return Window(s, self.end) if s <= self.end else Window(self.end + timedelta(1), self.end)


def git_dates(paths, window, skip_prefixes=("track: auto",)):
    """Distinct commit dates touching `paths` in the window, skipping automated commits."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "log", f"--since={window.start.isoformat()} 00:00",
             f"--until={window.end.isoformat()} 23:59", "--format=%as\t%s", "--", *paths],
            capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()
    dates = set()
    for line in out.splitlines():
        d, _, subject = line.partition("\t")
        if not subject.startswith(skip_prefixes):
            dates.add(d)
    return dates


def score(count, expected):
    if expected is None or expected <= 0:
        return None
    return min(1.0, count / expected)


def use_label(rate):
    if rate is None:
        return "n/a"
    if rate >= USED_FLOOR:
        return "used"
    if rate >= PARTLY_FLOOR:
        return "partly"
    return "unused"


def verdict(recent, prior):
    """Suggested verdict from the two rates. See module docstring."""
    if recent is None:
        return "on demand"
    if recent >= USED_FLOOR:
        return "keep"
    if prior is None:  # too new to have a history
        return "just use it"
    if prior >= USED_FLOOR or recent > prior + 0.15:
        return "just use it"
    if prior >= PARTLY_FLOOR or recent >= PARTLY_FLOOR:
        return "change cadence"
    return "change feature"


# ── the data, loaded once ──────────────────────────────────────────────────────

class Data:
    def __init__(self, today: date):
        self.today = today
        self.day_tracking = read_ndjson("data/day-tracking.ndjson")
        self.habits_daily = read_ndjson("7-habits/_data/habits-daily.ndjson")
        self.habits_monthly = read_ndjson("7-habits/_data/habits-monthly.ndjson")
        self.daily_focus = read_ndjson("6-tasks/_data/daily-focus.ndjson")
        self.task_events = read_ndjson("6-tasks/_data/task_events.ndjson")
        self.tasks = read_ndjson("6-tasks/_data/tasks.ndjson") + read_ndjson("6-tasks/_data/tasks-archive.ndjson")
        self.ledger = read_ndjson("data/review-ledger.ndjson")
        self.focus = read_ndjson("4-focus/_data/focus.ndjson")
        self.projects = read_ndjson("5-projects/_data/projects.ndjson")
        self.life_wheel = read_ndjson("2-areas/_data/life-wheel.ndjson")
        self.household = read_ndjson("2-areas/_data/household-status.ndjson")
        self.area_items = read_ndjson("2-areas/_data/area-items.ndjson")
        self.area_checkins = read_ndjson("2-areas/_data/area-checkins.ndjson")
        self.brainstorm = read_ndjson("3-visions/_data/vision-brainstorm.ndjson")
        self.insights = read_ndjson("data/insights.ndjson")
        self.hypotheses = read_ndjson("data/hypotheses.ndjson")
        self.findings = read_ndjson("data/findings.ndjson")
        self.grounding = read_ndjson("data/grounding.ndjson")
        self.supplements = read_ndjson("data/supplements.ndjson")
        self.revive = read_ndjson("data/revive-events.ndjson")
        self.schema = yaml.safe_load((REPO / "config/habit_schema.yaml").read_text())

    def current_quarter(self):
        return f"{self.today.year}-Q{(self.today.month - 1) // 3 + 1}"


# ── features ───────────────────────────────────────────────────────────────────
# Each measure(d, w) returns (count, expected). expected None = on demand (no target).

def m_day_rating(d, w):
    n = len({r["date"] for r in d.day_tracking if w.has(r.get("date")) and r.get("rating") is not None})
    return n, w.days


def m_habit_ticks(d, w):
    n = len({r["date"] for r in d.habits_daily + d.habits_monthly
             if w.has(r.get("date")) and not r.get("skipped")
             and r.get("source") not in AUTO_HABIT_SOURCES})
    return n, w.days


def m_pick_2plus1(d, w):
    n = len({r["date"] for r in d.daily_focus if w.has(r.get("date")) and r.get("critical")})
    return n, w.days


def m_finish_2plus1(d, w):
    # A pick day counts when any pick was finished that day: the row's own
    # `completed` list, or a completed task event for a pick on that date (the
    # web page and Trello close the task without touching the 2+1 row).
    closed = {(e.get("task_id"), day(e.get("timestamp"))) for e in d.task_events
              if e.get("event") == "completed"}
    rows = [r for r in d.daily_focus if w.has(r.get("date")) and r.get("critical")]
    done = 0
    for r in rows:
        picks = list(r["critical"]) + ([r["bonus"]] if r.get("bonus") else [])
        if r.get("completed") or r.get("bonus_completed") or any((t, r["date"]) in closed for t in picks):
            done += 1
    return done, len(rows)


def m_close_tasks(d, w):
    n = len({day(e.get("timestamp")) for e in d.task_events
             if e.get("event") == "completed" and w.has(e.get("timestamp"))
             and e.get("source") not in AUTO_TASK_SOURCES})
    return n, round(w.days / 2)  # a task closed every other day


def m_capture_tasks(d, w):
    n = len({day(e.get("timestamp")) for e in d.task_events
             if e.get("event") in ("created", "task_created") and w.has(e.get("timestamp"))
             and e.get("source") not in AUTO_TASK_SOURCES})
    return n, round(w.days * 2 / 7)  # two capture days a week


def m_reviews(d, w):
    # The ledger keeps only last_done, so this counts review items done at least
    # once in the window, out of the items whose cadence fits inside it.
    due = [r for r in d.ledger if r.get("cadence_days", 999) <= max(w.days, 1)]
    done = sum(1 for r in due if w.has(r.get("last_done")))
    return done, len(due)


def m_focus_repick(d, w):
    if w.end == d.today:  # recent window: are live focuses tagged with this quarter?
        live = [f for f in d.focus if not f.get("retired_date") and not f.get("parked")]
        return sum(1 for f in live if f.get("quarter") == d.current_quarter()), len(live)
    item = next((r for r in d.ledger if r.get("id") == "focus-repick"), {})
    return (1 if w.has(item.get("last_done")) else 0), 1


def m_projects_moving(d, w):
    active = {p["id"] for p in d.projects if p.get("active")}
    moved = {t.get("project") for t in d.tasks
             if t.get("project") in active and w.has(t.get("completed"))}
    return len(moved), len(active)


def m_area_lights(d, w):
    n = sum(1 for r in d.life_wheel + d.household if w.has(r.get("date")))
    return n, max(1, round(w.days / 30)) * 2  # life wheel + rooms, once a month each


def m_area_checkins(d, w):
    asked = [i for i in d.area_items if i.get("active") and i.get("question")]
    answered = {c.get("item_id") or c.get("item") for c in d.area_checkins
                if w.has(c.get("date") or c.get("logged_at"))}
    return len(answered), len(asked)


def m_visions(d, w):
    # System commits rename or reword files; they are not the user tending a vision.
    touched = git_dates(["3-visions/"], w, skip_prefixes=("track:", "system:"))
    touched |= {r["created"] for r in d.brainstorm if w.has(r.get("created"))}
    return len(touched), max(1, round(w.days / 30))


def m_insights(d, w):
    n = sum(1 for r in d.insights + d.findings if w.has(r.get("created") or r.get("date")))
    n += sum(1 for r in d.hypotheses if w.has(r.get("started") or r.get("created")))
    return n, max(1, round(w.days / 15))  # one noticing every two weeks


def m_on_demand(rows_fn):
    def m(d, w):
        return sum(1 for v in rows_fn(d) if w.has(v)), None
    return m


FEATURES = [
    # id, group, title, measure, core, proof, since
    ("day-rating", "Daily", "Rate the day", m_day_rating, True,
     "data/day-tracking.ndjson rating", None),
    ("habit-ticks", "Daily", "Tick habits by hand", m_habit_ticks, True,
     "7-habits/_data hand-logged rows", None),
    ("pick-2plus1", "Daily", "Pick your own 2+1", m_pick_2plus1, True,
     "6-tasks/_data/daily-focus.ndjson source", None),
    ("finish-2plus1", "Daily", "Finish 2+1 picks", m_finish_2plus1, True,
     "daily-focus.ndjson completed", None),
    ("close-tasks", "Tasks", "Close tasks", m_close_tasks, False,
     "6-tasks/_data/task_events.ndjson completed", None),
    ("capture-tasks", "Tasks", "Capture tasks", m_capture_tasks, False,
     "task_events.ndjson created", None),
    ("reviews", "Reviews", "Rolling reviews", m_reviews, True,
     "data/review-ledger.ndjson last_done", None),
    ("focus-repick", "Quarter", "Focus re-pick", m_focus_repick, True,
     "4-focus/_data/focus.ndjson quarter", None),
    ("projects", "Quarter", "Projects moving", m_projects_moving, True,
     "tasks completed per active project", None),
    ("area-lights", "Quarter", "Life wheel + room lights", m_area_lights, False,
     "2-areas/_data/life-wheel + household-status", None),
    ("area-checkins", "Quarter", "Area check-in questions", m_area_checkins, False,
     "2-areas/_data/area-checkins.ndjson", None),
    ("visions", "Direction", "Visions", m_visions, False,
     "3-visions/ edits + vision-brainstorm", None),
    ("insights", "Knowledge", "Insights, hypotheses, findings", m_insights, False,
     "data/insights|hypotheses|findings.ndjson", None),
    ("revive", "On demand", "Revive a slipping item", m_on_demand(
        lambda d: [r.get("date") for r in d.revive]), False, "data/revive-events.ndjson", None),
    ("trello-capture", "On demand", "Trello captures", m_on_demand(
        lambda d: [e.get("timestamp") for e in d.task_events
                   if e.get("source") in ("trello", "trello-inbox")]), False,
     "task_events.ndjson source trello", None),
    ("grounding", "On demand", "Front-of-mind anchors", m_on_demand(
        lambda d: [r.get("created") for r in d.grounding]), False, "data/grounding.ndjson", None),
    ("supplements", "On demand", "Supplement log", m_on_demand(
        lambda d: [r.get("started") for r in d.supplements] + [r.get("stopped") for r in d.supplements]),
     False, "data/supplements.ndjson", None),
]


def automatic(d: Data):
    """Things the system runs on its own: last date each wrote something."""
    def last(values):
        vals = sorted(v for v in (day(x) for x in values) if v)
        return vals[-1] if vals else None
    # daily=True: writes every day, so an old date means the job stopped.
    # daily=False: writes only when there is something (a session, a labeled mail),
    # so an old date proves nothing.
    rows = [
        ("Health fetch", True, last(r["date"] for r in d.day_tracking if r.get("health"))),
        ("Sleep habit from the watch", True, last(r["date"] for r in d.habits_daily if r.get("source") == "fitbit-derived")),
        ("Workout habits from the watch", False, last(r["date"] for r in d.habits_daily if r.get("source") == "health-derived")),
        ("Email to task", False, last(e.get("timestamp") for e in d.task_events if e.get("source") in ("email-sync", "email-triage"))),
    ]
    out = []
    for name, daily, last_date in rows:
        age = (d.today - date.fromisoformat(last_date)).days if last_date else None
        status = ("running" if age is not None and age <= 3 else "stale") if daily else "when needed"
        out.append({"name": name, "last": last_date, "age_days": age, "status": status})
    return out


def _started(habit):
    """The habit's `started` date, or date.min when it is unset or still a placeholder."""
    try:
        return date.fromisoformat(str(habit.get("started")))
    except ValueError:
        return date.min


def habits(d: Data):
    """Per-habit completion over the last 30 days against its live frequency."""
    vehicles = {}
    for f in d.focus:
        if not f.get("retired_date"):
            for h in f.get("habits") or []:
                vehicles[h] = f["title"]
    end = d.today.isoformat()
    out = []
    for block, cadence, logs in (("daily_habits", "daily", d.habits_daily),
                                 ("monthly_habits", "monthly", d.habits_monthly)):
        for h in d.schema.get(block) or []:
            start = max(d.today - timedelta(RECENT_DAYS - 1), _started(h))
            r = habit_rate(logs, h["id"], start.isoformat(), end, h["frequency"], cadence)
            out.append({"id": h["id"], "name": h.get("short") or h["description"],
                        "frequency": f"{h['frequency']}/{'wk' if cadence == 'daily' else 'mo'}",
                        "done": r["completed"], "target": r["target"], "rate": round(r["rate"], 2),
                        "light": light(r["rate"]), "auto": bool(h.get("auto_derived")),
                        "focus": vehicles.get(h["id"])})
    out.sort(key=lambda x: x["rate"])
    return out


def build(today: date):
    d = Data(today)
    recent = Window(today - timedelta(RECENT_DAYS - 1), today)
    prior = Window(today - timedelta(RECENT_DAYS + PRIOR_DAYS - 1), today - timedelta(RECENT_DAYS))
    rows = []
    for fid, group, title, measure, core, proof, since in FEATURES:
        rw, pw = recent.clamp(since), prior.clamp(since)
        c30, e30 = measure(d, rw)
        c60, e60 = measure(d, pw) if pw.days else (0, 0)
        r30, r60 = score(c30, e30), score(c60, e60) if pw.days else None
        rows.append({"id": fid, "group": group, "title": title, "core": core, "proof": proof,
                     "recent": {"count": c30, "expected": e30, "rate": r30, "use": use_label(r30)},
                     "prior": {"count": c60, "expected": e60, "rate": r60, "use": use_label(r60)},
                     "verdict": verdict(r30, r60)})
    return {"today": today.isoformat(), "quarter": d.current_quarter(), "features": rows,
            "habits": habits(d), "automatic": automatic(d)}


# ── output ─────────────────────────────────────────────────────────────────────

DOT = {"used": "🟢", "partly": "🟡", "unused": "🔴", "n/a": "⚪"}


def fmt(part):
    if part["expected"] is None:
        return f"{part['count']} times"
    return f"{DOT[part['use']]} {part['count']}/{part['expected']}"


def markdown(rep):
    lines = [f"Feature scorecard, {rep['today']} (last 30 days vs the 60 before)", ""]
    lines += ["| Group | Feature | Core | Last 30 days | Days 31-90 | Suggested verdict |",
              "|---|---|---|---|---|---|"]
    order = {"unused": 0, "partly": 1, "used": 2, "n/a": 3}
    feats = sorted(rep["features"], key=lambda f: (not f["core"], order[f["recent"]["use"]]))
    for f in feats:
        lines.append(f"| {f['group']} | {f['title']} | {'yes' if f['core'] else ''} | "
                     f"{fmt(f['recent'])} | {fmt(f['prior'])} | {f['verdict']} |")
    lines += ["", "Habits, last 30 days against their live frequency", "",
              "| Habit | Target | Done / asked | Light | Feeds focus |", "|---|---|---|---|---|"]
    for h in rep["habits"]:
        auto = " (automatic)" if h["auto"] else ""
        lines.append(f"| {h['name']}{auto} | {h['frequency']} | {h['done']}/{h['target']} | "
                     f"{DOT[{'green': 'used', 'yellow': 'partly', 'red': 'unused'}[h['light']]]} | "
                     f"{h['focus'] or ''} |")
    lines += ["", "Runs on its own", "", "| Job | Last wrote | Status |", "|---|---|---|"]
    for a in rep["automatic"]:
        mark = {"running": "🟢 running", "stale": "🔴 stale", "when needed": "⚪ writes when needed"}
        lines.append(f"| {a['name']} | {a['last'] or 'never'} | {mark[a['status']]} |")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--today", help="YYYY-MM-DD (default: local date)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    tz = ZoneInfo(os.environ.get("LOCAL_TZ", "America/Denver"))
    today = date.fromisoformat(a.today) if a.today else datetime.now(tz).date()
    rep = build(today)
    print(json.dumps(rep, indent=1) if a.json else markdown(rep))


if __name__ == "__main__":
    main()
