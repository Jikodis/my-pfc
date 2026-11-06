"""Unit tests for the TRMNL payload builders that live in trmnl_push.py: Front of mind,
Week, and the two pulse builders home_data folds into the Body first band."""
import datetime as dt
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import trmnl_push  # noqa: E402

WORDS = {"RED", "YELLOW", "GREEN", "NO DATA"}

GROUNDING = [
    {"id": "g1", "title": "Anchor one", "area": "relationship", "status": "active", "created": "2025-01-02"},
    {"id": "g2", "title": "Anchor two", "area": "health", "status": "retired", "created": "2025-01-03"},
    {"id": "g3", "title": "Anchor three", "area": "personal", "status": "active", "created": "2025-01-01"},
]


class TestFrontOfMind(unittest.TestCase):
    @patch("trmnl_push._minutes_since_epoch", return_value=0)
    @patch("trmnl_push.read_ndjson", return_value=GROUNDING)
    def test_active_only_created_ascending(self, _read, _t):
        p = trmnl_push.build_pfc_front_of_mind({}, "2025-01-06")
        self.assertEqual([a["title"] for a in p["anchors"]], ["Anchor three", "Anchor one"])
        self.assertEqual(p["count"], 2)
        self.assertTrue(p["poster"])
        self.assertTrue(p["title"] and p["horizon"])

    @patch("trmnl_push._minutes_since_epoch", return_value=15)  # index 1 of 2
    @patch("trmnl_push.read_ndjson", return_value=GROUNDING)
    def test_rotation_advances_with_clock(self, _read, _t):
        p = trmnl_push.build_pfc_front_of_mind({}, "2025-01-06")
        self.assertEqual(p["anchors_rotated"][0]["title"], "Anchor one")


def _pulse_day(date, deep=90, rem=110, hours=8.0, awake=5, debt=10):
    return {"date": date,
            "health": {"sleep_hours": hours, "awake_minutes": awake,
                       "sleep_deep_minutes": deep, "sleep_rem_minutes": rem,
                       "awakenings_count": 1, "sleep_bedtime": f"{date}T22:00:00-07:00",
                       "sleep_wake_time": f"{date}T06:00:00-07:00"},
            "qqrt": {"score": 3, "sleep_debt": {"avg_shortfall_min": debt}}}


class TestPulseBuilder(unittest.TestCase):
    def _build(self, habit_logs):
        rows = {"data/day-tracking.ndjson": [_pulse_day("2025-01-06", deep=20, hours=5.0, debt=120)],
                "7-habits/_data/habits-daily.ndjson": habit_logs}
        with patch.object(trmnl_push, "read_ndjson", side_effect=lambda p: rows.get(p, [])):
            return trmnl_push.build_pfc_pulse({}, "2025-01-06")

    def test_levers_spell_out_status_sorted_red_first(self):
        p = self._build([])
        marks = [lv["mark"] for lv in p["levers"]]
        self.assertTrue(set(marks) <= WORDS)
        order = [{"RED": 0, "YELLOW": 1, "GREEN": 2}.get(m, 3) for m in marks]
        self.assertEqual(order, sorted(order))
        self.assertEqual(marks[0], "RED")
        self.assertIn(p["verdict_mark"], WORDS)

    def test_exercise_habit_done_today(self):
        p = self._build([{"habit_id": trmnl_push.EXERCISE_HABIT_ID, "date": "2025-01-06", "completed": True}])
        self.assertTrue(p["exercise_done"])
        self.assertEqual(p["exercise_label"], trmnl_push.EXERCISE_LABEL)

    def test_exercise_not_done_on_another_day(self):
        p = self._build([{"habit_id": trmnl_push.EXERCISE_HABIT_ID, "date": "2025-01-05", "completed": True}])
        self.assertFalse(p["exercise_done"])
        self.assertEqual(p["exercise_text"], "not yet")

    def test_no_sleep_data_is_an_empty_shape(self):
        with patch.object(trmnl_push, "read_ndjson", return_value=[]):
            p = trmnl_push.build_pfc_pulse({}, "2025-01-06")
        self.assertEqual(p["levers"], [])
        self.assertEqual(p["verdict_mark"], "NO DATA")


class TestPulseTrend(unittest.TestCase):
    def _build(self, deep):
        rows = [_pulse_day((dt.date(2025, 1, 30) - dt.timedelta(days=i)).isoformat(), deep=deep)
                for i in range(29, -1, -1)]
        with patch.object(trmnl_push, "read_ndjson", return_value=rows):
            return trmnl_push.build_pfc_pulse_trend({}, "2025-01-30")

    def test_counts_point_one_way_and_sort_worst_first(self):
        p = self._build(deep=20)  # deep sleep short every night
        self.assertEqual(p["window"], 30)
        ons = [lv["on"] for lv in p["levers"]]
        self.assertEqual(ons, sorted(ons))
        for lv in p["levers"]:
            self.assertEqual(lv["n"], 30)
            self.assertNotIn("off", lv)
            self.assertIn(lv["status"], WORDS)

    def test_ascii_only(self):
        blob = json.dumps(self._build(deep=20), ensure_ascii=False)
        for bad in ("≥", "≤", "—", "\U0001F7E2", "\U0001F7E1", "\U0001F534"):
            self.assertNotIn(bad, blob)

    def test_no_data_returns_an_empty_shape(self):
        with patch.object(trmnl_push, "read_ndjson", return_value=[]):
            p = trmnl_push.build_pfc_pulse_trend({}, "2025-01-30")
        self.assertEqual(p["levers"], [])
        self.assertIsNone(p["chronic"])
        self.assertEqual(p["green_days"], 0)


class TestWeek(unittest.TestCase):
    def _build(self, cache, filters=None):
        with patch("trmnl_push._read_calendar_cache", return_value=cache), \
                patch("trello_render.load_calendar_filters", return_value=filters or {}):
            return trmnl_push.build_pfc_week({}, "2025-01-05")

    def test_groups_events_by_day_and_flags_stale(self):
        p = self._build({
            "fetched_at": "2025-01-03T21:00:00-07:00",  # more than 26 hours old
            "events": [
                {"summary": "Dentist", "start": {"dateTime": "2025-01-06T15:00:00-07:00"}},
                {"summary": "Team lunch", "start": {"dateTime": "2025-01-06T12:00:00-07:00"}},
                {"summary": "Day off", "start": {"date": "2025-01-07"}, "end": {"date": "2025-01-08"}},
                {"summary": "Last week", "start": {"dateTime": "2024-12-30T10:00:00-07:00"}},
                {"summary": "PFC - 2+1 anchor", "start": {"dateTime": "2025-01-06T16:00:00-07:00"}},
            ]}, {"exclude_titles": ["2+1"], "exclude_calendars": []})
        self.assertTrue(p["stale"])
        self.assertEqual(p["title"], "Week")
        self.assertEqual(len(p["days"]), 7)
        self.assertEqual(p["days"][0]["label"], "Sun 1/5")
        by = {d["label"]: d["events"] for d in p["days"]}
        self.assertEqual([e["title"] for e in by["Mon 1/6"]], ["Team lunch", "Dentist"])
        self.assertEqual(by["Mon 1/6"][0]["time"], "12:00 PM")
        self.assertEqual(by["Tue 1/7"][0]["time"], "all day")
        self.assertEqual(by["Sun 1/5"], [])

    def test_multi_day_all_day_event_spans_its_whole_range(self):
        p = self._build({"fetched_at": "2025-01-05T08:00:00-07:00", "events": [
            {"summary": "Visitors in town", "start": {"date": "2025-01-06"}, "end": {"date": "2025-01-09"}},
            {"summary": "Standup", "start": {"dateTime": "2025-01-07T09:00:00-07:00"}}]})
        by = {d["label"]: [e["title"] for e in d["events"]] for d in p["days"]}
        self.assertEqual(by["Mon 1/6"], ["Visitors in town"])
        self.assertEqual(by["Tue 1/7"], ["Visitors in town", "Standup"])
        self.assertEqual(by["Wed 1/8"], ["Visitors in town"])
        self.assertEqual(by["Thu 1/9"], [])  # end date is exclusive

    def test_every_event_of_a_day_is_shown(self):
        events = [{"summary": f"Event {i}", "start": {"dateTime": f"2025-01-06T{8 + i:02d}:00:00-07:00"}}
                  for i in range(8)]
        p = self._build({"fetched_at": "2025-01-05T08:00:00-07:00", "events": events})
        mon = next(d for d in p["days"] if d["label"] == "Mon 1/6")
        self.assertEqual(len(mon["events"]), 8)
        self.assertEqual(mon["more"], 0)

    def test_titles_are_ascii(self):
        p = self._build({"fetched_at": "2025-01-05T08:00:00-07:00", "events": [
            {"summary": "\U0001F3B8 Guitar — lesson", "start": {"dateTime": "2025-01-06T17:00:00-07:00"}}]})
        title = p["days"][1]["events"][0]["title"]
        self.assertTrue(title.isascii())
        self.assertEqual(title, "Guitar - lesson")

    def test_a_mac_stamp_without_offset_still_parses(self):
        p = self._build({"fetched_at": "2025-01-05T08:15:20:z", "events": []})
        self.assertEqual(p["fetched"], "1/5 8:15 AM")

    def test_no_cache_is_empty_and_stale(self):
        p = self._build(None)
        self.assertEqual(p["days"], [])
        self.assertTrue(p["stale"])


if __name__ == "__main__":
    unittest.main()
