"""Unit tests for derive_workout_habits.

Workout habits log themselves from the Google Health sessions the watch already
recorded. Unlike the sleep deriver these habits stay hand-loggable, because a
workout done without starting the watch still counts.
"""
import json
from pathlib import Path

import yaml

import derive_workout_habits as d

ROW = {"id": "morning-walk", "types": {"WALKING"}, "min_minutes": 10, "started": "2025-01-01"}
LIFT = {"id": "gym-session", "types": {"STRENGTH_TRAINING"}, "min_minutes": 0, "started": "2025-02-10"}


def day(date, *types, workouts="list"):
    health = {"sleep_hours": 7.0}
    if workouts == "list":
        health["workouts"] = [{"type": t, "minutes": 40} for t in types]
    elif workouts == "null":
        health["workouts"] = None
    return {"date": date, "health": health}


def derived(habit_id, date):
    return {"habit_id": habit_id, "date": date, "completed": True, "source": d.SOURCE}


# ── which days count ──────────────────────────────────────────────────────────

class TestSessionDates:
    def test_a_matching_session_is_a_rep(self):
        hit, known = d.session_dates(ROW, [day("2025-03-10", "WALKING")])
        assert hit == {"2025-03-10"} and known == {"2025-03-10"}

    def test_a_session_of_ten_real_minutes_counts_and_a_shorter_one_does_not(self):
        def row(date, real, timer):
            return {"date": date, "health": {"workouts": [
                {"type": "WALKING", "minutes": timer, "real_minutes": real}]}}
        hit, known = d.session_dates(ROW, [row("2025-03-10", 15, 40), row("2025-03-11", 10, 12),
                                           row("2025-03-12", 9, 45), row("2025-03-13", 3, 10)])
        assert hit == {"2025-03-10", "2025-03-11"}
        assert known == {"2025-03-10", "2025-03-11", "2025-03-12", "2025-03-13"}

    def test_the_timer_decides_only_when_there_is_no_derived_length(self):
        def row(date, timer):
            return {"date": date, "health": {"workouts": [
                {"type": "WALKING", "minutes": timer, "real_minutes": None}]}}
        hit, _ = d.session_dates(ROW, [row("2025-03-10", 22), row("2025-03-11", 6)])
        assert hit == {"2025-03-10"}

    def test_a_habit_with_no_minimum_counts_any_length(self):
        short = {"date": "2025-03-12", "health": {"workouts": [
            {"type": "STRENGTH_TRAINING", "minutes": 29, "real_minutes": 1}]}}
        hit, _ = d.session_dates(LIFT, [short])
        assert hit == {"2025-03-12"}

    def test_other_session_types_are_not_a_rep(self):
        hit, known = d.session_dates(ROW, [day("2025-03-11", "OTHER", "SPORT"),
                                           day("2025-03-12", "STRENGTH_TRAINING")])
        assert hit == set()
        assert known == {"2025-03-11", "2025-03-12"}

    def test_two_sessions_on_one_day_are_one_rep(self):
        hit, _ = d.session_dates(ROW, [day("2025-03-10", "WALKING", "WALKING")])
        assert hit == {"2025-03-10"}

    def test_a_day_with_no_sessions_is_known_and_empty(self):
        hit, known = d.session_dates(LIFT, [day("2025-03-13")])
        assert hit == set() and known == {"2025-03-13"}

    def test_a_failed_or_missing_exercise_fetch_is_unknown(self):
        days = [day("2025-03-01", workouts="null"), day("2025-03-02", workouts="absent"),
                {"date": "2025-03-03"}]
        hit, known = d.session_dates(LIFT, days)
        assert hit == set() and known == set()

    def test_sessions_before_the_habit_started_are_ignored(self):
        hit, known = d.session_dates(LIFT, [day("2025-02-09", "STRENGTH_TRAINING"),
                                            day("2025-02-10", "STRENGTH_TRAINING")])
        assert hit == {"2025-02-10"} and known == {"2025-02-10"}


# ── merging into the log ──────────────────────────────────────────────────────

class TestMerge:
    def test_adds_a_row_for_a_new_session(self):
        out = d.merge([], "gym-session", {"2025-03-12"}, {"2025-03-12"})
        assert out == [derived("gym-session", "2025-03-12")]

    def test_is_idempotent(self):
        once = d.merge([], "gym-session", {"2025-03-12"}, {"2025-03-12"})
        assert d.merge(once, "gym-session", {"2025-03-12"}, {"2025-03-12"}) == once

    def test_a_hand_logged_row_wins(self):
        hand = {"habit_id": "gym-session", "date": "2025-03-05", "completed": True, "source": "web"}
        out = d.merge([hand], "gym-session", {"2025-03-05"}, {"2025-03-05"})
        assert out == [hand]

    def test_a_hand_logged_miss_or_skip_is_left_alone(self):
        miss = {"habit_id": "gym-session", "date": "2025-03-05", "completed": False, "source": "chat"}
        skip = {"habit_id": "gym-session", "date": "2025-03-06", "completed": False,
                "skipped": True, "skip_reason": "sick", "source": "chat"}
        both = {"2025-03-05", "2025-03-06"}
        assert d.merge([miss, skip], "gym-session", both, both) == [miss, skip]

    def test_other_habits_rows_are_untouched(self):
        other = {"habit_id": "read-15-min", "date": "2025-03-12", "completed": True, "source": "web"}
        out = d.merge([other], "gym-session", {"2025-03-12"}, {"2025-03-12"})
        assert out == [other, derived("gym-session", "2025-03-12")]

    def test_a_derived_row_drops_when_the_session_is_gone(self):
        # A mis-started session was deleted on the watch; the next fetch shows none.
        old = derived("gym-session", "2025-03-12")
        assert d.merge([old], "gym-session", set(), {"2025-03-12"}) == []

    def test_a_derived_row_stays_when_the_day_became_unknown(self):
        # A later fetch failed (workouts null): no evidence either way, keep the rep.
        old = derived("gym-session", "2025-03-12")
        assert d.merge([old], "gym-session", set(), set()) == [old]

    def test_a_derived_row_beside_a_hand_row_falls_out(self):
        hand = {"habit_id": "gym-session", "date": "2025-03-12", "completed": True, "source": "web"}
        old = derived("gym-session", "2025-03-12")
        out = d.merge([old, hand], "gym-session", {"2025-03-12"}, {"2025-03-12"})
        assert out == [hand]


# ── schema loading ────────────────────────────────────────────────────────────

class TestLoadHabits:
    def test_picks_active_daily_habits_with_a_workout_rule(self):
        schema = {"daily_habits": [
            {"id": "row", "started": "2025-01-01", "workout": {"types": ["WALKING"], "min_minutes": 10}},
            {"id": "stretch-daily"},
            {"id": "old", "active": False, "workout": {"types": ["RUNNING"]}},
            {"id": "empty", "workout": {"types": []}},
        ]}
        assert d.load_habits(schema) == [{"id": "row", "types": {"WALKING"}, "min_minutes": 10,
                                          "started": "2025-01-01"}]

    def test_the_real_schema_loads(self):
        # The starter habits carry no `workout:` rule; add one to opt a habit in.
        schema = yaml.safe_load((Path(d.REPO_ROOT) / "config/habit_schema.yaml").read_text())
        for h in d.load_habits(schema):
            assert h["types"] and h["min_minutes"] >= 0


# ── end to end on a temp repo ─────────────────────────────────────────────────

def make_repo(tmp_path, days, logs):
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "7-habits/_data").mkdir(parents=True)
    (tmp_path / "config/habit_schema.yaml").write_text(yaml.safe_dump({"daily_habits": [
        {"id": "morning-walk", "started": "2025-01-01", "workout": {"types": ["WALKING"]}},
        {"id": "gym-session", "started": "2025-02-10", "workout": {"types": ["STRENGTH_TRAINING"]}},
    ]}))
    (tmp_path / "data/day-tracking.ndjson").write_text("".join(json.dumps(r) + "\n" for r in days))
    (tmp_path / "7-habits/_data/habits-daily.ndjson").write_text("".join(l + "\n" for l in logs))
    return tmp_path


def test_run_writes_compact_rows_and_keeps_existing_lines_byte_for_byte(tmp_path):
    hand = '{"habit_id":"gym-session","date":"2025-03-05","completed":true,"source":"web"}'
    spaced = '{"habit_id": "read-15-min", "date": "2025-03-09", "completed": true}'
    repo = make_repo(tmp_path,
                     [day("2025-03-05", "STRENGTH_TRAINING"), day("2025-03-10", "WALKING"),
                      day("2025-03-12", "STRENGTH_TRAINING")],
                     [hand, spaced])
    assert d.run(repo) is True
    lines = (repo / "7-habits/_data/habits-daily.ndjson").read_text().splitlines()
    assert lines == [
        hand, spaced,
        '{"habit_id":"morning-walk","date":"2025-03-10","completed":true,"source":"health-derived"}',
        '{"habit_id":"gym-session","date":"2025-03-12","completed":true,"source":"health-derived"}',
    ]
    assert d.run(repo) is False  # second pass: nothing to write


def test_dry_run_writes_nothing(tmp_path):
    repo = make_repo(tmp_path, [day("2025-03-12", "STRENGTH_TRAINING")], [])
    assert d.run(repo, dry_run=True) is True
    assert (repo / "7-habits/_data/habits-daily.ndjson").read_text() == ""
