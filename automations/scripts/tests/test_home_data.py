"""Unit tests for home_data: the data behind the one-page web UI."""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from automations.scripts import home_data
from automations.scripts.home_data import build_home, rate_target_date, rotate


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
created: 2025-06-02
---

# {title}

## Why it matters

Serves **Creativity**, **Growth**. Also **Guitar** is not a value.
"""


@pytest.fixture
def tmp_repo(tmp_path):
    _write(tmp_path, "1-values/values.md",
           "# Top Values\n\n1. Curiosity\n2. Courage\n3. Kindness\n4. Health\n5. Growth\n")
    _write(tmp_path, "3-visions/run-a-marathon.md",
           VISION.format(slug="run-a-marathon", area="recreation", status="active", title="Run a marathon"))
    _write(tmp_path, "3-visions/paused-one.md",
           VISION.format(slug="paused-one", area="career", status="paused", title="Paused"))
    _write(tmp_path, "3-visions/_template.md", "---\nstatus: active\n---\n# Template\n")
    _write(tmp_path, "3-visions/README.md", "# Visions\n")
    _write(tmp_path, "3-visions/AGENTS.md", "# Agents\n")
    _write(tmp_path, "config/habit_schema.yaml",
           "daily_habits:\n  - id: practice-guitar\n    frequency: 7\n    started: '2025-01-02'\n"
           "  - id: morning-walk\n    frequency: 3\n    started: '2025-01-02'\nmonthly_habits: []\n")
    _write(tmp_path, "4-focus/_data/focus.ndjson", _nd([
        {"id": "f1", "tier": "pursuit", "title": "Guitar", "impact": "medium", "urgency": "medium",
         "habits": ["practice-guitar"], "retired_date": None, "parked": False},
    ]))
    _write(tmp_path, "7-habits/_data/habits-daily.ndjson", "")
    _write(tmp_path, "7-habits/_data/habits-monthly.ndjson", "")
    _write(tmp_path, "data/grounding.ndjson", _nd([
        {"id": "g1", "title": "Rest before you are tired", "status": "active", "retired_date": None},
        {"id": "g2", "title": "Old", "status": "retired", "retired_date": "2025-01-02"},
    ]))
    _write(tmp_path, "6-tasks/_data/daily-focus.ndjson", _nd([{"date": "2025-10-19", "critical": []}]))
    _write(tmp_path, "data/day-tracking.ndjson", _nd([
        {"date": "2025-09-05", "rating": 4, "health": {}},
        {"date": "2025-11-02", "rating": None,
         "health": {"sleep_hours": 7.2, "awake_minutes": 75}},
    ]))
    from automations.scripts import trello_render, trmnl_push
    with patch.object(home_data, "REPO", tmp_path), patch.object(trmnl_push, "REPO_ROOT", tmp_path), \
            patch.object(trello_render, "REPO_ROOT", tmp_path):
        yield tmp_path


def test_rate_target_before_evening_is_yesterday():
    assert rate_target_date(datetime(2025, 11, 2, 17, 59)) == "2025-11-01"


def test_rate_target_in_evening_is_today():
    assert rate_target_date(datetime(2025, 11, 2, 18, 0)) == "2025-11-02"


def test_rate_target_just_after_midnight_is_yesterday():
    assert rate_target_date(datetime(2025, 11, 3, 0, 5)) == "2025-11-02"


def test_rotate_changes_daily_and_is_stable():
    items = ["a", "b", "c"]
    assert rotate(items, "2025-11-02") == rotate(items, "2025-11-02")
    assert rotate(items, "2025-11-02") != rotate(items, "2025-11-03")


def test_rotate_empty_is_none():
    assert rotate([], "2025-11-02") is None


def test_rated_day_is_not_unrated(tmp_repo):
    _write(tmp_repo, "data/day-tracking.ndjson", _nd([{"date": "2025-11-02", "rating": 4, "health": {}}]))
    assert build_home({}, datetime(2025, 11, 3, 9, 0))["rate_target"] == {"date": "2025-11-02", "unrated": False}


def test_unrated_day_is_unrated(tmp_repo):
    assert build_home({}, datetime(2025, 11, 2, 19, 0))["rate_target"] == {"date": "2025-11-02", "unrated": True}


def test_welcome_back_when_rating_and_picks_both_older_than_yesterday(tmp_repo):
    _write(tmp_repo, "data/day-tracking.ndjson", _nd([{"date": "2025-09-05", "rating": 4, "health": {}}]))
    assert build_home({}, datetime(2025, 11, 2, 9, 0))["welcome_back"] is True


def test_a_skip_only_record_is_not_a_pick_day(tmp_repo):
    _write(tmp_repo, "data/day-tracking.ndjson", _nd([{"date": "2025-09-05", "rating": 4, "health": {}}]))
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2025-10-19", "critical": ["task-a"]},
        {"date": "2025-11-02", "critical": [], "bonus": None, "completed": [], "bonus_completed": False,
         "skipped": ["task-b"]}]))
    home = build_home({}, datetime(2025, 11, 2, 9, 0))
    assert home["welcome_back"] is True
    assert home["picks"] is None


def test_no_welcome_back_when_recent_rating(tmp_repo):
    _write(tmp_repo, "data/day-tracking.ndjson", _nd([{"date": "2025-11-01", "rating": 4, "health": {}}]))
    assert build_home({}, datetime(2025, 11, 2, 9, 0))["welcome_back"] is False


def test_broken_night_flag(tmp_repo):
    assert build_home({}, datetime(2025, 11, 2, 9, 0))["body"]["broken_night"] is True


def test_unbroken_night(tmp_repo):
    _write(tmp_repo, "data/day-tracking.ndjson",
           _nd([{"date": "2025-11-02", "health": {"sleep_hours": 7.5, "awake_minutes": 20}}]))
    body = build_home({}, datetime(2025, 11, 2, 9, 0))["body"]
    assert body == {"sleep_hours": 7.5, "awake_minutes": 20, "broken_night": False, "window": 30}


def test_values_visions_focus_and_anchor(tmp_repo):
    home = build_home({}, datetime(2025, 11, 2, 9, 0))
    assert home["values"] == ["Curiosity", "Courage", "Kindness", "Health", "Growth"]
    assert home["visions"] == [{"id": "run-a-marathon", "title": "Run a marathon", "area": "recreation"}]
    assert home["vision_of_day"] == {"id": "run-a-marathon", "title": "Run a marathon", "value": "Growth"}
    assert [f["focus_id"] for f in home["focus"]] == ["f1"]
    assert home["anchors"] == [{"id": "g1", "title": "Rest before you are tired"}]
    assert home["evening"] is False and home["date"] == "2025-11-02"


NOW = datetime(2025, 11, 2, 9, 0)
EVENING = datetime(2025, 11, 2, 19, 0)


def _frow(fid, title, status, weeks_red=0):
    return {"focus_id": fid, "title": title, "status": status, "weeks_red": weeks_red}


def _task(tid, **kw):
    base = {"id": tid, "status": "open", "description": tid, "impact": "B", "urgency": "B",
            "project": "none", "deadline": None, "created": "2025-10-02", "agent_doable": "no"}
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
        _task("task-dl", deadline="2025-11-03"),
    ])
    with patch.object(home_data, "status_rows", return_value=[_frow("r", "R", "red", 2)]):
        home = build_home({}, NOW)
    assert [n["kind"] for n in home["needs_you"]] == ["deadline", "email"]


def test_needs_you_focus_when_nothing_else(tmp_repo):
    _put_tasks(tmp_repo, [_task("task-far", deadline="2026-01-01")])
    with patch.object(home_data, "status_rows", return_value=[_frow("r", "R", "red", 2)]):
        home = build_home({}, NOW)
    assert home["needs_you"] == [{"kind": "focus", "id": "r", "title": "R", "why": "red for 2 weeks", "date": None,
                                  "in_picks": None}]


def test_needs_you_deadline_publishes_the_date_for_the_page_to_format(tmp_repo, no_focus):
    _put_tasks(tmp_repo, [_task("task-late", deadline="2025-10-31"), _task("task-soon", deadline="2025-11-03")])
    rows = build_home({}, NOW)["needs_you"]
    assert [(n["id"], n["why"], n["date"]) for n in rows] == [
        ("task-late", "overdue since", "2025-10-31"), ("task-soon", "due", "2025-11-03")]


def test_deferred_tasks_are_never_offered(tmp_repo, no_focus):
    _healthy_day(tmp_repo)
    _put_tasks(tmp_repo, [
        _task("task-parked", impact="A", urgency="A", deadline="2025-11-02", deferred=True),
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
        {"id": "habit-rate", "label": "Habit rates", "tier": "weekly", "cadence_days": 7, "last_done": "2025-01-02"}]))
    _put_tasks(tmp_repo, [_task("task-dl", deadline="2025-11-02")])
    with patch.object(home_data, "status_rows", return_value=[]):
        assert build_home({}, NOW)["due_review"] is None


def test_due_review_most_overdue_with_skill(tmp_repo, no_focus):
    _write(tmp_repo, "data/review-ledger.ndjson", _nd([
        {"id": "habit-rate", "label": "Habit rates", "tier": "weekly", "cadence_days": 7, "last_done": "2025-10-21"},
        {"id": "usage-audit", "label": "Usage audit", "tier": "monthly", "cadence_days": 30, "last_done": "2025-08-02"},
        {"id": "life-wheel", "label": "Life wheel", "tier": "monthly", "cadence_days": 30, "last_done": "2025-10-31"},
    ]))
    assert build_home({}, NOW)["due_review"] == {
        "id": "usage-audit", "label": "Usage audit", "skill": home_data.REVIEW_SKILLS["usage-audit"]}


def test_reviews_due_counts_every_due_review_even_when_something_needs_you(tmp_repo, no_focus):
    _write(tmp_repo, "data/review-ledger.ndjson", _nd([
        {"id": "habit-rate", "label": "Habit rates", "cadence_days": 7, "last_done": "2025-10-21"},
        {"id": "usage-audit", "label": "Usage audit", "cadence_days": 30, "last_done": None},
        {"id": "life-wheel", "label": "Life wheel", "cadence_days": 30, "last_done": "2025-10-31"},
    ]))
    _put_tasks(tmp_repo, [_task("task-due", deadline="2025-11-02")])
    home = build_home({}, NOW)
    assert home["due_review"] is None and home["reviews_due"] == 2


def test_review_skills_cover_the_ledger_ids():
    assert "usage-audit" in home_data.REVIEW_SKILLS and len(home_data.REVIEW_SKILLS) == 21


def test_suggested_excludes_agent_doable_and_blocked(tmp_repo, no_focus):
    _put_tasks(tmp_repo, [
        _task("task-20251002-001", agent_doable="yes"),
        _task("task-20251002-002", depends_on=["task-20251002-003"]),
        _task("task-20251002-003"),
    ])
    ids = [t["id"] for t in build_home({}, NOW)["suggested"]]
    assert "task-20251002-001" not in ids
    assert "task-20251002-002" not in ids
    assert ids == ["task-20251002-003"]


def _healthy_day(root):
    """A continuous night and a walk logged."""
    _write(root, "data/day-tracking.ndjson",
           _nd([{"date": "2025-11-02", "health": {"sleep_hours": 7.5, "awake_minutes": 20}}]))
    _write(root, "7-habits/_data/habits-daily.ndjson",
           _nd([{"habit_id": "morning-walk", "date": "2025-11-02", "completed": True}]))


def test_suggested_order(tmp_repo, no_focus):
    _healthy_day(tmp_repo)
    _put_tasks(tmp_repo, [
        _task("task-c", impact="A", urgency="B", created="2025-09-02"),
        _task("task-b", impact="A", urgency="A", deadline="2025-12-06"),
        _task("task-a", impact="A", urgency="A", deadline="2025-12-02"),
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
    assert build_home({}, datetime(2025, 11, 2, 19, 0))["pick_date"] == "2025-11-03"
    assert build_home({}, NOW)["pick_date"] == "2025-11-02"


def _chain_repo(root):
    _write(root, "3-visions/become-data-analyst.md",
           VISION.format(slug="become-data-analyst", area="career", status="active", title="Become a data analyst"))
    _write(root, "5-projects/_data/projects.ndjson", _nd([{"id": "proj-1", "vision": "become-data-analyst"}]))
    _write(root, "4-focus/_data/focus.ndjson", _nd([
        {"id": "f-ai", "tier": "pursuit", "title": "Data analysis course", "impact": "high", "urgency": "high",
         "link": {"type": "vision", "ref": "become-data-analyst"}, "habits": ["practice-guitar"],
         "retired_date": None, "parked": False}]))
    _write(root, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2025-11-03", "critical": ["task-ai", "task-orphan"], "bonus": "task-ai"}]))
    _put_tasks(root, [_task("task-ai", project="proj-1"), _task("task-orphan", project="none")])


def test_why_chain_from_task_to_value(tmp_repo):
    _chain_repo(tmp_repo)
    picks = build_home({}, datetime(2025, 11, 2, 19, 0))["tomorrow_picks"]
    assert picks["critical"][0]["why"] == ["Data analysis course", "Become a data analyst", "Growth"]
    assert picks["critical"][1]["why"] == []   # no project: the chain stops, nothing invented
    assert picks["bonus"]["id"] == "task-ai"


def test_picks_none_without_a_record(tmp_repo):
    assert build_home({}, NOW)["picks"] is None


def test_evening_keeps_todays_picks_and_adds_tomorrows(tmp_repo):
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2025-11-02", "critical": ["task-a"], "bonus": None, "completed": []},
        {"date": "2025-11-03", "critical": ["task-b"], "bonus": None}]))
    _put_tasks(tmp_repo, [_task("task-a"), _task("task-b")])
    evening = build_home({}, datetime(2025, 11, 2, 19, 0))
    assert [p["id"] for p in evening["picks"]["critical"]] == ["task-a"]
    assert [p["id"] for p in evening["tomorrow_picks"]["critical"]] == ["task-b"]
    morning = build_home({}, NOW)
    assert [p["id"] for p in morning["picks"]["critical"]] == ["task-a"]
    assert morning["tomorrow_picks"] is None


def test_evening_tomorrow_picks_none_without_a_record(tmp_repo):
    assert build_home({}, datetime(2025, 11, 2, 19, 0))["tomorrow_picks"] is None


def test_a_broken_night_with_no_row_still_suggests_a_full_2_plus_1(tmp_repo, no_focus):
    # The home page always offers a full 2+1, even after a broken night.
    _put_tasks(tmp_repo, [_task("task-a"), _task("task-b"), _task("task-c"), _task("task-d")])
    home = build_home({}, NOW)
    assert home["body"]["broken_night"] is True
    assert len(home["suggested"]) == 3
    assert "single_pick" not in home


def test_offer_open_day_only_fri_sat_evening(tmp_repo):
    assert build_home({}, datetime(2025, 10, 31, 19, 0))["offer_open_day"] is True   # Friday
    assert build_home({}, datetime(2025, 10, 30, 19, 0))["offer_open_day"] is False  # Thursday
    assert build_home({}, datetime(2025, 10, 31, 9, 0))["offer_open_day"] is False   # Friday morning


def test_agent_doable_picks_are_dropped(tmp_repo):
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2025-11-02", "critical": ["task-bot", "task-me"], "bonus": "task-bot2"}]))
    _put_tasks(tmp_repo, [_task("task-bot", agent_doable="yes"), _task("task-me"),
                          _task("task-bot2", agent_doable="yes")])
    picks = build_home({}, NOW)["picks"]
    assert [p["id"] for p in picks["critical"]] == ["task-me"]
    assert picks["bonus"] is None


def test_why_falls_back_to_area_title_without_project(tmp_repo):
    _write(tmp_repo, "2-areas/career/statement.md", "# Career — Area Statement\n\ntext\n")
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2025-11-02", "critical": ["task-a", "task-b", "task-c"], "bonus": None}]))
    _put_tasks(tmp_repo, [_task("task-a", area="career"), _task("task-b", area="side-projects"),
                          _task("task-c")])
    why = [p["why"] for p in build_home({}, NOW)["picks"]["critical"]]
    assert why == [["Career"], ["Side Projects"], []]


def test_picks_carry_their_done_state(tmp_repo):
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2025-11-02", "critical": ["task-a", "task-b"], "bonus": "task-c",
         "completed": ["task-a"], "bonus_completed": True}]))
    _put_tasks(tmp_repo, [_task("task-a"), _task("task-b"), _task("task-c")])
    picks = build_home({}, NOW)["picks"]
    assert [p["done"] for p in picks["critical"]] == [True, False]
    assert picks["bonus"]["done"] is True


def test_pick_done_state_defaults_to_not_done(tmp_repo):
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2025-11-02", "critical": ["task-a"], "bonus": "task-c"}]))
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
           "  - id: practice-guitar\n    description: Play the guitar\n    frequency: 7\n    started: '2025-01-02'\n"
           "  - id: morning-walk\n    frequency: 3\n    started: '2025-01-02'\n    auto_derived: true\n"
           "  - id: old-one\n    frequency: 3\n    started: '2025-01-02'\n    active: false\n"
           "monthly_habits:\n  - id: social-time\n    frequency: 2\n    started: '2025-01-02'\n")
    _write(tmp_repo, "7-habits/_data/habits-daily.ndjson",
           _nd([{"habit_id": "practice-guitar", "date": "2025-11-01", "completed": True}]))
    _write(tmp_repo, "7-habits/_data/habits-monthly.ndjson",
           _nd([{"habit_id": "social-time", "month": "2025-10", "date": "2025-10-28", "completed": True}]))
    home = build_home({}, NOW)
    habits = {h["id"]: h for h in home["habits"]}
    assert set(habits) == {"practice-guitar", "morning-walk", "social-time"}
    assert habits["practice-guitar"] == {"id": "practice-guitar", "title": "Practice guitar", "description": "Play the guitar",
                                        "auto_derived": False, "cadence": "daily", "logged_today": False,
                                        "logged_yesterday": True, "title_plain": "Practice guitar"}
    assert habits["morning-walk"]["auto_derived"] is True
    assert "show_monthly" not in home and "anchor_of_day" not in home


def _project_repo(root):
    _write(root, "3-visions/become-data-analyst.md",
           VISION.format(slug="become-data-analyst", area="career", status="active", title="Become a data analyst"))
    _write(root, "4-focus/_data/focus.ndjson", _nd([
        {"id": "f-ai", "tier": "pursuit", "title": "Data course", "link": {"type": "vision", "ref": "become-data-analyst"},
         "habits": ["practice-guitar"], "retired_date": None, "parked": False},
        {"id": "f-guitar", "tier": "foundation", "title": "Guitar", "habits": ["practice-guitar"],
         "retired_date": None, "parked": False},
        {"id": "f-book", "tier": "consuming", "title": "A book", "link": {"type": "vision", "ref": "become-data-analyst"},
         "habits": [], "retired_date": None, "parked": False},
    ]))
    _write(root, "5-projects/_data/projects.ndjson", _nd([
        {"id": "proj-live", "name": "Ship the dashboard", "status": "active", "vision": "become-data-analyst"},
        {"id": "proj-done", "name": "Old one", "status": "completed", "vision": "become-data-analyst"},
        {"id": "proj-other", "name": "Unlinked", "status": "active"},
        {"id": "proj-direct", "name": "Learn a song", "status": "active", "focus": "f-guitar"},
    ]))


def test_active_project_sits_under_the_focus_whose_vision_it_serves(tmp_repo):
    _project_repo(tmp_repo)
    rows = [_vfrow("f-ai", None, title="Data course"), _vfrow("f-guitar", None, tier="foundation", title="Guitar")]
    with patch.object(home_data, "status_rows", return_value=rows):
        focus = {f["focus_id"]: f for f in build_home({}, NOW)["focus"]}
    assert focus["f-ai"]["projects"] == [{"id": "proj-live", "name": "Ship the dashboard"}]
    assert focus["f-guitar"]["projects"] == [{"id": "proj-direct", "name": "Learn a song"}]


def test_focus_of_day_rotates_over_live_foundations_and_pursuits(tmp_repo):
    _project_repo(tmp_repo)
    rows = [_vfrow("f-ai", None, title="Data course"), _vfrow("f-guitar", None, tier="foundation", title="Guitar"),
            _vfrow("f-book", None, tier="consuming", title="A book"),
            _vfrow("f-parked", None, parked=True, title="Parked")]
    with patch.object(home_data, "status_rows", return_value=rows):
        days = {build_home({}, datetime(2025, 11, d, 9, 0))["focus_of_day"]["id"] for d in (1, 2, 3, 4)}
        assert days == {"f-ai", "f-guitar"}
        picked = [build_home({}, datetime(2025, 11, d, 9, 0))["focus_of_day"] for d in (1, 2)]
    by_id = {p["id"]: p for p in picked}
    assert by_id["f-ai"] == {"id": "f-ai", "title": "Data course", "vision": "Become a data analyst", "value": "Growth"}
    assert by_id["f-guitar"] == {"id": "f-guitar", "title": "Guitar", "vision": None, "value": None}


def test_focus_of_day_none_without_live_focuses(tmp_repo):
    with patch.object(home_data, "status_rows", return_value=[]):
        assert build_home({}, NOW)["focus_of_day"] is None


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


def test_area_why_names_the_items_behind_the_colour():
    items = [{"title": "Sleep", "light": "red", "weight": 3, "why": "on target 5 of 30"},
             {"title": "Stretch", "light": "red", "weight": 2, "why": "2 of 30"},
             {"title": "Walk", "light": "green", "weight": 1, "why": "fine"}]
    assert home_data._area_why({"source": "items", "light": "red", "items": items}) == \
        "Sleep: on target 5 of 30; Stretch: 2 of 30"
    assert home_data._area_why({"source": "items", "light": "green", "items": items}) == "every item on track"
    assert home_data._area_why({"source": "manual", "light": "red", "note": "More time", "items": []}) == "More time"


def test_areas_use_the_latest_row_red_first_with_labels_and_notes(tmp_repo):
    _write(tmp_repo, "2-areas/_data/life-wheel.ndjson", _nd([
        _wheel("2025-04-02", {"career": "red"}),
        _wheel("2025-10-21", {"career": "green", "pets": "red", "den": "yellow"}, {"pets": "More time"}),
    ]))
    areas = build_home({}, NOW)["areas"]
    assert areas["date"] == "2025-10-21" and areas["stale"] is False
    # No area items: every row is its manual light, unchanged.
    manual = {"manual": None, "source": "manual", "hours": None, "items": []}
    assert areas["rows"] == [
        {**manual, "key": "pets", "label": "Pets", "light": "red", "manual": "red", "note": "More time", "why": "More time"},
        {**manual, "key": "den", "label": "Den", "light": "yellow", "manual": "yellow", "note": None, "why": "set by hand"},
        {**manual, "key": "career", "label": "Career", "light": "green", "manual": "green", "note": None, "why": "set by hand"},
    ]
    assert build_home({}, NOW)["plate"] is None


def _area_item(id_, area, weight=3, **kw):
    return {"id": id_, "area": area, "title": id_, "kind": "time", "weight": weight, "hours": 2,
            "question": "Going well?", "active": True, **kw}


def test_area_items_light_their_area_and_fill_the_plate(tmp_repo):
    _write(tmp_repo, "2-areas/_data/life-wheel.ndjson", _nd([_wheel("2025-10-21", {"career": "green", "pets": "green"})]))
    _write(tmp_repo, "2-areas/_data/area-items.ndjson", _nd([
        _area_item("item-career-job", "career", hours=40),
        _area_item("item-health-sleep", "health", hours=56, source="fitbit:sleep", question=None),
    ]).replace(', "question": null', ""))
    _write(tmp_repo, "2-areas/_data/area-checkins.ndjson",
           _nd([{"date": "2025-10-31", "item_id": "item-career-job", "answer": "rough"}]))
    home = build_home({}, NOW)
    rows = {r["key"]: r for r in home["areas"]["rows"]}
    assert rows["career"]["light"] == "red" and rows["career"]["manual"] == "green"
    assert rows["career"]["source"] == "items" and rows["career"]["hours"] == 40
    assert rows["pets"]["source"] == "manual"
    assert [r["key"] for r in home["areas"]["rows"]][0] == "career"  # red first
    assert home["areas"]["date"] == "2025-10-31"  # the newest check-in is newer than the wheel
    assert home["plate"]["free"] == 112 and home["plate"]["committed"] == 40 and home["plate"]["light"] == "green"


def test_a_recent_check_in_keeps_the_areas_band_fresh(tmp_repo):
    _write(tmp_repo, "2-areas/_data/life-wheel.ndjson", _nd([_wheel("2025-08-02", {"career": "green"})]))
    _write(tmp_repo, "2-areas/_data/area-items.ndjson", _nd([_area_item("item-career-job", "career")]))
    assert build_home({}, NOW)["areas"]["stale"] is True
    _write(tmp_repo, "2-areas/_data/area-checkins.ndjson",
           _nd([{"date": "2025-11-01", "item_id": "item-career-job", "answer": "good"}]))
    areas = build_home({}, NOW)["areas"]
    assert areas["stale"] is False and areas["date"] == "2025-11-01"


def test_areas_take_the_later_row_when_two_share_the_newest_date(tmp_repo):
    # The same rule as pfc_writes.set_rating: newest date, then the later line.
    _write(tmp_repo, "2-areas/_data/life-wheel.ndjson", _nd([
        _wheel("2025-10-21", {"career": "red"}), _wheel("2025-10-21", {"career": "green"})]))
    assert build_home({}, NOW)["areas"]["rows"][0]["light"] == "green"


def test_areas_stale_when_older_than_31_days(tmp_repo):
    _write(tmp_repo, "2-areas/_data/life-wheel.ndjson", _nd([_wheel("2025-10-01", {"career": "green"})]))
    assert build_home({}, NOW)["areas"]["stale"] is True  # 32 days
    _write(tmp_repo, "2-areas/_data/life-wheel.ndjson", _nd([_wheel("2025-10-02", {"career": "green"})]))
    assert build_home({}, NOW)["areas"]["stale"] is False  # 31 days


def test_household_has_the_same_shape_and_a_missing_file_gives_no_rows(tmp_repo):
    assert build_home({}, NOW)["household"]["rows"] == []
    _write(tmp_repo, "2-areas/_data/household-status.ndjson",
           _nd([_wheel("2025-10-26", {"hall_closet": "green", "car": "red"})]))
    household = build_home({}, NOW)["household"]
    assert household["date"] == "2025-10-26"
    assert [r["label"] for r in household["rows"]] == ["Car", "Hall closet"]


def test_focuses_group_by_tier_with_light_projects_and_parked(tmp_repo):
    _project_repo(tmp_repo)
    rows = [_vfrow("f-ai", None, title="Data course", status="green"),
            _vfrow("f-guitar", None, tier="foundation", title="Guitar", parked=True, status="parked"),
            _vfrow("f-book", None, tier="consuming", title="A book", status="yellow")]
    with patch.object(home_data, "status_rows", return_value=rows):
        focuses = build_home({}, NOW)["focuses"]
    assert [f["focus_id"] for f in focuses["pursuit"]] == ["f-ai"]
    assert [f["focus_id"] for f in focuses["foundation"]] == ["f-guitar"]
    assert [f["focus_id"] for f in focuses["consuming"]] == ["f-book"]
    ai = focuses["pursuit"][0]
    assert ai["light"] == "green" and ai["parked"] is False
    assert ai["projects"] == [{"id": "proj-live", "name": "Ship the dashboard"}]
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
    row = {k: v for k, v in projects["active"][0].items() if k in ("id", "name", "area", "status", "pct", "next_task")}
    assert row == {"id": "p-live", "name": "Live", "area": "career", "status": "active", "pct": 25,
                   "next_task": {"id": "t-high", "title": "First step"}}
    assert [p["id"] for p in projects["active"]] == ["p-live", "p-statused"]
    assert projects["active"][1]["pct"] == 0 and projects["active"][1]["next_task"] is None
    assert [p["id"] for p in projects["other"]] == ["p-ondeck", "p-nostatus", "p-parked-active", "p-parked"]
    assert projects["other"][1]["status"] == "on-deck"


def test_active_projects_carry_the_project_gauges(tmp_repo):
    """Velocity and days idle from project_gauges, the web Projects band reads them here."""
    _put_tasks(tmp_repo, [_task("t-1", project="p-late")])
    _write(tmp_repo, "6-tasks/_data/task_events.ndjson", _nd([
        {"task_id": "t-1", "event": "completed", "timestamp": "2025-10-26"}]))
    _write(tmp_repo, "5-projects/_data/projects.ndjson", _nd([
        {"id": "p-late", "name": "Late", "area": "career", "active": True, "created": "2025-10-03",
         "total_parts": 10, "completed_parts": 3, "deadline": "2025-11-11"},
        {"id": "p-new", "name": "New", "area": "career", "active": True, "created": "2025-09-02",
         "started": "2025-09-02", "total_parts": 5, "completed_parts": 0}]))
    late, new = build_home({}, NOW)["projects"]["active"]
    # 3 parts in 30 days: 0.7 a week, 7 parts left = 70 more days, far past Nov 10.
    assert late["pace"] == 0.7 and late["est_finish"] == "2026-01-11"
    assert late["light"] == "red" and late["days_late"] == 61
    assert late["days_idle"] == 7 and late["stalled"] is False
    assert new["pace"] is None and new["est_finish"] is None and new["light"] is None
    assert new["days_idle"] == 61 and new["stalled"] is True


def test_anchors_are_every_active_grounding_anchor(tmp_repo):
    assert build_home({}, NOW)["anchors"] == [{"id": "g1", "title": "Rest before you are tired"}]


# --- pulse, trends, week, skipped suggestions ---------------------------------

def _days_back(n):
    from datetime import date, timedelta
    return (date(2025, 11, 2) - timedelta(days=n)).isoformat()


def _trend(home, name):
    return next(t for t in home["trends"] if t["name"] == name)


def _tracking(root, ratings):
    rows = [{"date": _days_back(i), "rating": r, "health": {"sleep_hours": 7.5, "awake_minutes": 5}}
            for i, r in enumerate(ratings)]
    _write(root, "data/day-tracking.ndjson", _nd(rows))


def test_pulse_is_the_pulse_builder_output(pulse_repo):
    _tracking(pulse_repo, [4, 4])
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


def test_pulse_levers_carry_nights_on_target(pulse_repo):
    _tracking(pulse_repo, [4] * 30)
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
    _write(tmp_repo, "data/calendar-cache.json", json.dumps({"fetched_at": "2025-11-02T06:00:00-07:00", "events": [
        {"id": "a", "summary": "Dentist visit", "start": {"dateTime": "2025-11-04T14:30:00-07:00"},
         "end": {"dateTime": "2025-11-04T15:30:00-07:00"}},
        {"id": "b", "summary": "Zorp festival", "start": {"date": "2025-11-03"}, "end": {"date": "2025-11-05"}},
        {"id": "c", "summary": "Too far away", "start": {"dateTime": "2025-11-21T09:00:00-07:00"},
         "end": {"dateTime": "2025-11-21T10:00:00-07:00"}},
    ]}))
    week = build_home({}, NOW)["week"]
    assert [d["date"] for d in week] == [_days_back(-i) for i in range(7)]
    by = {d["date"]: d["events"] for d in week}
    assert by["2025-11-04"] == [{"start": None, "title": "Zorp festival"},
                                {"start": "2025-11-04T14:30:00-07:00", "title": "Dentist visit"}]
    assert by["2025-11-03"] == [{"start": None, "title": "Zorp festival"}]
    assert by["2025-11-05"] == []


def test_week_empty_without_the_cache(tmp_repo):
    assert build_home({}, NOW)["week"] == []


def test_skipped_pick_is_left_out_of_that_days_suggestions_only(tmp_repo, no_focus):
    _healthy_day(tmp_repo)
    _put_tasks(tmp_repo, [_task("task-a", impact="A", urgency="A"), _task("task-b", impact="B", urgency="B")])
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson",
           _nd([{"date": "2025-11-02", "critical": [], "skipped": ["task-a"]}]))
    assert [t["id"] for t in build_home({}, NOW)["suggested"]] == ["task-b"]
    # From the evening the suggestions are for tomorrow, which skipped nothing.
    assert [t["id"] for t in build_home({}, EVENING)["suggested"]] == ["task-a", "task-b"]


def test_tomorrows_skipped_list_filters_tomorrows_suggestions(tmp_repo, no_focus):
    _healthy_day(tmp_repo)
    _put_tasks(tmp_repo, [_task("task-a", impact="A", urgency="A"), _task("task-b")])
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson",
           _nd([{"date": "2025-11-03", "critical": [], "skipped": ["task-a"]}]))
    assert [t["id"] for t in build_home({}, EVENING)["suggested"]] == ["task-b"]
    assert "tomorrow_suggested" not in build_home({}, NOW)


def test_all_picks_done_when_every_critical_pick_is_completed(tmp_repo, no_focus):
    _healthy_day(tmp_repo)
    _put_tasks(tmp_repo, [_task("task-a", status="done"), _task("task-b", status="done"),
                          _task("task-c", impact="A", urgency="A"), _task("task-d")])
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2025-11-02", "critical": ["task-a", "task-b"], "bonus": "task-d", "completed": ["task-a", "task-b"]}]))
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
        {"date": "2025-11-02", "critical": ["task-a", "task-b"], "completed": ["task-a"]}]))
    assert build_home({}, NOW)["all_picks_done"] is False
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2025-11-02", "critical": [], "skipped": ["task-b"]}]))
    assert build_home({}, NOW)["all_picks_done"] is False  # a skip-only record has no picks


def _tour(tmp_repo, areas_fresh=True):
    if areas_fresh:
        _write(tmp_repo, "2-areas/_data/life-wheel.ndjson", _nd([{"date": "2025-10-31", "ratings": {"health": "green"}}]))


def test_tour_look_prefers_stale_areas(tmp_repo):
    look = build_home({}, NOW)["tour_look"]
    assert look == {"kind": "stale_areas", "title": "Life wheel", "detail": "never rated", "date": None}
    _write(tmp_repo, "2-areas/_data/life-wheel.ndjson", _nd([_wheel("2025-06-04", {"career": "green"})]))
    # The date travels as a field; the page formats it.
    look = build_home({}, NOW)["tour_look"]
    assert look == {"kind": "stale_areas", "title": "Life wheel", "detail": "last rated", "date": "2025-06-04"}


def test_tour_look_red_focus_when_areas_fresh(tmp_repo):
    _tour(tmp_repo)
    with patch.object(home_data, "status_rows", return_value=[{**_frow("f1", "Guitar", "red", 3), "tier": "pursuit"}]):
        look = build_home({}, NOW)["tour_look"]
    assert look["kind"] == "red_focus" and look["title"] == "Guitar"


def test_tour_look_stalled_project_then_none(tmp_repo, no_focus):
    _tour(tmp_repo)
    _write(tmp_repo, "5-projects/_data/projects.ndjson", _nd([
        {"id": "p1", "name": "Stalled one", "area": "career", "active": True, "started": "2025-09-02"}]))
    look = build_home({}, NOW)["tour_look"]
    assert look["kind"] == "stalled_project" and look["title"] == "Stalled one"
    _write(tmp_repo, "5-projects/_data/projects.ndjson", _nd([
        {"id": "p1", "name": "Fresh", "area": "career", "active": True, "started": "2025-10-31"}]))
    assert build_home({}, NOW)["tour_look"] is None


def _home(ids, evening=False):
    return {"evening": evening, "suggested": [{"id": i} for i in ids]}


@pytest.mark.parametrize("log,needs", [
    ("2025-11-02 05:04:10 DONE ok=4 fail=0\n", False),
    ("2025-11-02 05:04:10 DONE ok=3 fail=1\n", True),
    ("2025-10-31 05:04:10 DONE ok=4 fail=0\n", True),
    ("2025-11-02 05:00:01 START x\n", True),
])
# --- Long-running red: a red that has held CHRONIC_DAYS (14) or more is "chronic", so
# the page can fold it into a count line and let a red that is new today stand out.

def _frow_t(fid, status, weeks_red, tier="pursuit", parked=False):
    return {"focus_id": fid, "title": fid.upper(), "tier": tier, "status": status,
            "weeks_red": weeks_red, "parked": parked}


def test_chronic_threshold_is_two_weeks():
    assert home_data.CHRONIC_DAYS == 14


def test_focus_red_two_weeks_or_more_is_chronic_and_the_worst_per_tier_leads(tmp_repo):
    rows = [_frow_t("new", "red", 1), _frow_t("old", "red", 2), _frow_t("oldest", "red", 8),
            _frow_t("also8", "red", 8), _frow_t("yel", "yellow", 0), _frow_t("park", "parked", 0, parked=True),
            _frow_t("found", "red", 3, tier="foundation")]
    with patch.object(home_data, "status_rows", return_value=rows):
        home = build_home({}, NOW)
    by = {f["focus_id"]: f for f in home["focus"]}
    assert [k for k, f in by.items() if f["chronic"]] == ["old", "oldest", "also8", "found"]
    # The worst (most weeks red, first in the list's order on a tie) leads each tier.
    assert [k for k, f in by.items() if f["chronic_lead"]] == ["oldest", "found"]
    # The tier lists carry the same fields.
    assert [f["focus_id"] for f in home["focuses"]["pursuit"] if f["chronic"]] == ["old", "oldest", "also8"]


def test_stalled_project_idle_another_two_weeks_is_chronic(tmp_repo):
    _write(tmp_repo, "5-projects/_data/projects.ndjson", _nd([
        {"id": f"p-{d}", "name": f"P{d}", "area": "career", "active": True, "created": _days_back(d),
         "started": _days_back(d), "total_parts": 5, "completed_parts": 0} for d in (6, 14, 27, 28, 90)]))
    active = build_home({}, NOW)["projects"]["active"]
    assert [(p["days_idle"], p["stalled"], p["chronic"]) for p in active] == [
        (6, False, False), (14, True, False), (27, True, False), (28, True, True), (90, True, True)]
    assert [p["id"] for p in active if p["chronic_lead"]] == ["p-90"]


def _nights(root, awake_by_night):
    """One tracked night per value, oldest first, the last one last night (NOW's date)."""
    n = len(awake_by_night)
    rows = [{"date": _days_back(n - 1 - i), "rating": 4,
             "health": {"sleep_hours": 7.5, "awake_minutes": a}} for i, a in enumerate(awake_by_night)]
    _write(root, "data/day-tracking.ndjson", _nd(rows))


@pytest.fixture
def pulse_repo(tmp_repo):
    """home_data imports trmnl_push by its bare name (sys.path), a second module object
    from the package import tmp_repo patches; patch that one too, so last night's
    levers come from the test's nights and not from the real day-tracking file."""
    import sys
    import trmnl_push as bare
    with patch.object(bare, "REPO_ROOT", tmp_repo), patch.dict(sys.modules, {"trmnl_push": bare}):
        yield tmp_repo


def _continuity(home):
    return next(lv for lv in home["pulse"]["levers"] if lv["label"] == "Continuity (awake)")


def test_lever_red_on_half_the_last_14_nights_is_chronic(pulse_repo):
    _nights(pulse_repo, [5] * 7 + [60] * 7)  # red the last 7 of 14 nights
    lv = _continuity(build_home({}, NOW))
    assert lv["mark"] == "RED" and lv["red_nights"] == 7 and lv["nights"] == 14
    assert lv["chronic"] is True and lv["chronic_lead"] is True


def test_lever_red_last_night_only_is_new_not_chronic(pulse_repo):
    _nights(pulse_repo, [5] * 13 + [60])
    lv = _continuity(build_home({}, NOW))
    assert lv["mark"] == "RED" and lv["red_nights"] == 1
    assert lv["chronic"] is False and lv["chronic_lead"] is False


def test_lever_green_last_night_is_never_chronic(pulse_repo):
    _nights(pulse_repo, [30] * 13 + [5])
    lv = _continuity(build_home({}, NOW))
    assert lv["mark"] == "GREEN" and lv["chronic"] is False



# Plain words on the page: targets, lever names, no dashes, and a pick that is also overdue.
@pytest.mark.parametrize("raw,words", [
    ("<=10m, 70m to yellow", "10 min or less, 70 min short of yellow"),
    (">=7.4h, 12m to yellow", "7.4 hours or more, 12 min short of yellow"),
    ("<=50m", "50 min or less"),
    ("<=1x, 2x to yellow", "1 time or fewer, 2 times short of yellow"),
    ("<=3x", "3 times or fewer"),
    ("<=6:45 AM, 15m to yellow", "by 6:45 AM, 15 min short of yellow"),
    ("<=10:45 PM, 24m to green", "by 10:45 PM, 24 min short of green"),
    (">=2, 1 pt to yellow", "2 or more, 1 point short of yellow"),
    (">=108m", "108 min or more"),
    ("", ""),
])
def test_target_words_read_the_e_ink_target_as_plain_words(raw, words):
    assert home_data.target_words(raw) == words


def test_levers_carry_a_plain_label_and_target_words(pulse_repo):
    _nights(pulse_repo, [5] * 3)
    levers = {lv["label"]: lv for lv in build_home({}, NOW)["pulse"]["levers"]}
    assert levers["QQRT score"]["label_plain"] == "Sleep score (quantity, quality, timing)"
    assert levers["REM"]["label_plain"] == "Dream sleep (REM)"
    assert levers["Sleep hours"]["label_plain"] == "Sleep hours"
    assert levers["Sleep hours"]["target"] == ">=7.5h"  # the e-ink text stays as it was
    assert levers["Sleep hours"]["target_words"] == "7.5 hours or more"


def test_pulse_verdict_and_move_carry_no_dashes(pulse_repo):
    _nights(pulse_repo, [30] * 14)
    pulse = build_home({}, NOW)["pulse"]
    assert "—" not in pulse["verdict"] and "–" not in pulse["verdict"]
    assert "—" not in pulse["move"] and "–" not in pulse["move"]


def test_needs_you_rows_say_when_they_are_one_of_todays_picks(tmp_repo, no_focus):
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([
        {"date": "2025-11-02", "critical": ["task-crit"], "bonus": "task-late"}]))
    _put_tasks(tmp_repo, [_task("task-late", deadline="2025-10-31"), _task("task-crit", deadline="2025-11-03"),
                          _task("task-other", deadline="2025-11-01")])
    home = build_home({}, NOW)
    # needs_you keeps its rows and cap for every surface; the new field only tags them.
    assert [(n["id"], n["in_picks"]) for n in home["needs_you"]] == [("task-late", "bonus"), ("task-other", None)]
    # The pick whose row the page hides carries the deadline flag instead, so the page
    # shows one card with one Done. A pick with no needs_you row gets no flag.
    assert home["picks"]["bonus"]["flag"] == {"why": "overdue since", "date": "2025-10-31"}
    assert home["picks"]["critical"][0]["flag"] is None


def test_habits_carry_a_plain_title_for_the_page(tmp_repo):
    _write(tmp_repo, "config/habit_schema.yaml",
           "daily_habits: []\nmonthly_habits:\n  - id: hiit-session\n    frequency: 1\n    started: '2025-01-02'\n")
    with patch.dict(home_data.HABIT_PLAIN, {"HIIT": "Interval training"}):
        habit = build_home({}, NOW)["habits"][0]
    assert habit["title"] == "HIIT session"  # every other surface keeps its title
    assert habit["title_plain"] == "Interval training session"


def test_a_pick_without_a_deadline_in_the_window_has_no_flag(tmp_repo, no_focus):
    _write(tmp_repo, "6-tasks/_data/daily-focus.ndjson", _nd([{"date": "2025-11-02", "critical": ["task-a"]}]))
    _put_tasks(tmp_repo, [_task("task-a", deadline="2025-12-02")])
    assert build_home({}, NOW)["picks"]["critical"][0]["flag"] is None



def test_review_hints_carry_no_dashes():
    """The home page shows a due review's hint as written here (web UI text: no dashes)."""
    assert not [k for k, v in home_data.REVIEW_SKILLS.items() if "\u2014" in v or "\u2013" in v]
