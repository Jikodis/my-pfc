"""Tests for slippage detection helper."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

from revive_watchlist import (
    Project,
    Task,
    TaskEvent,
    WatchlistItem,
    detect_signal_a_velocity,
)


def _project(**overrides):
    base = dict(
        id="proj-20260101-001",
        name="Test",
        active=True,
        total_parts=10,
        completed_parts=2,
        created="2026-01-01",
        deadline="2026-04-01",
        area="career",
    )
    base.update(overrides)
    return Project(**base)


def test_signal_a_fires_when_active_project_more_than_7_days_late() -> None:
    today = date(2026, 5, 18)
    # 2/10 parts done over (2026-01-01 → 2026-05-18) ≈ 138 days
    # parts_per_day = 2/138 ≈ 0.0145; remaining 8 parts → ~551 days from today
    # vs deadline 2026-04-01 → way more than 7 days late
    p = _project(active=True, completed_parts=2, total_parts=10, deadline="2026-04-01")
    result = detect_signal_a_velocity([p], today=today)
    assert [r.item_id for r in result] == ["proj-20260101-001"]


def test_signal_a_skips_inactive_projects() -> None:
    today = date(2026, 5, 18)
    p = _project(active=False, completed_parts=2, total_parts=10, deadline="2026-04-01")
    assert detect_signal_a_velocity([p], today=today) == []


def test_signal_a_skips_project_on_track() -> None:
    today = date(2026, 5, 18)
    # Started yesterday, 0 parts done — no velocity data yet
    p = _project(active=True, created="2026-05-17", completed_parts=0, deadline="2026-12-01")
    assert detect_signal_a_velocity([p], today=today) == []


def test_signal_a_skips_project_without_deadline() -> None:
    today = date(2026, 5, 18)
    p = _project(active=True, deadline=None)
    assert detect_signal_a_velocity([p], today=today) == []


from revive_watchlist import detect_signal_b_zero_parts  # noqa: E402


def test_signal_b_fires_at_14_days_zero_parts_active() -> None:
    today = date(2026, 5, 18)
    started = (today - timedelta(days=14)).isoformat()
    p = _project(active=True, created=started, completed_parts=0, total_parts=5)
    result = detect_signal_b_zero_parts([p], today=today)
    assert [r.item_id for r in result] == ["proj-20260101-001"]


def test_signal_b_does_not_fire_before_14_days() -> None:
    today = date(2026, 5, 18)
    started = (today - timedelta(days=13)).isoformat()
    p = _project(active=True, created=started, completed_parts=0)
    assert detect_signal_b_zero_parts([p], today=today) == []


def test_signal_b_skips_when_progress_exists() -> None:
    today = date(2026, 5, 18)
    p = _project(active=True, created="2026-01-01", completed_parts=1)
    assert detect_signal_b_zero_parts([p], today=today) == []


def test_signal_b_skips_inactive_projects() -> None:
    today = date(2026, 5, 18)
    started = (today - timedelta(days=20)).isoformat()
    p = _project(active=False, created=started, completed_parts=0)
    assert detect_signal_b_zero_parts([p], today=today) == []


from revive_watchlist import detect_signal_c_task_age  # noqa: E402


def _task(**overrides):
    base = dict(
        id="task-20260101-001",
        status="open",
        description="t",
        impact="medium",
        urgency="medium",
        project="none",
        created="2026-01-01",
    )
    base.update(overrides)
    return Task(**base)


def test_signal_c_fires_for_open_task_older_than_30_days() -> None:
    today = date(2026, 5, 18)
    created = (today - timedelta(days=30)).isoformat()
    t = _task(status="open", created=created)
    assert [r.item_id for r in detect_signal_c_task_age([t], today=today)] == ["task-20260101-001"]


def test_signal_c_does_not_fire_at_29_days() -> None:
    today = date(2026, 5, 18)
    created = (today - timedelta(days=29)).isoformat()
    t = _task(status="open", created=created)
    assert detect_signal_c_task_age([t], today=today) == []


def test_signal_c_skips_done_tasks() -> None:
    today = date(2026, 5, 18)
    t = _task(status="done", created="2026-01-01")
    assert detect_signal_c_task_age([t], today=today) == []


from revive_watchlist import detect_signal_d_high_impact  # noqa: E402


def test_signal_d_fires_for_high_impact_at_7_days() -> None:
    today = date(2026, 5, 18)
    created = (today - timedelta(days=7)).isoformat()
    t = _task(status="open", impact="high", created=created)
    assert [r.item_id for r in detect_signal_d_high_impact([t], today=today)] == ["task-20260101-001"]


def test_signal_d_does_not_fire_for_medium_impact() -> None:
    today = date(2026, 5, 18)
    created = (today - timedelta(days=14)).isoformat()
    t = _task(status="open", impact="medium", created=created)
    assert detect_signal_d_high_impact([t], today=today) == []


def test_signal_d_skips_done_tasks() -> None:
    today = date(2026, 5, 18)
    t = _task(status="done", impact="high", created="2026-01-01")
    assert detect_signal_d_high_impact([t], today=today) == []


from revive_watchlist import DailyFocus, detect_signal_e_carry_forward  # noqa: E402


def _focus(date_str: str, critical=None, bonus=None, project=None) -> "DailyFocus":
    return DailyFocus(
        date=date_str,
        critical=list(critical or []),
        bonus=bonus,
        project=project,
    )


def test_signal_e_fires_at_3_distinct_days_for_open_task() -> None:
    today = date(2026, 5, 18)
    t = _task(id="task-X", status="open")
    focuses = [
        _focus("2026-05-16", critical=["task-X"]),
        _focus("2026-05-17", critical=["task-X"]),
        _focus("2026-05-18", critical=["task-X"]),
    ]
    result = detect_signal_e_carry_forward([t], focuses, today=today)
    assert [r.item_id for r in result] == ["task-X"]


def test_signal_e_counts_bonus_and_project_slots_too() -> None:
    today = date(2026, 5, 18)
    t = _task(id="task-X", status="open")
    focuses = [
        _focus("2026-05-16", critical=["task-X"]),
        _focus("2026-05-17", bonus="task-X"),
        _focus("2026-05-18", project="task-X"),
    ]
    result = detect_signal_e_carry_forward([t], focuses, today=today)
    assert [r.item_id for r in result] == ["task-X"]


def test_signal_e_does_not_fire_at_2_days() -> None:
    today = date(2026, 5, 18)
    t = _task(id="task-X", status="open")
    focuses = [
        _focus("2026-05-17", critical=["task-X"]),
        _focus("2026-05-18", critical=["task-X"]),
    ]
    assert detect_signal_e_carry_forward([t], focuses, today=today) == []


def test_signal_e_skips_done_tasks() -> None:
    today = date(2026, 5, 18)
    t = _task(id="task-X", status="done")
    focuses = [
        _focus("2026-05-16", critical=["task-X"]),
        _focus("2026-05-17", critical=["task-X"]),
        _focus("2026-05-18", critical=["task-X"]),
    ]
    assert detect_signal_e_carry_forward([t], focuses, today=today) == []


from revive_watchlist import detect_signal_f_dormant_project  # noqa: E402


def test_signal_f_fires_when_no_events_in_10_days() -> None:
    today = date(2026, 5, 18)
    p = _project(id="proj-X", active=True)
    # Task in this project, event 11 days ago
    t = _task(id="task-X", project="proj-X")
    events = [TaskEvent(task_id="task-X", event="created", timestamp="2026-05-07T10:00:00-06:00")]
    result = detect_signal_f_dormant_project([p], [t], events, today=today)
    assert [r.item_id for r in result] == ["proj-X"]


def test_signal_f_does_not_fire_when_recent_event() -> None:
    today = date(2026, 5, 18)
    p = _project(id="proj-X", active=True)
    t = _task(id="task-X", project="proj-X")
    events = [TaskEvent(task_id="task-X", event="created", timestamp="2026-05-15T10:00:00-06:00")]
    assert detect_signal_f_dormant_project([p], [t], events, today=today) == []


def test_signal_f_skips_inactive_projects() -> None:
    today = date(2026, 5, 18)
    p = _project(id="proj-X", active=False)
    t = _task(id="task-X", project="proj-X")
    events = [TaskEvent(task_id="task-X", event="created", timestamp="2026-05-07T10:00:00-06:00")]
    assert detect_signal_f_dormant_project([p], [t], events, today=today) == []


def test_signal_f_fires_for_active_project_with_no_events_at_all() -> None:
    today = date(2026, 5, 18)
    # Active project, no tasks, no events → dormant by definition
    p = _project(id="proj-X", active=True, created="2026-04-01")
    assert [r.item_id for r in detect_signal_f_dormant_project([p], [], [], today=today)] == ["proj-X"]


from revive_watchlist import apply_hierarchy_rule  # noqa: E402


def test_hierarchy_drops_task_when_parent_project_also_slipped() -> None:
    proj_item = WatchlistItem(item_type="project", item_id="proj-X", signals=["A"], detail="d1")
    task_item = WatchlistItem(item_type="task", item_id="task-X", signals=["C"], detail="d2")
    task_X = _task(id="task-X", project="proj-X")
    result = apply_hierarchy_rule([proj_item, task_item], tasks=[task_X])
    ids = [(r.item_type, r.item_id) for r in result]
    assert ids == [("project", "proj-X")]


def test_hierarchy_keeps_standalone_task() -> None:
    task_item = WatchlistItem(item_type="task", item_id="task-Y", signals=["C"], detail="d")
    task_Y = _task(id="task-Y", project="none")
    result = apply_hierarchy_rule([task_item], tasks=[task_Y])
    assert [(r.item_type, r.item_id) for r in result] == [("task", "task-Y")]


def test_hierarchy_keeps_task_when_parent_project_not_slipped() -> None:
    task_item = WatchlistItem(item_type="task", item_id="task-Z", signals=["D"], detail="d")
    task_Z = _task(id="task-Z", project="proj-Y")  # proj-Y not in watchlist
    result = apply_hierarchy_rule([task_item], tasks=[task_Z])
    assert [(r.item_type, r.item_id) for r in result] == [("task", "task-Z")]


from revive_watchlist import ReviveEvent, apply_skip_cooldown_and_e_once  # noqa: E402


def _revive(date_str, item_id, intervention, signals=None, item_type="task"):
    return ReviveEvent(
        id=f"revive-{date_str.replace('-','')}-001",
        date=date_str,
        item_type=item_type,
        item_id=item_id,
        signals=signals or [],
        diagnostic=[],
        intervention=intervention,
    )


def test_cooldown_suppresses_skip_within_7_days() -> None:
    today = date(2026, 5, 18)
    item = WatchlistItem(item_type="task", item_id="task-X", signals=["D"], detail="d")
    revive_log = [_revive("2026-05-15", "task-X", ["skip"])]
    result = apply_skip_cooldown_and_e_once([item], revive_log, today=today)
    assert result == []


def test_cooldown_releases_after_7_days() -> None:
    today = date(2026, 5, 18)
    item = WatchlistItem(item_type="task", item_id="task-X", signals=["D"], detail="d")
    revive_log = [_revive("2026-05-10", "task-X", ["skip"])]  # 8 days ago
    result = apply_skip_cooldown_and_e_once([item], revive_log, today=today)
    assert [r.item_id for r in result] == ["task-X"]


def test_non_skip_intervention_does_not_trigger_cooldown() -> None:
    today = date(2026, 5, 18)
    item = WatchlistItem(item_type="task", item_id="task-X", signals=["D"], detail="d")
    revive_log = [_revive("2026-05-17", "task-X", ["break_down"])]
    result = apply_skip_cooldown_and_e_once([item], revive_log, today=today)
    assert [r.item_id for r in result] == ["task-X"]


def test_e_fires_only_once_per_task() -> None:
    today = date(2026, 5, 18)
    item = WatchlistItem(item_type="task", item_id="task-X", signals=["E"], detail="d")
    revive_log = [_revive("2026-04-01", "task-X", ["break_down"], signals=["E"])]
    result = apply_skip_cooldown_and_e_once([item], revive_log, today=today)
    assert result == []  # E already logged for this task


def test_e_does_not_block_other_signals_on_same_task() -> None:
    # If task-X is now slipping via D AND E, and only E was previously logged,
    # the item should still surface because D is independent.
    today = date(2026, 5, 18)
    item = WatchlistItem(item_type="task", item_id="task-X", signals=["D", "E"], detail="d")
    revive_log = [_revive("2026-04-01", "task-X", ["break_down"], signals=["E"])]
    result = apply_skip_cooldown_and_e_once([item], revive_log, today=today)
    # E gets stripped, but D remains → item still in
    assert len(result) == 1
    assert result[0].signals == ["D"]


import subprocess


def test_main_emits_empty_json_array_when_no_data(tmp_path) -> None:
    # Build a minimal repo skeleton
    (tmp_path / "4-projects" / "_data").mkdir(parents=True)
    (tmp_path / "5-actions" / "_data").mkdir(parents=True)
    (tmp_path / "data").mkdir(parents=True)
    for f in [
        "4-projects/_data/projects.ndjson",
        "5-actions/_data/tasks.ndjson",
        "5-actions/_data/daily-focus.ndjson",
        "5-actions/_data/task_events.ndjson",
        "data/revive-events.ndjson",
    ]:
        (tmp_path / f).write_text("")

    result = subprocess.run(
        [sys.executable, "automations/scripts/revive_watchlist.py",
         "--repo-root", str(tmp_path), "--today", "2026-05-18"],
        cwd=str(Path(__file__).resolve().parents[3]),
        capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == []


def test_main_emits_watchlist_for_seeded_slip(tmp_path) -> None:
    (tmp_path / "4-projects" / "_data").mkdir(parents=True)
    (tmp_path / "5-actions" / "_data").mkdir(parents=True)
    (tmp_path / "data").mkdir(parents=True)
    # Seed: one open task created 40 days ago (signal C)
    (tmp_path / "5-actions" / "_data" / "tasks.ndjson").write_text(
        json.dumps({
            "id": "task-X", "status": "open", "description": "t",
            "size": "S", "location": "PC", "impact": "medium",
            "urgency": "low", "project": "none", "created": "2026-04-08",
            "area": "career",
        }) + "\n"
    )
    for f in [
        "4-projects/_data/projects.ndjson",
        "5-actions/_data/daily-focus.ndjson",
        "5-actions/_data/task_events.ndjson",
        "data/revive-events.ndjson",
    ]:
        (tmp_path / f).write_text("")

    result = subprocess.run(
        [sys.executable, "automations/scripts/revive_watchlist.py",
         "--repo-root", str(tmp_path), "--today", "2026-05-18"],
        cwd=str(Path(__file__).resolve().parents[3]),
        capture_output=True, text=True, check=True,
    )
    out = json.loads(result.stdout)
    assert len(out) == 1
    assert out[0]["item_id"] == "task-X"
    assert "C" in out[0]["signals"]
