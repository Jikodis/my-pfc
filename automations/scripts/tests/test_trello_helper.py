"""Unit tests for trello_helper."""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from trello_helper import list_cards, delete_card, main


def _mock_response(payload):
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda s, *a: None
    return resp


class TestListCards(unittest.TestCase):
    @patch("trello_helper.urllib.request.urlopen")
    def test_list_returns_id_and_name_per_card(self, mock_open):
        mock_open.return_value = _mock_response([
            {"id": "abc", "name": "Card one"},
            {"id": "def", "name": "Card two"},
        ])
        cards = list_cards("KEY", "TOKEN", "LIST_ID")
        self.assertEqual(cards, [
            {"id": "abc", "name": "Card one"},
            {"id": "def", "name": "Card two"},
        ])

    @patch("trello_helper.urllib.request.urlopen")
    def test_list_empty_inbox_returns_empty_list(self, mock_open):
        mock_open.return_value = _mock_response([])
        self.assertEqual(list_cards("K", "T", "L"), [])

    @patch("trello_helper.urllib.request.urlopen")
    def test_list_401_raises(self, mock_open):
        mock_open.side_effect = HTTPError("u", 401, "Unauthorized", {}, None)
        with self.assertRaises(HTTPError):
            list_cards("K", "T", "L")


class TestDeleteCard(unittest.TestCase):
    @patch("trello_helper.urllib.request.urlopen")
    def test_delete_200_returns_true(self, mock_open):
        mock_open.return_value = _mock_response({})
        self.assertTrue(delete_card("K", "T", "abc"))

    @patch("trello_helper.urllib.request.urlopen")
    def test_delete_404_returns_true_already_gone(self, mock_open):
        mock_open.side_effect = HTTPError("u", 404, "Not Found", {}, None)
        self.assertTrue(delete_card("K", "T", "abc"))

    @patch("trello_helper.urllib.request.urlopen")
    def test_delete_500_raises(self, mock_open):
        mock_open.side_effect = HTTPError("u", 500, "Server Error", {}, None)
        with self.assertRaises(HTTPError):
            delete_card("K", "T", "abc")


class TestMainCli(unittest.TestCase):
    @patch.dict("os.environ", {
        "TRELLO_API_KEY": "K", "TRELLO_API_TOKEN": "T", "TRELLO_INBOX_LIST_ID": "L"
    }, clear=True)
    @patch("trello_helper.list_cards")
    def test_main_list_emits_jsonl(self, mock_list):
        mock_list.return_value = [
            {"id": "abc", "name": "First"},
            {"id": "def", "name": "Second"},
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(["list"])
        self.assertEqual(rc, 0)
        lines = [l for l in buf.getvalue().splitlines() if l.strip()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0]), {"id": "abc", "name": "First"})
        self.assertEqual(json.loads(lines[1]), {"id": "def", "name": "Second"})

    @patch.dict("os.environ", {}, clear=True)
    @patch("trello_helper.load_env", return_value={})
    def test_main_missing_env_returns_1(self, mock_load):
        err = io.StringIO()
        with redirect_stderr(err):
            rc = main(["list"])
        self.assertEqual(rc, 1)
        self.assertIn("TRELLO_API_KEY", err.getvalue())

    @patch.dict("os.environ", {
        "TRELLO_API_KEY": "K", "TRELLO_API_TOKEN": "T", "TRELLO_INBOX_LIST_ID": "L"
    }, clear=True)
    @patch("trello_helper.delete_card")
    def test_main_delete_happy_path_returns_0(self, mock_delete):
        mock_delete.return_value = True
        rc = main(["delete", "abc123"])
        self.assertEqual(rc, 0)
        mock_delete.assert_called_once_with("K", "T", "abc123")

    def test_main_delete_missing_card_id_returns_1(self):
        err = io.StringIO()
        with redirect_stderr(err):
            rc = main(["delete"])
        self.assertEqual(rc, 1)
        self.assertIn("card_id", err.getvalue())


class TestBoards(unittest.TestCase):
    @patch("trello_helper.urllib.request.urlopen")
    def test_list_boards_returns_id_and_name(self, mock_open):
        mock_open.return_value = _mock_response([
            {"id": "b1", "name": "Personal"},
            {"id": "b2", "name": "Work"},
        ])
        from trello_helper import list_boards
        self.assertEqual(
            list_boards("K", "T"),
            [{"id": "b1", "name": "Personal"}, {"id": "b2", "name": "Work"}],
        )


class TestLists(unittest.TestCase):
    @patch("trello_helper.urllib.request.urlopen")
    def test_list_lists_returns_id_and_name(self, mock_open):
        mock_open.return_value = _mock_response([
            {"id": "l1", "name": "Inbox", "closed": False},
            {"id": "l2", "name": "Done", "closed": False},
        ])
        from trello_helper import list_lists
        result = list_lists("K", "T", "BOARD_ID")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "Inbox")


class TestCardsOnBoard(unittest.TestCase):
    @patch("trello_helper.urllib.request.urlopen")
    def test_cards_on_board_returns_full_records(self, mock_open):
        mock_open.return_value = _mock_response([
            {"id": "c1", "name": "Card1", "idList": "l1", "desc": "", "dueComplete": False, "closed": False, "idLabels": []},
        ])
        from trello_helper import list_cards_on_board
        result = list_cards_on_board("K", "T", "BOARD_ID", filter_="open")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "c1")
        self.assertEqual(result[0]["dueComplete"], False)


class TestCardWrite(unittest.TestCase):
    @patch("trello_helper.urllib.request.urlopen")
    def test_create_card_returns_new_id(self, mock_open):
        mock_open.return_value = _mock_response({"id": "newcard123", "name": "Hello"})
        from trello_helper import create_card
        result = create_card("K", "T", "list_id", name="Hello", desc="body")
        self.assertEqual(result["id"], "newcard123")

    @patch("trello_helper.urllib.request.urlopen")
    def test_update_card_returns_updated_record(self, mock_open):
        mock_open.return_value = _mock_response({"id": "c1", "dueComplete": True})
        from trello_helper import update_card
        result = update_card("K", "T", "c1", dueComplete=True)
        self.assertTrue(result["dueComplete"])

    @patch("trello_helper.urllib.request.urlopen")
    def test_archive_card_sets_closed_true(self, mock_open):
        mock_open.return_value = _mock_response({"id": "c1", "closed": True})
        from trello_helper import archive_card
        result = archive_card("K", "T", "c1")
        self.assertTrue(result["closed"])


class TestListWrite(unittest.TestCase):
    @patch("trello_helper.urllib.request.urlopen")
    def test_create_list_returns_new_id(self, mock_open):
        mock_open.return_value = _mock_response({"id": "newlist", "name": "📖 Insights"})
        from trello_helper import create_list
        result = create_list("K", "T", "BOARD", name="📖 Insights", pos="bottom")
        self.assertEqual(result["id"], "newlist")

    @patch("trello_helper.urllib.request.urlopen")
    def test_archive_list_sets_closed_true(self, mock_open):
        mock_open.return_value = _mock_response({"id": "l1", "closed": True})
        from trello_helper import archive_list
        result = archive_list("K", "T", "l1")
        self.assertTrue(result["closed"])


class TestLabels(unittest.TestCase):
    @patch("trello_helper.urllib.request.urlopen")
    def test_list_labels_returns_id_name_color(self, mock_open):
        mock_open.return_value = _mock_response([
            {"id": "lab1", "name": "AA", "color": "red"},
            {"id": "lab2", "name": "AB", "color": "orange"},
        ])
        from trello_helper import list_labels
        result = list_labels("K", "T", "BOARD")
        self.assertEqual(result[0]["name"], "AA")
        self.assertEqual(result[0]["color"], "red")

    @patch("trello_helper.urllib.request.urlopen")
    def test_create_label_returns_new_id(self, mock_open):
        mock_open.return_value = _mock_response({"id": "newlab", "name": "AA", "color": "red"})
        from trello_helper import create_label
        result = create_label("K", "T", "BOARD", name="AA", color="red")
        self.assertEqual(result["id"], "newlab")


class TestChecklists(unittest.TestCase):
    @patch("trello_helper.urllib.request.urlopen")
    def test_list_checklists_returns_records(self, mock_open):
        mock_open.return_value = _mock_response([
            {"id": "cl1", "name": "Progress", "checkItems": [{"id":"i1","name":"Part 1","state":"complete"}]}
        ])
        from trello_helper import list_checklists
        result = list_checklists("K", "T", "card123")
        self.assertEqual(result[0]["name"], "Progress")

    @patch("trello_helper.urllib.request.urlopen")
    def test_create_checklist_returns_new_id(self, mock_open):
        mock_open.return_value = _mock_response({"id": "newcl", "name": "Progress"})
        from trello_helper import create_checklist
        result = create_checklist("K", "T", "card123", "Progress")
        self.assertEqual(result["id"], "newcl")

    @patch("trello_helper.urllib.request.urlopen")
    def test_delete_checklist(self, mock_open):
        mock_open.return_value = _mock_response({})
        from trello_helper import delete_checklist
        delete_checklist("K", "T", "cl123")  # no exception = pass

    @patch("trello_helper.urllib.request.urlopen")
    def test_add_checkitem_returns_new_id(self, mock_open):
        mock_open.return_value = _mock_response({"id": "newitem", "name": "Part 5", "state": "incomplete"})
        from trello_helper import add_checkitem
        result = add_checkitem("K", "T", "cl123", "Part 5", checked=False)
        self.assertEqual(result["id"], "newitem")

    @patch("trello_helper.urllib.request.urlopen")
    def test_update_checkitem_state_complete(self, mock_open):
        mock_open.return_value = _mock_response({"id": "i1", "state": "complete"})
        from trello_helper import update_checkitem
        result = update_checkitem("K", "T", "card123", "i1", state="complete")
        self.assertEqual(result["state"], "complete")

    @patch("trello_helper.urllib.request.urlopen")
    def test_delete_checkitem(self, mock_open):
        mock_open.return_value = _mock_response({})
        from trello_helper import delete_checkitem
        delete_checkitem("K", "T", "cl123", "i1")  # no exception = pass


if __name__ == "__main__":
    unittest.main()
