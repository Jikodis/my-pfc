"""Unit tests for pfc_writes: the task, habit, and focus mutations every writer shares."""

from __future__ import annotations

from pfc_writes import (EXERCISE_HABIT_ID, complete_task, drop_task, log_habit, rate_day, retire_anchor, set_parked, set_picks,
                        set_project, set_rating, skip_suggestion, stamp_review)

TODAY = "2026-09-10"


def _task(task_id="task-20260901-001", **overrides):
    base = {"id": task_id, "status": "open", "description": "Call the dentist", "created": "2026-09-01"}
    base.update(overrides)
    return base


def _focus_day(date=TODAY, critical=None, bonus=None, completed=None, bonus_completed=False):
    return {"date": date, "critical": critical or [], "bonus": bonus,
            "completed": completed if completed is not None else [], "bonus_completed": bonus_completed}


# ---------------------------------------------------------------- complete_task

def test_complete_task_marks_done_and_appends_event():
    tasks, events, focus = [_task()], [], []
    status, info = complete_task(tasks, events, focus, "task-20260901-001", TODAY, "web")
    assert status == "completed"
    assert tasks[0]["status"] == "done"
    assert tasks[0]["completed"] == TODAY
    assert events == [{"task_id": "task-20260901-001", "event": "completed", "timestamp": TODAY, "source": "web"}]
    assert info == {"title": "Call the dentist", "email_linked": False, "focus_updated": False}


def test_complete_task_uses_the_source_it_is_given():
    events = []
    complete_task([_task()], events, [], "task-20260901-001", TODAY, "trello")
    assert events[0]["source"] == "trello"


def test_complete_task_already_done_changes_nothing():
    tasks = [_task(status="done", completed="2026-09-02")]
    events, focus = [], [_focus_day(critical=["task-20260901-001"])]
    status, info = complete_task(tasks, events, focus, "task-20260901-001", TODAY, "web")
    assert status == "already_done"
    assert tasks[0]["completed"] == "2026-09-02"
    assert events == []
    assert focus[0]["completed"] == []
    assert info == {"title": "Call the dentist", "email_linked": False, "focus_updated": False}


def test_complete_task_unknown_id_changes_nothing():
    tasks, events, focus = [_task()], [], []
    status, info = complete_task(tasks, events, focus, "task-19990101-001", TODAY, "web")
    assert status == "unknown"
    assert tasks == [_task()]
    assert events == []
    assert info == {"title": "", "email_linked": False, "focus_updated": False}


def test_complete_task_email_linked_when_thread_id_is_a_non_empty_string():
    status, info = complete_task([_task(source_email_thread_id="1955a9ebcf534a01")], [], [], "task-20260901-001", TODAY, "web")
    assert status == "completed"
    assert info["email_linked"] is True


def test_complete_task_not_email_linked_for_null_or_empty_thread_id():
    for value in (None, "", 42):
        _, info = complete_task([_task(source_email_thread_id=value)], [], [], "task-20260901-001", TODAY, "web")
        assert info["email_linked"] is False, value


def test_complete_task_adds_a_critical_pick_to_todays_completed():
    focus = [_focus_day(critical=["task-20260901-002", "task-20260901-001"], completed=["task-20260901-002"])]
    _, info = complete_task([_task()], [], focus, "task-20260901-001", TODAY, "web")
    assert focus[0]["completed"] == ["task-20260901-002", "task-20260901-001"]
    assert focus[0]["bonus_completed"] is False
    assert info["focus_updated"] is True


def test_complete_task_does_not_duplicate_a_completed_critical_pick():
    # The task was reopened by hand after being ticked off in the 2+1.
    focus = [_focus_day(critical=["task-20260901-001"], completed=["task-20260901-001"])]
    _, info = complete_task([_task()], [], focus, "task-20260901-001", TODAY, "web")
    assert focus[0]["completed"] == ["task-20260901-001"]
    assert info["focus_updated"] is False


def test_complete_task_starts_completed_when_the_record_has_none():
    day = {"date": TODAY, "critical": ["task-20260901-001"], "bonus": None}
    focus = [day]
    _, info = complete_task([_task()], [], focus, "task-20260901-001", TODAY, "web")
    assert day["completed"] == ["task-20260901-001"]
    assert info["focus_updated"] is True


def test_complete_task_sets_bonus_completed_for_the_bonus_pick():
    focus = [_focus_day(critical=["task-20260901-002"], bonus="task-20260901-001")]
    _, info = complete_task([_task()], [], focus, "task-20260901-001", TODAY, "web")
    assert focus[0]["bonus_completed"] is True
    assert focus[0]["completed"] == []
    assert info["focus_updated"] is True


def test_complete_task_ticks_the_focus_date_it_is_given():
    focus = [_focus_day(date="2026-09-09", critical=["task-20260901-001"]),
             _focus_day(critical=["task-20260901-001"])]
    tasks = [_task()]
    _, info = complete_task(tasks, [], focus, "task-20260901-001", TODAY, "trello", focus_date="2026-09-09")
    assert focus[0]["completed"] == ["task-20260901-001"]
    assert focus[1]["completed"] == []
    assert tasks[0]["completed"] == TODAY
    assert info["focus_updated"] is True


def test_complete_task_leaves_other_days_focus_alone():
    yesterday = _focus_day(date="2026-09-09", critical=["task-20260901-001"], bonus="task-20260901-001")
    focus = [yesterday]
    _, info = complete_task([_task()], [], focus, "task-20260901-001", TODAY, "web")
    assert yesterday["completed"] == []
    assert yesterday["bonus_completed"] is False
    assert info["focus_updated"] is False


def test_complete_task_leaves_todays_focus_alone_when_the_task_is_not_in_it():
    day = _focus_day(critical=["task-20260901-002"], bonus="task-20260901-003")
    focus = [day]
    _, info = complete_task([_task()], [], focus, "task-20260901-001", TODAY, "web")
    assert day == _focus_day(critical=["task-20260901-002"], bonus="task-20260901-003")
    assert info["focus_updated"] is False


def test_complete_task_mutates_the_lists_in_place():
    tasks, events, focus = [_task()], [], [_focus_day(critical=["task-20260901-001"])]
    ids = (id(tasks), id(events), id(focus))
    complete_task(tasks, events, focus, "task-20260901-001", TODAY, "web")
    assert (id(tasks), id(events), id(focus)) == ids
    assert len(tasks) == 1 and len(events) == 1 and len(focus) == 1


# ---------------------------------------------------------------- log_habit

def test_log_habit_appends_a_completed_row():
    logs = [{"habit_id": "row", "date": "2026-09-09", "completed": True, "source": "manual"}]
    assert log_habit(logs, "row", TODAY, "web") == "logged"
    assert logs[-1] == {"habit_id": "row", "date": TODAY, "completed": True, "source": "web"}
    assert len(logs) == 2


def test_log_habit_is_idempotent_per_habit_and_date():
    logs = []
    assert log_habit(logs, "row", TODAY, "web") == "logged"
    assert log_habit(logs, "row", TODAY, "trello") == "already_logged"
    assert len(logs) == 1


def test_log_habit_another_habit_or_date_still_logs():
    logs = [{"habit_id": "row", "date": TODAY, "completed": True, "source": "manual"}]
    assert log_habit(logs, "read", TODAY, "web") == "logged"
    assert log_habit(logs, "row", "2026-09-11", "web") == "logged"
    assert len(logs) == 3


def test_log_habit_a_missed_row_is_updated_in_place():
    logs = [{"habit_id": "row", "date": TODAY, "completed": False, "source": "evening-checkin"}]
    assert log_habit(logs, "row", TODAY, "web") == "updated"
    assert logs == [{"habit_id": "row", "date": TODAY, "completed": True, "source": "web"}]


def test_log_habit_a_skipped_row_loses_the_skip_and_counts():
    logs = [{"habit_id": "row", "date": TODAY, "completed": False, "skipped": True,
             "skip_reason": "sick", "source": "evening-checkin"}]
    assert log_habit(logs, "row", TODAY, "trello") == "updated"
    assert logs == [{"habit_id": "row", "date": TODAY, "completed": True, "source": "trello"}]


def test_log_habit_a_completed_row_is_left_alone():
    row = {"habit_id": "row", "date": TODAY, "completed": True, "source": "manual"}
    logs = [dict(row)]
    assert log_habit(logs, "row", TODAY, "web") == "already_logged"
    assert logs == [row]


def test_log_habit_no_row_appends_one():
    logs = [{"habit_id": "row", "date": "2026-09-09", "completed": False, "source": "manual"}]
    assert log_habit(logs, "row", TODAY, "web") == "logged"
    assert len(logs) == 2
    assert logs[0]["completed"] is False


# ---------------------------------------------------------------- set_parked

def _focus(focus_id="focus-20260706-001", **overrides):
    base = {"id": focus_id, "tier": "pursuit", "title": "Guitar", "status": "red", "parked": False}
    base.update(overrides)
    return base


def test_set_parked_parks_and_unparks():
    focus = [_focus()]
    assert set_parked(focus, "focus-20260706-001", True) == ("updated", {"title": "Guitar"})
    assert focus[0]["parked"] is True
    assert set_parked(focus, "focus-20260706-001", False) == ("updated", {"title": "Guitar"})
    assert focus[0]["parked"] is False


def test_set_parked_unchanged_when_the_value_already_matches():
    focus = [_focus(parked=True)]
    assert set_parked(focus, "focus-20260706-001", True) == ("unchanged", {"title": "Guitar"})
    assert focus[0] == _focus(parked=True)


def test_set_parked_treats_a_missing_field_as_not_parked():
    record = _focus()
    del record["parked"]
    focus = [record]
    assert set_parked(focus, "focus-20260706-001", False) == ("unchanged", {"title": "Guitar"})
    assert "parked" not in record
    assert set_parked(focus, "focus-20260706-001", True) == ("updated", {"title": "Guitar"})
    assert record["parked"] is True


def test_set_parked_unknown_id():
    focus = [_focus()]
    assert set_parked(focus, "focus-19990101-001", True) == ("unknown", {"title": ""})
    assert focus == [_focus()]


def test_set_parked_a_retired_focus_is_unknown():
    focus = [_focus(retired_date="2026-08-01")]
    assert set_parked(focus, "focus-20260706-001", True) == ("unknown", {"title": ""})
    assert focus == [_focus(retired_date="2026-08-01")]


def test_set_parked_leaves_other_records_alone():
    other = _focus("focus-20260706-002", title="Japanese")
    focus = [_focus(), other]
    set_parked(focus, "focus-20260706-001", True)
    assert other == _focus("focus-20260706-002", title="Japanese")


def test_complete_task_bonus_already_ticked_is_not_an_update():
    focus = [_focus_day(bonus="task-20260901-001", bonus_completed=True)]
    _, info = complete_task([_task()], [], focus, "task-20260901-001", TODAY, "web")
    assert focus[0]["bonus_completed"] is True
    assert info["focus_updated"] is False


# ---------------------------------------------------------------- drop_task

def test_drop_task_logs_a_deleted_event_and_names_the_record_to_remove():
    tasks, events = [_task("task-20260901-000"), _task()], []
    status, info = drop_task(tasks, events, "task-20260901-001", TODAY, "web")
    assert status == "dropped"
    assert info == {"title": "Call the dentist", "email_linked": False, "index": 1, "archive": None}
    assert events == [{"task_id": "task-20260901-001", "event": "deleted", "timestamp": TODAY, "source": "web",
                       "note": "Dropped: won't do."}]
    # Removing the record is the file layer's job, so its line goes with it.
    assert len(tasks) == 2


def test_drop_task_refuses_a_done_task():
    tasks, events = [_task(status="done", completed="2026-09-02")], []
    status, info = drop_task(tasks, events, "task-20260901-001", TODAY, "web")
    assert status == "not_open"
    assert events == []


def test_drop_task_unknown_id():
    events = []
    status, info = drop_task([_task()], events, "task-19990101-001", TODAY, "web")
    assert status == "unknown" and events == []


def test_drop_task_email_linked():
    _, info = drop_task([_task(source_email_thread_id="1955a9ebcf534a01")], [], "task-20260901-001", TODAY, "web")
    assert info["email_linked"] is True


def test_drop_task_ever_picked_for_a_2_plus_1_hands_back_an_archive_copy():
    focus = [_focus_day(date="2026-09-05", bonus="task-20260901-001")]
    _, info = drop_task([_task()], [], "task-20260901-001", TODAY, "web", focus)
    assert info["archive"] == {**_task(), "dropped": TODAY}


def test_drop_task_ever_skipped_hands_back_an_archive_copy():
    # A `skipped` id must still resolve (scripts/validate.sh step 6b), the same as a pick.
    focus = [{"date": "2026-09-05", "critical": [], "bonus": None, "skipped": ["task-20260901-001"]}]
    _, info = drop_task([_task()], [], "task-20260901-001", TODAY, "web", focus)
    assert info["archive"] == {**_task(), "dropped": TODAY}


# ---------------------------------------------------------------- rate_day

def test_rate_day_derives_rating_and_exercised():
    days = [{"date": TODAY, "health": {}}]
    habits = [{"habit_id": EXERCISE_HABIT_ID, "date": TODAY, "completed": True}]
    assert rate_day(days, habits, TODAY, 4, 3, 5, None) == "updated"
    assert days[-1]["rating"] == 4 and days[-1]["exercised"] is True


def test_rate_day_rounds_to_the_nearest_whole_number():
    days = []
    rate_day(days, [], TODAY, 4, 4, 3, None)
    assert days[-1]["rating"] == 4 and days[-1]["exercised"] is False
    rate_day(days, [], "2026-09-11", 3, 3, 4, None)
    assert days[-1]["rating"] == 3


def test_rate_day_refuses_a_rated_day():
    days = [{"date": TODAY, "rating": 2}]
    assert rate_day(days, [], TODAY, 3, 3, 3, None) == "already_rated"
    assert days == [{"date": TODAY, "rating": 2}]


def test_rate_day_keeps_unasked_fields_null_or_untouched():
    days = [{"date": TODAY, "hyperfocused": True, "sick": False}]
    rate_day(days, [], TODAY, 3, 3, 3, None)
    assert days[-1]["hyperfocused"] is True and days[-1]["sick"] is False
    assert "evening_notes" not in days[-1]
    fresh = []
    assert rate_day(fresh, [], TODAY, 3, 3, 3, True) == "added"
    assert fresh[-1]["sick"] is None and fresh[-1]["evening_notes"] is None
    assert fresh[-1]["hyperfocused"] is True


# ---------------------------------------------------------------- set_picks

def test_set_picks_one_pick_day():
    focus = []
    assert set_picks(focus, TODAY, ["task-1"], None) == "added"
    assert focus[-1]["critical"] == ["task-1"] and focus[-1]["bonus"] is None


def test_set_picks_same_picks_twice_is_unchanged():
    focus = []
    set_picks(focus, TODAY, ["task-1", "task-2"], "task-3")
    assert set_picks(focus, TODAY, ["task-1", "task-2"], "task-3") == "unchanged"


def test_set_picks_keeps_project_slot_and_done_picks_that_remain():
    focus = [{"date": TODAY, "critical": ["task-1", "task-2"], "bonus": "task-3", "project": "task-9",
              "completed": ["task-1", "task-2"], "bonus_completed": True}]
    assert set_picks(focus, TODAY, ["task-2", "task-4"], "task-3") == "updated"
    assert focus[0]["project"] == "task-9" and focus[0]["completed"] == ["task-2"]
    assert focus[0]["bonus_completed"] is True
    set_picks(focus, TODAY, ["task-2"], "task-5")
    assert focus[0]["bonus_completed"] is False


# ---------------------------------------------------------------- stamp_review

def test_stamp_review():
    ledger = [{"id": "a", "last_done": "2026-01-01"}]
    assert stamp_review(ledger, "a", TODAY) == "stamped" and ledger[0]["last_done"] == TODAY
    assert stamp_review(ledger, "a", TODAY) == "unchanged"
    assert stamp_review(ledger, "b", TODAY) == "unknown"


# ---------------------------------------------------------------- skip_suggestion

def test_skip_suggestion_creates_a_record_for_a_day_with_none():
    focus = []
    assert skip_suggestion(focus, TODAY, "task-1") == "added"
    assert focus == [{"date": TODAY, "critical": [], "bonus": None, "completed": [], "bonus_completed": False,
                      "skipped": ["task-1"]}]


def test_skip_suggestion_adds_to_an_existing_list_once():
    focus = [_focus_day(critical=["task-9"])]
    assert skip_suggestion(focus, TODAY, "task-1") == "updated"
    assert skip_suggestion(focus, TODAY, "task-2") == "updated"
    assert focus[0]["skipped"] == ["task-1", "task-2"] and focus[0]["critical"] == ["task-9"]
    assert skip_suggestion(focus, TODAY, "task-1") == "unchanged"


# ---------------------------------------------------------------- set_rating

SNAPSHOT = {"date": "2026-06-03", "ratings": {"career": "green", "health": "red"},
            "notes": {"health": "Not enough sleep."}, "logged_at": "2026-06-03T12:44:41-0600"}
NOW = "2026-09-10T08:00:00-0600"


def test_set_rating_appends_a_snapshot_that_keeps_every_other_key_and_note():
    rows = [dict(SNAPSHOT)]
    assert set_rating(rows, "career", "yellow", None, TODAY, NOW) == "added"
    assert rows[0] == SNAPSHOT
    assert rows[1] == {"date": TODAY, "ratings": {"career": "yellow", "health": "red"},
                       "notes": {"health": "Not enough sleep."}, "logged_at": NOW}


def test_set_rating_sets_and_clears_a_note():
    rows = [dict(SNAPSHOT)]
    set_rating(rows, "career", "green", "Promotion talk.", TODAY, NOW)
    assert rows[-1]["notes"] == {"health": "Not enough sleep.", "career": "Promotion talk."}
    set_rating(rows, "health", "red", "", TODAY, NOW)
    assert rows[-1]["notes"] == {"career": "Promotion talk."}


def test_set_rating_unknown_key_and_no_change():
    rows = [dict(SNAPSHOT)]
    assert set_rating(rows, "pets", "green", None, TODAY, NOW) == "unknown"
    assert set_rating(rows, "career", "green", None, TODAY, NOW) == "unchanged"
    assert set_rating(rows, "health", "red", "Not enough sleep.", TODAY, NOW) == "unchanged"
    assert len(rows) == 1
    assert set_rating([], "career", "green", None, TODAY, NOW) == "unknown"


def test_set_rating_twice_in_one_day_updates_that_day_snapshot():
    rows = [dict(SNAPSHOT)]
    set_rating(rows, "career", "yellow", None, TODAY, NOW)
    assert set_rating(rows, "health", "yellow", None, TODAY, "2026-09-10T09:00:00-0600") == "updated"
    assert len(rows) == 2
    assert rows[1]["ratings"] == {"career": "yellow", "health": "yellow"}
    assert rows[1]["logged_at"] == "2026-09-10T09:00:00-0600"


# ---------------------------------------------------------------- retire_anchor

def test_retire_anchor():
    rows = [{"id": "ground-1", "title": "A", "status": "active", "retired_date": None}]
    assert retire_anchor(rows, "ground-1", TODAY) == "retired"
    assert rows[0]["status"] == "retired" and rows[0]["retired_date"] == TODAY
    assert retire_anchor(rows, "ground-1", "2026-09-11") == "unchanged"
    assert rows[0]["retired_date"] == TODAY
    assert retire_anchor(rows, "ground-2", TODAY) == "unknown"


# ---------------------------------------------------------------- set_project

def test_set_project_switches_between_active_and_parked():
    rows = [{"id": "p", "name": "P", "active": False, "status": "on-deck"}]
    assert set_project(rows, "p", True) == "updated"
    assert rows[0]["active"] is True and rows[0]["status"] == "active"
    assert set_project(rows, "p", True) == "unchanged"
    assert set_project(rows, "p", False) == "updated"
    assert rows[0]["active"] is False and rows[0]["status"] == "parked"


def test_set_project_refuses_closed_projects_and_unknown_ids():
    rows = [{"id": "d", "active": False, "status": "done"}, {"id": "x", "active": False, "status": "dropped"}]
    assert set_project(rows, "d", True) == "closed"
    assert set_project(rows, "x", False) == "closed"
    assert set_project(rows, "nope", True) == "unknown"
    assert rows[0]["status"] == "done"
