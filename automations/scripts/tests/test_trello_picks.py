"""The system-picked 2+1 and dropping a pick by archiving its ✅ 2+1 card (trello_writeback)."""

from __future__ import annotations


class FakeCommitter:
    """Stands in for trello_writeback.GitCommitter: no git in unit tests."""

    def __init__(self, ready=True):
        self.is_ready, self.commits = ready, []

    def ready(self, path):
        return self.is_ready

    def commit(self, path, message):
        self.commits.append(message)


FAKE = FakeCommitter()

import json
from datetime import datetime
from unittest.mock import patch

import pytest

import trello_writeback
from trello_writeback import auto_pick_today, sync_dropped_picks

MORNING = datetime(2025, 11, 10, 5, 0)
TODAY = "2025-11-10"


def _rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.fixture
def focus_file(tmp_path):
    path = tmp_path / "daily-focus.ndjson"
    path.write_text(json.dumps({"date": "2025-11-09", "critical": ["task-old"], "bonus": None,
                                "completed": [], "bonus_completed": False}) + "\n")
    return path


def _home(ids):
    return {"evening": False, "date": TODAY, "suggested": [{"id": i} for i in ids]}


# ---------------------------------------------------------------- auto-pick

def test_no_picks_today_sets_the_tour_suggestions_as_auto(focus_file):
    with patch("home_data.build_home", return_value=_home(["task-a", "task-b", "task-c"])):
        assert auto_pick_today(MORNING, focus_path=focus_file, committer=FAKE) == "picked"
    rec = _rows(focus_file)[-1]
    assert rec == {"date": TODAY, "critical": ["task-a", "task-b"], "bonus": "task-c", "completed": [],
                   "bonus_completed": False, "source": "auto"}


def test_his_picks_are_never_touched_and_the_suggester_is_not_even_run(focus_file):
    before = focus_file.read_text() + json.dumps({"date": TODAY, "critical": ["task-mine"], "bonus": None}) + "\n"
    focus_file.write_text(before)
    with patch("home_data.build_home") as bh:
        assert auto_pick_today(MORNING, focus_path=focus_file, committer=FAKE) == "kept"
    bh.assert_not_called()
    assert focus_file.read_text() == before


def test_running_twice_picks_once(focus_file):
    with patch("home_data.build_home", return_value=_home(["task-a", "task-b", "task-c"])):
        auto_pick_today(MORNING, focus_path=focus_file, committer=FAKE)
    after = focus_file.read_text()
    with patch("home_data.build_home", return_value=_home(["task-x", "task-y", "task-z"])):
        assert auto_pick_today(MORNING, focus_path=focus_file, committer=FAKE) == "kept"
    assert focus_file.read_text() == after


def test_nothing_is_picked_from_the_evening_hour(focus_file):
    before = focus_file.read_text()
    with patch("home_data.build_home") as bh:
        assert auto_pick_today(datetime(2025, 11, 10, 18, 30), focus_path=focus_file, committer=FAKE) == "evening"
    bh.assert_not_called()
    assert focus_file.read_text() == before


def test_no_suggestions_writes_nothing(focus_file):
    before = focus_file.read_text()
    with patch("home_data.build_home", return_value=_home([])):
        assert auto_pick_today(MORNING, focus_path=focus_file, committer=FAKE) == "kept"
    assert focus_file.read_text() == before


# ---------------------------------------------------------------- archive = drop the pick

def _action(card_id, list_name="✅ The 2+1", app=None, closed=True):
    return {"type": "updateCard", "appCreator": app,
            "data": {"old": {"closed": not closed}, "card": {"id": card_id, "closed": closed},
                     "list": {"id": "L21", "name": list_name}}}


API = {"id": "6a001d7a9291ee934b8d8dcb", "authType": "appKeyToken"}


@pytest.fixture
def pick_files(tmp_path):
    focus = tmp_path / "daily-focus.ndjson"
    tasks = tmp_path / "tasks.ndjson"
    focus.write_text(json.dumps({"date": TODAY, "critical": ["task-a", "task-b"], "bonus": "task-c",
                                 "completed": [], "bonus_completed": False}) + "\n")
    tasks.write_text("".join(json.dumps({"id": t, "status": "open", "description": t}) + "\n"
                             for t in ("task-a", "task-b", "task-c")))
    return focus, tasks


def _drop(pick_files, actions, cards):
    focus, tasks = pick_files
    desc = {cid: f"---\npfc-id: {pid}\npfc-type: task\n---\n\nb" for cid, pid in cards.items()}
    with patch("trello_writeback.list_board_actions", return_value=actions) as la, \
            patch("trello_writeback.get_card", side_effect=lambda k, t, cid, fields: {"id": cid, "desc": desc[cid]}):
        result = sync_dropped_picks("K", "T", "B", today=TODAY, focus_path=focus, tasks_path=tasks, committer=FAKE)
    return result, la


def test_archiving_a_2_plus_1_card_in_trello_drops_that_pick(pick_files):
    dropped, la = _drop(pick_files, [_action("c-b")], {"c-b": "task-b"})
    assert dropped == ["task-b"]
    rec = _rows(pick_files[0])[0]
    assert rec["critical"] == ["task-a"] and rec["skipped"] == ["task-b"] and rec["dropped"] == ["task-b"]
    # The task stays open in the backlog.
    assert {t["id"]: t["status"] for t in _rows(pick_files[1])}["task-b"] == "open"
    since = la.call_args.kwargs["since"]
    assert since.startswith("2025-11-10T07:00:00")  # local midnight, in UTC


def test_an_archive_made_through_the_api_is_never_a_drop(pick_files):
    before = pick_files[0].read_text()
    dropped, _ = _drop(pick_files, [_action("c-b", app=API)], {"c-b": "task-b"})
    assert dropped == [] and pick_files[0].read_text() == before


def test_an_archive_in_another_list_is_not_a_drop(pick_files):
    before = pick_files[0].read_text()
    dropped, _ = _drop(pick_files, [_action("c-b", list_name="✅ Tasks")], {"c-b": "task-b"})
    assert dropped == [] and pick_files[0].read_text() == before


def test_a_done_task_is_not_dropped(pick_files):
    focus, tasks = pick_files
    tasks.write_text(json.dumps({"id": "task-b", "status": "done"}) + "\n")
    before = focus.read_text()
    dropped, _ = _drop(pick_files, [_action("c-b")], {"c-b": "task-b"})
    assert dropped == [] and focus.read_text() == before


def test_the_bonus_can_be_dropped(pick_files):
    dropped, _ = _drop(pick_files, [_action("c-c")], {"c-c": "task-c"})
    assert dropped == ["task-c"] and _rows(pick_files[0])[0]["bonus"] is None


def test_an_unarchive_is_ignored(pick_files):
    before = pick_files[0].read_text()
    dropped, _ = _drop(pick_files, [_action("c-b", closed=False)], {"c-b": "task-b"})
    assert dropped == [] and pick_files[0].read_text() == before


# ---------------------------------------------------------------- committing what the sync wrote

def test_the_auto_pick_is_committed_with_the_picks_subject(focus_file):
    fake = FakeCommitter()
    with patch("home_data.build_home", return_value=_home(["task-a", "task-b", "task-c"])):
        auto_pick_today(MORNING, focus_path=focus_file, committer=fake)
    assert fake.commits == ["focus: set 2025-11-10 (auto-pick)"]


def test_nothing_is_written_when_the_file_cannot_be_committed(focus_file):
    before = focus_file.read_text()
    with patch("home_data.build_home", return_value=_home(["task-a"])):
        assert auto_pick_today(MORNING, focus_path=focus_file, committer=FakeCommitter(ready=False)) == "not_ready"
    assert focus_file.read_text() == before


def _git(repo, *args):
    import subprocess
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def test_git_committer_is_ready_only_on_main_with_the_file_clean(tmp_path):
    from trello_writeback import GitCommitter
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    f = tmp_path / "daily-focus.ndjson"
    f.write_text("{}\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    c = GitCommitter(tmp_path)
    assert c.ready(f) is True
    f.write_text('{"a":1}\n')
    assert c.ready(f) is False
    with patch("web_write.push", return_value=(True, None)):
        c.commit(f, "focus: set 2025-11-10 (auto-pick)")
    assert c.ready(f) is True
    assert _git(tmp_path, "log", "-1", "--format=%s").stdout.strip() == "focus: set 2025-11-10 (auto-pick)"
    _git(tmp_path, "checkout", "-q", "-b", "other")
    assert c.ready(f) is False
