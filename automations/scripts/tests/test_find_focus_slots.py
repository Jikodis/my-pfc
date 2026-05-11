"""Unit tests for find_focus_slots.schedule()."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

from automations.scripts.find_focus_slots import schedule


class TestEmptyWeekday(unittest.TestCase):
    def test_three_S_tasks_fit_in_morning_window(self):
        # Monday 2026-04-20, no busy events, three S tasks (15 min each).
        result = schedule(
            date_str="2026-04-20",
            busy_events=[],
            tasks=[
                {"id": "t1", "size": "S"},
                {"id": "t2", "size": "S"},
                {"id": "t3", "size": "S"},
            ],
        )
        self.assertEqual(result["unscheduled"], [])
        self.assertEqual(len(result["placements"]), 3)
        self.assertEqual(result["placements"][0]["task_id"], "t1")
        self.assertEqual(result["placements"][0]["start"], "2026-04-20T08:00:00-06:00")
        self.assertEqual(result["placements"][0]["end"],   "2026-04-20T08:15:00-06:00")
        self.assertEqual(result["placements"][1]["start"], "2026-04-20T08:15:00-06:00")
        self.assertEqual(result["placements"][1]["end"],   "2026-04-20T08:30:00-06:00")
        self.assertEqual(result["placements"][2]["start"], "2026-04-20T08:30:00-06:00")
        self.assertEqual(result["placements"][2]["end"],   "2026-04-20T08:45:00-06:00")


class TestBusyEventsSubtract(unittest.TestCase):
    def test_morning_meeting_pushes_tasks_to_lunch(self):
        # Monday 2026-04-20. Meeting 8:00-9:00 blocks the whole morning window.
        # Three S tasks (15 min each) pack sequentially into the lunch window
        # (12:00-13:00). All three fit within lunch (total 45 min).
        result = schedule(
            date_str="2026-04-20",
            busy_events=[
                {"start": "2026-04-20T08:00:00-06:00", "end": "2026-04-20T09:00:00-06:00"},
            ],
            tasks=[
                {"id": "t1", "size": "S"},
                {"id": "t2", "size": "S"},
                {"id": "t3", "size": "S"},
            ],
        )
        self.assertEqual(result["unscheduled"], [])
        self.assertEqual(result["placements"][0]["start"], "2026-04-20T12:00:00-06:00")
        self.assertEqual(result["placements"][0]["end"],   "2026-04-20T12:15:00-06:00")
        self.assertEqual(result["placements"][1]["start"], "2026-04-20T12:15:00-06:00")
        self.assertEqual(result["placements"][1]["end"],   "2026-04-20T12:30:00-06:00")
        self.assertEqual(result["placements"][2]["start"], "2026-04-20T12:30:00-06:00")
        self.assertEqual(result["placements"][2]["end"],   "2026-04-20T12:45:00-06:00")

    def test_partial_overlap_splits_window(self):
        # Monday. A 30-min busy block 12:15-12:45 splits lunch into two halves.
        # Two M tasks (30 min each): first takes 12:00-12:15? No, too short.
        # First M goes to 8:00-8:30. Second M goes to 8:30-9:00.
        # Lunch is now unused because neither half fits a 30-min task.
        result = schedule(
            date_str="2026-04-20",
            busy_events=[
                {"start": "2026-04-20T12:15:00-06:00", "end": "2026-04-20T12:45:00-06:00"},
            ],
            tasks=[
                {"id": "m1", "size": "M"},
                {"id": "m2", "size": "M"},
            ],
        )
        self.assertEqual(result["unscheduled"], [])
        self.assertEqual(result["placements"][0]["start"], "2026-04-20T08:00:00-06:00")
        self.assertEqual(result["placements"][0]["end"],   "2026-04-20T08:30:00-06:00")
        self.assertEqual(result["placements"][1]["start"], "2026-04-20T08:30:00-06:00")
        self.assertEqual(result["placements"][1]["end"],   "2026-04-20T09:00:00-06:00")


class TestWeekendWindow(unittest.TestCase):
    def test_saturday_uses_single_long_window(self):
        # Saturday 2026-04-18. Empty calendar. An L task fits before noon
        # even though weekday windows wouldn't allow it.
        result = schedule(
            date_str="2026-04-18",
            busy_events=[],
            tasks=[{"id": "big", "size": "L"}],
        )
        self.assertEqual(result["unscheduled"], [])
        self.assertEqual(result["placements"][0]["start"], "2026-04-18T08:00:00-06:00")
        self.assertEqual(result["placements"][0]["end"],   "2026-04-18T09:00:00-06:00")

    def test_sunday_midday_event_splits_window(self):
        # Sunday 2026-04-19. Morning commitment 9:00-12:00. A 60-min task fits 8-9,
        # next 60-min task fits 12:00-13:00.
        result = schedule(
            date_str="2026-04-19",
            busy_events=[
                {"start": "2026-04-19T09:00:00-06:00", "end": "2026-04-19T12:00:00-06:00"},
            ],
            tasks=[
                {"id": "a", "size": "L"},
                {"id": "b", "size": "L"},
            ],
        )
        self.assertEqual(result["unscheduled"], [])
        self.assertEqual(result["placements"][0]["start"], "2026-04-19T08:00:00-06:00")
        self.assertEqual(result["placements"][0]["end"],   "2026-04-19T09:00:00-06:00")
        self.assertEqual(result["placements"][1]["start"], "2026-04-19T12:00:00-06:00")
        self.assertEqual(result["placements"][1]["end"],   "2026-04-19T13:00:00-06:00")


class TestUnscheduled(unittest.TestCase):
    def test_task_that_doesnt_fit_goes_to_unscheduled(self):
        # Monday. Busy blocks fill all windows except a 20-min gap 8:00-8:20.
        # An L (60 min) task cannot fit anywhere → unscheduled.
        # An S (15 min) task fits in the 8:00 gap.
        result = schedule(
            date_str="2026-04-20",
            busy_events=[
                {"start": "2026-04-20T08:20:00-06:00", "end": "2026-04-20T09:00:00-06:00"},
                {"start": "2026-04-20T12:00:00-06:00", "end": "2026-04-20T13:00:00-06:00"},
                {"start": "2026-04-20T17:00:00-06:00", "end": "2026-04-20T21:00:00-06:00"},
            ],
            tasks=[
                {"id": "small", "size": "S"},
                {"id": "big",   "size": "L"},
            ],
        )
        self.assertEqual(result["unscheduled"], ["big"])
        self.assertEqual(len(result["placements"]), 1)
        self.assertEqual(result["placements"][0]["task_id"], "small")
        self.assertEqual(result["placements"][0]["start"], "2026-04-20T08:00:00-06:00")

    def test_lower_priority_can_still_fit_when_higher_cannot(self):
        # Monday. Only an 8:00-8:20 window is free. L can't fit, but S after it can.
        result = schedule(
            date_str="2026-04-20",
            busy_events=[
                {"start": "2026-04-20T08:20:00-06:00", "end": "2026-04-20T09:00:00-06:00"},
                {"start": "2026-04-20T12:00:00-06:00", "end": "2026-04-20T13:00:00-06:00"},
                {"start": "2026-04-20T17:00:00-06:00", "end": "2026-04-20T21:00:00-06:00"},
            ],
            tasks=[
                {"id": "big",   "size": "L"},
                {"id": "small", "size": "S"},
            ],
        )
        self.assertEqual(result["unscheduled"], ["big"])
        self.assertEqual(result["placements"][0]["task_id"], "small")


class TestNullSize(unittest.TestCase):
    def test_null_size_treated_as_M(self):
        # Monday. Task with size: null should get 30 min (M default).
        result = schedule(
            date_str="2026-04-20",
            busy_events=[],
            tasks=[{"id": "unknown", "size": None}],
        )
        self.assertEqual(result["unscheduled"], [])
        self.assertEqual(result["placements"][0]["start"], "2026-04-20T08:00:00-06:00")
        self.assertEqual(result["placements"][0]["end"],   "2026-04-20T08:30:00-06:00")

    def test_missing_size_key_treated_as_M(self):
        result = schedule(
            date_str="2026-04-20",
            busy_events=[],
            tasks=[{"id": "unknown"}],
        )
        self.assertEqual(result["placements"][0]["end"], "2026-04-20T08:30:00-06:00")


class TestDST(unittest.TestCase):
    def test_spring_forward_uses_mdt_offset(self):
        # 2026-03-08 is the Sunday the US springs forward. 8 AM local = MDT (-06:00).
        result = schedule(
            date_str="2026-03-08",
            busy_events=[],
            tasks=[{"id": "t", "size": "S"}],
        )
        self.assertEqual(result["placements"][0]["start"], "2026-03-08T08:00:00-06:00")

    def test_before_spring_forward_uses_mst_offset(self):
        # 2026-03-07 is still MST (-07:00).
        result = schedule(
            date_str="2026-03-07",
            busy_events=[],
            tasks=[{"id": "t", "size": "S"}],
        )
        self.assertEqual(result["placements"][0]["start"], "2026-03-07T08:00:00-07:00")

    def test_fall_back_uses_mst_offset(self):
        # 2026-11-01 falls back to MST.
        result = schedule(
            date_str="2026-11-01",
            busy_events=[],
            tasks=[{"id": "t", "size": "S"}],
        )
        self.assertEqual(result["placements"][0]["start"], "2026-11-01T08:00:00-07:00")


class TestCLI(unittest.TestCase):
    def test_main_reads_stdin_and_writes_stdout(self):
        repo = Path(__file__).resolve().parents[3]
        script = repo / "automations" / "scripts" / "find_focus_slots.py"
        payload = {
            "date": "2026-04-20",
            "busy_events": [],
            "tasks": [{"id": "cli-task", "size": "S"}],
        }
        proc = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(proc.stdout)
        self.assertEqual(result["unscheduled"], [])
        self.assertEqual(result["placements"][0]["task_id"], "cli-task")
        self.assertEqual(result["placements"][0]["start"], "2026-04-20T08:00:00-06:00")


class TestNowClipping(unittest.TestCase):
    def test_now_skips_past_windows(self):
        # Monday 2026-04-20. Current time is 2 PM, past the 8-9 AM and 12-1 PM
        # windows. A 15-min S task should land at 5 PM, not 8 AM.
        result = schedule(
            date_str="2026-04-20",
            busy_events=[],
            tasks=[{"id": "t", "size": "S"}],
            now="2026-04-20T14:00:00-06:00",
        )
        self.assertEqual(result["placements"][0]["start"], "2026-04-20T17:00:00-06:00")

    def test_now_rounds_up_to_quarter(self):
        # If now = 2:03 PM, the usable start should be 2:15 PM — but that's inside
        # the work block. The next personal window is 5 PM, so task lands there.
        result = schedule(
            date_str="2026-04-20",
            busy_events=[],
            tasks=[{"id": "t", "size": "S"}],
            now="2026-04-20T14:03:00-06:00",
        )
        self.assertEqual(result["placements"][0]["start"], "2026-04-20T17:00:00-06:00")

    def test_now_inside_current_window_clips_start(self):
        # Weekend 2026-04-18. 10-hour window 8 AM - 9 PM. If now = 10:07 AM,
        # the task starts at 10:15 AM (next quarter-hour).
        result = schedule(
            date_str="2026-04-18",
            busy_events=[],
            tasks=[{"id": "t", "size": "M"}],
            now="2026-04-18T10:07:00-06:00",
        )
        self.assertEqual(result["placements"][0]["start"], "2026-04-18T10:15:00-06:00")
        self.assertEqual(result["placements"][0]["end"],   "2026-04-18T10:45:00-06:00")

    def test_now_past_all_windows_leaves_unscheduled(self):
        # Monday. now = 9:30 PM, after the 5-9 PM window closes.
        result = schedule(
            date_str="2026-04-20",
            busy_events=[],
            tasks=[{"id": "t", "size": "S"}],
            now="2026-04-20T21:30:00-06:00",
        )
        self.assertEqual(result["unscheduled"], ["t"])
        self.assertEqual(result["placements"], [])

    def test_now_omitted_preserves_original_behavior(self):
        result = schedule(
            date_str="2026-04-20",
            busy_events=[],
            tasks=[{"id": "t", "size": "S"}],
        )
        self.assertEqual(result["placements"][0]["start"], "2026-04-20T08:00:00-06:00")


class TestExtraSizes(unittest.TestCase):
    def test_XS_floored_to_15_minute_slot(self):
        # XS = 5 min intrinsic, but MIN_SLOT_MINUTES floors the calendar block at 15 min.
        result = schedule(
            date_str="2026-04-20",
            busy_events=[],
            tasks=[{"id": "tiny", "size": "XS"}],
        )
        self.assertEqual(result["placements"][0]["start"], "2026-04-20T08:00:00-06:00")
        self.assertEqual(result["placements"][0]["end"],   "2026-04-20T08:15:00-06:00")

    def test_XL_is_120_minutes(self):
        # XL = 2 hours. Only fits in the evening window on a weekday (5-9 PM = 4h).
        result = schedule(
            date_str="2026-04-20",
            busy_events=[],
            tasks=[{"id": "huge", "size": "XL"}],
        )
        self.assertEqual(result["placements"][0]["start"], "2026-04-20T17:00:00-06:00")
        self.assertEqual(result["placements"][0]["end"],   "2026-04-20T19:00:00-06:00")


if __name__ == "__main__":
    unittest.main()
