"""Unit tests for feature_use — verdict rules, windows, and what counts as the user's use."""
from datetime import date

from automations.scripts import feature_use as fu


def test_verdict_rules():
    assert fu.verdict(0.8, 0.1) == "keep"
    assert fu.verdict(0.1, 0.9) == "just use it"      # worked before, lapsed
    assert fu.verdict(0.4, 0.2) == "just use it"      # climbing
    assert fu.verdict(0.3, 0.3) == "change cadence"   # steady half-use
    assert fu.verdict(0.05, 0.1) == "change feature"  # never caught on
    assert fu.verdict(0.1, None) == "just use it"     # too new to judge
    assert fu.verdict(None, None) == "on demand"


def test_window_has_and_clamp():
    w = fu.Window(date(2025, 10, 17), date(2025, 11, 15))
    assert w.days == 30
    assert w.has("2025-11-15T08:00:00-07:00") and not w.has("2025-10-16")
    assert w.clamp("2025-11-01").days == 15
    assert w.clamp("2025-12-01").days == 0


class FakeData:
    def __init__(self, **kw):
        self.today = date(2025, 11, 15)
        for k in ("habits_daily", "habits_monthly", "daily_focus", "task_events", "day_tracking"):
            setattr(self, k, kw.get(k, []))


W = fu.Window(date(2025, 11, 9), date(2025, 11, 15))


def test_habit_ticks_skip_system_rows():
    d = FakeData(habits_daily=[
        {"habit_id": "a", "date": "2025-11-10", "completed": True, "source": "web"},
        {"habit_id": "b", "date": "2025-11-11", "completed": True, "source": "fitbit-derived"},
        {"habit_id": "c", "date": "2025-11-12", "completed": False, "skipped": True},
    ])
    assert fu.m_habit_ticks(d, W) == (1, 7)


def test_finish_2plus1_counts_task_closed_that_day():
    d = FakeData(
        daily_focus=[{"date": "2025-11-10", "critical": ["t1"], "completed": []},
                     {"date": "2025-11-11", "critical": ["t2"], "completed": []}],
        task_events=[{"task_id": "t1", "event": "completed", "timestamp": "2025-11-10"}])
    assert fu.m_finish_2plus1(d, W) == (1, 2)


def test_report_builds_on_live_repo():
    rep = fu.build(date(2025, 11, 15))
    ids = {f["id"] for f in rep["features"]}
    assert {"day-rating", "habit-ticks", "reviews", "focus-repick"} <= ids
    assert fu.markdown(rep).startswith("Feature scorecard")
