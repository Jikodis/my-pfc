"""The rating card in 🦸 Body first: render (trello_home) and write-back (trello_writeback)."""

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

import trello_render
from trello_home import render_rate
from trello_render import (BODY_LIST, Card, annotate_rate_card, compute_diff, rating_answers, short_day)

RATE_LIST_NAME = BODY_LIST


def render_rate_day(home):
    return render_rate(home)


def _lists(e=None, m=None, f=None):
    """Checklist state as fetch_current_state builds it: {name: [(item, checked), ...]}."""
    def group(picked):
        picked = picked if isinstance(picked, (list, tuple)) else ([picked] if picked else [])
        return [(str(n), n in picked) for n in range(1, 6)]
    return {"Energy": group(e), "Mood": group(m), "Focus": group(f)}


# ---------------------------------------------------------------- reading the ticks

def test_short_day():
    assert short_day("2025-11-09") == "Sun Nov 9"


def test_three_single_ticks_are_complete():
    a = rating_answers(_lists(4, 5, 3))
    assert a["complete"] is True
    assert a["values"] == {"Energy": 4, "Mood": 5, "Focus": 3}
    assert a["ambiguous"] == {}


def test_a_group_with_no_tick_is_partial():
    a = rating_answers(_lists(4, None, 3))
    assert a["complete"] is False
    assert a["values"]["Mood"] is None and a["ambiguous"] == {}


def test_two_ticks_in_one_group_is_ambiguous_not_complete():
    a = rating_answers(_lists(4, [3, 4], 3))
    assert a["complete"] is False
    assert a["ambiguous"] == {"Mood": [3, 4]}
    assert a["values"]["Mood"] is None


def test_a_missing_checklist_is_not_complete():
    lists = _lists(4, 5, 3)
    del lists["Focus"]
    assert rating_answers(lists)["complete"] is False


def test_no_checklists_at_all():
    assert rating_answers(None)["complete"] is False


# ---------------------------------------------------------------- the card

def _home(target="2025-11-09", unrated=True, today="2025-11-10"):
    """The two fields of home_data.build_home the card reads: rate_target names the day
    (yesterday before the evening hour, today after) and whether it is rated."""
    return {"date": today, "rate_target": {"date": target, "unrated": unrated}}


def test_before_evening_the_card_rates_yesterday_with_three_checklists():
    [card] = render_rate_day(_home())
    assert card.pfc_id == "rate-day-2025-11-09"
    assert card.pfc_type == "rate-day"
    assert card.list_name == "🦸 Body first"
    assert card.name == "⭐ How was yesterday? Sun Nov 9"
    assert card.seed_checklists == [(g, ["1", "2", "3", "4", "5"]) for g in ("Energy", "Mood", "Focus")]


def test_from_the_evening_hour_the_card_rates_today():
    [card] = render_rate_day(_home(target="2025-11-10"))
    assert card.pfc_id == "rate-day-2025-11-10"
    assert card.name == "⭐ How was today? Mon Nov 10"


def test_a_rated_day_has_no_card_as_on_the_web():
    assert render_rate_day(_home(unrated=False)) == []


def _current(pfc_id, checklists):
    c = Card(pfc_id=pfc_id, pfc_type="rate-day", list_name=RATE_LIST_NAME, name="⭐ Rate Sun Nov 9", body="old")
    c.checklist_state = checklists
    return c


def test_the_body_says_what_is_answered_so_far():
    [card] = render_rate_day(_home())
    annotate_rate_card([card], [(_current(card.pfc_id, _lists(4, None, None)), "tc1")])
    assert "Answered: Energy 4 · Mood — · Focus —" in card.body


def test_the_body_names_a_group_with_two_ticks():
    [card] = render_rate_day(_home())
    annotate_rate_card([card], [(_current(card.pfc_id, _lists(4, [2, 5], None)), "tc1")])
    assert "Mood has 2 ticks (2, 5): untick one so the rating can save." in card.body


def test_a_new_card_says_nothing_is_answered():
    [card] = render_rate_day(_home())
    annotate_rate_card([card], [])
    assert "Answered: Energy — · Mood — · Focus —" in card.body


def test_checklist_ticks_never_cause_an_update():
    """The ticks are the user's, not the render's: a card halfway through is left alone."""
    [card] = render_rate_day(_home())
    current = _current(card.pfc_id, _lists(4, None, None))
    annotate_rate_card([card], [(current, "tc1")])
    current.name, current.body = card.name, card.body
    assert compute_diff([card], [(current, "tc1")])["updates"] == []


# ---------------------------------------------------------------- board plumbing

def test_creating_a_card_seeds_its_checklists():
    card = Card(pfc_id="rate-day-2025-11-09", pfc_type="rate-day", list_name="L", name="⭐", body="b",
                seed_checklists=[("Energy", ["1", "2"]), ("Mood", ["1", "2"])])
    with patch("trello_render.create_card", return_value={"id": "c1"}) as cc, \
            patch("trello_render.update_card"), \
            patch("trello_render.create_checklist", side_effect=[{"id": "cl1"}, {"id": "cl2"}]) as ccl, \
            patch("trello_render.add_checkitem") as aci:
        trello_render.apply_creates("K", "T", [card], {"L": "lid"}, {})
    assert [c.args[3] for c in ccl.call_args_list] == ["Energy", "Mood"]
    assert [(c.args[2], c.args[3]) for c in aci.call_args_list] == [("cl1", "1"), ("cl1", "2"), ("cl2", "1"), ("cl2", "2")]
    cc.assert_called_once()


def test_position_is_compared_only_when_the_render_sets_it():
    a = Card("x", "t", "L", "n", "b", pos=2048)
    b = Card("x", "t", "L", "n", "b", pos=2048.0)
    c = Card("x", "t", "L", "n", "b", pos=4096)
    loose = Card("x", "t", "L", "n", "b")
    assert compute_diff([a], [(b, "1")])["updates"] == []
    assert len(compute_diff([a], [(c, "1")])["updates"]) == 1
    assert compute_diff([loose], [(c, "1")])["updates"] == []


# ---------------------------------------------------------------- write-back

def _board_card(pfc_id, checklists, list_id="LR"):
    desc = f"---\npfc-id: {pfc_id}\npfc-type: rate-day\n---\n\nbody"
    return {"id": "card1", "idList": list_id, "desc": desc, "name": "⭐",
            "checklists": [{"name": name, "checkItems": [{"name": item, "pos": i, "state": "complete" if on else "incomplete"}
                                                          for i, (item, on) in enumerate(items)]}
                           for name, items in checklists.items()]}


@pytest.fixture
def files(tmp_path):
    days = tmp_path / "day-tracking.ndjson"
    habits = tmp_path / "habits-daily.ndjson"
    days.write_text(json.dumps({"date": "2025-11-08", "rating": 3}) + "\n")
    habits.write_text(json.dumps({"habit_id": "morning-walk", "date": "2025-11-09", "completed": True}) + "\n")
    return days, habits


def _sync(files, card, today="2025-11-10"):
    from trello_writeback import sync_rating
    days, habits = files
    with patch("trello_writeback.list_lists", return_value=[{"id": "LR", "name": RATE_LIST_NAME}]), \
            patch("trello_writeback.list_cards_on_board", return_value=[card]):
        return sync_rating("K", "T", "B", today=today, days_path=days, committer=FAKE)


def _rows(files):
    return [json.loads(line) for line in files[0].read_text().splitlines()]


def test_three_answers_rate_the_day_the_card_names(files):
    status = _sync(files, _board_card("rate-day-2025-11-09", _lists(4, 5, 3)))
    assert status == "added"
    row = _rows(files)[-1]
    assert (row["date"], row["rating"], row["energy"], row["mood"], row["focus"]) == \
        ("2025-11-09", 4, 4, 5, 3)
    assert row["hyperfocused"] is None


def test_a_partial_card_writes_nothing(files):
    before = files[0].read_text()
    assert _sync(files, _board_card("rate-day-2025-11-09", _lists(4, None, 3))) == "waiting"
    assert files[0].read_text() == before


def test_an_ambiguous_card_writes_nothing(files):
    before = files[0].read_text()
    assert _sync(files, _board_card("rate-day-2025-11-09", _lists(4, [1, 2], 3))) == "ambiguous"
    assert files[0].read_text() == before


def test_an_already_rated_day_is_left_alone(files):
    before = files[0].read_text()
    assert _sync(files, _board_card("rate-day-2025-11-08", _lists(1, 1, 1)), today="2025-11-09") == "already_rated"
    assert files[0].read_text() == before


def test_a_card_for_a_day_outside_today_and_yesterday_writes_nothing(files):
    before = files[0].read_text()
    assert _sync(files, _board_card("rate-day-2025-11-06", _lists(4, 5, 3))) == "out_of_window"
    assert files[0].read_text() == before


def test_a_fitbit_row_without_a_rating_is_filled_in_place(files):
    days, _ = files
    days.write_text(json.dumps({"date": "2025-11-09", "rating": None, "health": {"sleep_hours": 7}}) + "\n")
    assert _sync(files, _board_card("rate-day-2025-11-09", _lists(2, 2, 2))) == "updated"
    [row] = _rows(files)
    assert row["rating"] == 2 and row["health"] == {"sleep_hours": 7}


def test_no_rate_card_on_the_board(files):
    from trello_writeback import sync_rating
    with patch("trello_writeback.list_lists", return_value=[{"id": "LR", "name": RATE_LIST_NAME}]), \
            patch("trello_writeback.list_cards_on_board", return_value=[]):
        assert sync_rating("K", "T", "B", today="2025-11-10", days_path=files[0], committer=FAKE) == "no_card"
