"""Unit tests for focus_status — rate math, light thresholds, red-week counting."""

import unittest

from automations.scripts.focus_status import (
    code,
    compute,
    consecutive_red_weeks,
    habit_rate,
    light,
    window_target,
)


def daily_log(habit_id, date, completed=True, skipped=False):
    return {"habit_id": habit_id, "date": date, "completed": completed, "skipped": skipped}


def days(start_day, n):
    """n consecutive dates in 2025-01, starting at start_day."""
    return [f"2025-01-{start_day + i:02d}" for i in range(n)]


class TestWindowTarget(unittest.TestCase):
    def test_daily_seven_per_week_over_28_days_is_28(self):
        self.assertEqual(window_target(7, "daily", 28), 28)

    def test_daily_three_per_week_over_28_days_is_12(self):
        self.assertEqual(window_target(3, "daily", 28), 12)

    def test_daily_one_per_week_over_28_days_is_4(self):
        self.assertEqual(window_target(1, "daily", 28), 4)

    def test_skipped_days_shrink_the_target(self):
        # A 7/wk habit with 10 structurally-unavailable days -> 18 available.
        self.assertEqual(window_target(7, "daily", 18), 18)

    def test_monthly_two_per_month_over_28_days_is_2(self):
        self.assertEqual(window_target(2, "monthly", 28), 2)

    def test_target_never_drops_below_one(self):
        self.assertEqual(window_target(1, "daily", 1), 1)


class TestLightThresholds(unittest.TestCase):
    def test_seventy_percent_is_green(self):
        self.assertEqual(light(0.70), "green")

    def test_just_under_seventy_is_yellow(self):
        self.assertEqual(light(0.699), "yellow")

    def test_forty_percent_is_yellow(self):
        self.assertEqual(light(0.40), "yellow")

    def test_just_under_forty_is_red(self):
        self.assertEqual(light(0.399), "red")

    def test_zero_is_red(self):
        self.assertEqual(light(0.0), "red")


class TestHabitRate(unittest.TestCase):
    """A synthetic 2025-01-04..2025-01-31 window (28 days)."""

    def test_zero_of_four_is_red(self):
        # practice-guitar at a ramped frequency of 1/wk: 0 completed.
        logs = [daily_log("practice-guitar", d, completed=False) for d in days(4, 8)]
        r = habit_rate(logs, "practice-guitar", "2025-01-04", "2025-01-31", 1, "daily")
        self.assertEqual(r["completed"], 0)
        self.assertEqual(r["target"], 4)
        self.assertEqual(r["rate"], 0.0)

    def test_six_of_twelve_is_fifty_percent(self):
        logs = [daily_log("study-spanish", d) for d in days(4, 6)]
        logs += [daily_log("study-spanish", d, completed=False) for d in days(12, 5)]
        r = habit_rate(logs, "study-spanish", "2025-01-04", "2025-01-31", 3, "daily")
        self.assertEqual(r["completed"], 6)
        self.assertEqual(r["target"], 12)
        self.assertEqual(r["rate"], 0.5)
        self.assertEqual(light(r["rate"]), "yellow")

    def test_skipped_days_leave_both_numerator_and_denominator(self):
        # 4 completed, 10 skipped (structurally unavailable), 7/wk over 28 days.
        logs = [daily_log("family-reading", d) for d in days(4, 4)]
        logs += [daily_log("family-reading", d, completed=False, skipped=True)
                 for d in days(10, 10)]
        r = habit_rate(logs, "family-reading", "2025-01-04", "2025-01-31", 7, "daily")
        self.assertEqual(r["skipped"], 10)
        self.assertEqual(r["target"], 18)
        self.assertEqual(r["completed"], 4)

    def test_unlogged_days_count_as_misses(self):
        # Only 2 of 28 nights logged, both complete. Unlogged = missed.
        logs = [daily_log("read-before-bed", d) for d in days(4, 2)]
        r = habit_rate(logs, "read-before-bed", "2025-01-04", "2025-01-31", 7, "daily")
        self.assertEqual(r["completed"], 2)
        self.assertEqual(r["target"], 28)
        self.assertEqual(light(r["rate"]), "red")

    def test_logs_outside_the_window_are_ignored(self):
        logs = [daily_log("morning-workout", "2024-12-01")]
        r = habit_rate(logs, "morning-workout", "2025-01-04", "2025-01-31", 7, "daily")
        self.assertEqual(r["completed"], 0)

    def test_other_habits_are_ignored(self):
        logs = [daily_log("study-spanish", d) for d in days(4, 6)]
        r = habit_rate(logs, "practice-guitar", "2025-01-04", "2025-01-31", 1, "daily")
        self.assertEqual(r["completed"], 0)


class TestCode(unittest.TestCase):
    def test_high_high_is_AA(self):
        self.assertEqual(code({"impact": "high", "urgency": "high"}), "AA")

    def test_high_medium_is_AB(self):
        self.assertEqual(code({"impact": "high", "urgency": "medium"}), "AB")

    def test_medium_low_is_BC(self):
        self.assertEqual(code({"impact": "medium", "urgency": "low"}), "BC")


class TestConsecutiveRedWeeks(unittest.TestCase):
    def test_nothing_logged_hits_the_cap(self):
        n = consecutive_red_weeks([], "practice-guitar", "2025-01-31", 1, "daily")
        self.assertEqual(n, 8)  # nothing logged at all -> every window red

    def test_weeks_before_the_habit_existed_do_not_count(self):
        # A habit started 3 days ago has had no full week — it cannot be
        # "red 8 weeks running" on day one.
        n = consecutive_red_weeks([], "online-course-unit", "2025-01-31", 1, "daily",
                                  started="2025-01-29")
        self.assertEqual(n, 0)

    def test_a_habit_alive_two_full_weeks_can_show_two_red_weeks(self):
        n = consecutive_red_weeks([], "online-course-unit", "2025-01-31", 1, "daily",
                                  started="2025-01-18")
        self.assertEqual(n, 2)

    def test_a_green_week_stops_the_count(self):
        # Most recent 7 days (2025-01-25..01-31) fully complete -> not red.
        logs = [daily_log("morning-workout", f"2025-01-{d}") for d in range(25, 32)]
        n = consecutive_red_weeks(logs, "morning-workout", "2025-01-31", 7, "daily")
        self.assertEqual(n, 0)


class TestCompute(unittest.TestCase):
    def setUp(self):
        self.schema = {
            "daily_habits": [
                {"id": "read-before-bed", "frequency": 7},
                {"id": "no-phone-in-bedroom", "frequency": 7},
                {"id": "practice-guitar", "frequency": 1},
            ],
            "monthly_habits": [{"id": "volunteer-shift", "frequency": 2}],
        }

    def test_primary_vehicle_drives_the_light_not_the_supporting_one(self):
        focuses = [{
            "id": "focus-20250106-001", "title": "Sleep", "tier": "foundation",
            "impact": "high", "urgency": "high", "parked": False,
            "retired_date": None,
            "habits": ["read-before-bed", "no-phone-in-bedroom"],
        }]
        logs = [daily_log("read-before-bed", d) for d in days(4, 20)]
        logs += [daily_log("no-phone-in-bedroom", d) for d in days(4, 2)]
        out = compute(focuses, logs, [], self.schema, "2025-01-31")[0]
        self.assertEqual(out["primary"]["habit_id"], "read-before-bed")
        self.assertEqual(out["status"], "green")           # 20/28 = 71%
        self.assertEqual(len(out["supporting"]), 1)
        self.assertEqual(light(out["supporting"][0]["rate"]), "red")

    def test_parked_focus_reports_parked_and_is_not_red(self):
        focuses = [{
            "id": "focus-20250106-002", "title": "Guitar", "tier": "pursuit",
            "impact": "medium", "urgency": "medium", "parked": True,
            "retired_date": None, "habits": ["practice-guitar"],
        }]
        out = compute(focuses, [], [], self.schema, "2025-01-31")[0]
        self.assertEqual(out["status"], "parked")
        self.assertEqual(out["weeks_red"], 0)

    def test_retired_focus_is_excluded(self):
        focuses = [{
            "id": "focus-20250106-002", "title": "Guitar", "tier": "pursuit",
            "impact": "medium", "urgency": "medium", "parked": False,
            "retired_date": "2025-01-01", "habits": ["practice-guitar"],
        }]
        self.assertEqual(compute(focuses, [], [], self.schema, "2025-01-31"), [])

    def test_focus_with_no_vehicle_reports_unknown_rather_than_crashing(self):
        focuses = [{
            "id": "focus-x", "title": "Orphan", "tier": "consuming",
            "impact": "low", "urgency": "low", "parked": False,
            "retired_date": None, "habits": [],
        }]
        out = compute(focuses, [], [], self.schema, "2025-01-31")[0]
        self.assertEqual(out["status"], "unknown")
        self.assertIsNone(out["primary"])


if __name__ == "__main__":
    unittest.main()
