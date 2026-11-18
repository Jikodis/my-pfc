"""The TRMNL screens are the web page's bands: same data, e-ink safe."""

import json
import re
from pathlib import Path

import pytest

import trmnl_home
import trmnl_push
from automations.scripts.home_data import build_home
from automations.scripts.tests.test_home_data import NOW, pulse_repo, tmp_repo  # noqa: F401  (fixtures)

WORDS = {"RED", "YELLOW", "GREEN", "NO DATA", "PARKED"}
PAYLOADS = [trmnl_home.values_payload, trmnl_home.areas_payload, trmnl_home.visions_payload,
            trmnl_home.focus_payload, trmnl_home.projects_payload, trmnl_home.body_payload,
            trmnl_home.tasks_payload, trmnl_home.habits_payload, trmnl_home.trends_payload,
            trmnl_home.week_payload, trmnl_home.front_of_mind_payload]


BAND_PLUGIN = {"body": "pfc-pulse", "trends": "pfc-trends", "values": "pfc-values",
               "areas": "pfc-areas", "visions": "pfc-visions", "focuses": "pfc-focus",
               "projects": "pfc-projects", "tasks": "pfc-today", "habits": "pfc-habits",
               "front-of-mind": "pfc-front-of-mind", "week": "pfc-week"}


def test_one_screen_per_web_band_in_page_order():
    # Read the order off the page itself, so a regrouped page fails this test.
    page = (Path(__file__).resolve().parents[3] / "web/src/pages/index.astro").read_text()
    bands = re.findall(r'<Band band="([^"]+)"', page)
    assert list(trmnl_push.BUILDERS) == [BAND_PLUGIN[b] for b in bands]


@pytest.mark.parametrize("fn", PAYLOADS, ids=lambda f: f.__name__)
def test_payloads_are_ascii_and_spell_out_lights(tmp_repo, fn):  # noqa: F811
    p = fn(build_home({}, NOW))
    text = json.dumps(p, ensure_ascii=False)
    assert text.isascii(), text
    assert p["title"] and p["date"]

    def statuses(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.endswith("status"):
                    yield v
                yield from statuses(v)
        elif isinstance(o, list):
            for v in o:
                yield from statuses(v)
    assert set(statuses(p)) <= WORDS


def test_body_rows_carry_today_and_thirty_nights(pulse_repo):  # noqa: F811
    from automations.scripts.tests.test_home_data import _tracking
    _tracking(pulse_repo, [4, 4])
    p = trmnl_home.body_payload(build_home({}, NOW))
    assert p["has_levers"]
    assert all(" of " in lv["month"] for lv in p["levers"] if lv["month"])
    assert p["exercise"] in {"Done", "Not yet"}


def test_body_folds_levers_on_target_into_a_count(pulse_repo):  # noqa: F811
    from automations.scripts.tests.test_home_data import _tracking
    _tracking(pulse_repo, [4, 4])
    h = build_home({}, NOW)
    p = trmnl_home.body_payload(h)
    levers = h["pulse"]["levers"]
    assert all(lv["status"] != "GREEN" for lv in p["levers"])
    assert len(p["levers"]) <= trmnl_home.LEVER_ROWS
    assert p["on_target"] + len(p["levers"]) + p["levers_more"] == len(levers)


def test_trends_hold_no_sleep_levers(tmp_repo):  # noqa: F811
    p = trmnl_home.trends_payload(build_home({}, NOW))
    names = {r["name"] for r in p["rows"]} | set(p["green"])
    assert names == {"Day rating", "Energy", "Mood", "Focus", "Picks done"}
    assert all(r["status"] != "GREEN" for r in p["rows"])


def test_areas_fold_greens_into_counts(tmp_repo):  # noqa: F811
    h = build_home({}, NOW)
    p = trmnl_home.areas_payload(h)
    assert p["count"] == len(h["areas"]["rows"]) and p["rooms_count"] == len(h["household"]["rows"])
    assert all(r["status"] != "GREEN" for r in p["rows"])
    assert p["green"] + len(p["rows"]) + p["more"] == p["count"]


def test_areas_carry_the_plate_when_there_are_items(tmp_repo):  # noqa: F811
    assert trmnl_home.areas_payload(build_home({}, NOW))["plate"] is None
    (tmp_repo / "2-areas/_data").mkdir(parents=True, exist_ok=True)
    (tmp_repo / "2-areas/_data/area-items.ndjson").write_text(
        json.dumps({"id": "item-health-sleep", "area": "health", "title": "Sleep", "kind": "time", "weight": 3,
                    "hours": 56, "source": "fitbit:sleep", "active": True}) + "\n"
        + json.dumps({"id": "item-career-job", "area": "career", "title": "Job", "kind": "time", "weight": 3,
                      "hours": 40, "question": "Going well?", "active": True}) + "\n")
    p = trmnl_home.areas_payload(build_home({}, NOW))
    assert {k: p["plate"][k] for k in ("status", "committed", "free", "pct")} == \
        {"status": "GREEN", "committed": "40", "free": "112", "pct": 36}


def test_week_caps_events_per_day_and_names_today(tmp_repo):  # noqa: F811
    h = build_home({}, NOW)
    h["week"] = [{"date": h["date"], "events": [{"start": None, "title": "Away"}]
                  + [{"start": f"{h['date']}T{9 + i:02d}:00:00-07:00", "title": f"E{i}"} for i in range(4)]}]
    p = trmnl_home.week_payload(h)
    day = p["days"][0]
    assert day["label"] == "Today"
    assert [e["time"] for e in day["events"]] == ["All day", "9:00 AM", "10:00 AM"]
    assert day["more"] == 2


def test_two_plus_one_folds_an_overdue_pick_into_its_row(tmp_repo):  # noqa: F811
    h = build_home({}, NOW)
    h["picks"] = {"critical": [{"id": "t1", "title": "Late thing", "why": [], "done": False}], "bonus": None}
    h["needs_you"] = [{"kind": "deadline", "id": "t1", "title": "Late thing", "why": "overdue since", "date": "2025-10-31"},
                      {"kind": "deadline", "id": "t2", "title": "Other", "why": "due", "date": "2025-11-03"}]
    p = trmnl_home.tasks_payload(h)
    assert p["picks"][0]["note"] == "overdue since Fri Oct 31"
    assert [n["title"] for n in p["needs"]][:1] == ["Other"]
