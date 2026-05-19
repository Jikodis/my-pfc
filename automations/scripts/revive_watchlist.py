"""Slippage detection for pfc-revive.

Reads tasks, projects, daily-focus, task_events, and revive-events from the
canonical NDJSON files. Applies the six signal rules (A–F per the design spec),
the active-only constraint, the project-subsumes-task hierarchy rule, and the
7-day skip cooldown. Prints a JSON array of watchlist items to stdout.

Usage:
    python revive_watchlist.py [--today YYYY-MM-DD] [--repo-root PATH]

Exit 0 on success.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

# Thresholds (per design spec; tune by editing here)
SIGNAL_A_LATE_DAYS = 7        # project velocity > N days late
SIGNAL_B_ZERO_PARTS_DAYS = 14 # active project at 0 completed parts since started
SIGNAL_C_TASK_AGE_DAYS = 30   # open task age
SIGNAL_D_HIGH_IMPACT_DAYS = 7 # high-impact open task age
SIGNAL_E_CARRY_DAYS = 3       # carried in 2+1 ≥ K distinct days
SIGNAL_F_DORMANT_DAYS = 10    # active project no task_event activity
COOLDOWN_DAYS = 7             # skip suppresses item for N days


@dataclass
class Project:
    id: str
    name: str
    active: bool
    total_parts: int
    completed_parts: int
    created: str
    area: str
    deadline: Optional[str] = None


@dataclass
class Task:
    id: str
    status: str
    description: str
    impact: str
    urgency: str
    project: str
    created: str
    area: Optional[str] = None
    completed: Optional[str] = None


@dataclass
class TaskEvent:
    task_id: str
    event: str
    timestamp: str  # ISO 8601


@dataclass
class WatchlistItem:
    item_type: str  # "task" | "project"
    item_id: str
    signals: list[str]  # subset of ["A","B","C","D","E","F"]
    detail: str  # human-readable signal summary, shown in skill chat


@dataclass
class DailyFocus:
    date: str
    critical: list[str] = field(default_factory=list)
    bonus: Optional[str] = None
    project: Optional[str] = None


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


def detect_signal_a_velocity(projects: Iterable[Project], today: date) -> list[WatchlistItem]:
    """Signal A: active project velocity 🔴 (>7 days late vs deadline)."""
    out: list[WatchlistItem] = []
    for p in projects:
        if not p.active:
            continue
        deadline = _parse_date(p.deadline)
        if deadline is None:
            continue
        started = _parse_date(p.created)
        if started is None:
            continue
        days_elapsed = max(1, (today - started).days)
        if p.completed_parts <= 0:
            continue  # no velocity data; falls under signal B
        parts_per_day = p.completed_parts / days_elapsed
        remaining = max(0, p.total_parts - p.completed_parts)
        remaining_days = remaining / parts_per_day
        estimated_completion = today + timedelta(days=remaining_days)
        days_late = (estimated_completion - deadline).days
        if days_late > SIGNAL_A_LATE_DAYS:
            out.append(WatchlistItem(
                item_type="project",
                item_id=p.id,
                signals=["A"],
                detail=f"velocity 🔴 — est completion {estimated_completion.isoformat()} vs deadline {deadline.isoformat()} ({days_late} days late)",
            ))
    return out


def detect_signal_b_zero_parts(projects: Iterable[Project], today: date) -> list[WatchlistItem]:
    """Signal B: active project at 0 completed parts since started ≥14 days."""
    out: list[WatchlistItem] = []
    for p in projects:
        if not p.active:
            continue
        if p.completed_parts > 0:
            continue
        started = _parse_date(p.created)
        if started is None:
            continue
        days_idle = (today - started).days
        if days_idle >= SIGNAL_B_ZERO_PARTS_DAYS:
            out.append(WatchlistItem(
                item_type="project",
                item_id=p.id,
                signals=["B"],
                detail=f"0/{p.total_parts} parts done in {days_idle} days since start",
            ))
    return out


def detect_signal_c_task_age(tasks: Iterable[Task], today: date) -> list[WatchlistItem]:
    """Signal C: open task age ≥30 days (any task, standalone or project)."""
    out: list[WatchlistItem] = []
    for t in tasks:
        if t.status != "open":
            continue
        created = _parse_date(t.created)
        if created is None:
            continue
        age = (today - created).days
        if age >= SIGNAL_C_TASK_AGE_DAYS:
            out.append(WatchlistItem(
                item_type="task",
                item_id=t.id,
                signals=["C"],
                detail=f"open {age} days",
            ))
    return out


def detect_signal_d_high_impact(tasks: Iterable[Task], today: date) -> list[WatchlistItem]:
    """Signal D: high-impact open task ≥7 days old."""
    out: list[WatchlistItem] = []
    for t in tasks:
        if t.status != "open" or t.impact != "high":
            continue
        created = _parse_date(t.created)
        if created is None:
            continue
        age = (today - created).days
        if age >= SIGNAL_D_HIGH_IMPACT_DAYS:
            out.append(WatchlistItem(
                item_type="task",
                item_id=t.id,
                signals=["D"],
                detail=f"high-impact, open {age} days",
            ))
    return out


def detect_signal_e_carry_forward(
    tasks: Iterable[Task],
    focuses: Iterable[DailyFocus],
    today: date,
) -> list[WatchlistItem]:
    """Signal E: same open task in 2+1 (any slot) ≥3 distinct days.

    Caller suppresses once-per-task via the cooldown / prior-revive logic in Task 9.
    """
    by_id: dict[str, set[str]] = {}
    for f in focuses:
        ids = set(f.critical)
        if f.bonus:
            ids.add(f.bonus)
        if f.project:
            ids.add(f.project)
        for tid in ids:
            by_id.setdefault(tid, set()).add(f.date)

    out: list[WatchlistItem] = []
    open_ids = {t.id: t for t in tasks if t.status == "open"}
    for tid, dates in by_id.items():
        if tid not in open_ids:
            continue
        if len(dates) >= SIGNAL_E_CARRY_DAYS:
            out.append(WatchlistItem(
                item_type="task",
                item_id=tid,
                signals=["E"],
                detail=f"carried in 2+1 {len(dates)} distinct days without completion",
            ))
    return out


def detect_signal_f_dormant_project(
    projects: Iterable[Project],
    tasks: Iterable[Task],
    events: Iterable[TaskEvent],
    today: date,
) -> list[WatchlistItem]:
    """Signal F: active project with no task_event activity ≥10 days."""
    tasks_by_project: dict[str, set[str]] = {}
    for t in tasks:
        tasks_by_project.setdefault(t.project, set()).add(t.id)

    last_event_by_task: dict[str, date] = {}
    for e in events:
        try:
            ts = datetime.fromisoformat(e.timestamp).date()
        except ValueError:
            continue
        prev = last_event_by_task.get(e.task_id)
        if prev is None or ts > prev:
            last_event_by_task[e.task_id] = ts

    out: list[WatchlistItem] = []
    for p in projects:
        if not p.active:
            continue
        task_ids = tasks_by_project.get(p.id, set())
        latest = None
        for tid in task_ids:
            ts = last_event_by_task.get(tid)
            if ts and (latest is None or ts > latest):
                latest = ts
        if latest is None:
            days = (today - _parse_date(p.created)).days if _parse_date(p.created) else 999
        else:
            days = (today - latest).days
        if days >= SIGNAL_F_DORMANT_DAYS:
            out.append(WatchlistItem(
                item_type="project",
                item_id=p.id,
                signals=["F"],
                detail=f"no task_event activity in {days} days",
            ))
    return out


def apply_hierarchy_rule(
    items: Iterable[WatchlistItem],
    tasks: Iterable[Task],
) -> list[WatchlistItem]:
    """Project slip subsumes its task slips — drop task rows whose parent project is also in the watchlist."""
    items = list(items)
    project_ids_in_watchlist = {i.item_id for i in items if i.item_type == "project"}
    task_to_project = {t.id: t.project for t in tasks}
    out: list[WatchlistItem] = []
    for i in items:
        if i.item_type == "task":
            parent = task_to_project.get(i.item_id)
            if parent and parent != "none" and parent in project_ids_in_watchlist:
                continue
        out.append(i)
    return out


@dataclass
class ReviveEvent:
    id: str
    date: str
    item_type: str
    item_id: str
    signals: list[str]
    diagnostic: list[str]
    intervention: list[str]


def apply_skip_cooldown_and_e_once(
    items: Iterable[WatchlistItem],
    revive_log: Iterable[ReviveEvent],
    today: date,
) -> list[WatchlistItem]:
    """Apply two suppressions:
      1. Skip cooldown — if last revive for this item was 'skip' and within 7 days, suppress entirely.
      2. E-once — strip signal E from items that already have an E-revive logged for the same item_id.
    """
    log = list(revive_log)
    # latest revive event per item
    latest: dict[tuple[str, str], ReviveEvent] = {}
    e_logged: set[tuple[str, str]] = set()
    for ev in log:
        key = (ev.item_type, ev.item_id)
        ev_date = _parse_date(ev.date)
        if ev_date is None:
            continue
        cur = latest.get(key)
        if cur is None or _parse_date(cur.date) < ev_date:
            latest[key] = ev
        if "E" in ev.signals:
            e_logged.add(key)

    out: list[WatchlistItem] = []
    for item in items:
        key = (item.item_type, item.item_id)
        last = latest.get(key)
        if last and "skip" in last.intervention:
            last_date = _parse_date(last.date)
            if last_date and (today - last_date).days < COOLDOWN_DAYS:
                continue  # skip cooldown active
        signals = list(item.signals)
        if key in e_logged and "E" in signals:
            signals = [s for s in signals if s != "E"]
        if not signals:
            continue
        out.append(dataclasses.replace(item, signals=signals))
    return out


def _load_ndjson(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    out: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def load_projects(repo_root: Path) -> list[Project]:
    rows = _load_ndjson(repo_root / "4-projects/_data/projects.ndjson")
    out: list[Project] = []
    for r in rows:
        out.append(Project(
            id=r["id"], name=r["name"], active=bool(r["active"]),
            total_parts=int(r.get("total_parts", 0)),
            completed_parts=int(r.get("completed_parts", 0)),
            created=r["created"], area=r["area"],
            deadline=r.get("deadline"),
        ))
    return out


def load_tasks(repo_root: Path) -> list[Task]:
    rows = _load_ndjson(repo_root / "5-actions/_data/tasks.ndjson")
    out: list[Task] = []
    for r in rows:
        out.append(Task(
            id=r["id"], status=r["status"], description=r["description"],
            impact=r["impact"], urgency=r["urgency"],
            project=r.get("project", "none"),
            created=r["created"], area=r.get("area"),
            completed=r.get("completed"),
        ))
    return out


def load_focuses(repo_root: Path) -> list[DailyFocus]:
    rows = _load_ndjson(repo_root / "5-actions/_data/daily-focus.ndjson")
    out: list[DailyFocus] = []
    for r in rows:
        out.append(DailyFocus(
            date=r["date"],
            critical=list(r.get("critical") or []),
            bonus=r.get("bonus"),
            project=r.get("project"),
        ))
    return out


def load_events(repo_root: Path) -> list[TaskEvent]:
    """Load task events tolerantly — task_events.ndjson has legacy variants.

    Accepts: task_id | id (task id), timestamp | ts | date (when), event (required).
    Rows missing the task id, timestamp, or event are skipped (logged event file has drift).
    """
    rows = _load_ndjson(repo_root / "5-actions/_data/task_events.ndjson")
    out: list[TaskEvent] = []
    for r in rows:
        task_id = r.get("task_id") or r.get("id")
        timestamp = r.get("timestamp") or r.get("ts") or r.get("date")
        event = r.get("event")
        if not task_id or not timestamp or not event:
            continue
        out.append(TaskEvent(task_id=task_id, event=event, timestamp=timestamp))
    return out


def load_revive_log(repo_root: Path) -> list[ReviveEvent]:
    rows = _load_ndjson(repo_root / "data/revive-events.ndjson")
    out: list[ReviveEvent] = []
    for r in rows:
        out.append(ReviveEvent(
            id=r["id"], date=r["date"], item_type=r["item_type"],
            item_id=r["item_id"], signals=list(r.get("signals") or []),
            diagnostic=list(r.get("diagnostic") or []),
            intervention=list(r.get("intervention") or []),
        ))
    return out


def compose_watchlist(repo_root: Path, today: date) -> list[WatchlistItem]:
    projects = load_projects(repo_root)
    tasks = load_tasks(repo_root)
    focuses = load_focuses(repo_root)
    events = load_events(repo_root)
    revive_log = load_revive_log(repo_root)

    raw: list[WatchlistItem] = []
    raw.extend(detect_signal_a_velocity(projects, today))
    raw.extend(detect_signal_b_zero_parts(projects, today))
    raw.extend(detect_signal_c_task_age(tasks, today))
    raw.extend(detect_signal_d_high_impact(tasks, today))
    raw.extend(detect_signal_e_carry_forward(tasks, focuses, today))
    raw.extend(detect_signal_f_dormant_project(projects, tasks, events, today))

    # Merge duplicate items (same id with multiple signals)
    merged: dict[tuple[str, str], WatchlistItem] = {}
    for it in raw:
        key = (it.item_type, it.item_id)
        if key in merged:
            existing = merged[key]
            sigs = sorted(set(existing.signals) | set(it.signals))
            detail = "; ".join(filter(None, [existing.detail, it.detail]))
            merged[key] = WatchlistItem(item_type=it.item_type, item_id=it.item_id, signals=sigs, detail=detail)
        else:
            merged[key] = it

    items = list(merged.values())
    items = apply_hierarchy_rule(items, tasks)
    items = apply_skip_cooldown_and_e_once(items, revive_log, today)
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", default=None, help="Override today's date (YYYY-MM-DD) for testing.")
    parser.add_argument("--repo-root", default=None, help="Repo root (defaults to script location).")
    args = parser.parse_args(argv)

    today = _parse_date(args.today) if args.today else date.today()
    repo_root = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parents[2]
    items = compose_watchlist(repo_root, today)
    print(json.dumps([dataclasses.asdict(i) for i in items], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
