"""The Trello cards that mirror the web home page (trello_home.py)."""

from __future__ import annotations

import trello_home
import trello_render


def _home(**over):
    base = {
        "household": {"date": "2025-11-06", "stale": False, "rows": [
            {"key": "kitchen", "label": "Kitchen", "light": "red", "note": "Dishes piled"},
            {"key": "garage", "label": "Garage", "light": "yellow", "note": None},
            {"key": "pantry", "label": "Pantry", "light": "green", "note": None}]},
        "trends": [{"name": "Picks done", "light": "red", "why": "0 of 4 critical picks done"},
                   {"name": "Mood", "light": "green", "why": "avg 5.0 over 1 rated days"}],
        "projects": {"active": [], "other": []},
        "areas": {"date": "2025-11-06", "stale": False, "rows": []},
        "plate": None,
        "visions": [],
        "focus": [],
    }
    base.update(over)
    return base


def test_household_folds_into_one_areas_card_like_the_web():
    card = trello_home.render_areas(_home(), {})[-1]
    assert card.pfc_id == "household" and card.list_name == "🧭 Areas"
    assert card.name == "🏠 Household: 1 of 3 rooms green · rated Thu Nov 6"
    assert card.body.splitlines()[:3] == ["🔴 Kitchen — Dishes piled", "🟡 Garage", "🟢 Pantry"]


def test_household_says_stale_like_the_web():
    home = _home()
    home["household"]["stale"] = True
    assert trello_home.render_areas(home, {})[-1].name.endswith(" · stale")


def test_trends_rows_with_their_why():
    cards = trello_home.render_trends(_home())
    assert [c.name for c in cards] == ["🔴 Picks done — 0 of 4 critical picks done",
                                       "🟢 Mood — avg 5.0 over 1 rated days"]
    assert cards[0].pfc_id == "trend-picks-done"


def _prow(pid, name, pct, light=None, idle=3, stalled=False, pace=None, est=None, late=None, nxt=None):
    return {"id": pid, "name": name, "pct": pct, "light": light, "days_idle": idle, "stalled": stalled,
            "pace": pace, "est_finish": est, "days_late": late, "next_task": nxt}


def test_projects_show_the_gauges_red_first():
    home = _home(projects={"active": [
        _prow("p-calm", "Calm", 40, idle=2),
        _prow("p-late", "Late", 30, light="red", pace=0.7, est="2025-12-01", late=61,
              nxt={"id": "t", "title": "Write intro"}),
        _prow("p-stuck", "Stuck", 0, idle=40, stalled=True)], "other": []})
    raw = [{"id": "p-late", "total_parts": 10, "completed_parts": 3, "deadline": "2025-10-01",
            "impact": "high", "urgency": "medium", "area": "career", "values": ["Growth"]},
           {"id": "p-calm", "total_parts": 5, "completed_parts": 2, "impact": "low", "urgency": "low"},
           {"id": "p-stuck", "total_parts": 0, "completed_parts": 0}]
    cards = trello_home.render_projects(home, raw, plain_color_labels={"orange": "lo"})
    assert [c.name for c in cards] == ["🔴 30% Late · idle 3d", "0% Stuck · stalled 40d", "40% Calm · idle 2d"]
    late = cards[0]
    # _month_day adds the year only when it is not this year, so build the text with it.
    assert f"Pace: 0.7 parts a week · finish about {trello_home._month_day('2025-12-01')}" in late.body
    assert f"On time: 🔴 finishes 61 days past the {trello_home._month_day('2025-10-01')} deadline" in late.body
    assert "Next: Write intro" in late.body
    assert late.label_names == ["_plain:orange"]
    assert late.checklist == [(f"Part {i + 1}", i < 3) for i in range(10)]
    assert "no deadline, so no on-time light" in cards[2].body
    assert cards[1].checklist is None


def test_areas_lead_with_the_plate_then_each_area_with_items():
    home = _home(plate={"free": 112, "committed": 110.0, "pct": 98, "light": "yellow"},
                 areas={"date": "2025-11-06", "stale": False, "rows": [
                     {"key": "health", "label": "Health", "light": "red", "note": "Not enough sleep.",
                      "source": "items", "hours": 3.5, "items": [
                          {"title": "Sleep, 8 hours a night", "kind": "time", "weight": 3, "hours": 56.0,
                           "light": "red", "why": "on target 5 of 30", "stale": False, "ended": False},
                          {"title": "Whole foods", "kind": "status", "weight": 1, "hours": None,
                           "light": None, "why": "no answer yet", "stale": False, "ended": False}]},
                     {"key": "family", "label": "Family", "light": "green", "note": None, "source": "manual",
                      "hours": None, "items": []}]})
    cards = trello_home.render_areas(home, {"health": "# Health\n\nStatement."}, plain_color_labels={"red": "lr"})
    assert [c.name for c in cards][:3] == ["🟡 Plate: 110 of 112 free hours committed (98%)", "🔴 Health", "🟢 Family"]
    assert "(168 minus sleep)" in cards[0].body
    health = cards[1]
    assert health.label_names == ["_plain:red"]
    assert "Light: 🔴 red, from 2 items · 3.5 h a week" in health.body
    assert "🔴 Sleep, 8 hours a night — Time · 56 h a week · weight 3 · on target 5 of 30" in health.body
    assert "▫️ Whole foods — Status · weight 1 · no answer yet" in health.body
    assert health.body.endswith("Statement.")
    assert "manual light · no weekly hours" in cards[2].body


def _focus(fid, title, status, parked=False):
    return {"focus_id": fid, "title": title, "status": status, "parked": parked,
            "primary": {"completed": 1, "target": 4, "habit_id": "h"}}


def test_visions_borrow_their_focus_and_project_lights_and_rest_dormant():
    home = _home(
        visions=[{"id": "ai", "title": "Ship a side project"}, {"id": "cook", "title": "Become a great cook"},
                 {"id": "lang", "title": "Learn a language"}, {"id": "pottery", "title": "Pottery"}],
        focus=[_focus("f-build", "Build course", "yellow"), _focus("f-chess", "Chess", "yellow", parked=True),
               _focus("f-lang", "Spanish", "red")],
        projects={"active": [_prow("p-build", "Woodworking course", 0), _prow("p-lang", "Spanish course", 11)], "other": []})
    focus_records = [{"id": "f-build", "link": {"type": "vision", "ref": "ai"}},
                     {"id": "f-chess", "link": {"type": "vision", "ref": "pottery"}},
                     {"id": "f-lang", "link": {"type": "vision", "ref": "lang"}}]
    projects = [{"id": "p-build", "vision": "ai"}, {"id": "p-lang", "vision": "lang"}]
    files = [{"slug": "ai", "body": "---\nstatus: active\n---\n# Ship a side project\n\nWhy."}]
    cards = trello_home.render_visions(home, focus_records, projects, files)
    names = [c.name for c in cards]
    assert names == ["🔴 Learn a language — focus 🔴 Spanish · project 11%",
                     "🟡 Ship a side project — focus 🟡 Build course · project 0%",
                     "⚪ Become a great cook — dormant",
                     "⚪ Pottery — dormant"]
    ai = cards[1]
    assert ai.pfc_id == "vision-ai"
    assert "Focus 🟡 Build course · 1 of 4 via h" in ai.body and "Project 0% Woodworking course · idle 3d" in ai.body
    assert "status: active" not in ai.body and "# Ship a side project" in ai.body
    assert "Focus 🅿️ Chess: parked" in cards[3].body


def test_parked_and_on_deck_projects_fold_into_one_closing_card():
    home = _home(projects={"active": [], "other": [
        {"id": "p1", "name": "Guitar lessons", "status": "on-deck", "pct": 50},
        {"id": "p2", "name": "Learn to Cook", "status": "parked", "pct": 0}]})
    [card] = trello_home.render_projects(home, [])
    assert card.name == "Parked and on deck (2)"
    assert card.body.splitlines()[:2] == ["On deck: Guitar lessons (50%)", "Parked: Learn to Cook (0%)"]


def _body_home(**over):
    base = {"date": "2025-11-10", "rate_target": {"date": "2025-11-09", "unrated": True},
            "body": {"sleep_hours": 5.9, "awake_minutes": 5, "broken_night": False, "window": 30},
            "pulse": {"verdict_mark": "RED", "verdict": "Depleted — recover first.", "move": "Bed by 10:30 PM.",
                      "levers": [
                          {"label": "Sleep hours", "value": "5.9h", "target": ">=7.4h", "tier": "CRITICAL",
                           "mark": "RED", "on": 5, "n": 30},
                          {"label": "Deep sleep", "value": "97m", "target": ">=90m", "tier": "CRITICAL",
                           "mark": "GREEN", "on": 20, "n": 30},
                          {"label": "Bedtime", "value": "11:09 PM", "target": "<=10:45 PM", "tier": "MODERATE",
                           "mark": "YELLOW", "on": 9, "n": 30}]}}
    base.update(over)
    return base


def test_body_first_reads_like_the_web_band():
    cards = trello_home.render_body(_body_home())
    assert [c.name for c in cards] == [
        "🔴 Body first: Depleted — recover first.",
        "⭐ How was yesterday? Sun Nov 9",
        "🔴 Sleep hours: 5.9h · target >=7.4h · on target 5 of 30 nights",
        "🟡 Bedtime: 11:09 PM · target <=10:45 PM · on target 9 of 30 nights",
        "🟢 1 on target last night"]
    assert {c.list_name for c in cards} == {"🦸 Body first"}
    # Below the 🤖 Brief (pos 1), in this order.
    assert [c.pos for c in cards] == sorted(c.pos for c in cards) and cards[0].pos > 1
    assert "Tonight: Bed by 10:30 PM." in cards[0].body
    assert cards[4].body == "Deep sleep: 97m · target >=90m · on target 20 of 30 nights"


def test_body_first_has_no_rating_card_once_the_day_is_rated():
    cards = trello_home.render_body(_body_home(rate_target={"date": "2025-11-09", "unrated": False}))
    assert all(c.pfc_type != "rate-day" for c in cards)


def _picks_home(**over):
    base = {"evening": False, "pick_date": "2025-11-10",
            "focus_of_day": {"id": "f", "title": "Guitar", "vision": "Play for friends", "value": "Family"},
            "handoffs": [{"id": "t9", "title": "Book a checkup", "why": []}],
            "needs_you": [{"kind": "deadline", "id": "t1", "title": "Renew tags", "why": "overdue since",
                           "date": "2025-11-05"}],
            "due_review": None, "tour_look": {"kind": "red_focus", "title": "Guitar", "detail": "red for 8 weeks",
                                              "date": None}}
    base.update(over)
    return base


def test_the_2plus1_list_wraps_the_picks_like_the_web_band():
    pick = trello_render.Card(pfc_id="t2", pfc_type="task", list_name="✅ The 2+1", name="🔴 AA (S) - X", body="")
    cards = trello_home.render_picks(_picks_home(), [pick])
    # The picks, then one card holding the rest of the band (no Why or hand-off cards).
    assert [c.name for c in cards] == ["🔴 AA (S) - X", "🔴 What needs you: 2"]
    assert cards[1].body.splitlines() == [
        "What needs you:", "• Renew tags — overdue since Wed Nov 5", "• Look at: Guitar red for 8 weeks", "",
        "Why: Guitar → Play for friends → Family", "",
        "An agent can do these (1), hand one off on the web home page or in chat:", "• Book a checkup"]
    assert [c.pos for c in cards] == sorted(c.pos for c in cards)


def test_from_the_evening_the_2plus1_list_shows_tomorrow():
    home = _picks_home(evening=True, pick_date="2025-11-11", handoffs=[], needs_you=[], tour_look=None,
                       tomorrow_picks={"critical": [{"title": "A"}, {"title": "B"}], "bonus": {"title": "C"}})
    cards = trello_home.render_picks(home, [])
    assert [c.name for c in cards] == ["Tomorrow, Tue Nov 11: A · B · bonus C", "ℹ️ Why today, and hand-offs"]


def test_week_is_one_card_per_day_with_the_rest_counted():
    days = [{"date": "2025-11-10", "events": [
                {"start": None, "title": "Holiday"},
                {"start": "2025-11-10T09:00:00-07:00", "title": "Standup"},
                {"start": "2025-11-10T12:00:00-07:00", "title": "Lunch"},
                {"start": "2025-11-10T15:30:00-07:00", "title": "Dentist"}]},
            {"date": "2025-11-11", "events": []}]
    cards = trello_home.render_week(days, "2025-11-10")
    assert [c.name for c in cards] == ["Today: All day Holiday · 9:00 AM Standup · 12:00 PM Lunch · 1 more",
                                       "Tue Nov 11: nothing scheduled"]
    assert cards[0].body.splitlines()[-1] == "3:30 PM Dentist"
    assert cards[0].pfc_id == "week-2025-11-10" and cards[0].list_name == "🗓️ Week"


def test_values_end_with_the_question_of_the_day():
    values = trello_render.render_values({"values": "1. Honesty\n2. Courage\n"})
    cards = trello_home.render_values({"question_of_day": {"n": 7, "text": "What does this week need?"}}, values)
    assert [c.name for c in cards] == ["1. Honesty", "2. Courage", "Question of the day: What does this week need?"]
    assert {c.list_name for c in cards} == {"💎 Values"}


def test_current_focus_uses_the_derived_light_like_the_web():
    state = {"focus": [{"id": "f1", "tier": "pursuit", "title": "Spanish", "area": "relationship", "status": "green",
                        "impact": "high", "urgency": "low", "retired_date": None}],
             "focus_status": [{"focus_id": "f1", "status": "red", "primary": None, "supporting": []}]}
    [card] = trello_render.render_focus(state)
    assert "🔴" in card.name and "🟢" not in card.name
