"""Unit tests for web_data: habit rows and habit titles for the web UI."""

import unittest
import unittest.mock

from automations.scripts import web_data
from automations.scripts.web_data import current_run, habit_rows, habit_title, run_label

SCHEMA = {
    "daily_habits": [
        {"id": "walk", "description": "Walk", "frequency": 7, "area": "health", "started": "2026-01-01"},
        {"id": "old", "description": "Old", "frequency": 7, "area": "health", "active": False},
    ],
    "monthly_habits": [
        {"id": "deep-clean", "description": "Deep clean the kitchen", "frequency": 2, "area": "household"},
    ],
}


def log(habit_id, date, completed=True):
    return {"habit_id": habit_id, "date": date, "completed": completed}


class TestHabitRows(unittest.TestCase):
    def test_unlogged_days_count_as_missed(self):
        daily = [log("walk", f"2026-07-{d:02d}") for d in range(15, 29)]  # 14 of 28 days
        rows = habit_rows(SCHEMA, daily, [], "2026-07-28", window_days=28)
        row = next(r for r in rows if r["id"] == "walk")
        self.assertEqual(row["completed"], 14)
        self.assertEqual(row["target"], 28)
        self.assertEqual(row["rate_pct"], 50)

    def test_inactive_habits_are_left_out(self):
        rows = habit_rows(SCHEMA, [], [], "2026-07-28", window_days=28)
        self.assertNotIn("old", [r["id"] for r in rows])

    def test_monthly_habit_uses_monthly_cadence(self):
        monthly = [log("deep-clean", "2026-07-10"), log("deep-clean", "2026-07-20")]
        rows = habit_rows(SCHEMA, [], monthly, "2026-07-28", window_days=28)
        row = next(r for r in rows if r["id"] == "deep-clean")
        self.assertEqual(row["cadence"], "monthly")
        self.assertEqual(row["rate_pct"], 100)
        self.assertEqual(row["light"], "green")

    def test_rows_sort_red_first(self):
        daily = [log("walk", f"2026-07-{d:02d}") for d in range(1, 29)]
        rows = habit_rows(SCHEMA, daily, [], "2026-07-28", window_days=28)
        self.assertEqual([r["light"] for r in rows], ["red", "green"])

    def test_every_row_carries_a_short_title_derived_from_the_id(self):
        rows = habit_rows(SCHEMA, [], [], "2026-07-28", window_days=28)
        titles = {r["id"]: r["title"] for r in rows}
        self.assertEqual(titles["walk"], "Walk")
        self.assertEqual(titles["deep-clean"], "Deep clean")

    def test_a_long_title_is_not_clipped(self):
        schema = {"daily_habits": [
            {"id": "stretch-before-bed-every-single-night", "description": "x" * 400, "frequency": 7},
        ]}
        rows = habit_rows(schema, [], [], "2026-07-28", window_days=28)
        self.assertEqual(rows[0]["title"], "Stretch before bed every single night")


def skip(habit_id, date):
    return {"habit_id": habit_id, "date": date, "completed": False, "skipped": True}


class TestCurrentRun(unittest.TestCase):
    """The run a habit is on right now: today, or yesterday when today has no log yet."""

    def test_a_run_ending_yesterday_survives_an_unlogged_today(self):
        logs = [log("walk", d) for d in ("2026-07-25", "2026-07-26", "2026-07-27")]
        self.assertEqual(current_run(logs, "walk", None, "2026-07-28", "daily", 7), 3)

    def test_the_same_run_with_today_done_is_one_longer(self):
        logs = [log("walk", d) for d in ("2026-07-25", "2026-07-26", "2026-07-27", "2026-07-28")]
        self.assertEqual(current_run(logs, "walk", None, "2026-07-28", "daily", 7), 4)

    def test_a_skipped_day_neither_breaks_the_run_nor_counts_toward_it(self):
        logs = [log("walk", "2026-07-26"), skip("walk", "2026-07-27"), log("walk", "2026-07-28")]
        self.assertEqual(current_run(logs, "walk", None, "2026-07-28", "daily", 7), 2)

    def test_an_unlogged_day_in_the_middle_ends_the_run(self):
        logs = [log("walk", "2026-07-25"), log("walk", "2026-07-26"), log("walk", "2026-07-28")]
        self.assertEqual(current_run(logs, "walk", None, "2026-07-28", "daily", 7), 1)

    def test_a_logged_miss_in_the_middle_ends_the_run(self):
        logs = [log("walk", "2026-07-26"), log("walk", "2026-07-27", completed=False), log("walk", "2026-07-28")]
        self.assertEqual(current_run(logs, "walk", None, "2026-07-28", "daily", 7), 1)

    def test_a_run_never_walks_back_past_the_day_the_habit_started(self):
        logs = [log("walk", d) for d in ("2026-07-25", "2026-07-26", "2026-07-27", "2026-07-28")]
        self.assertEqual(current_run(logs, "walk", "2026-07-27", "2026-07-28", "daily", 7), 2)

    def test_a_habit_never_done_is_on_no_run(self):
        self.assertEqual(current_run([], "walk", None, "2026-07-28", "daily", 7), 0)

    def test_two_full_months_then_a_short_current_month_is_two(self):
        logs = ([log("deep-clean", "2026-05-08"), log("deep-clean", "2026-05-22")]
                + [log("deep-clean", "2026-06-05"), log("deep-clean", "2026-06-19")]
                + [log("deep-clean", "2026-07-10")])
        self.assertEqual(current_run(logs, "deep-clean", None, "2026-07-28", "monthly", 2), 2)

    def test_a_current_month_that_reached_its_frequency_counts(self):
        logs = ([log("deep-clean", "2026-06-05"), log("deep-clean", "2026-06-19")]
                + [log("deep-clean", "2026-07-10"), log("deep-clean", "2026-07-24")])
        self.assertEqual(current_run(logs, "deep-clean", None, "2026-07-28", "monthly", 2), 2)

    def test_every_habit_row_carries_its_run_and_the_unit_it_is_counted_in(self):
        daily = [log("walk", "2026-07-27"), log("walk", "2026-07-28")]
        monthly = [log("deep-clean", "2026-07-10"), log("deep-clean", "2026-07-20")]
        rows = {r["id"]: r for r in habit_rows(SCHEMA, daily, monthly, "2026-07-28", window_days=28)}
        self.assertEqual((rows["walk"]["current_run"], rows["walk"]["run_unit"]), (2, "days"))
        self.assertEqual((rows["deep-clean"]["current_run"], rows["deep-clean"]["run_unit"]), (1, "months"))


    def test_a_habit_the_system_logs_itself_says_so(self):
        schema = {"daily_habits": [
            {"id": "walk", "description": "Walk", "frequency": 7, "area": "health"},
            {"id": "asleep", "description": "Asleep", "frequency": 7, "area": "health", "auto_derived": True},
        ]}
        rows = {r["id"]: r for r in habit_rows(schema, [], [], "2026-07-28", window_days=28)}
        self.assertIs(rows["asleep"]["auto_derived"], True)
        self.assertIs(rows["walk"]["auto_derived"], False)


class TestLoggedToday(unittest.TestCase):
    """Whether a habit already has a completed row for today, so a page can hide Log today."""

    def rows(self, daily, monthly=()):
        return {r["id"]: r for r in habit_rows(SCHEMA, daily, list(monthly), "2026-07-28", window_days=28)}

    def test_a_completed_row_for_today_is_logged(self):
        self.assertIs(self.rows([log("walk", "2026-07-28")])["walk"]["logged_today"], True)

    def test_no_row_for_today_is_not_logged(self):
        self.assertIs(self.rows([log("walk", "2026-07-27")])["walk"]["logged_today"], False)

    def test_a_missed_row_for_today_is_not_logged(self):
        self.assertIs(self.rows([log("walk", "2026-07-28", completed=False)])["walk"]["logged_today"], False)

    def test_a_skipped_row_for_today_is_not_logged(self):
        self.assertIs(self.rows([skip("walk", "2026-07-28")])["walk"]["logged_today"], False)

    def test_the_latest_row_for_today_wins(self):
        rows = self.rows([log("walk", "2026-07-28", completed=False), log("walk", "2026-07-28")])
        self.assertIs(rows["walk"]["logged_today"], True)

    def test_monthly_habits_read_their_own_log(self):
        rows = self.rows([], [log("deep-clean", "2026-07-28")])
        self.assertIs(rows["deep-clean"]["logged_today"], True)

    def test_a_completed_row_for_yesterday_is_logged_yesterday(self):
        rows = self.rows([log("walk", "2026-07-27")])
        self.assertIs(rows["walk"]["logged_yesterday"], True)
        self.assertIs(rows["walk"]["logged_today"], False)

    def test_a_missed_row_for_yesterday_is_not_logged_yesterday(self):
        self.assertIs(self.rows([log("walk", "2026-07-27", completed=False)])["walk"]["logged_yesterday"], False)

    def test_yesterday_reads_as_logged_for_a_habit_that_had_not_started(self):
        # Nothing to log on a day before the habit existed, so no page offers it.
        schema = {"daily_habits": [{"id": "new", "description": "New", "frequency": 7, "started": "2026-07-28"}]}
        row = habit_rows(schema, [], [], "2026-07-28", window_days=28)[0]
        self.assertIs(row["logged_yesterday"], True)


class TestRunLabel(unittest.TestCase):
    """The run and its unit, written out as one phrase, so no surface joins them itself."""

    def test_one_of_something_is_singular(self):
        self.assertEqual(run_label(1, "daily"), "1 day")
        self.assertEqual(run_label(1, "monthly"), "1 month")

    def test_more_than_one_is_plural(self):
        self.assertEqual(run_label(3, "daily"), "3 days")
        self.assertEqual(run_label(2, "monthly"), "2 months")

    def test_a_run_of_nothing_says_so_in_words(self):
        self.assertEqual(run_label(0, "daily"), "none yet")
        self.assertEqual(run_label(0, "monthly"), "none yet")

    def test_every_habit_row_carries_the_label_beside_the_number(self):
        daily = [log("walk", "2026-07-27"), log("walk", "2026-07-28")]
        monthly = [log("deep-clean", "2026-07-10"), log("deep-clean", "2026-07-20")]
        rows = {r["id"]: r for r in habit_rows(SCHEMA, daily, monthly, "2026-07-28", window_days=28)}
        self.assertEqual(rows["walk"]["run_label"], "2 days")
        self.assertEqual(rows["deep-clean"]["run_label"], "1 month")


class TestHabitTitleCasing(unittest.TestCase):
    """Capitalize alone lowercases everything after the first letter, which turned
    initialisms and units into `Ai course unit` and `Hydration 2l`."""

    def test_an_initialism_is_uppercased_wherever_it_sits(self):
        self.assertEqual(habit_title("ai-course-unit"), "AI course unit")
        self.assertEqual(habit_title("practice-hiit"), "Practice HIIT")
        self.assertEqual(habit_title("hydration-2l"), "Hydration 2L")

    def test_a_known_phrase_keeps_its_own_capitals(self):
        with unittest.mock.patch.dict(web_data.TITLE_CASING, {"new york": "New York"}):
            self.assertEqual(habit_title("visit-new-york"), "Visit New York")

    def test_a_clock_time_reads_as_a_12_hour_time(self):
        self.assertEqual(habit_title("asleep-before-11pm"), "Asleep before 11 PM")

    def test_a_plain_title_is_left_alone(self):
        self.assertEqual(habit_title("practice-guitar"), "Practice guitar")
