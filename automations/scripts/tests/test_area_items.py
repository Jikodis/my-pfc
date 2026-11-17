"""Unit tests for area_items: item lights, the area rollup, and the plate."""

import json

import pytest

import area_items
from area_items import (calendar_hours, compute, habit_light, latest_answers, pace_light, rollup,
                        sleep_light, weekly_hours, wheel_snapshot)

TODAY = "2025-11-06"
CAL = "calendar:Volunteer shifts"


def _item(id_, area="health", kind="time", weight=1, **kw):
    base = {"id": id_, "area": area, "title": id_, "kind": kind, "weight": weight, "active": True}
    if "source" not in kw and "question" not in kw:
        kw["question"] = "How is it going?"
    if kind == "time" and "hours" not in kw and not str(kw.get("source", "")).startswith("calendar:"):
        kw["hours"] = 1
    return {**base, **kw}


def _wheel(**lights):
    return {"date": "2025-11-05", "stale": False,
            "rows": [{"key": k, "label": k.capitalize(), "light": v, "note": None} for k, v in lights.items()]}


def _compute(items, checkins=(), wheel=None, events=None, sleep=(None, "no sleep data"), habits=None):
    return compute(list(items), list(checkins), wheel or _wheel(health="green"), TODAY,
                   events=events, sleep=sleep, habits=habits or {})


def _row(result, key):
    return next(r for r in result["rows"] if r["key"] == key)


def _ans(item_id, answer, date=TODAY):
    return {"date": date, "item_id": item_id, "answer": answer}


# ── rollup ────────────────────────────────────────────────────────────────────

def test_rollup_thresholds():
    assert rollup([{"light": "green", "weight": 1}]) == "green"
    assert rollup([{"light": "green", "weight": 3}, {"light": "yellow", "weight": 1}]) == "green"  # 7 of 8
    assert rollup([{"light": "green", "weight": 2}, {"light": "yellow", "weight": 2}]) == "green"  # exactly 75%
    assert rollup([{"light": "green", "weight": 1}, {"light": "red", "weight": 1}]) == "yellow"    # 50%
    assert rollup([{"light": "green", "weight": 2}, {"light": "red", "weight": 2}, {"light": "red", "weight": 1}]) == "yellow"  # 4 of 10
    assert rollup([{"light": "yellow", "weight": 1}, {"light": "red", "weight": 2}]) == "red"      # 1 of 6


def test_red_on_a_weight_three_item_caps_the_area_at_yellow():
    items = [{"light": "green", "weight": 3}] * 4 + [{"light": "red", "weight": 3}]  # 24 of 30 = 80%
    assert rollup(items) == "yellow"
    assert rollup([{"light": "green", "weight": 3}] * 4 + [{"light": "red", "weight": 1}]) == "green"


def test_items_with_no_data_are_left_out_and_all_none_is_none():
    assert rollup([{"light": None, "weight": 3}, {"light": "green", "weight": 1}]) == "green"
    assert rollup([{"light": None, "weight": 3}]) is None
    assert rollup([]) is None


# ── hours ─────────────────────────────────────────────────────────────────────

def test_upkeep_converts_to_hours_per_week():
    assert weekly_hours(_item("a", hours=2, every="month"), {}) == pytest.approx(2 * 12 / 52)
    assert weekly_hours(_item("a", hours=4, every="quarter"), {}) == pytest.approx(4 * 4 / 52)
    assert weekly_hours(_item("a", hours=3, every="year"), {}) == pytest.approx(3 / 52)
    assert weekly_hours(_item("a", hours=3, every="week"), {}) == 3


def test_status_items_have_no_hours_and_calendar_items_take_the_calendar():
    assert weekly_hours(_item("a", kind="status"), {}) is None
    assert weekly_hours(_item("g", source=CAL), {"Volunteer shifts": 2.5}) == 2.5
    assert weekly_hours(_item("g", source=CAL), {}) == 0


# ── the calendar ──────────────────────────────────────────────────────────────

def _allday(summary, start, end, cal="Volunteer shifts"):
    return {"summary": summary, "start": {"date": start}, "end": {"date": end}, "organizer": {"displayName": cal}}


def _timed(summary, start, end, cal="Volunteer shifts"):
    return {"summary": summary, "start": {"dateTime": start}, "end": {"dateTime": end},
            "organizer": {"displayName": cal}}


def test_calendar_hours_sum_timed_events_in_the_next_seven_days():
    events = [
        _timed("Game", "2025-11-07T09:00:00-07:00", "2025-11-07T10:30:00-07:00"),
        _timed("Practice", "2025-11-12T17:00:00-07:00", "2025-11-12T18:00:00-07:00"),
        _timed("Too late", "2025-11-13T17:00:00-07:00", "2025-11-13T18:00:00-07:00"),
        _timed("Team meeting", "2025-11-08T09:00:00-07:00", "2025-11-08T10:00:00-07:00", cal="Events"),
        _allday("Trip", "2025-11-06", "2025-11-11"),
    ]
    assert calendar_hours(events, TODAY, "Volunteer shifts") == pytest.approx(2.5)
    assert calendar_hours(None, TODAY, "Volunteer shifts") == 0


# ── item lights ───────────────────────────────────────────────────────────────

def test_newest_answer_wins_and_answers_map_to_lights():
    rows = [_ans("a", "rough", "2025-11-01"), _ans("a", "good", "2025-11-05"), _ans("a", "okay", "2025-11-05")]
    assert latest_answers(rows)["a"]["answer"] == "okay"  # same date: the later line
    res = _compute([_item("a"), _item("b"), _item("c")],
                   [_ans("a", "good"), _ans("b", "okay"), _ans("c", "rough")])
    lights = {i["id"]: i["light"] for i in _row(res, "health")["items"]}
    assert lights == {"a": "green", "b": "yellow", "c": "red"}


def test_unanswered_question_is_no_data_not_red():
    res = _compute([_item("a", weight=3)], wheel=_wheel(health="green"))
    item = _row(res, "health")["items"][0]
    assert item["light"] is None and item["why"] == "no answer yet"
    assert _row(res, "health")["light"] == "green" and _row(res, "health")["source"] == "manual"


def test_answer_older_than_31_days_is_stale_but_still_counts():
    res = _compute([_item("a")], [_ans("a", "rough", "2025-10-05")])  # 32 days
    item = _row(res, "health")["items"][0]
    assert item["stale"] is True and item["light"] == "red"
    res = _compute([_item("a")], [_ans("a", "rough", "2025-10-06")])  # 31 days
    assert _row(res, "health")["items"][0]["stale"] is False


def test_answers_for_unknown_items_are_ignored():
    res = _compute([_item("a")], [_ans("gone", "rough")])
    assert _row(res, "health")["items"][0]["light"] is None


def test_habit_source_reads_the_habit_light():
    res = _compute([_item("w", source="habit:morning-walk", weight=3)],
                   habits={"morning-walk": ("yellow", "done 7 of the last 30 days (pace 13)")})
    item = _row(res, "health")["items"][0]
    assert item["light"] == "yellow" and item["why"].startswith("done 7")


def test_habit_light_is_the_weekly_pace():
    logs = [{"habit_id": "h", "date": f"2025-11-{d:02d}", "completed": True} for d in range(1, 7)]
    logs += [{"habit_id": "h", "date": "2025-10-08", "completed": True}]  # day 30 of the window
    logs += [{"habit_id": "h", "date": "2025-10-07", "completed": True}]  # outside 30 days
    logs += [{"habit_id": "h", "date": "2025-10-20", "completed": False}]
    schema = {"daily_habits": [{"id": "h", "frequency": 3}]}
    light, why = habit_light("h", logs, schema, TODAY)
    assert light == "yellow" and why == "done 7 of the last 30 days, pace is 13"
    assert habit_light("missing", logs, schema, TODAY)[0] is None


def test_pace_light():
    assert pace_light(13, 3, 30) == "green"   # 3 * 30 / 7 = 12.9
    assert pace_light(7, 3, 30) == "yellow"
    assert pace_light(6, 3, 30) == "red"


def _night(date, hours, awake):
    return {"date": date, "health": {"sleep_hours": hours, "awake_minutes": awake}}


def test_sleep_light_is_the_worse_of_hours_and_continuity():
    good = [_night(f"2025-10-{d:02d}", 8.0, 5) for d in range(1, 31)]
    assert sleep_light(good)[0] == "green"
    broken = [_night(f"2025-10-{d:02d}", 8.0, 45) for d in range(1, 31)]  # hours fine, continuity red
    light, why = sleep_light(broken)
    assert light == "red" and "unbroken 0 of 30" in why
    assert sleep_light([])[0] is None


def test_calendar_item_has_hours_but_no_light():
    events = [_timed("Game", "2025-11-07T09:00:00-07:00", "2025-11-07T11:00:00-07:00")]
    res = _compute([_item("g", area="family", source=CAL, weight=2)], wheel=_wheel(family="yellow"),
                   events=events)
    item = _row(res, "family")["items"][0]
    assert item["light"] is None and item["hours"] == 2.0
    assert _row(res, "family")["light"] == "yellow"  # manual fallback


# ── area rows ─────────────────────────────────────────────────────────────────

def test_area_with_data_uses_the_rollup_and_keeps_the_manual_light_alongside():
    res = _compute([_item("a", weight=3)], [_ans("a", "rough")], wheel=_wheel(health="green"))
    row = _row(res, "health")
    assert row["light"] == "red" and row["manual"] == "green" and row["source"] == "items"


def test_area_without_items_falls_back_to_its_manual_light():
    res = _compute([_item("a")], wheel=_wheel(health="green", legal="red"))
    row = _row(res, "legal")
    assert row == {"key": "legal", "label": "Legal", "light": "red", "manual": "red", "note": None,
                   "source": "manual", "hours": None, "items": []}


def test_area_with_items_but_no_wheel_rating_and_no_data_has_no_light():
    res = _compute([_item("a", area="family")], wheel=_wheel(health="green"))
    row = _row(res, "family")
    assert row["light"] is None and row["manual"] is None and row["label"] == "Family"


def test_retired_items_are_left_out():
    res = _compute([_item("a", active=False)], [_ans("a", "rough")], wheel=_wheel(health="green"))
    assert _row(res, "health")["items"] == [] and _row(res, "health")["light"] == "green"


def test_season_after_its_end_drops_out_of_light_and_hours_and_is_flagged():
    items = [_item("s", hours=4, ends="2025-11-05"), _item("t", hours=2, ends="2025-11-06")]
    res = _compute(items, [_ans("s", "rough"), _ans("t", "good")])
    by = {i["id"]: i for i in _row(res, "health")["items"]}
    assert by["s"]["ended"] is True and by["s"]["light"] is None
    assert by["t"]["ended"] is False  # ends today: still on
    assert _row(res, "health")["hours"] == 2.0 and _row(res, "health")["light"] == "green"


def test_rows_sort_red_first_and_no_light_last():
    res = _compute([_item("a", area="family")], [_ans("a", "rough")],
                   wheel=_wheel(health="green", legal="yellow", career=None))
    assert [r["key"] for r in res["rows"]] == ["family", "legal", "health", "career"]


def test_item_rows_carry_kind_hours_and_weight():
    res = _compute([_item("c", hours=2, every="month", weight=1), _item("d", kind="status", weight=3)])
    by = {i["id"]: i for i in _row(res, "health")["items"]}
    assert by["c"]["kind"] == "time" and by["c"]["hours"] == 0.5 and by["c"]["weight"] == 1
    assert by["d"]["kind"] == "status" and by["d"]["hours"] is None and by["d"]["weight"] == 3


# ── the plate ─────────────────────────────────────────────────────────────────

def _plate(*hours, sleep=56, events=None):
    items = [_item("sleep", hours=sleep, source="fitbit:sleep")] + [_item(f"i{n}", hours=h) for n, h in enumerate(hours)]
    return _compute(items, events=events)["plate"]


def test_plate_free_hours_leave_out_sleep_and_light_by_share():
    p = _plate(100.8)  # 90% of 112
    assert p["free"] == 112 and p["committed"] == 100.8 and p["pct"] == 90 and p["light"] == "green"
    assert _plate(101)["light"] == "yellow"
    assert _plate(112)["light"] == "yellow" and _plate(112)["pct"] == 100
    assert _plate(112.5)["light"] == "red"


def test_plate_counts_calendar_hours():
    items = [_item("sleep", hours=56, source="fitbit:sleep"), _item("kids", area="family", source=CAL),
             _item("job", area="career", hours=40)]
    events = [_timed("Game", "2025-11-07T09:00:00-07:00", "2025-11-07T13:00:00-07:00")]
    assert _compute(items, events=events)["plate"]["committed"] == 44
    assert _compute(items, events=None)["plate"]["committed"] == 40


def test_status_items_and_ended_seasons_add_no_hours():
    items = [_item("sleep", hours=56, source="fitbit:sleep"), _item("d", kind="status"),
             _item("s", hours=9, ends="2025-11-01"), _item("w", hours=3)]
    assert _compute(items)["plate"]["committed"] == 3


def test_no_items_gives_no_plate_and_the_wheel_rows_unchanged():
    res = _compute([], wheel=_wheel(health="green"))
    assert res["plate"] is None
    assert res["rows"] == [{"key": "health", "label": "Health", "light": "green", "manual": "green", "note": None,
                            "source": "manual", "hours": None, "items": []}]


def test_checked_is_the_newest_check_in_date():
    assert _compute([_item("a")], [_ans("a", "good", "2025-11-02"), _ans("a", "okay", "2025-11-04")])["checked"] == "2025-11-04"
    assert _compute([_item("a")])["checked"] is None


# ── build: reads the repo files ───────────────────────────────────────────────

def test_wheel_snapshot_reads_the_newest_row(tmp_path):
    p = tmp_path / "wheel.ndjson"
    p.write_text(json.dumps({"date": "2025-10-01", "ratings": {"health": "red"}}) + "\n"
                 + json.dumps({"date": "2025-11-01", "ratings": {"health": "green"}, "notes": {"health": "ok"}}) + "\n")
    snap = wheel_snapshot(p, TODAY)
    assert snap["date"] == "2025-11-01" and snap["stale"] is False
    assert snap["rows"] == [{"key": "health", "label": "Health", "light": "green", "note": "ok"}]
    assert wheel_snapshot(tmp_path / "missing.ndjson", TODAY)["rows"] == []


def test_build_reads_the_files(tmp_path):
    (tmp_path / "2-areas/_data").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "2-areas/_data/area-items.ndjson").write_text(json.dumps(_item("a", weight=2)) + "\n")
    (tmp_path / "2-areas/_data/area-checkins.ndjson").write_text(json.dumps(_ans("a", "okay")) + "\n")
    (tmp_path / "config/habit_schema.yaml").write_text("daily_habits: []\n")
    res = area_items.build(tmp_path, TODAY, _wheel(health="green"))
    assert _row(res, "health")["light"] == "yellow"
    assert res["plate"]["free"] == 168  # no sleep item
