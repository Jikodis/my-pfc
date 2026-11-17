"""Unit tests for review_forms: which review is up, and the form each one shows."""

import json

import pytest

from automations.scripts import review_forms

TODAY = "2025-03-10"


def _nd(rows):
    return "".join(json.dumps(r) + "\n" for r in rows)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "6-tasks/_data").mkdir(parents=True)
    (tmp_path / "5-projects/_data").mkdir(parents=True)
    monkeypatch.setattr(review_forms, "REPO", tmp_path)
    return tmp_path


def _ledger(repo, rows):
    (repo / "data/review-ledger.ndjson").write_text(_nd(rows))


def _row(rid, last_done, cadence=7, **extra):
    return {"id": rid, "label": rid.title(), "tier": "weekly", "cadence_days": cadence,
            "last_done": last_done, **extra}


def test_nothing_due_is_none(repo):
    _ledger(repo, [_row("day-trend-peek", "2025-03-09")])
    assert review_forms.current_review({}, TODAY) is None


def test_most_overdue_first_and_an_empty_form_is_skipped(repo):
    # values-alignment is the most overdue, but no active project lacks values, so
    # its form has nothing to ask and the next due review surfaces instead.
    _ledger(repo, [_row("values-alignment", "2025-01-01"), _row("day-trend-peek", "2025-02-20")])
    (repo / "5-projects/_data/projects.ndjson").write_text(
        _nd([{"id": "proj-20250101-001", "name": "Garden", "active": True, "values": ["Growth"]}]))
    review = review_forms.current_review({}, TODAY)
    assert review["id"] == "day-trend-peek" and review["due_count"] == 2
    assert review["sections"][0]["kind"] == "prompt"


def test_household_status_rows_come_from_the_home_dict(repo):
    _ledger(repo, [_row("household-status", "2025-01-01", cadence=30)])
    home = {"household": {"rows": [{"key": "kitchen", "label": "Kitchen", "light": "red", "note": "Dishes"},
                                   {"key": "garage", "label": "Garage", "light": "green", "note": None}]}}
    section = review_forms.current_review(home, TODAY)["sections"][0]
    assert section["options"] == ["Green", "Yellow", "Red"]
    assert [(r["id"], r["detail"]) for r in section["rows"]] == [("kitchen", "red: Dishes"), ("garage", "green")]


def test_findings_alignment_lists_active_findings_only(repo):
    _ledger(repo, [_row("findings-alignment", "2025-01-01", cadence=30)])
    (repo / "data/findings.ndjson").write_text(_nd([
        {"id": "finding-20250101-001", "status": "active", "finding": "Walks help sleep", "domain": "sleep"},
        {"id": "finding-20250101-002", "status": "superseded", "finding": "Old", "domain": "work"}]))
    rows = review_forms.current_review({}, TODAY)["sections"][0]["rows"]
    assert [r["id"] for r in rows] == ["finding-20250101-001"]


def test_seen_rows_are_left_out_and_said(repo):
    _ledger(repo, [_row("tasks-missing-area", "2025-01-01", seen=["task-20250101-001"])])
    (repo / "6-tasks/_data/tasks.ndjson").write_text(_nd([
        {"id": "task-20250101-001", "status": "open", "description": "One", "project": "none"},
        {"id": "task-20250101-002", "status": "open", "description": "Two", "project": "none"}]))
    review = review_forms.current_review({"areas": {"rows": []}}, TODAY)
    assert [r["id"] for r in review["sections"][0]["rows"]] == ["task-20250101-002"]
    assert "1 rows done earlier" in review["intro"]


def test_a_named_review_is_shown_even_when_not_due(repo):
    _ledger(repo, [_row("usage-audit", "2025-03-09", cadence=30)])
    review = review_forms.current_review({}, TODAY, "usage-audit")
    assert review["id"] == "usage-audit" and review["overdue_days"] is None


def test_every_ledger_id_in_the_template_has_a_form_and_an_owning_skill():
    from pathlib import Path
    from automations.scripts import home_data
    ledger = Path(review_forms.__file__).resolve().parents[2] / "data/review-ledger.ndjson"
    ids = [json.loads(line)["id"] for line in ledger.read_text().splitlines() if line.strip()]
    assert ids
    assert [i for i in ids if i not in home_data.REVIEW_SKILLS] == []
    generic = review_forms.build_form("no-such-review", {}, TODAY)
    # No ledger review falls through to the catch-all "What do you want to change?" form.
    assert [i for i in ids if review_forms.build_form(i, {}, TODAY) == generic] == []


def test_life_wheel_without_items_or_snapshot_rates_the_area_folders(repo):
    _ledger(repo, [_row("life-wheel", "2025-01-01", cadence=30)])
    for name in ("career", "health", "_data"):
        (repo / "2-areas" / name).mkdir(parents=True, exist_ok=True)
    section = review_forms.current_review({"areas": {"rows": []}}, TODAY)["sections"][0]
    assert section["options"] == ["Green", "Yellow", "Red"]
    assert [r["id"] for r in section["rows"]] == ["career", "health"]


def test_household_without_a_snapshot_asks_for_the_rooms(repo):
    _ledger(repo, [_row("household-status", "2025-01-01", cadence=30)])
    section = review_forms.current_review({"household": {"rows": []}}, TODAY)["sections"][0]
    assert section["kind"] == "prompt" and section["id"] == "rooms"
