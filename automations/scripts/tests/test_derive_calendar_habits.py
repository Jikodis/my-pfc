"""Unit tests for derive_calendar_habits.

Habits whose reps already sit on the calendar log themselves. The example
habit here is a synthetic yoga class, one rep per class night.
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

import derive_calendar_habits as d

TZ = ZoneInfo("America/Denver")
NOW = datetime(2025, 11, 9, 5, 0, tzinfo=TZ)  # a 5:00 AM run
Yoga = {"id": "yoga-class", "cadence": "monthly",
       "match": d.compile_rule({"match": r"^Yoga\b", "exclude": "MISSED"})}


def timed(summary, when, **extra):
    return {"summary": summary, "start": {"dateTime": when}, **extra}


def allday(summary, day, end=None):
    ev = {"summary": summary, "start": {"date": day}}
    if end:
        ev["end"] = {"date": end}
    return ev


def dates(rows):
    return [r["date"] for r in rows]


# ── which events count ────────────────────────────────────────────────────────

class TestDerivedRows:
    def test_class_night_with_two_classes_is_one_rep(self):
        rows = d.derived_rows(Yoga, [
            timed("Yoga - Flow", "2025-11-03T19:00:00-07:00"),
            timed("Yoga - Stretch", "2025-11-03T20:00:00-07:00"),
        ], NOW)
        assert dates(rows) == ["2025-11-03"]
        assert rows[0] == {"habit_id": "yoga-class", "date": "2025-11-03",
                           "completed": True, "source": d.SOURCE}

    def test_missed_class_is_not_a_rep(self):
        assert d.derived_rows(Yoga, [timed("Yoga - Flow (MISSED)",
                                          "2025-11-03T19:00:00-07:00")], NOW) == []

    def test_all_day_solo_practice_counts(self):
        assert dates(d.derived_rows(Yoga, [allday("Yoga Practice", "2025-11-05", "2025-11-06")], NOW)) == ["2025-11-05"]

    def test_title_must_match_at_the_start(self):
        assert d.derived_rows(Yoga, [timed("Drive to Yoga", "2025-11-03T19:00:00-07:00"),
                                    timed("YogaX social", "2025-11-03T19:00:00-07:00")], NOW) == []

    def test_event_that_has_not_started_is_not_a_rep_yet(self):
        # 5 AM: tonight's class has not happened. Tomorrow's run logs it as yesterday.
        assert d.derived_rows(Yoga, [timed("Yoga", "2025-11-09T20:00:00-07:00")], NOW) == []

    def test_today_all_day_counts_once_the_day_has_begun(self):
        assert dates(d.derived_rows(Yoga, [allday("Yoga Practice", "2025-11-09")], NOW)) == ["2025-11-09"]

    def test_future_dates_never_produce_rows(self):
        assert d.derived_rows(Yoga, [allday("Yoga Practice", "2025-11-12")], NOW) == []

    def test_cancelled_event_is_not_a_rep(self):
        assert d.derived_rows(Yoga, [timed("Yoga", "2025-11-03T19:00:00-07:00", status="cancelled")], NOW) == []

    def test_utc_timestamp_lands_on_the_local_date(self):
        # 8 PM Mountain on 11-03 is 03:00Z on 11-04.
        assert dates(d.derived_rows(Yoga, [timed("Yoga", "2025-11-04T03:00:00Z")], NOW)) == ["2025-11-03"]

    def test_rows_are_in_date_order(self):
        rows = d.derived_rows(Yoga, [timed("Yoga", "2025-11-03T20:00:00-07:00"),
                                    timed("Yoga", "2025-10-27T20:00:00-06:00")], NOW)
        assert dates(rows) == ["2025-10-27", "2025-11-03"]


# ── merging into the log ──────────────────────────────────────────────────────

def derived(day):
    return {"habit_id": "yoga-class", "date": day, "completed": True, "source": d.SOURCE}


class TestMerge:
    covered = {"2025-11-08", "2025-11-09"}

    def test_unrelated_rows_are_untouched(self):
        other = {"habit_id": "social-time", "date": "2025-11-08", "completed": True, "source": "chat"}
        out = d.merge([other], "yoga-class", [derived("2025-11-08")], self.covered)
        assert out == [other, derived("2025-11-08")]

    def test_rerun_is_idempotent(self):
        once = d.merge([], "yoga-class", [derived("2025-11-08")], self.covered)
        assert d.merge(once, "yoga-class", [derived("2025-11-08")], self.covered) == once

    def test_manual_row_wins(self):
        manual = {"habit_id": "yoga-class", "date": "2025-11-08", "completed": False, "source": "chat"}
        out = d.merge([manual], "yoga-class", [derived("2025-11-08")], self.covered)
        assert out == [manual]

    def test_derived_row_whose_event_vanished_drops_inside_the_covered_window(self):
        # Renamed to "(MISSED)" after the run, or deleted: the calendar is the truth.
        out = d.merge([derived("2025-11-08")], "yoga-class", [], self.covered)
        assert out == []

    def test_derived_rows_outside_the_covered_window_are_kept(self):
        # The daily cache covers only yesterday and today; history must survive it.
        out = d.merge([derived("2025-10-27")], "yoga-class", [], self.covered)
        assert out == [derived("2025-10-27")]

    def test_new_rows_append_in_date_order(self):
        out = d.merge([], "yoga-class", [derived("2025-11-09"), derived("2025-11-08")], self.covered)
        assert dates(out) == ["2025-11-08", "2025-11-09"]


# ── the window the source covers ──────────────────────────────────────────────

class TestCovered:
    def test_cache_from_yesterday_covers_yesterday_and_today(self):
        blob = {"from": "2025-11-08", "fetched_at": "2025-11-09T05:02:29-0700"}
        assert d.covered_dates(blob, "2025-11-09") == {"2025-11-08", "2025-11-09"}

    def test_cache_without_from_covers_only_its_fetch_day(self):
        blob = {"fetched_at": "2025-11-09T05:02:29-0700"}
        assert d.covered_dates(blob, "2025-11-09") == {"2025-11-09"}

    def test_stale_cache_stops_at_its_seven_day_horizon(self):
        blob = {"from": "2025-11-01", "fetched_at": "2025-11-02T05:00:00-0700"}
        got = d.covered_dates(blob, "2025-11-20")
        assert min(got) == "2025-11-01" and max(got) == "2025-11-08"


# ── schema loading ────────────────────────────────────────────────────────────

class TestLoadHabits:
    def test_picks_only_auto_derived_habits_with_a_calendar_rule(self):
        schema = {
            "daily_habits": [
                {"id": "sleep-on-time", "auto_derived": True},  # wearable, no calendar rule
                {"id": "read", "calendar": {"match": "^Read"}},       # not auto_derived
                {"id": "gym", "auto_derived": True, "calendar": {"match": "^Gym"}},
            ],
            "monthly_habits": [
                {"id": "yoga-class", "auto_derived": True,
                 "calendar": {"match": r"^Yoga\b", "exclude": "MISSED"}},
                {"id": "old", "auto_derived": True, "active": False, "calendar": {"match": "^Old"}},
            ],
        }
        got = {h["id"]: h["cadence"] for h in d.load_habits(schema)}
        assert got == {"gym": "daily", "yoga-class": "monthly"}

    def test_the_real_schema_rules_compile(self):
        schema = yaml.safe_load((d.REPO_ROOT / "config/habit_schema.yaml").read_text())
        for h in d.load_habits(schema):
            assert h["cadence"] in ("daily", "monthly")


# ── end to end against a temp repo ────────────────────────────────────────────

@pytest.fixture
def repo(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "7-habits/_data").mkdir(parents=True)
    (tmp_path / "config/habit_schema.yaml").write_text(yaml.safe_dump({
        "daily_habits": [{"id": "gym", "auto_derived": True, "calendar": {"match": "^Gym"}}],
        "monthly_habits": [{"id": "yoga-class", "auto_derived": True,
                            "calendar": {"match": r"^Yoga\b", "exclude": "MISSED"}}],
    }))
    (tmp_path / "7-habits/_data/habits-daily.ndjson").write_text("")
    (tmp_path / "7-habits/_data/habits-monthly.ndjson").write_text(
        json.dumps({"habit_id": "yoga-class", "date": "2025-11-03", "completed": True, "source": "chat"}) + "\n")
    (tmp_path / "data/calendar-cache.json").write_text(json.dumps({
        "fetched_at": "2025-11-09T05:00:00-0700", "from": "2025-11-08", "events": [
            timed("Yoga - Flow", "2025-11-08T19:00:00-07:00"),
            timed("Yoga - Stretch", "2025-11-08T20:00:00-07:00"),
            timed("Gym", "2025-11-08T06:00:00-07:00"),
            timed("Yoga", "2025-11-10T20:00:00-07:00"),
        ]}))
    return tmp_path


def read(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def test_run_writes_each_habit_to_its_cadence_file(repo):
    d.run(repo, now=NOW)
    monthly = read(repo / "7-habits/_data/habits-monthly.ndjson")
    daily = read(repo / "7-habits/_data/habits-daily.ndjson")
    assert [(r["date"], r["source"]) for r in monthly] == [("2025-11-03", "chat"), ("2025-11-08", d.SOURCE)]
    assert [(r["habit_id"], r["date"]) for r in daily] == [("gym", "2025-11-08")]


def test_second_run_changes_nothing(repo):
    d.run(repo, now=NOW)
    before = (repo / "7-habits/_data/habits-monthly.ndjson").read_text()
    assert d.run(repo, now=NOW) == []
    assert (repo / "7-habits/_data/habits-monthly.ndjson").read_text() == before


def test_events_file_backfill_uses_its_own_from(repo, tmp_path):
    feed = tmp_path / "feed.json"
    feed.write_text(json.dumps({"from": "2025-08-01", "events": [
        timed("Yoga - Flow (MISSED)", "2025-08-04T19:00:00-06:00"),
        allday("Yoga Practice", "2025-08-05", "2025-08-06"),
        timed("Yoga", "2025-09-08T19:45:00-06:00")]}))
    d.run(repo, now=NOW, events_path=feed)
    monthly = read(repo / "7-habits/_data/habits-monthly.ndjson")
    assert dates(monthly) == ["2025-11-03", "2025-08-05", "2025-09-08"]


def test_untouched_lines_keep_their_exact_text(repo):
    # Rewriting every row's spacing would bury the real change in a whole-file diff.
    path = repo / "7-habits/_data/habits-monthly.ndjson"
    spaced = '{"habit_id": "social-time", "date": "2025-11-01", "completed": true}\n'
    path.write_text(path.read_text() + spaced)
    before = path.read_text()
    d.run(repo, now=NOW)
    after = path.read_text()
    assert after.startswith(before)
    assert after[len(before):] == '{"habit_id":"yoga-class","date":"2025-11-08","completed":true,"source":"calendar-derived"}\n'


def test_missing_cache_writes_nothing(repo):
    (repo / "data/calendar-cache.json").unlink()
    assert d.run(repo, now=NOW) == []
