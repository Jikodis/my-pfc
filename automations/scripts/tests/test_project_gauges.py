"""Unit tests for project_gauges: velocity and days idle, the two project gauges."""

from __future__ import annotations

from datetime import date

import pytest

from project_gauges import days_idle, velocity


def _project(**overrides):
    base = dict(
        id="proj-20250101-001",
        name="Test",
        active=True,
        total_parts=10,
        completed_parts=5,
        created="2025-01-01",
        deadline="2025-06-01",
        area="career",
    )
    base.update(overrides)
    return base


class TestVelocity:
    def test_a_project_on_pace_is_green_and_finishes_before_its_deadline(self):
        # 5 of 10 parts over 60 days is 0.0833 parts a day, so the last 5 parts
        # take another 60 days: 2025-05-01, a month inside the 2025-06-01 deadline.
        v = velocity(_project(), date(2025, 3, 2))
        assert v["parts_per_week"] == pytest.approx(0.5833333333333333)
        assert v["estimated_completion"] == "2025-05-01"
        assert v["days_late"] == -31
        assert v["light"] == "green"

    def test_a_project_past_the_late_threshold_is_red(self):
        # 2 of 10 parts over 137 days puts the finish at 2026-11-17, 595 days
        # past a 2025-04-01 deadline.
        v = velocity(
            _project(completed_parts=2, deadline="2025-04-01"),
            date(2025, 5, 18),
        )
        assert v["estimated_completion"] == "2026-11-17"
        assert v["days_late"] == 595
        assert v["light"] == "red"

    def test_seven_days_late_is_still_yellow_and_eight_is_red(self):
        # The repo draws the line at "within 7 days late" (5-projects/AGENTS.md).
        yellow = velocity(_project(deadline="2025-04-24"), date(2025, 3, 2))
        assert yellow["days_late"] == 7
        assert yellow["light"] == "yellow"
        red = velocity(_project(deadline="2025-04-23"), date(2025, 3, 2))
        assert red["days_late"] == 8
        assert red["light"] == "red"

    def test_zero_completed_parts_gives_no_velocity_at_all(self):
        v = velocity(_project(completed_parts=0), date(2025, 3, 2))
        assert v == {
            "parts_per_week": None,
            "estimated_completion": None,
            "days_late": None,
            "light": None,
        }

    def test_no_deadline_still_gives_a_pace_and_a_finish_date(self):
        v = velocity(_project(deadline=None), date(2025, 3, 2))
        assert v["parts_per_week"] == pytest.approx(0.5833333333333333)
        assert v["estimated_completion"] == "2025-05-01"
        assert v["days_late"] is None
        assert v["light"] is None

    def test_no_start_date_gives_no_velocity_at_all(self):
        v = velocity(_project(created=None), date(2025, 3, 2))
        assert v["parts_per_week"] is None
        assert v["estimated_completion"] is None
        assert v["days_late"] is None
        assert v["light"] is None


TASKS = [
    {"id": "task-1", "project": "proj-20250101-001"},
    {"id": "task-2", "project": "proj-other"},
]


class TestDaysIdle:
    def test_idle_days_count_from_the_newest_event_on_the_project_s_tasks(self):
        events = [
            {"task_id": "task-1", "event": "created", "timestamp": "2025-09-02T08:00:00"},
            {"task_id": "task-1", "event": "focus", "timestamp": "2025-09-10T08:00:00"},
            {"task_id": "task-2", "event": "focus", "timestamp": "2025-09-19T08:00:00"},
        ]
        assert days_idle(_project(), TASKS, events, date(2025, 9, 20)) == 10

    def test_without_events_the_count_falls_back_to_the_project_start(self):
        project = _project(started="2025-09-01", created="2025-08-01")
        assert days_idle(project, TASKS, [], date(2025, 9, 20)) == 19

    def test_with_no_tasks_at_all_the_count_falls_back_to_created(self):
        project = _project(created="2025-08-01")
        assert days_idle(project, [], [], date(2025, 9, 20)) == 50

    def test_an_event_without_a_timestamp_field_is_ignored(self):
        # An older event row may carry its date under `ts` or `date`. This
        # gauge reads `timestamp` only, so such a row does not move the count.
        events = [{"task_id": "task-1", "event": "focus", "ts": "2025-09-10T08:00:00"}]
        project = _project(started="2025-09-01")
        assert days_idle(project, TASKS, events, date(2025, 9, 20)) == 19

    def test_a_project_with_no_start_and_no_events_has_no_count(self):
        project = _project(created=None)
        assert days_idle(project, [], [], date(2025, 9, 20)) is None
