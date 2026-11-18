"""Unit tests for trello_writeback."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _card(card_id, name="X", desc="", id_list="L1", due_complete=False, closed=False,
          id_labels=None, date_completed=None):
    return {"id": card_id, "name": name, "desc": desc, "idList": id_list,
            "dueComplete": due_complete, "closed": closed, "idLabels": id_labels or [],
            "dateCompleted": date_completed}


class TestPollCompleted(unittest.TestCase):
    @patch("trello_writeback.list_cards_on_board")
    @patch("trello_writeback.list_lists")
    def test_returns_only_due_complete_in_interactive_lists(self, mock_lists, mock_cards):
        from trello_writeback import poll_completed_cards
        mock_lists.return_value = [
            {"id": "L_2plus1", "name": "✅ The 2+1", "closed": False},
            {"id": "L_actions", "name": "✅ Tasks", "closed": False},
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
            {"id": "L_actions", "name": "✅ Tasks", "closed": False},
        ]
        mock_cards.return_value = [
            _card("c1", id_list="L_actions", due_complete=True, desc="No frontmatter"),
        ]
        completed = poll_completed_cards("K", "T", "BOARD")
        self.assertEqual(completed, [])

    @patch("trello_writeback.list_cards_on_board")
    @patch("trello_writeback.list_lists")
    def test_carries_date_completed_through(self, mock_lists, mock_cards):
        """The check timestamp must survive the poll — it is what dates the log."""
        from trello_writeback import poll_completed_cards
        mock_lists.return_value = [
            {"id": "L_actions", "name": "✅ Tasks", "closed": False},
        ]
        mock_cards.return_value = [
            _card("c1", id_list="L_actions", due_complete=True,
                  desc="---\npfc-id: task-1\npfc-type: task\n---\n\nb",
                  date_completed="2025-08-07T05:56:57.893Z"),
        ]
        completed = poll_completed_cards("K", "T", "BOARD")
        self.assertEqual(completed[0]["date_completed"], "2025-08-07T05:56:57.893Z")


class TestLocalDateFromISO(unittest.TestCase):
    """Trello stamps UTC; the repo dates everything in local time."""

    def test_utc_evening_maps_back_to_previous_local_day(self):
        from trello_writeback import _local_date_from_iso
        # 05:56 UTC on 8/6 is 11:56 PM MDT on 8/5 — the day the habit was done.
        self.assertEqual(_local_date_from_iso("2025-08-07T05:56:57.893Z"), "2025-08-06")

    def test_utc_afternoon_stays_on_same_local_day(self):
        from trello_writeback import _local_date_from_iso
        self.assertEqual(_local_date_from_iso("2025-08-07T20:15:00.000Z"), "2025-08-07")

    def test_missing_or_malformed_returns_none(self):
        from trello_writeback import _local_date_from_iso
        self.assertIsNone(_local_date_from_iso(None))
        self.assertIsNone(_local_date_from_iso(""))
        self.assertIsNone(_local_date_from_iso("not-a-timestamp"))


class TestCompleteTaskFromCard(unittest.TestCase):
    def setUp(self):
        # Use a temp tasks.ndjson and task_events.ndjson for isolation
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        self.tasks_path = Path(self.tmpdir) / "tasks.ndjson"
        self.events_path = Path(self.tmpdir) / "task_events.ndjson"
        self.tasks_path.write_text(
            '{"id":"task-1","status":"open","description":"X","completed":null}\n'
            '{"id":"task-2","status":"done","description":"Y","completed":"2025-05-02"}\n'
        )
        self.events_path.write_text("")
        # The daily-focus file defaults to REPO_ROOT; point that at the temp folder
        # so no test here reads or writes the real one.
        self.focus_path = Path(self.tmpdir) / "6-tasks/_data/daily-focus.ndjson"
        root = patch("trello_writeback.REPO_ROOT", Path(self.tmpdir))
        root.start()
        self.addCleanup(root.stop)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def _focus(self, *days):
        self.focus_path.parent.mkdir(parents=True, exist_ok=True)
        text = "".join(json.dumps(d, separators=(",", ":")) + "\n" for d in days)
        self.focus_path.write_text(text)
        return text

    def _complete(self, pfc_id="task-1", date_completed="2025-05-11T18:00:00.000Z"):
        from trello_writeback import complete_task_from_card
        card = {"pfc_id": pfc_id, "pfc_type": "task", "list_name": "✅ The 2+1",
                "trello_card_id": "c1", "card_name": "X", "date_completed": date_completed}
        return complete_task_from_card("K", "T", card, tasks_path=self.tasks_path, events_path=self.events_path)

    @patch("trello_writeback.archive_card")
    def test_a_critical_pick_is_ticked_on_the_day_the_card_was_checked(self, mock_archive):
        self._focus({"date": "2025-05-10", "critical": ["task-1"], "bonus": None, "completed": [], "bonus_completed": False},
                    {"date": "2025-05-11", "critical": ["task-1", "task-3"], "bonus": None, "completed": ["task-3"],
                     "bonus_completed": False})
        # Checked at noon on 5/10 local, synced any time later.
        self.assertEqual(self._complete(), "completed")
        days = [json.loads(l) for l in self.focus_path.read_text().splitlines()]
        self.assertEqual(days[0]["completed"], [])
        self.assertEqual(days[1]["completed"], ["task-3", "task-1"])

    @patch("trello_writeback.archive_card")
    def test_a_bonus_pick_sets_bonus_completed(self, mock_archive):
        self._focus({"date": "2025-05-11", "critical": ["task-3"], "bonus": "task-1", "completed": [],
                     "bonus_completed": False})
        self._complete()
        day = json.loads(self.focus_path.read_text().splitlines()[0])
        self.assertIs(day["bonus_completed"], True)

    @patch("trello_writeback.archive_card")
    def test_a_task_not_in_the_days_picks_leaves_the_file_alone(self, mock_archive):
        text = self._focus({"date": "2025-05-11", "critical": ["task-3"], "bonus": None, "completed": [],
                            "bonus_completed": False})
        self.assertEqual(self._complete(), "completed")
        self.assertEqual(self.focus_path.read_text(), text)

    @patch("trello_writeback.archive_card")
    def test_a_day_with_no_record_leaves_the_file_alone(self, mock_archive):
        text = self._focus({"date": "2025-05-10", "critical": ["task-1"], "bonus": None, "completed": [],
                            "bonus_completed": False})
        self.assertEqual(self._complete(), "completed")
        self.assertEqual(self.focus_path.read_text(), text)

    @patch("trello_writeback.archive_card")
    def test_no_daily_focus_file_is_fine(self, mock_archive):
        self.assertEqual(self._complete(), "completed")
        self.assertFalse(self.focus_path.exists())

    @patch("trello_writeback.archive_card")
    def test_marks_open_task_done_and_archives(self, mock_archive):
        from trello_writeback import complete_task_from_card
        card = {"pfc_id": "task-1", "pfc_type": "task", "list_name": "✅ Tasks",
                "trello_card_id": "c1", "card_name": "X"}
        result = complete_task_from_card(
            "K", "T", card, tasks_path=self.tasks_path, events_path=self.events_path,
            log_date="2025-05-11",
        )
        self.assertEqual(result, "completed")
        # Verify task status updated
        lines = self.tasks_path.read_text().splitlines()
        task = json.loads(lines[0])
        self.assertEqual(task["status"], "done")
        self.assertEqual(task["completed"], "2025-05-11")
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
        card = {"pfc_id": "task-2", "pfc_type": "task", "list_name": "✅ Tasks",
                "trello_card_id": "c2", "card_name": "Y"}
        result = complete_task_from_card(
            "K", "T", card, tasks_path=self.tasks_path, events_path=self.events_path,
            log_date="2025-05-11",
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
        card = {"pfc_id": "task-999", "pfc_type": "task", "list_name": "✅ Tasks",
                "trello_card_id": "cX", "card_name": "?"}
        result = complete_task_from_card(
            "K", "T", card, tasks_path=self.tasks_path, events_path=self.events_path,
            log_date="2025-05-11",
        )
        self.assertEqual(result, "unknown")
        mock_archive.assert_not_called()

    @patch("trello_writeback._today_mt", return_value="2025-08-07")
    @patch("trello_writeback.archive_card")
    def test_completion_dates_from_card_check_not_sync_time(self, mock_archive, mock_today):
        """A card checked at 11:56 PM belongs to that day, even if sync runs after midnight."""
        from trello_writeback import complete_task_from_card
        card = {"pfc_id": "task-1", "pfc_type": "task", "list_name": "✅ Tasks",
                "trello_card_id": "c1", "card_name": "X",
                "date_completed": "2025-08-07T05:56:57.893Z"}
        result = complete_task_from_card(
            "K", "T", card, tasks_path=self.tasks_path, events_path=self.events_path)
        self.assertEqual(result, "completed")
        task = json.loads(self.tasks_path.read_text().splitlines()[0])
        self.assertEqual(task["completed"], "2025-08-06")
        events = [json.loads(l) for l in self.events_path.read_text().splitlines()]
        self.assertEqual(events[0]["timestamp"], "2025-08-06")

    @patch("trello_writeback._today_mt", return_value="2025-08-07")
    @patch("trello_writeback.archive_card")
    def test_completion_falls_back_to_today_without_check_timestamp(self, mock_archive, mock_today):
        from trello_writeback import complete_task_from_card
        card = {"pfc_id": "task-1", "pfc_type": "task", "list_name": "✅ Tasks",
                "trello_card_id": "c1", "card_name": "X", "date_completed": None}
        complete_task_from_card(
            "K", "T", card, tasks_path=self.tasks_path, events_path=self.events_path)
        task = json.loads(self.tasks_path.read_text().splitlines()[0])
        self.assertEqual(task["completed"], "2025-08-07")


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
        card = {"pfc_id": "habit-daily-morning-walk", "pfc_type": "habit-daily", "list_name": "☀️ Habits",
                "trello_card_id": "c1", "card_name": "✓ Morning walk"}
        result = log_habit_from_card(
            "K", "T", card,
            daily_path=self.daily_path, monthly_path=self.monthly_path,
            log_date="2025-05-11",
        )
        self.assertEqual(result, "logged")
        records = [json.loads(l) for l in self.daily_path.read_text().splitlines()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["habit_id"], "morning-walk")
        self.assertEqual(records[0]["date"], "2025-05-11")
        self.assertTrue(records[0]["completed"])
        self.assertEqual(records[0]["source"], "trello")

    @patch("trello_writeback.update_card")
    def test_double_log_is_idempotent_for_today(self, mock_update):
        from trello_writeback import log_habit_from_card
        card = {"pfc_id": "habit-daily-morning-walk", "pfc_type": "habit-daily", "list_name": "☀️ Habits",
                "trello_card_id": "c1", "card_name": "✓ Morning walk"}
        # First log
        log_habit_from_card("K", "T", card, daily_path=self.daily_path, monthly_path=self.monthly_path, log_date="2025-05-11")
        # Second log on same day should not duplicate
        result = log_habit_from_card("K", "T", card, daily_path=self.daily_path, monthly_path=self.monthly_path, log_date="2025-05-11")
        self.assertEqual(result, "already_logged")
        records = [json.loads(l) for l in self.daily_path.read_text().splitlines()]
        self.assertEqual(len(records), 1)

    @patch("trello_writeback.update_card")
    def test_a_missed_row_is_marked_done_in_place(self, mock_update):
        from trello_writeback import log_habit_from_card
        self.daily_path.write_text(
            json.dumps({"habit_id": "morning-walk", "date": "2025-05-10", "completed": True, "source": "chat"}) + "\n"
            + json.dumps({"habit_id": "morning-walk", "date": "2025-05-11", "completed": False,
                          "skipped": True, "skip_reason": "sick", "source": "evening-checkin"}) + "\n")
        card = {"pfc_id": "habit-daily-morning-walk", "pfc_type": "habit-daily", "list_name": "☀️ Habits",
                "trello_card_id": "c1", "card_name": "✓ Morning walk"}
        result = log_habit_from_card("K", "T", card, daily_path=self.daily_path, monthly_path=self.monthly_path,
                                     log_date="2025-05-11")
        self.assertEqual(result, "updated")
        records = [json.loads(l) for l in self.daily_path.read_text().splitlines()]
        self.assertEqual(records, [
            {"habit_id": "morning-walk", "date": "2025-05-10", "completed": True, "source": "chat"},
            {"habit_id": "morning-walk", "date": "2025-05-11", "completed": True, "source": "trello"},
        ])

    @patch("trello_writeback.update_card")
    def test_monthly_habit_logs(self, mock_update):
        from trello_writeback import log_habit_from_card
        card = {"pfc_id": "habit-monthly-deep-clean", "pfc_type": "habit-monthly",
                "list_name": "☀️ Habits", "trello_card_id": "c2", "card_name": "Deep clean"}
        result = log_habit_from_card(
            "K", "T", card,
            daily_path=self.daily_path, monthly_path=self.monthly_path,
            log_date="2025-05-11",
        )
        self.assertEqual(result, "logged")
        records = [json.loads(l) for l in self.monthly_path.read_text().splitlines()]
        self.assertEqual(records[0]["habit_id"], "deep-clean")
        self.assertEqual(records[0]["date"], "2025-05-11")

    @patch("trello_writeback._today_mt", return_value="2025-08-07")
    @patch("trello_writeback.update_card")
    def test_habit_dates_from_card_check_not_sync_time(self, mock_update, mock_today):
        """The 2025-08-07 regression: a card checked at 11:56 PM on 8/5, synced after
        midnight, was logged under 8/6. It belongs to 8/5."""
        from trello_writeback import log_habit_from_card
        card = {"pfc_id": "habit-daily-read-15-min", "pfc_type": "habit-daily",
                "list_name": "☀️ Habits", "trello_card_id": "c1",
                "card_name": "Read 15 minutes",
                "date_completed": "2025-08-07T05:56:57.893Z"}
        result = log_habit_from_card(
            "K", "T", card, daily_path=self.daily_path, monthly_path=self.monthly_path)
        self.assertEqual(result, "logged")
        records = [json.loads(l) for l in self.daily_path.read_text().splitlines()]
        self.assertEqual(records[0]["date"], "2025-08-06")

    @patch("trello_writeback._today_mt", return_value="2025-08-07")
    @patch("trello_writeback.update_card")
    def test_habit_falls_back_to_today_without_check_timestamp(self, mock_update, mock_today):
        from trello_writeback import log_habit_from_card
        card = {"pfc_id": "habit-daily-morning-walk", "pfc_type": "habit-daily",
                "list_name": "☀️ Habits", "trello_card_id": "c1",
                "card_name": "Morning walk", "date_completed": None}
        log_habit_from_card(
            "K", "T", card, daily_path=self.daily_path, monthly_path=self.monthly_path)
        records = [json.loads(l) for l in self.daily_path.read_text().splitlines()]
        self.assertEqual(records[0]["date"], "2025-08-07")

    @patch("trello_writeback._today_mt", return_value="2025-08-07")
    @patch("trello_writeback.update_card")
    def test_idempotent_against_the_day_the_card_was_checked(self, mock_update, mock_today):
        """Repeat syncs of a still-checked card must not append a second 8/5 record."""
        from trello_writeback import log_habit_from_card
        card = {"pfc_id": "habit-daily-read-15-min", "pfc_type": "habit-daily",
                "list_name": "☀️ Habits", "trello_card_id": "c1",
                "card_name": "Read 15 minutes",
                "date_completed": "2025-08-07T05:56:57.893Z"}
        log_habit_from_card("K", "T", card, daily_path=self.daily_path, monthly_path=self.monthly_path)
        result = log_habit_from_card("K", "T", card, daily_path=self.daily_path, monthly_path=self.monthly_path)
        self.assertEqual(result, "already_logged")
        records = [json.loads(l) for l in self.daily_path.read_text().splitlines()]
        self.assertEqual(len(records), 1)


class TestNdjsonSpacing(unittest.TestCase):
    """Every line the sync writes uses `jq -c` spacing and leaves other lines alone."""

    def test_rewrite_changes_only_the_changed_line_and_writes_it_compact(self):
        import tempfile
        from trello_writeback import _write_ndjson
        rows = [{"id": "a", "status": "open"}, {"id": "b", "status": "open", "note": "é"}, {"id": "c"}]
        raw = ['{"id": "a", "status": "open"}',  # spaced, written by some older tool
               json.dumps(rows[1], ensure_ascii=False, separators=(",", ":")),
               '{"id":"c"}']
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.ndjson"
            path.write_text("".join(line + "\n" for line in raw))
            rows[1] = {**rows[1], "status": "done"}
            _write_ndjson(path, rows)
            after = path.read_text().splitlines()
        self.assertEqual(after[0], raw[0])
        self.assertEqual(after[2], raw[2])
        self.assertEqual(after[1], json.dumps(rows[1], ensure_ascii=False, separators=(",", ":")))

    def test_append_is_compact(self):
        import tempfile
        from trello_writeback import _append_ndjson
        record = {"task_id": "t", "event": "completed", "note": "é"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.ndjson"
            path.write_text('{"a": 1}\n')
            _append_ndjson(path, record)
            lines = path.read_text().splitlines()
        self.assertEqual(lines, ['{"a": 1}', json.dumps(record, ensure_ascii=False, separators=(",", ":"))])


class TestSyncRewriteKeepsLines(unittest.TestCase):
    def test_completing_a_task_from_a_card_changes_only_its_lines(self):
        import tempfile
        from trello_writeback import complete_task_from_card
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            tasks = tmp / "tasks.ndjson"
            events = tmp / "events.ndjson"
            focus = tmp / "focus.ndjson"
            tasks.write_text('{"id": "task-20250902-001", "status": "open", "description": "Call"}\n'
                             '{"id": "task-20250902-002", "status": "open", "description": "Other"}\n')
            events.write_text('{"task_id": "task-20250902-001", "event": "created"}\n')
            focus.write_text('{"date": "2025-09-02", "critical": ["task-20250902-009"], "completed": []}\n'
                             '{"date": "2025-09-03", "critical": ["task-20250902-001"], "completed": []}\n')
            before_tasks = tasks.read_text().splitlines()
            before_focus = focus.read_text().splitlines()
            card = {"pfc_id": "task-20250902-001", "trello_card_id": "c1", "date_completed": "2025-09-03T18:00:00Z"}
            with patch("trello_writeback.archive_card"):
                complete_task_from_card("K", "T", card, tasks_path=tasks, events_path=events,
                                        log_date="2025-09-03", focus_path=focus)
            after_tasks = tasks.read_text().splitlines()
            after_focus = focus.read_text().splitlines()
        self.assertEqual(after_tasks[1], before_tasks[1])
        self.assertEqual(json.loads(after_tasks[0])["status"], "done")
        self.assertNotIn('": ', after_tasks[0])
        self.assertEqual(after_focus[0], before_focus[0])
        self.assertEqual(json.loads(after_focus[1])["completed"], ["task-20250902-001"])
        self.assertNotIn('": ', after_focus[1])
