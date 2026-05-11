"""Unit tests for trello_writeback."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _card(card_id, name="X", desc="", id_list="L1", due_complete=False, closed=False, id_labels=None):
    return {"id": card_id, "name": name, "desc": desc, "idList": id_list,
            "dueComplete": due_complete, "closed": closed, "idLabels": id_labels or []}


class TestPollCompleted(unittest.TestCase):
    @patch("trello_writeback.list_cards_on_board")
    @patch("trello_writeback.list_lists")
    def test_returns_only_due_complete_in_interactive_lists(self, mock_lists, mock_cards):
        from trello_writeback import poll_completed_cards
        mock_lists.return_value = [
            {"id": "L_2plus1", "name": "✅ 2+1", "closed": False},
            {"id": "L_actions", "name": "✅ Actions", "closed": False},
            {"id": "L_values", "name": "💎 Values", "closed": False},
            {"id": "L_inbox", "name": "📥 Inbox", "closed": False},
        ]
        mock_cards.return_value = [
            _card("c1", id_list="L_2plus1", due_complete=True, desc="---\npfc-id: task-1\npfc-type: task\n---\n\nb"),
            _card("c2", id_list="L_actions", due_complete=True, desc="---\npfc-id: task-2\npfc-type: task\n---\n\nb"),
            _card("c3", id_list="L_actions", due_complete=False, desc="---\npfc-id: task-3\npfc-type: task\n---\n\nb"),
            # Card on read-only list with dueComplete — must be ignored.
            _card("c4", id_list="L_values", due_complete=True, desc="---\npfc-id: value-1\npfc-type: value\n---\n\n"),
            # Card on Inbox — must be ignored even with dueComplete.
            _card("c5", id_list="L_inbox", due_complete=True, desc=""),
        ]
        completed = poll_completed_cards("K", "T", "BOARD")
        ids = sorted([c["pfc_id"] for c in completed])
        self.assertEqual(ids, ["task-1", "task-2"])

    @patch("trello_writeback.list_cards_on_board")
    @patch("trello_writeback.list_lists")
    def test_skips_cards_without_pfc_id(self, mock_lists, mock_cards):
        from trello_writeback import poll_completed_cards
        mock_lists.return_value = [
            {"id": "L_actions", "name": "✅ Actions", "closed": False},
        ]
        mock_cards.return_value = [
            _card("c1", id_list="L_actions", due_complete=True, desc="No frontmatter"),
        ]
        completed = poll_completed_cards("K", "T", "BOARD")
        self.assertEqual(completed, [])


class TestCompleteTaskFromCard(unittest.TestCase):
    def setUp(self):
        # Use a temp tasks.ndjson and task_events.ndjson for isolation
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        self.tasks_path = Path(self.tmpdir) / "tasks.ndjson"
        self.events_path = Path(self.tmpdir) / "task_events.ndjson"
        self.tasks_path.write_text(
            '{"id":"task-1","status":"open","description":"X","completed":null}\n'
            '{"id":"task-2","status":"done","description":"Y","completed":"2026-05-01"}\n'
        )
        self.events_path.write_text("")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    @patch("trello_writeback.archive_card")
    def test_marks_open_task_done_and_archives(self, mock_archive):
        from trello_writeback import complete_task_from_card
        card = {"pfc_id": "task-1", "pfc_type": "task", "list_name": "✅ Actions",
                "trello_card_id": "c1", "card_name": "X"}
        result = complete_task_from_card(
            "K", "T", card, tasks_path=self.tasks_path, events_path=self.events_path,
            today="2026-05-10",
        )
        self.assertEqual(result, "completed")
        # Verify task status updated
        lines = self.tasks_path.read_text().splitlines()
        task = json.loads(lines[0])
        self.assertEqual(task["status"], "done")
        self.assertEqual(task["completed"], "2026-05-10")
        # Verify event logged
        events = [json.loads(l) for l in self.events_path.read_text().splitlines()]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["task_id"], "task-1")
        self.assertEqual(events[0]["event"], "completed")
        self.assertEqual(events[0]["source"], "trello")
        # Verify archive called
        mock_archive.assert_called_once_with("K", "T", "c1")

    @patch("trello_writeback.archive_card")
    def test_already_done_is_idempotent(self, mock_archive):
        from trello_writeback import complete_task_from_card
        card = {"pfc_id": "task-2", "pfc_type": "task", "list_name": "✅ Actions",
                "trello_card_id": "c2", "card_name": "Y"}
        result = complete_task_from_card(
            "K", "T", card, tasks_path=self.tasks_path, events_path=self.events_path,
            today="2026-05-10",
        )
        self.assertEqual(result, "already_done")
        # Task unchanged; only archive_card called (so we clean up the rogue Trello state)
        lines = self.tasks_path.read_text().splitlines()
        task = json.loads(lines[0])
        self.assertEqual(task["status"], "open")  # task-1 unchanged
        # Archive still happens
        mock_archive.assert_called_once_with("K", "T", "c2")

    @patch("trello_writeback.archive_card")
    def test_unknown_task_id_returns_unknown(self, mock_archive):
        from trello_writeback import complete_task_from_card
        card = {"pfc_id": "task-999", "pfc_type": "task", "list_name": "✅ Actions",
                "trello_card_id": "cX", "card_name": "?"}
        result = complete_task_from_card(
            "K", "T", card, tasks_path=self.tasks_path, events_path=self.events_path,
            today="2026-05-10",
        )
        self.assertEqual(result, "unknown")
        mock_archive.assert_not_called()


class TestHabitCompletion(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        self.daily_path = Path(self.tmpdir) / "habits-daily.ndjson"
        self.monthly_path = Path(self.tmpdir) / "habits-monthly.ndjson"
        self.daily_path.write_text("")
        self.monthly_path.write_text("")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    @patch("trello_writeback.update_card")
    def test_daily_habit_logs_for_today(self, mock_update):
        from trello_writeback import log_habit_from_card
        card = {"pfc_id": "habit-daily-morning-walk", "pfc_type": "habit-daily", "list_name": "☀️ Daily Habits",
                "trello_card_id": "c1", "card_name": "✓ Morning walk"}
        result = log_habit_from_card(
            "K", "T", card,
            daily_path=self.daily_path, monthly_path=self.monthly_path,
            today="2026-05-10",
        )
        self.assertEqual(result, "logged")
        records = [json.loads(l) for l in self.daily_path.read_text().splitlines()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["habit_id"], "morning-walk")
        self.assertEqual(records[0]["date"], "2026-05-10")
        self.assertTrue(records[0]["completed"])
        self.assertEqual(records[0]["source"], "trello")

    @patch("trello_writeback.update_card")
    def test_double_log_is_idempotent_for_today(self, mock_update):
        from trello_writeback import log_habit_from_card
        card = {"pfc_id": "habit-daily-morning-walk", "pfc_type": "habit-daily", "list_name": "☀️ Daily Habits",
                "trello_card_id": "c1", "card_name": "✓ Morning walk"}
        # First log
        log_habit_from_card("K", "T", card, daily_path=self.daily_path, monthly_path=self.monthly_path, today="2026-05-10")
        # Second log on same day should not duplicate
        result = log_habit_from_card("K", "T", card, daily_path=self.daily_path, monthly_path=self.monthly_path, today="2026-05-10")
        self.assertEqual(result, "already_logged")
        records = [json.loads(l) for l in self.daily_path.read_text().splitlines()]
        self.assertEqual(len(records), 1)

    @patch("trello_writeback.update_card")
    def test_monthly_habit_logs(self, mock_update):
        from trello_writeback import log_habit_from_card
        card = {"pfc_id": "habit-monthly-deep-clean", "pfc_type": "habit-monthly",
                "list_name": "🌙 Monthly Habits", "trello_card_id": "c2", "card_name": "Deep clean"}
        result = log_habit_from_card(
            "K", "T", card,
            daily_path=self.daily_path, monthly_path=self.monthly_path,
            today="2026-05-10",
        )
        self.assertEqual(result, "logged")
        records = [json.loads(l) for l in self.monthly_path.read_text().splitlines()]
        self.assertEqual(records[0]["habit_id"], "deep-clean")
        self.assertEqual(records[0]["date"], "2026-05-10")


class TestMoveHelpers(unittest.TestCase):
    @patch("trello_writeback.update_card")
    @patch("trello_writeback.list_cards_on_board")
    @patch("trello_writeback.list_lists")
    def test_move_2plus1_from_actions(self, mock_lists, mock_cards, mock_update):
        from trello_writeback import move_2plus1_from_actions
        mock_lists.return_value = [
            {"id": "L_2plus1", "name": "✅ 2+1", "closed": False},
            {"id": "L_actions", "name": "✅ Actions", "closed": False},
        ]
        mock_cards.return_value = [
            {"id": "c1", "idList": "L_actions", "desc": "---\npfc-id: task-A\npfc-type: task\n---\n\nb"},
            {"id": "c2", "idList": "L_actions", "desc": "---\npfc-id: task-B\npfc-type: task\n---\n\nb"},
            {"id": "c3", "idList": "L_actions", "desc": "---\npfc-id: task-C\npfc-type: task\n---\n\nb"},
        ]
        moved = move_2plus1_from_actions("K", "T", "BOARD", focus_task_ids=["task-A", "task-C"])
        self.assertEqual(moved, 2)
        # Both should have been update_card with idList=L_2plus1
        called_ids = sorted([call.args[2] for call in mock_update.call_args_list])
        self.assertEqual(called_ids, ["c1", "c3"])
        for call in mock_update.call_args_list:
            self.assertEqual(call.kwargs.get("idList"), "L_2plus1")

    @patch("trello_writeback.update_card")
    @patch("trello_writeback.list_cards_on_board")
    @patch("trello_writeback.list_lists")
    def test_move_back_uncompleted(self, mock_lists, mock_cards, mock_update):
        from trello_writeback import move_back_uncompleted
        mock_lists.return_value = [
            {"id": "L_2plus1", "name": "✅ 2+1", "closed": False},
            {"id": "L_actions", "name": "✅ Actions", "closed": False},
        ]
        mock_cards.return_value = [
            # In 2+1, not completed → move back
            {"id": "c1", "idList": "L_2plus1", "dueComplete": False, "desc": "---\npfc-id: task-A\npfc-type: task\n---\n\nb"},
            # In 2+1, completed → leave (gets archived by complete_task_from_card)
            {"id": "c2", "idList": "L_2plus1", "dueComplete": True, "desc": "---\npfc-id: task-B\npfc-type: task\n---\n\nb"},
        ]
        moved = move_back_uncompleted("K", "T", "BOARD")
        self.assertEqual(moved, 1)
        called_ids = [call.args[2] for call in mock_update.call_args_list]
        self.assertEqual(called_ids, ["c1"])
        self.assertEqual(mock_update.call_args_list[0].kwargs.get("idList"), "L_actions")
