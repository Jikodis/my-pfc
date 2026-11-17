"""Unit tests for derive_sleep_habit.

The bar itself is qqrt.timing; these tests cover the mirroring, not the bar.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from derive_sleep_habit import HABIT_ID, SOURCE, derived_rows, merge


def day(date, timing):
    return {"date": date, "qqrt": None if timing is None else {"timing": timing}}


class TestDerivedRows(unittest.TestCase):
    def test_true_and_false_both_produce_rows(self):
        rows = derived_rows([day("2025-01-26", True), day("2025-01-27", False)])
        self.assertEqual([(r["date"], r["completed"]) for r in rows],
                         [("2025-01-26", True), ("2025-01-27", False)])

    def test_night_without_sleep_data_produces_no_row(self):
        # Absence already reads as a miss; writing `false` for a night the watch
        # was off would be a fabricated miss, which poisons the rate.
        self.assertEqual(derived_rows([day("2025-01-26", None)]), [])

    def test_missing_qqrt_block_produces_no_row(self):
        self.assertEqual(derived_rows([{"date": "2025-01-26"}]), [])

    def test_rows_carry_the_derived_source(self):
        self.assertEqual(derived_rows([day("2025-01-26", True)])[0]["source"], SOURCE)


class TestMerge(unittest.TestCase):
    def test_unrelated_habits_are_untouched(self):
        existing = [{"habit_id": "morning-walk", "date": "2025-01-26",
                     "completed": True, "source": "chat"}]
        out = merge(existing, derived_rows([day("2025-01-26", True)]))
        self.assertIn(existing[0], out)

    def test_rerun_is_idempotent(self):
        rows = derived_rows([day("2025-01-26", True), day("2025-01-27", False)])
        once = merge([], rows)
        self.assertEqual(merge(once, rows), once)

    def test_corrected_night_is_rewritten_not_duplicated(self):
        stale = merge([], derived_rows([day("2025-01-26", False)]))
        fixed = merge(stale, derived_rows([day("2025-01-26", True)]))
        mine = [r for r in fixed if r["habit_id"] == HABIT_ID]
        self.assertEqual(len(mine), 1)
        self.assertTrue(mine[0]["completed"])

    def test_hand_logged_row_wins_over_the_derived_one(self):
        manual = {"habit_id": HABIT_ID, "date": "2025-01-26",
                  "completed": True, "source": "chat"}
        out = merge([manual], derived_rows([day("2025-01-26", False)]))
        mine = [r for r in out if r["habit_id"] == HABIT_ID]
        self.assertEqual(mine, [manual])

    def test_night_that_lost_its_data_drops_its_derived_row(self):
        stale = merge([], derived_rows([day("2025-01-26", True)]))
        out = merge(stale, derived_rows([]))
        self.assertEqual([r for r in out if r["habit_id"] == HABIT_ID], [])

    def test_new_nights_are_appended_in_date_order(self):
        out = merge([], derived_rows([day("2025-01-27", True), day("2025-01-26", False)]))
        self.assertEqual([r["date"] for r in out], ["2025-01-26", "2025-01-27"])


if __name__ == "__main__":
    unittest.main()
