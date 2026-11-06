"""The TRMNL screens are the web page's bands: same data, e-ink safe."""

import json
from datetime import datetime

import pytest

import trmnl_home
import trmnl_push
from automations.scripts.home_data import build_home
from automations.scripts.tests.test_home_data import tmp_repo as _home_repo  # noqa: F401  (fixture)

NOW = datetime(2026, 11, 1, 9, 0)


@pytest.fixture
def tmp_repo(_home_repo, monkeypatch):  # noqa: F811
    """test_home_data's throwaway repo, with the bare `trmnl_push` module (which
    home_data imports by its short name) pointed at it as well."""
    monkeypatch.setattr(trmnl_push, "REPO_ROOT", _home_repo)
    return _home_repo
WORDS = {"RED", "YELLOW", "GREEN", "NO DATA", "PARKED"}
PAYLOADS = [trmnl_home.values_payload, trmnl_home.areas_payload, trmnl_home.visions_payload,
            trmnl_home.focus_payload, trmnl_home.projects_payload, trmnl_home.body_payload,
            trmnl_home.tasks_payload, trmnl_home.habits_payload, trmnl_home.trends_payload]


def test_one_screen_per_web_band_in_page_order():
    assert list(trmnl_push.BUILDERS) == [
        "pfc-values", "pfc-areas", "pfc-visions", "pfc-focus", "pfc-projects", "pfc-pulse",
        "pfc-today", "pfc-habits", "pfc-trends", "pfc-front-of-mind", "pfc-week"]


def test_every_plugin_folder_has_a_builder_and_back():
    folders = {p.name for p in (trmnl_push.TRMNL_DIR).iterdir() if p.is_dir() and p.name.startswith("pfc-")}
    assert folders == set(trmnl_push.BUILDERS)


@pytest.mark.parametrize("fn", PAYLOADS, ids=lambda f: f.__name__)
def test_payloads_are_ascii_and_spell_out_lights(tmp_repo, fn):  # noqa: F811
    p = fn(build_home({}, NOW))
    text = json.dumps(p, ensure_ascii=False)
    assert text.isascii(), text
    assert p["title"] and p["horizon"]

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


@pytest.mark.parametrize("fn", PAYLOADS, ids=lambda f: f.__name__)
def test_payloads_fit_the_webhook_limit(tmp_repo, fn):  # noqa: F811
    p = fn(build_home({}, NOW))
    assert len(json.dumps({"merge_variables": p}).encode()) <= trmnl_push.DEFAULT_PAYLOAD_LIMIT_BYTES


def test_body_rows_carry_today_and_thirty_nights(tmp_repo):  # noqa: F811
    from automations.scripts.tests.test_home_data import _tracking
    _tracking(tmp_repo, [4, 4])
    p = trmnl_home.body_payload(build_home({}, NOW))
    assert p["levers"] and all(" of " in lv["month"] for lv in p["levers"] if lv["month"])
    assert p["exercise_label"]
    assert " of the last " in p["exercise_month"]


def test_trends_hold_no_sleep_or_exercise(tmp_repo):  # noqa: F811
    names = {r["name"] for r in trmnl_home.trends_payload(build_home({}, NOW))["rows"]}
    assert names == {"Day rating", "Energy", "Mood", "Focus", "Picks done"}


def test_areas_show_life_wheel_and_household(tmp_repo):  # noqa: F811
    groups = trmnl_home.areas_payload(build_home({}, NOW))["groups"]
    assert [g["label"] for g in groups] == ["Life wheel", "Household"]
