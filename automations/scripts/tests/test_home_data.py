"""Unit tests for home_data: the data behind the one-page web UI."""

import json
from datetime import datetime
from unittest.mock import patch

import pytest

from automations.scripts import home_data
from automations.scripts.home_data import EXERCISE_HABIT_ID, EXERCISE_LABEL, build_home, rate_target_date, rotate


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _nd(rows):
    return "".join(json.dumps(r) + "\n" for r in rows)


VISION = """---
name: {slug}
area: {area}
status: {status}
created: 2026-06-01
---

# {title}

## Why it matters

Serves **Creativity**, **Craft**. Also **Guitar** is not a value.
"""


@pytest.fixture
def tmp_repo(tmp_path):
    _write(tmp_path, "1-values/values.md",
           "# Top Values\n\n1. Curiosity\n2. Kindness\n3. Adventure\n4. Community\n5. Craft\n")
    _write(tmp_path, "3-visions/run-a-marathon.md",
           VISION.format(slug="run-a-marathon", area="health", status="active", title="Run a marathon"))
    _write(tmp_path, "3-visions/paused-one.md",
           VISION.format(slug="paused-one", area="career", status="paused", title="Paused"))
    _write(tmp_path, "3-visions/_template.md", "---\nstatus: active\n---\n# Template\n")
    _write(tmp_path, "3-visions/README.md", "# Visions\n")
    _write(tmp_path, "3-visions/AGENTS.md", "# Agents\n")
    _write(tmp_path, "config/habit_schema.yaml",
           "daily_habits:\n  - id: practice-guitar\n    frequency: 7\n    started: '2026-01-01'\n"
           "  - id: morning-walk\n    frequency: 3\n    started: '2026-01-01'\nmonthly_habits: []\n")
    _write(tmp_path, "4-focus/_data/focus.ndjson", _nd([
        {"id": "f1", "tier": "pursuit", "title": "Guitar", "impact": "medium", "urgency": "medium",
         "habits": ["practice-guitar"], "retired_date": None, "parked": False},
    ]))
    _write(tmp_path, "7-habits/_data/habits-daily.ndjson", "")
    _write(tmp_path, "7-habits/_data/habits-monthly.ndjson", "")
    _write(tmp_path, "data/grounding.ndjson", _nd([
        {"id": "g1", "title": "Example anchor", "status": "active", "retired_date": None},
        {"id": "g2", "title": "Old", "status": "retired", "retired_date": "2026-01-01"},
    ]))
    _write(tmp_path, "6-tasks/_data/daily-focus.ndjson", _nd([{"date": "2026-10-18", "critical": []}]))
    _write(tmp_path, "data/day-tracking.ndjson", _nd([
        {"date": "2026-09-04", "rating": 4, "health": {}},
        {"date": "2026-11-01", "rating": None,
         "health": {"sleep_hours": 7.2, "awake_minutes": 75}},
    ]))
    from automations.scripts import trello_render, trmnl_push
    # home_data imports these by their bare names (automations/scripts is on sys.path),
    # which is a second copy of each module; patch both so no reader sees the real repo.
    import trello_render as bare_trello_render
    import trmnl_push as bare_trmnl_push
    with patch.object(home_data, "REPO", tmp_path), patch.object(trmnl_push, "REPO_ROOT", tmp_path), \
            patch.object(trello_render, "REPO_ROOT", tmp_path), \
            patch.object(bare_trmnl_push, "REPO_ROOT", tmp_path), \
            patch.object(bare_trello_render, "REPO_ROOT", tmp_path):
        yield tmp_path


def test_values_skip_empty_numbered_lines_and_bullets(tmp_repo):
    _write(tmp_repo, "1-values/values.md",
           "# Values\n\n- Curiosity\n- Kindness\n\n## Your ranked values\n\n1.\n2. **Craft**\n3.\n4. Community\n5.\n")
    assert build_home({}, datetime(2026, 11, 1, 9, 0))["values"] == ["Craft", "Community"]


def test_underscore_vision_files_are_skipped(tmp_repo):
    _write(tmp_repo, "3-visions/_draft.md",
           VISION.format(slug="_draft", area="health", status="active", title="Draft"))
    assert [v["id"] for v in build_home({}, datetime(2026, 11, 1, 9, 0))["visions"]] == ["run-a-marathon"]


def test_rate_target_before_evening_is_yesterday():
    assert rate_target_date(datetime(2026, 11, 1, 17, 59)) == "2026-10-31"


def test_rate_target_in_evening_is_today():
    assert rate_target_date(datetime(2026, 11, 1, 18, 0)) == "2026-11-01"


def test_rate_target_just_after_midnight_is_yesterday():
    assert rate_target_date(datetime(2026, 11, 2, 0, 5)) == "2026-11-01"


def test_rotate_changes_daily_and_is_stable():
    items = ["a", "b", "c"]
    assert rotate(items, "2026-11-01") == rotate(items, "2026-11-01")
    assert rotate(items, "2026-11-01") != rotate(items, "2026-11-02")


def test_rotate_empty_is_none():
    assert rotate([], "2026-11-01") is None


def test_rated_day_is_not_unrated(tmp_repo):
    _write(tmp_repo, "data/day-tracking.ndjson", _nd([{"date": "2026-11-01", "rating": 4, "health": {}}]))
    assert build_home({}, datetime(2026, 11, 2, 9, 0))["rate_target"] == {"date": "2026-11-01", "unrated": False}


def test_unrated_day_is_unrated(tmp_repo):
    assert build_home({}, datetime(2026, 11, 1, 19, 0))["rate_target"] == {"date": "2026-11-01", "unrated": True}


def test_welcome_back_when_rating_and_picks_both_older_than_yesterday(tmp_repo):
    _write(tmp_repo, "data/day-tracking.ndjson", _nd([{"date": "2026-09-04", "rating": 4, "health": {}}]))
    assert build_home({}, datetime(2026, 11, 1, 9, 0))["welcome_back"] is True


def test_a_skip_only_record_is_not_a_pick_day(tmp_repo):
    _write(tmp_repo, "data/day-tracking.ndjson", _nd([{"date": "2026-09-04", "rating": 4, "health": {}}]))
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2026-10-18", "critical": ["task-a"]},
        {"date": "2026-11-01", "critical": [], "bonus": None, "completed": [], "bonus_completed": False,
         "skipped": ["task-b"]}]))
    home = build_home({}, datetime(2026, 11, 1, 9, 0))
    assert home["welcome_back"] is True
    assert home["picks"] is None


def test_no_welcome_back_when_recent_rating(tmp_repo):
    _write(tmp_repo, "data/day-tracking.ndjson", _nd([{"date": "2026-10-31", "rating": 4, "health": {}}]))
    assert build_home({}, datetime(2026, 11, 1, 9, 0))["welcome_back"] is False


def test_broken_night_flag(tmp_repo):
    assert build_home({}, datetime(2026, 11, 1, 9, 0))["body"]["broken_night"] is True


def test_unbroken_night(tmp_repo):
    _write(tmp_repo, "data/day-tracking.ndjson",
           _nd([{"date": "2026-11-01", "health": {"sleep_hours": 7.5, "awake_minutes": 20}}]))
    body = build_home({}, datetime(2026, 11, 1, 9, 0))["body"]
    assert body == {"sleep_hours": 7.5, "awake_minutes": 20, "broken_night": False, "exercised": False,
                    "exercise_label": EXERCISE_LABEL, "exercised_days": 0, "exercise_light": "red", "window": 30}


def test_exercised_comes_from_the_exercise_habit_log(tmp_repo):
    _write(tmp_repo, "7-habits/_data/habits-daily.ndjson",
           _nd([{"habit_id": EXERCISE_HABIT_ID, "date": "2026-11-01", "completed": True}]))
    assert build_home({}, datetime(2026, 11, 1, 9, 0))["body"]["exercised"] is True


def test_values_visions_focus_and_anchor(tmp_repo):
    home = build_home({}, datetime(2026, 11, 1, 9, 0))
    assert home["values"] == ["Curiosity", "Kindness", "Adventure", "Community", "Craft"]
    assert home["visions"] == [{"id": "run-a-marathon", "title": "Run a marathon", "area": "health"}]
    assert home["vision_of_day"] == {"id": "run-a-marathon", "title": "Run a marathon", "value": "Craft"}
    assert [f["focus_id"] for f in home["focus"]] == ["f1"]
    assert home["anchors"] == [{"id": "g1", "title": "Example anchor"}]
    assert home["evening"] is False and home["date"] == "2026-11-01"


NOW = datetime(2026, 11, 1, 9, 0)
EVENING = datetime(2026, 11, 1, 19, 0)


def _frow(fid, title, status, weeks_red=0):
    return {"focus_id": fid, "title": title, "status": status, "weeks_red": weeks_red}


def _task(tid, **kw):
    base = {"id": tid, "status": "open", "description": tid, "impact": "B", "urgency": "B",
            "project": "none", "deadline": None, "created": "2026-10-01", "agent_doable": "no"}
    return {**base, **kw}


def _put_tasks(root, tasks):
    _write(root, "6-tasks/_data/tasks.ndjson", _nd(tasks))


@pytest.fixture
def no_focus():
    with patch.object(home_data, "status_rows", return_value=[]):
        yield


def test_focus_sorted_red_first(tmp_repo):
    rows = [_frow("g", "G", "green"), _frow("r", "R", "red"), _frow("y", "Y", "yellow")]
    with patch.object(home_data, "status_rows", return_value=rows):
        assert [f["focus_id"] for f in build_home({}, NOW)["focus"]] == ["r", "y", "g"]


def test_needs_you_caps_at_two_and_orders_deadline_email_focus(tmp_repo):
    _put_tasks(tmp_repo, [
        _task("task-email", source_email_thread_id="t1", priority="AA"),
        _task("task-dl", deadline="2026-11-02"),
    ])
    with patch.object(home_data, "status_rows", return_value=[_frow("r", "R", "red", 2)]):
        home = build_home({}, NOW)
    assert [n["kind"] for n in home["needs_you"]] == ["deadline", "email"]


def test_needs_you_focus_when_nothing_else(tmp_repo):
    _put_tasks(tmp_repo, [_task("task-far", deadline="2026-12-31")])
    with patch.object(home_data, "status_rows", return_value=[_frow("r", "R", "red", 2)]):
        home = build_home({}, NOW)
    assert home["needs_you"] == [{"kind": "focus", "id": "r", "title": "R", "why": "red for 2 weeks", "date": None}]


def test_needs_you_deadline_publishes_the_date_for_the_page_to_format(tmp_repo, no_focus):
    _put_tasks(tmp_repo, [_task("task-late", deadline="2026-10-30"), _task("task-soon", deadline="2026-11-02")])
    rows = build_home({}, NOW)["needs_you"]
    assert [(n["id"], n["why"], n["date"]) for n in rows] == [
        ("task-late", "overdue since", "2026-10-30"), ("task-soon", "due", "2026-11-02")]


def test_deferred_tasks_are_never_offered(tmp_repo, no_focus):
    _healthy_day(tmp_repo)
    _put_tasks(tmp_repo, [
        _task("task-parked", impact="A", urgency="A", deadline="2026-11-01", deferred=True),
        _task("task-parked-bot", agent_doable="yes", deferred=True),
        _task("task-live"),
        _task("task-bot", agent_doable="yes"),
    ])
    home = build_home({}, NOW)
    assert [t["id"] for t in home["suggested"]] == ["task-live"]
    assert [t["id"] for t in home["handoffs"]] == ["task-bot"]
    assert home["needs_you"] == []


def test_due_review_hidden_when_something_needs_you(tmp_repo):
    _write(tmp_repo, "data/review-ledger.ndjson", _nd([
        {"id": "habit-rate", "label": "Habit rates", "tier": "weekly", "cadence_days": 7, "last_done": "2026-01-01"}]))
    _put_tasks(tmp_repo, [_task("task-dl", deadline="2026-11-01")])
    with patch.object(home_data, "status_rows", return_value=[]):
        assert build_home({}, NOW)["due_review"] is None


def test_due_review_most_overdue_with_skill(tmp_repo, no_focus):
    _write(tmp_repo, "data/review-ledger.ndjson", _nd([
        {"id": "habit-rate", "label": "Habit rates", "tier": "weekly", "cadence_days": 7, "last_done": "2026-10-20"},
        {"id": "usage-audit", "label": "Usage audit", "tier": "monthly", "cadence_days": 30, "last_done": "2026-08-01"},
        {"id": "life-wheel", "label": "Life wheel", "tier": "monthly", "cadence_days": 30, "last_done": "2026-10-30"},
    ]))
    assert build_home({}, NOW)["due_review"] == {
        "id": "usage-audit", "label": "Usage audit", "skill": home_data.REVIEW_SKILLS["usage-audit"]}


def test_review_skills_cover_the_ledger_ids():
    assert "usage-audit" in home_data.REVIEW_SKILLS and len(home_data.REVIEW_SKILLS) == 21


def test_suggested_excludes_agent_doable_and_blocked(tmp_repo, no_focus):
    _put_tasks(tmp_repo, [
        _task("task-20261001-001", agent_doable="yes"),
        _task("task-20261001-002", depends_on=["task-20261001-003"]),
        _task("task-20261001-003"),
    ])
    ids = [t["id"] for t in build_home({}, NOW)["suggested"]]
    assert "task-20261001-001" not in ids
    assert "task-20261001-002" not in ids
    assert ids == ["task-20261001-003"]


def _healthy_day(root):
    """A continuous night and a row logged, so the day is not a one-pick day."""
    _write(root, "data/day-tracking.ndjson",
           _nd([{"date": "2026-11-01", "health": {"sleep_hours": 7.5, "awake_minutes": 20}}]))
    _write(root, "7-habits/_data/habits-daily.ndjson",
           _nd([{"habit_id": "morning-walk", "date": "2026-11-01", "completed": True}]))


def test_suggested_order(tmp_repo, no_focus):
    _healthy_day(tmp_repo)
    _put_tasks(tmp_repo, [
        _task("task-c", impact="A", urgency="B", created="2026-09-01"),
        _task("task-b", impact="A", urgency="A", deadline="2026-12-05"),
        _task("task-a", impact="A", urgency="A", deadline="2026-12-01"),
        _task("task-d", impact="C", urgency="C"),
    ])
    assert [t["id"] for t in build_home({}, NOW)["suggested"]] == ["task-a", "task-b", "task-c"]


def test_priority_field_outranks_impact_urgency(tmp_repo, no_focus):
    _put_tasks(tmp_repo, [_task("task-x", impact="C", urgency="C", priority="AA"),
                          _task("task-y", impact="A", urgency="B")])
    assert [t["id"] for t in build_home({}, NOW)["suggested"]][0] == "task-x"


def test_word_impacts_rank_like_letters(tmp_repo, no_focus):
    _healthy_day(tmp_repo)
    _put_tasks(tmp_repo, [_task("task-lo", impact="low", urgency="low"),
                          _task("task-hi", impact="high", urgency="high")])
    assert [t["id"] for t in build_home({}, NOW)["suggested"]] == ["task-hi", "task-lo"]


def test_no_eligible_tasks_gives_empty_suggested(tmp_repo, no_focus):
    _put_tasks(tmp_repo, [_task("task-1", agent_doable="yes")])
    home = build_home({}, NOW)
    assert home["suggested"] == []
    assert [h["id"] for h in home["handoffs"]] == ["task-1"]


def test_handoffs_cap_at_three(tmp_repo, no_focus):
    _put_tasks(tmp_repo, [_task(f"task-{i}", agent_doable="yes") for i in range(5)])
    assert len(build_home({}, NOW)["handoffs"]) == 3


def test_pick_date_is_tomorrow_in_evening(tmp_repo):
    assert build_home({}, datetime(2026, 11, 1, 19, 0))["pick_date"] == "2026-11-02"
    assert build_home({}, NOW)["pick_date"] == "2026-11-01"


def _chain_repo(root):
    _write(root, "3-visions/become-a-carpenter.md",
           VISION.format(slug="become-a-carpenter", area="career", status="active", title="Become a carpenter"))
    _write(root, "5-projects/_data/projects.ndjson", _nd([{"id": "proj-1", "vision": "become-a-carpenter"}]))
    _write(root, "4-focus/_data/focus.ndjson", _nd([
        {"id": "f-wood", "tier": "pursuit", "title": "Woodworking course", "impact": "high", "urgency": "high",
         "link": {"type": "vision", "ref": "become-a-carpenter"}, "habits": ["practice-guitar"],
         "retired_date": None, "parked": False}]))
    _write(root, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2026-11-02", "critical": ["task-wood", "task-orphan"], "bonus": "task-wood"}]))
    _put_tasks(root, [_task("task-wood", project="proj-1"), _task("task-orphan", project="none")])


def test_why_chain_from_task_to_value(tmp_repo):
    _chain_repo(tmp_repo)
    picks = build_home({}, datetime(2026, 11, 1, 19, 0))["tomorrow_picks"]
    assert picks["critical"][0]["why"] == ["Woodworking course", "Become a carpenter", "Craft"]
    assert picks["critical"][1]["why"] == []   # no project: the chain stops, nothing invented
    assert picks["bonus"]["id"] == "task-wood"


def test_picks_none_without_a_record(tmp_repo):
    assert build_home({}, NOW)["picks"] is None


def test_evening_keeps_todays_picks_and_adds_tomorrows(tmp_repo):
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2026-11-01", "critical": ["task-a"], "bonus": None, "completed": []},
        {"date": "2026-11-02", "critical": ["task-b"], "bonus": None}]))
    _put_tasks(tmp_repo, [_task("task-a"), _task("task-b")])
    evening = build_home({}, datetime(2026, 11, 1, 19, 0))
    assert [p["id"] for p in evening["picks"]["critical"]] == ["task-a"]
    assert [p["id"] for p in evening["tomorrow_picks"]["critical"]] == ["task-b"]
    morning = build_home({}, NOW)
    assert [p["id"] for p in morning["picks"]["critical"]] == ["task-a"]
    assert morning["tomorrow_picks"] is None


def test_evening_tomorrow_picks_none_without_a_record(tmp_repo):
    assert build_home({}, datetime(2026, 11, 1, 19, 0))["tomorrow_picks"] is None


def test_single_pick_is_false_when_picking_for_tomorrow(tmp_repo, no_focus):
    # The fixture's night is broken and there is no row, so today is a one-pick day,
    # but tomorrow's body is not known yet.
    _put_tasks(tmp_repo, [_task("task-a"), _task("task-b"), _task("task-c")])
    assert build_home({}, NOW)["single_pick"] is True
    evening = build_home({}, datetime(2026, 11, 1, 19, 0))
    assert evening["single_pick"] is False
    assert len(evening["suggested"]) == 3


def test_single_pick_on_broken_night_or_no_row(tmp_repo):
    assert build_home({}, NOW)["single_pick"] is True
    _write(tmp_repo, "data/day-tracking.ndjson",
           _nd([{"date": "2026-11-01", "health": {"sleep_hours": 7.5, "awake_minutes": 20}}]))
    _write(tmp_repo, "7-habits/_data/habits-daily.ndjson",
           _nd([{"habit_id": "morning-walk", "date": "2026-11-01", "completed": True}]))
    assert build_home({}, NOW)["single_pick"] is False


def test_offer_open_day_only_fri_sat_evening(tmp_repo):
    assert build_home({}, datetime(2026, 10, 30, 19, 0))["offer_open_day"] is True   # Friday
    assert build_home({}, datetime(2026, 10, 29, 19, 0))["offer_open_day"] is False  # Thursday
    assert build_home({}, datetime(2026, 10, 30, 9, 0))["offer_open_day"] is False   # Friday morning


def test_agent_doable_picks_are_dropped(tmp_repo):
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2026-11-01", "critical": ["task-bot", "task-me"], "bonus": "task-bot2"}]))
    _put_tasks(tmp_repo, [_task("task-bot", agent_doable="yes"), _task("task-me"),
                          _task("task-bot2", agent_doable="yes")])
    picks = build_home({}, NOW)["picks"]
    assert [p["id"] for p in picks["critical"]] == ["task-me"]
    assert picks["bonus"] is None


def test_why_falls_back_to_area_title_without_project(tmp_repo):
    _write(tmp_repo, "2-areas/career/statement.md", "# Career — Area Statement\n\ntext\n")
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2026-11-01", "critical": ["task-a", "task-b", "task-c"], "bonus": None}]))
    _put_tasks(tmp_repo, [_task("task-a", area="career"), _task("task-b", area="home-life"),
                          _task("task-c")])
    why = [p["why"] for p in build_home({}, NOW)["picks"]["critical"]]
    assert why == [["Career"], ["Home Life"], []]


def test_suggested_is_one_row_on_a_single_pick_day(tmp_repo, no_focus):
    _put_tasks(tmp_repo, [_task("task-a", impact="A", urgency="A"), _task("task-b"), _task("task-c")])
    home = build_home({}, NOW)
    assert home["single_pick"] is True
    assert [t["id"] for t in home["suggested"]] == ["task-a"]


def test_picks_carry_their_done_state(tmp_repo):
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2026-11-01", "critical": ["task-a", "task-b"], "bonus": "task-c",
         "completed": ["task-a"], "bonus_completed": True}]))
    _put_tasks(tmp_repo, [_task("task-a"), _task("task-b"), _task("task-c")])
    picks = build_home({}, NOW)["picks"]
    assert [p["done"] for p in picks["critical"]] == [True, False]
    assert picks["bonus"]["done"] is True


def test_pick_done_state_defaults_to_not_done(tmp_repo):
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2026-11-01", "critical": ["task-a"], "bonus": "task-c"}]))
    _put_tasks(tmp_repo, [_task("task-a"), _task("task-c")])
    picks = build_home({}, NOW)["picks"]
    assert picks["critical"][0]["done"] is False and picks["bonus"]["done"] is False


def _rate(hid, cadence="daily"):
    return {"habit_id": hid, "completed": 0, "target": 1, "skipped": 0, "rate": 0.0, "cadence": cadence, "light": "red"}


def _vfrow(fid, primary, supporting=(), parked=False, tier="pursuit", status="red", title=None):
    return {"focus_id": fid, "title": title or fid, "tier": tier, "status": status, "parked": parked,
            "weeks_red": 0, "primary": primary, "supporting": list(supporting)}


def test_habits_are_every_active_daily_and_monthly_habit(tmp_repo):
    _write(tmp_repo, "config/habit_schema.yaml",
           "daily_habits:\n"
           "  - id: practice-guitar\n    description: Play the guitar\n    frequency: 7\n    started: '2026-01-01'\n"
           "  - id: morning-walk\n    frequency: 3\n    started: '2026-01-01'\n    auto_derived: true\n"
           "  - id: old-one\n    frequency: 3\n    started: '2026-01-01'\n    active: false\n"
           "monthly_habits:\n  - id: deep-clean\n    frequency: 2\n    started: '2026-01-01'\n")
    _write(tmp_repo, "7-habits/_data/habits-daily.ndjson",
           _nd([{"habit_id": "practice-guitar", "date": "2026-10-31", "completed": True}]))
    _write(tmp_repo, "7-habits/_data/habits-monthly.ndjson",
           _nd([{"habit_id": "deep-clean", "month": "2026-10", "date": "2026-10-27", "completed": True}]))
    home = build_home({}, NOW)
    habits = {h["id"]: h for h in home["habits"]}
    assert set(habits) == {"practice-guitar", "morning-walk", "deep-clean"}
    assert habits["practice-guitar"] == {"id": "practice-guitar", "title": "Practice guitar", "description": "Play the guitar",
                                        "auto_derived": False, "cadence": "daily", "logged_today": False,
                                        "logged_yesterday": True}
    assert habits["morning-walk"]["auto_derived"] is True
    assert "show_monthly" not in home and "anchor_of_day" not in home


def _project_repo(root):
    _write(root, "3-visions/become-a-carpenter.md",
           VISION.format(slug="become-a-carpenter", area="career", status="active", title="Become a carpenter"))
    _write(root, "4-focus/_data/focus.ndjson", _nd([
        {"id": "f-wood", "tier": "pursuit", "title": "Woodworking course", "link": {"type": "vision", "ref": "become-a-carpenter"},
         "habits": ["practice-guitar"], "retired_date": None, "parked": False},
        {"id": "f-guitar", "tier": "foundation", "title": "Guitar", "habits": ["practice-guitar"],
         "retired_date": None, "parked": False},
        {"id": "f-book", "tier": "consuming", "title": "A book", "link": {"type": "vision", "ref": "become-a-carpenter"},
         "habits": [], "retired_date": None, "parked": False},
    ]))
    _write(root, "5-projects/_data/projects.ndjson", _nd([
        {"id": "proj-live", "name": "Build the workbench", "status": "active", "vision": "become-a-carpenter"},
        {"id": "proj-done", "name": "Old one", "status": "completed", "vision": "become-a-carpenter"},
        {"id": "proj-other", "name": "Unlinked", "status": "active"},
        {"id": "proj-direct", "name": "Learn a song", "status": "active", "focus": "f-guitar"},
    ]))


def test_active_project_sits_under_the_focus_whose_vision_it_serves(tmp_repo):
    _project_repo(tmp_repo)
    rows = [_vfrow("f-wood", None, title="Woodworking course"), _vfrow("f-guitar", None, tier="foundation", title="Guitar")]
    with patch.object(home_data, "status_rows", return_value=rows):
        focus = {f["focus_id"]: f for f in build_home({}, NOW)["focus"]}
    assert focus["f-wood"]["projects"] == [{"id": "proj-live", "name": "Build the workbench"}]
    assert focus["f-guitar"]["projects"] == [{"id": "proj-direct", "name": "Learn a song"}]


def test_focus_of_day_rotates_over_live_foundations_and_pursuits(tmp_repo):
    _project_repo(tmp_repo)
    rows = [_vfrow("f-wood", None, title="Woodworking course"), _vfrow("f-guitar", None, tier="foundation", title="Guitar"),
            _vfrow("f-book", None, tier="consuming", title="A book"),
            _vfrow("f-parked", None, parked=True, title="Parked")]
    with patch.object(home_data, "status_rows", return_value=rows):
        days = {build_home({}, datetime(2026, 11, d, 9, 0))["focus_of_day"]["id"] for d in (1, 2, 3, 4)}
        assert days == {"f-wood", "f-guitar"}
        picked = [build_home({}, datetime(2026, 11, d, 9, 0))["focus_of_day"] for d in (1, 2)]
    by_id = {p["id"]: p for p in picked}
    assert by_id["f-wood"] == {"id": "f-wood", "title": "Woodworking course", "vision": "Become a carpenter", "value": "Craft"}
    assert by_id["f-guitar"] == {"id": "f-guitar", "title": "Guitar", "vision": None, "value": None}


def test_focus_of_day_none_without_live_focuses(tmp_repo):
    with patch.object(home_data, "status_rows", return_value=[]):
        assert build_home({}, NOW)["focus_of_day"] is None


def _sync(tmp_path, text):
    log = tmp_path / "sync.log"
    log.write_text(text)
    return {"PFC_DAILY_SYNC_LOG": str(log)}


def test_daily_sync_ok_and_fresh(tmp_repo, tmp_path):
    env = _sync(tmp_path, "2026-11-01 05:00:01 START x\n2026-11-01 05:04:10 DONE ok=4 fail=0\n")
    assert build_home(env, NOW)["daily_sync"] == {"last_run": "2026-11-01T05:04:10", "ok": True, "stale": False}


def test_daily_sync_uses_the_last_done_line_and_fail_count(tmp_repo, tmp_path):
    env = _sync(tmp_path, "2026-10-31 05:04:10 DONE ok=4 fail=0\n2026-11-01 05:00:09 DONE ok=0 fail=1\n"
                          "2026-11-01 05:00:10 START trailing\n")
    assert build_home(env, NOW)["daily_sync"] == {"last_run": "2026-11-01T05:00:09", "ok": False, "stale": False}


def test_daily_sync_stale_after_30_hours(tmp_repo, tmp_path):
    env = _sync(tmp_path, "2026-10-31 03:00:00 DONE ok=4 fail=0\n")  # 30h before 9:00 AM
    assert build_home(env, NOW)["daily_sync"]["stale"] is False
    env = _sync(tmp_path, "2026-10-31 02:59:59 DONE ok=4 fail=0\n")
    assert build_home(env, NOW)["daily_sync"] == {"last_run": "2026-10-31T02:59:59", "ok": True, "stale": True}


def test_daily_sync_no_done_line_is_stale(tmp_repo, tmp_path):
    env = _sync(tmp_path, "2026-11-01 05:00:01 START x\n")
    assert build_home(env, NOW)["daily_sync"] == {"last_run": None, "ok": None, "stale": True}


def test_daily_sync_missing_log_is_stale(tmp_repo, tmp_path):
    env = {"PFC_DAILY_SYNC_LOG": str(tmp_path / "nope.log")}
    assert build_home(env, NOW)["daily_sync"] == {"last_run": None, "ok": None, "stale": True}


QUESTIONS_MD = """# Questions

Intro line.

## Current Questions

1. First question?
not a numbered line
2. Second question?
   continued indent line
3. Third question?

## Answered

1. Old one?
"""


def test_questions_parse_only_the_numbered_current_list(tmp_repo):
    _write(tmp_repo, "0-me/questions.md", QUESTIONS_MD)
    home = build_home({}, NOW)
    assert home["questions"] == [{"n": 1, "text": "First question?"}, {"n": 2, "text": "Second question?"},
                                 {"n": 3, "text": "Third question?"}]
    assert home["question_of_day"] in home["questions"]


def test_questions_empty_without_the_file(tmp_repo):
    home = build_home({}, NOW)
    assert home["questions"] == [] and home["question_of_day"] is None


def _wheel(date_, ratings, notes=None):
    return {"date": date_, "ratings": ratings, "notes": notes or {}, "logged_at": date_ + "T00:00:00-06:00"}


def test_areas_use_the_latest_row_red_first_with_labels_and_notes(tmp_repo):
    _write(tmp_repo, "2-areas/_data/life-wheel.ndjson", _nd([
        _wheel("2026-04-01", {"career": "red"}),
        _wheel("2026-10-20", {"career": "green", "family": "red", "living_room": "yellow"}, {"family": "More time"}),
    ]))
    areas = build_home({}, NOW)["areas"]
    assert areas["date"] == "2026-10-20" and areas["stale"] is False
    assert areas["rows"] == [
        {"key": "family", "label": "Family", "light": "red", "note": "More time"},
        {"key": "living_room", "label": "Living room", "light": "yellow", "note": None},
        {"key": "career", "label": "Career", "light": "green", "note": None},
    ]


def test_areas_take_the_later_row_when_two_share_the_newest_date(tmp_repo):
    # The same rule as pfc_writes.set_rating: newest date, then the later line.
    _write(tmp_repo, "2-areas/_data/life-wheel.ndjson", _nd([
        _wheel("2026-10-20", {"career": "red"}), _wheel("2026-10-20", {"career": "green"})]))
    assert build_home({}, NOW)["areas"]["rows"][0]["light"] == "green"


def test_areas_stale_when_older_than_31_days(tmp_repo):
    _write(tmp_repo, "2-areas/_data/life-wheel.ndjson", _nd([_wheel("2026-09-30", {"career": "green"})]))
    assert build_home({}, NOW)["areas"]["stale"] is True  # 32 days
    _write(tmp_repo, "2-areas/_data/life-wheel.ndjson", _nd([_wheel("2026-10-01", {"career": "green"})]))
    assert build_home({}, NOW)["areas"]["stale"] is False  # 31 days


def test_household_has_the_same_shape_and_a_missing_file_gives_no_rows(tmp_repo):
    assert build_home({}, NOW)["household"]["rows"] == []
    _write(tmp_repo, "2-areas/_data/household-status.ndjson",
           _nd([_wheel("2026-10-25", {"master_bathroom": "green", "car": "red"})]))
    household = build_home({}, NOW)["household"]
    assert household["date"] == "2026-10-25"
    assert [r["label"] for r in household["rows"]] == ["Car", "Master bathroom"]


def test_focuses_group_by_tier_with_light_projects_and_parked(tmp_repo):
    _project_repo(tmp_repo)
    rows = [_vfrow("f-wood", None, title="Woodworking course", status="green"),
            _vfrow("f-guitar", None, tier="foundation", title="Guitar", parked=True, status="parked"),
            _vfrow("f-book", None, tier="consuming", title="A book", status="yellow")]
    with patch.object(home_data, "status_rows", return_value=rows):
        focuses = build_home({}, NOW)["focuses"]
    assert [f["focus_id"] for f in focuses["pursuit"]] == ["f-wood"]
    assert [f["focus_id"] for f in focuses["foundation"]] == ["f-guitar"]
    assert [f["focus_id"] for f in focuses["consuming"]] == ["f-book"]
    wood = focuses["pursuit"][0]
    assert wood["light"] == "green" and wood["parked"] is False
    assert wood["projects"] == [{"id": "proj-live", "name": "Build the workbench"}]
    assert focuses["foundation"][0]["parked"] is True


def _pursuits(n, red_weeks_for=None, weeks=0):
    return [_vfrow(f"p{i}", None, status="red" if f"p{i}" == red_weeks_for else "green",
                   title=f"P{i}") | ({"weeks_red": weeks} if f"p{i}" == red_weeks_for else {}) for i in range(n)]


def test_repick_nudge_needs_six_pursuits_and_one_red_four_weeks(tmp_repo):
    with patch.object(home_data, "status_rows", return_value=_pursuits(6, "p0", 4)):
        assert build_home({}, NOW)["repick_nudge"] is True
    with patch.object(home_data, "status_rows", return_value=_pursuits(6, "p0", 3)):
        assert build_home({}, NOW)["repick_nudge"] is False
    with patch.object(home_data, "status_rows", return_value=_pursuits(5, "p0", 9)):
        assert build_home({}, NOW)["repick_nudge"] is False


def test_repick_nudge_ignores_parked_pursuits(tmp_repo):
    rows = _pursuits(6, "p0", 9)
    rows[5]["parked"] = True
    with patch.object(home_data, "status_rows", return_value=rows):
        assert build_home({}, NOW)["repick_nudge"] is False


def test_projects_active_and_other(tmp_repo):
    _put_tasks(tmp_repo, [_task("t-low", project="p-live", impact="C", urgency="C", description="Later step"),
                          _task("t-high", project="p-live", impact="A", urgency="A", description="First step"),
                          _task("t-done", project="p-live", status="done")])
    _write(tmp_repo, "5-projects/_data/projects.ndjson", _nd([
        {"id": "p-live", "name": "Live", "area": "career", "active": True, "total_parts": 4, "completed_parts": 1},
        {"id": "p-statused", "name": "Statused", "area": "career", "active": True, "status": "active",
         "total_parts": 0, "completed_parts": 0},
        {"id": "p-parked-active", "name": "Parked flag", "area": "career", "active": True, "status": "parked"},
        {"id": "p-ondeck", "name": "On deck", "area": "health", "active": False, "status": "on-deck"},
        {"id": "p-nostatus", "name": "No status", "area": "health", "active": False},
        {"id": "p-parked", "name": "Parked", "area": "health", "active": False, "status": "parked"},
        
        {"id": "p-done", "name": "Done", "area": "health", "active": False, "status": "done"},
        {"id": "p-dropped-active", "name": "Dropped A", "area": "health", "active": True, "status": "dropped"},
        {"id": "p-dropped", "name": "Dropped B", "area": "health", "active": False, "status": "dropped"},
    ]))
    projects = build_home({}, NOW)["projects"]
    assert projects["active"][0] == {"id": "p-live", "name": "Live", "area": "career", "status": "active", "pct": 25,
                                     "next_task": {"id": "t-high", "title": "First step"}}
    assert [p["id"] for p in projects["active"]] == ["p-live", "p-statused"]
    assert projects["active"][1]["pct"] == 0 and projects["active"][1]["next_task"] is None
    assert [p["id"] for p in projects["other"]] == ["p-ondeck", "p-nostatus", "p-parked-active", "p-parked"]
    assert projects["other"][1]["status"] == "on-deck"


def test_anchors_are_every_active_grounding_anchor(tmp_repo):
    assert build_home({}, NOW)["anchors"] == [{"id": "g1", "title": "Example anchor"}]


# --- pulse, trends, week, skipped suggestions ---------------------------------

def _days_back(n):
    from datetime import date, timedelta
    return (date(2026, 11, 1) - timedelta(days=n)).isoformat()


def _trend(home, name):
    return next(t for t in home["trends"] if t["name"] == name)


def _tracking(root, ratings):
    rows = [{"date": _days_back(i), "rating": r, "health": {"sleep_hours": 7.5, "awake_minutes": 5}}
            for i, r in enumerate(ratings)]
    _write(root, "data/day-tracking.ndjson", _nd(rows))


def test_pulse_is_the_pulse_builder_output(tmp_repo):
    _tracking(tmp_repo, [4, 4])
    pulse = build_home({}, NOW)["pulse"]
    assert {"levers", "verdict", "move"} <= set(pulse)
    assert pulse["levers"]


@pytest.mark.parametrize("ratings,light", [([4, 5], "green"), ([3, 4, 3, 4], "yellow"), ([2, 3, 3], "red")])
def test_day_rating_trend_thresholds(tmp_repo, ratings, light):
    _tracking(tmp_repo, ratings)
    t = _trend(build_home({}, NOW), "Day rating")
    assert t["light"] == light
    avg = round(sum(ratings) / len(ratings), 1)
    assert t["why"] == f"avg {avg} over {len(ratings)} rated days"


@pytest.mark.parametrize("done,light", [(7, "green"), (4, "yellow"), (3, "red")])
def test_picks_done_trend_thresholds(tmp_repo, done, light):
    ids = [f"t{i}" for i in range(10)]
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": _days_back(1), "critical": ids, "completed": ids[:done]}]))
    t = _trend(build_home({}, NOW), "Picks done")
    assert t["light"] == light and t["why"] == f"{done} of 10 critical picks done"


def test_body_counts_days_exercised_over_thirty(tmp_repo):
    _write(tmp_repo, "7-habits/_data/habits-daily.ndjson", _nd(
        [{"habit_id": "morning-walk", "date": _days_back(i), "completed": True} for i in range(1, 14)]
        + [{"habit_id": "morning-walk", "date": _days_back(60), "completed": True}]))
    body = build_home({}, NOW)["body"]
    assert body["exercised_days"] == 13 and body["window"] == 30 and body["exercise_light"] == "green"


def test_pulse_levers_carry_nights_on_target(tmp_repo):
    _tracking(tmp_repo, [4] * 30)
    levers = build_home({}, NOW)["pulse"]["levers"]
    assert all("on" in lv and "n" in lv for lv in levers)
    assert any(lv["n"] == 30 for lv in levers)


def test_trends_are_outcomes_only_and_sort_red_first(tmp_repo):
    rows = [{"date": _days_back(i), "rating": 5, "energy": 2, "mood": 3, "focus": 4} for i in range(3)]
    _write(tmp_repo, "data/day-tracking.ndjson", _nd(rows))
    trends = build_home({}, NOW)["trends"]
    assert {t["name"] for t in trends} == {"Day rating", "Energy", "Mood", "Focus", "Picks done"}
    by = {t["name"]: t["light"] for t in trends}
    assert by["Energy"] == "red" and by["Mood"] == "yellow" and by["Focus"] == "green"
    order = [{"red": 0, "yellow": 1, "green": 2}[t["light"]] for t in trends]
    assert order == sorted(order)


def test_week_lists_next_seven_days_from_the_cache(tmp_repo):
    _write(tmp_repo, "data/calendar-cache.json", json.dumps({"fetched_at": "2026-11-01T06:00:00-07:00", "events": [
        {"id": "a", "summary": "Dentist visit", "start": {"dateTime": "2026-11-03T14:30:00-07:00"},
         "end": {"dateTime": "2026-11-03T15:30:00-07:00"}},
        {"id": "b", "summary": "Zorp festival", "start": {"date": "2026-11-02"}, "end": {"date": "2026-11-04"}},
        {"id": "c", "summary": "Too far away", "start": {"dateTime": "2026-11-20T09:00:00-07:00"},
         "end": {"dateTime": "2026-11-20T10:00:00-07:00"}},
    ]}))
    week = build_home({}, NOW)["week"]
    assert [d["date"] for d in week] == [_days_back(-i) for i in range(7)]
    by = {d["date"]: d["events"] for d in week}
    assert by["2026-11-03"] == [{"start": None, "title": "Zorp festival"},
                                {"start": "2026-11-03T14:30:00-07:00", "title": "Dentist visit"}]
    assert by["2026-11-02"] == [{"start": None, "title": "Zorp festival"}]
    assert by["2026-11-04"] == []


def test_week_empty_without_the_cache(tmp_repo):
    assert build_home({}, NOW)["week"] == []


def test_skipped_pick_is_left_out_of_that_days_suggestions_only(tmp_repo, no_focus):
    _healthy_day(tmp_repo)
    _put_tasks(tmp_repo, [_task("task-a", impact="A", urgency="A"), _task("task-b", impact="B", urgency="B")])
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson",
           _nd([{"date": "2026-11-01", "critical": [], "skipped": ["task-a"]}]))
    assert [t["id"] for t in build_home({}, NOW)["suggested"]] == ["task-b"]
    # From the evening the suggestions are for tomorrow, which skipped nothing.
    assert [t["id"] for t in build_home({}, EVENING)["suggested"]] == ["task-a", "task-b"]


def test_tomorrows_skipped_list_filters_tomorrows_suggestions(tmp_repo, no_focus):
    _healthy_day(tmp_repo)
    _put_tasks(tmp_repo, [_task("task-a", impact="A", urgency="A"), _task("task-b")])
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson",
           _nd([{"date": "2026-11-02", "critical": [], "skipped": ["task-a"]}]))
    assert [t["id"] for t in build_home({}, EVENING)["suggested"]] == ["task-b"]
    assert "tomorrow_suggested" not in build_home({}, NOW)


def test_all_picks_done_when_every_critical_pick_is_completed(tmp_repo, no_focus):
    _healthy_day(tmp_repo)
    _put_tasks(tmp_repo, [_task("task-a", status="done"), _task("task-b", status="done"),
                          _task("task-c", impact="A", urgency="A"), _task("task-d")])
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2026-11-01", "critical": ["task-a", "task-b"], "bonus": "task-d", "completed": ["task-a", "task-b"]}]))
    home = build_home({}, NOW)
    assert home["all_picks_done"] is True
    # The record's own ids, so Set can send them back unchanged with the new ones.
    assert home["picks"]["critical_ids"] == ["task-a", "task-b"] and home["picks"]["bonus_id"] == "task-d"
    # Suggestions stay filled for today, without today's own bonus.
    assert [t["id"] for t in home["suggested"]] == ["task-c"]


def test_all_picks_done_is_false_with_an_open_pick_or_no_picks(tmp_repo, no_focus):
    _put_tasks(tmp_repo, [_task("task-a", status="done"), _task("task-b")])
    assert build_home({}, NOW)["all_picks_done"] is False  # no record
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2026-11-01", "critical": ["task-a", "task-b"], "completed": ["task-a"]}]))
    assert build_home({}, NOW)["all_picks_done"] is False
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2026-11-01", "critical": [], "skipped": ["task-b"]}]))
    assert build_home({}, NOW)["all_picks_done"] is False  # a skip-only record has no picks


def _tour(tmp_repo, areas_fresh=True):
    if areas_fresh:
        _write(tmp_repo, "2-areas/_data/life-wheel.ndjson", _nd([{"date": "2026-10-30", "ratings": {"health": "green"}}]))


def test_tour_look_prefers_stale_areas(tmp_repo):
    look = build_home({}, NOW)["tour_look"]
    assert look == {"kind": "stale_areas", "title": "Life wheel", "detail": "never rated", "date": None}
    _write(tmp_repo, "2-areas/_data/life-wheel.ndjson", _nd([_wheel("2026-06-03", {"career": "green"})]))
    # The date travels as a field; the page formats it.
    look = build_home({}, NOW)["tour_look"]
    assert look == {"kind": "stale_areas", "title": "Life wheel", "detail": "last rated", "date": "2026-06-03"}


def test_tour_look_red_focus_when_areas_fresh(tmp_repo):
    _tour(tmp_repo)
    with patch.object(home_data, "status_rows", return_value=[{**_frow("f1", "Guitar", "red", 3), "tier": "pursuit"}]):
        look = build_home({}, NOW)["tour_look"]
    assert look["kind"] == "red_focus" and look["title"] == "Guitar"


def test_tour_look_stalled_project_then_none(tmp_repo, no_focus):
    _tour(tmp_repo)
    _write(tmp_repo, "5-projects/_data/projects.ndjson", _nd([
        {"id": "p1", "name": "Stalled one", "area": "career", "active": True, "started": "2026-09-01"}]))
    look = build_home({}, NOW)["tour_look"]
    assert look["kind"] == "stalled_project" and look["title"] == "Stalled one"
    _write(tmp_repo, "5-projects/_data/projects.ndjson", _nd([
        {"id": "p1", "name": "Fresh", "area": "career", "active": True, "started": "2026-10-30"}]))
    assert build_home({}, NOW)["tour_look"] is None
