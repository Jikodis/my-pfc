"""The 🤖 Duet brief card: the whole day's state on one read-only card (trello_home.render_brief)."""

from __future__ import annotations

from datetime import datetime

import trello_home

NOW = datetime(2025, 11, 10, 14, 5)


def _home(**over):
    base = {
        "date": "2025-11-10",
        "rate_target": {"date": "2025-11-09", "unrated": True},
        "picks": {"critical": [{"id": "t1", "title": "Call the dentist", "done": True},
                               {"id": "t2", "title": "Draft the intro", "done": False}],
                  "bonus": {"id": "t3", "title": "Fix the gate", "done": False}},
        "pulse": {"verdict_mark": "RED", "verdict": "Depleted — recover first.", "levers": []},
        "focus": [{"focus_id": "f1", "title": "Walking", "status": "red", "parked": False},
                  {"focus_id": "f2", "title": "Chess", "status": "red", "parked": True},
                  {"focus_id": "f3", "title": "Presence", "status": "green", "parked": False}],
        "projects": {"active": [{"id": "p1", "name": "Late project", "light": "red"}], "other": []},
        "areas": {"rows": [{"key": "health", "label": "Health", "light": "red"},
                           {"key": "career", "label": "Career", "light": "green"}]},
        "household": {"rows": [{"key": "kitchen", "label": "Kitchen", "light": "red"}]},
        "trends": [{"name": "Picks done", "light": "red", "why": "x"}, {"name": "Mood", "light": "green", "why": "y"}],
        "reviews_due": 3,
        "week": [{"date": "2025-11-10", "events": [
            {"start": None, "title": "Holiday"},
            {"start": "2025-11-10T07:00:00-07:00", "title": "Pick up groceries"},
            {"start": "2025-11-10T16:45:00-07:00", "title": "Pottery class"}]}],
        "needs_you": [{"kind": "deadline", "title": "Check the probe", "why": "overdue since", "date": "2025-07-23"},
                      {"kind": "email", "title": "Reply to the landlord", "why": "priority AA email", "date": None}],
    }
    base.update(over)
    return base


HABITS = [{"short": "Walk 20+ min", "done_today": True, "completed": 1, "target": 3},
          {"short": "reading", "done_today": False, "completed": 2, "target": 7}]


def _brief(home=None, habits=HABITS, days=(), last_sync="2025-11-10T13:01:08-07:00"):
    return trello_home.render_brief(home or _home(), habits, list(days), NOW, last_sync)


def test_the_brief_is_the_first_card_of_body_first():
    card = _brief()
    assert card.list_name == "🦸 Body first" and card.pfc_id == "duet-brief" and card.pos == 1
    assert card.name == "🤖 Brief · Mon Nov 10 · updated 2:05 PM"


def test_the_brief_lines():
    lines = _brief().body.splitlines()
    assert lines == [
        "Rating: Sun Nov 9 not rated yet (rating card in 🦸 Body first)",
        "2+1 today, 1 of 3 done: Call the dentist (done); Draft the intro (not done); bonus Fix the gate (not done)",
        "Habits today: 1 of 2 done (not ticked yet: reading) · past 7 days: Walk 20+ min 1/3, reading 2/7",
        "Pulse: 🔴 Depleted — recover first.",
        "Red: Walking (focus); Late project (project); Health (area); Kitchen (room); Picks done (trend)",
        "Reviews due: 3",
        "Focuses: 🔴 Walking (focus); 🟢 Presence (focus)",
        "Next today: 4:45 PM Pottery class",
        "Needs you: Check the probe (overdue since Wed Jul 23); Reply to the landlord (priority AA email)",
        "Last Trello sync: 1:01 PM",
    ]


def test_a_rated_day_says_its_rating():
    body = _brief(_home(rate_target={"date": "2025-11-09", "unrated": False}),
                  days=[{"date": "2025-11-09", "rating": 4}]).body
    assert body.splitlines()[0] == "Rating: Sun Nov 9 rated 4/5"


def test_no_picks_no_red_nothing_left_today_and_no_sync_yet():
    home = _home(picks=None, focus=[], projects={"active": [], "other": []}, areas={"rows": []},
                 household={"rows": []}, trends=[], needs_you=[],
                 week=[{"date": "2025-11-10", "events": [{"start": "2025-11-10T07:00:00-07:00", "title": "Gone"}]}])
    lines = _brief(home, last_sync=None).body.splitlines()
    assert "2+1 today: none set" in lines
    assert "Red: none" in lines
    assert "Next today: nothing else on the calendar" in lines
    assert "Needs you: nothing" in lines
    assert "Last Trello sync: not recorded on this machine" in lines


def test_the_brief_names_the_one_review_up_now():
    review = {"id": "focus-accuracy", "label": "Current Focus accuracy", "tier": "weekly", "overdue_days": 12,
              "due_count": 3, "sections": [
                  {"kind": "choices", "title": "Focuses", "options": ["Right", "Wrong"], "rows": [{"title": "Walking"}]}]}
    lines = trello_home.render_brief(_home(), HABITS, [], NOW, None, review=review).body.splitlines()
    assert "Review now: Current Focus accuracy (weekly, 12 days overdue; 3 due, done one at a time)" in lines
    assert "First step: Focuses: Walking (Right / Wrong)" in lines
    assert not any(line.startswith("Reviews due") for line in lines)


def test_no_review_due_says_so():
    lines = _brief(_home(reviews_due=0)).body.splitlines()
    assert "Review now: none due" in lines


def test_current_review_is_fail_safe():
    assert trello_home.current_review({}) is None


def test_red_items_cap_at_five_with_a_count_of_the_rest():
    home = _home(household={"rows": [{"key": f"r{i}", "label": f"Room {i}", "light": "red"} for i in range(4)]})
    red = next(line for line in _brief(home).body.splitlines() if line.startswith("Red"))
    assert red.endswith("· and 3 more")
    assert red.count(";") == 4


def test_a_prompt_review_names_its_question_and_never_done_says_so():
    review = {"label": "Insights", "tier": "monthly", "overdue_days": None, "due_count": 1,
              "sections": [{"kind": "prompt", "question": "What surprised you?"}]}
    lines = trello_home.render_brief(_home(), HABITS, [], NOW, None, review=review).body.splitlines()
    assert "Review now: Insights (monthly, never done; 1 due, done one at a time)" in lines
    assert "First step: What surprised you?" in lines


def test_the_most_overdue_review_of_each_kind():
    overdue = [(None, {"label": "Never", "tier": "monthly"}), (40, {"label": "Old weekly", "tier": "weekly"}),
               (9, {"label": "New weekly", "tier": "weekly"}), (3, {"label": "Re-pick", "tier": "quarterly"})]
    lines = trello_home.render_brief(_home(), HABITS, [], NOW, None, overdue=overdue).body.splitlines()
    assert ("Most overdue by kind: weekly Old weekly (40 days overdue); monthly Never (never done); "
            "quarterly Re-pick (3 days overdue)") in lines


def test_focuses_worst_first_with_their_quarter_tag():
    home = _home(focus=[{"focus_id": "f3", "title": "Presence", "status": "green", "parked": False, "tier": "foundation"},
                        {"focus_id": "f1", "title": "Walking", "status": "red", "parked": False, "tier": "foundation"},
                        {"focus_id": "f2", "title": "Chess", "status": "red", "parked": True, "tier": "pursuit"}])
    rows = [{"id": "f1", "quarter": "2025-Q3"}, {"id": "f3", "quarter": "2025-Q4"}]
    lines = trello_home.render_brief(home, HABITS, [], NOW, None, focus_rows=rows).body.splitlines()
    assert ("Focuses (tagged 2025-Q3, now 2025-Q4: re-pick due): 🔴 Walking (foundation); "
            "🟢 Presence (foundation)") in lines
    rows = [{"id": "f1", "quarter": "2025-Q4"}, {"id": "f3", "quarter": "2025-Q4"}]
    lines = trello_home.render_brief(home, HABITS, [], NOW, None, focus_rows=rows).body.splitlines()
    assert any(line.startswith("Focuses (all tagged 2025-Q4): ") for line in lines)


def test_feature_use_skips_on_demand_features():
    features = [{"title": "Rate the day", "recent": {"count": 2, "expected": 30}, "verdict": "change cadence"},
                {"title": "Revive", "recent": {"count": 0, "expected": None}, "verdict": "on demand"}]
    lines = trello_home.render_brief(_home(), HABITS, [], NOW, None, features=features).body.splitlines()
    assert "Feature use, last 30 days: Rate the day 2/30 (change cadence)" in lines


def test_the_fail_safe_helpers():
    assert trello_home.due_reviews({}) == [] and trello_home.feature_scorecard({}) == []
    assert trello_home.quarter_of("2025-11-16") == "2025-Q4" and trello_home.quarter_of("2025-01-02") == "2025-Q1"
