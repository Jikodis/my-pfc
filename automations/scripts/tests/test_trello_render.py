"""Unit tests for trello_render."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trello_render import (
    parse_pfc_frontmatter, serialize_pfc_frontmatter, Card,
)


class TestFrontmatter(unittest.TestCase):
    def test_parse_well_formed(self):
        desc = "---\npfc-id: task-20260510-001\npfc-type: task\n---\n\nBody here\nLine 2"
        result = parse_pfc_frontmatter(desc)
        self.assertEqual(result["pfc-id"], "task-20260510-001")
        self.assertEqual(result["pfc-type"], "task")
        self.assertEqual(result["body"], "Body here\nLine 2")

    def test_parse_missing_frontmatter(self):
        desc = "Just a body, no frontmatter"
        result = parse_pfc_frontmatter(desc)
        self.assertIsNone(result["pfc-id"])
        self.assertIsNone(result["pfc-type"])
        self.assertEqual(result["body"], "Just a body, no frontmatter")

    def test_parse_malformed_delimiter(self):
        desc = "---\npfc-id: task-001\nNO CLOSING DELIM\nBody"
        result = parse_pfc_frontmatter(desc)
        self.assertIsNone(result["pfc-id"])
        self.assertEqual(result["body"], desc)

    def test_parse_frontmatter_missing_pfc_id(self):
        desc = "---\nsome-other-field: value\n---\n\nBody"
        result = parse_pfc_frontmatter(desc)
        self.assertIsNone(result["pfc-id"])

    def test_parse_empty_string(self):
        result = parse_pfc_frontmatter("")
        self.assertIsNone(result["pfc-id"])
        self.assertEqual(result["body"], "")

    def test_serialize_basic(self):
        result = serialize_pfc_frontmatter("task-001", "task", "Body line")
        expected = "---\npfc-id: task-001\npfc-type: task\n---\n\nBody line"
        self.assertEqual(result, expected)

    def test_serialize_empty_body(self):
        result = serialize_pfc_frontmatter("v-001", "value", "")
        self.assertEqual(result, "---\npfc-id: v-001\npfc-type: value\n---\n\n")

    def test_round_trip(self):
        original_body = "Line 1\nLine 2\n  indented"
        ser = serialize_pfc_frontmatter("hyp-001", "hypothesis", original_body)
        parsed = parse_pfc_frontmatter(ser)
        self.assertEqual(parsed["pfc-id"], "hyp-001")
        self.assertEqual(parsed["pfc-type"], "hypothesis")
        self.assertEqual(parsed["body"], original_body)


class TestCardDataclass(unittest.TestCase):
    def test_card_holds_all_fields(self):
        c = Card(
            pfc_id="task-001", pfc_type="task",
            list_name="✅ Actions", name="Do thing", body="impact:high",
            label_names=["AA"], due="2026-05-10T12:00:00.000Z", due_complete=False,
        )
        self.assertEqual(c.pfc_id, "task-001")
        self.assertEqual(c.list_name, "✅ Actions")
        self.assertEqual(c.label_names, ["AA"])

    def test_card_equality(self):
        a = Card("t1", "task", "Actions", "X", "", [], None, False)
        b = Card("t1", "task", "Actions", "X", "", [], None, False)
        self.assertEqual(a, b)


from trello_render import compute_diff


def _card(pfc_id, name="X", body="", list_name="L1", label_names=None, due=None, due_complete=False, checklist=None):
    return Card(pfc_id=pfc_id, pfc_type="task", list_name=list_name,
                name=name, body=body,
                label_names=label_names or [], due=due, due_complete=due_complete,
                checklist=checklist)


class TestDiff(unittest.TestCase):
    def test_empty_inputs_no_ops(self):
        ops = compute_diff(desired=[], current=[])
        self.assertEqual(ops["creates"], [])
        self.assertEqual(ops["updates"], [])
        self.assertEqual(ops["archives"], [])

    def test_one_create(self):
        ops = compute_diff(desired=[_card("t1")], current=[])
        self.assertEqual(len(ops["creates"]), 1)
        self.assertEqual(ops["creates"][0].pfc_id, "t1")

    def test_one_archive(self):
        # Existing card on Trello with pfc-id but no matching desired card → archive.
        ops = compute_diff(desired=[], current=[(_card("t1"), "trello_card_id_1")])
        self.assertEqual(len(ops["archives"]), 1)
        self.assertEqual(ops["archives"][0], "trello_card_id_1")

    def test_no_op_when_match(self):
        # Same card desired and current.
        c = _card("t1", name="Same", body="Same body")
        ops = compute_diff(desired=[c], current=[(c, "tcid")])
        self.assertEqual(ops["creates"], [])
        self.assertEqual(ops["updates"], [])
        self.assertEqual(ops["archives"], [])

    def test_update_on_name_change(self):
        old = _card("t1", name="Old")
        new = _card("t1", name="New")
        ops = compute_diff(desired=[new], current=[(old, "tcid")])
        self.assertEqual(len(ops["updates"]), 1)
        self.assertEqual(ops["updates"][0]["card_id"], "tcid")
        self.assertEqual(ops["updates"][0]["desired"].name, "New")

    def test_update_on_body_change(self):
        old = _card("t1", body="old body")
        new = _card("t1", body="new body")
        ops = compute_diff(desired=[new], current=[(old, "tcid")])
        self.assertEqual(len(ops["updates"]), 1)

    def test_update_on_list_change(self):
        old = _card("t1", list_name="✅ Actions")
        new = _card("t1", list_name="✅ 2+1")
        ops = compute_diff(desired=[new], current=[(old, "tcid")])
        self.assertEqual(len(ops["updates"]), 1)

    def test_update_on_label_change(self):
        old = _card("t1", label_names=["AA"])
        new = _card("t1", label_names=["BA"])
        ops = compute_diff(desired=[new], current=[(old, "tcid")])
        self.assertEqual(len(ops["updates"]), 1)

    def test_archive_card_with_no_pfc_id(self):
        # User added a card directly in Trello (no frontmatter); current set has it with pfc_id=None.
        rogue = Card(pfc_id=None, pfc_type=None, list_name="💎 Values", name="rogue", body="",
                     label_names=[], due=None, due_complete=False)
        ops = compute_diff(desired=[], current=[(rogue, "rogue_tcid")])
        self.assertEqual(len(ops["archives"]), 1)
        self.assertEqual(ops["archives"][0], "rogue_tcid")


from unittest.mock import patch as mpatch

class TestListReconciliation(unittest.TestCase):
    def test_ensure_lists_returns_existing_ids(self):
        from trello_render import ensure_lists
        with mpatch("trello_render.list_lists") as ll, mpatch("trello_render.create_list") as cl:
            ll.return_value = [
                {"id": "L1", "name": "💎 Values", "closed": False},
                {"id": "L2", "name": "🔭 Visions", "closed": False},
            ]
            result = ensure_lists("K", "T", "BOARD", ["💎 Values", "🔭 Visions"])
            self.assertEqual(result["💎 Values"], "L1")
            self.assertEqual(result["🔭 Visions"], "L2")
            cl.assert_not_called()

    def test_ensure_lists_creates_missing(self):
        from trello_render import ensure_lists
        with mpatch("trello_render.list_lists") as ll, mpatch("trello_render.create_list") as cl:
            ll.return_value = [{"id": "L1", "name": "💎 Values", "closed": False}]
            cl.return_value = {"id": "Lnew", "name": "🔭 Visions"}
            result = ensure_lists("K", "T", "BOARD", ["💎 Values", "🔭 Visions"])
            self.assertEqual(result["💎 Values"], "L1")
            self.assertEqual(result["🔭 Visions"], "Lnew")
            cl.assert_called_once_with("K", "T", "BOARD", "🔭 Visions", pos="bottom")


class TestTierPriorityMapping(unittest.TestCase):
    def test_tier_priority_color_collapses_9_to_5(self):
        from trello_render import TIER_PRIORITY_COLOR
        self.assertEqual(TIER_PRIORITY_COLOR["AA"], "red")
        self.assertEqual(TIER_PRIORITY_COLOR["AB"], "orange")
        self.assertEqual(TIER_PRIORITY_COLOR["BA"], "orange")
        self.assertEqual(TIER_PRIORITY_COLOR["AC"], "yellow")
        self.assertEqual(TIER_PRIORITY_COLOR["BB"], "yellow")
        self.assertEqual(TIER_PRIORITY_COLOR["CA"], "yellow")
        self.assertEqual(TIER_PRIORITY_COLOR["BC"], "green")
        self.assertEqual(TIER_PRIORITY_COLOR["CB"], "green")
        self.assertEqual(TIER_PRIORITY_COLOR["CC"], "purple")
        self.assertEqual(set(TIER_PRIORITY_COLOR.values()), {"red", "orange", "yellow", "green", "purple"})

    def test_priority_emoji_matches_label_color(self):
        from trello_render import PRIORITY_TIER_EMOJI
        self.assertEqual(PRIORITY_TIER_EMOJI["AA"], "🔴")
        self.assertEqual(PRIORITY_TIER_EMOJI["AB"], "🟠")
        self.assertEqual(PRIORITY_TIER_EMOJI["BA"], "🟠")
        self.assertEqual(PRIORITY_TIER_EMOJI["AC"], "🟡")
        self.assertEqual(PRIORITY_TIER_EMOJI["BC"], "🟢")
        self.assertEqual(PRIORITY_TIER_EMOJI["CC"], "🟣")

    def test_priority_emoji_codepoints_sort_in_priority_order(self):
        """Trello 'Sort by card name' must place AA cards first, CC cards last.
        Verify emoji codepoints monotonically increase across the priority chain."""
        from trello_render import PRIORITY_TIER_EMOJI
        ordered_emojis = [PRIORITY_TIER_EMOJI[t] for t in ("AA", "AB", "AC", "BC", "CC")]
        codepoints = [ord(e[0]) for e in ordered_emojis]
        self.assertEqual(codepoints, sorted(codepoints),
            f"Emoji codepoints {codepoints} not in ascending order — "
            "alphabetical title sort would mis-order priorities")


class TestRenderers(unittest.TestCase):
    def test_render_values_parses_numbered_list(self):
        from trello_render import render_values
        state = {"values": "# Top Values\n\n1. Love\n2. Faith\n3. Family\n"}
        cards = render_values(state)
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[0].name, "1. Love")
        self.assertEqual(cards[0].pfc_id, "value-1")

    def test_render_areas(self):
        from trello_render import render_areas
        state = {"areas": [{"name": "spiritual", "statement": "stmt"}]}
        cards = render_areas(state)
        self.assertEqual(cards[0].name, "Spiritual")
        self.assertEqual(cards[0].body, "stmt")

    def test_render_projects_with_completion_and_label(self):
        from trello_render import render_projects
        state = {"projects": [{
            "id": "proj-1", "name": "Test", "active": True,
            "impact": "high", "urgency": "medium", "excitement": "high",
            "area": "career", "values": ["Growth"],
            "total_parts": 4, "completed_parts": 1,
            "deadline": "2026-06-01",
        }]}
        # AB tier → orange plain-color label.
        cards = render_projects(state, plain_color_labels={"orange": "lab_orange"})
        self.assertEqual(cards[0].name, "🟠 [25%] Test")
        self.assertEqual(cards[0].label_names, ["_plain:orange"])
        self.assertEqual(cards[0].due, "2026-06-01T12:00:00.000Z")
        self.assertEqual(len(cards[0].checklist), 4)
        self.assertEqual(cards[0].checklist[0], ("Part 1", True))
        self.assertEqual(cards[0].checklist[1], ("Part 2", False))

    def test_render_actions_excludes_done_and_2plus1(self):
        from trello_render import render_actions
        state = {"tasks": [
            {"id": "t1", "status": "open", "description": "X", "impact": "high", "urgency": "high", "size": "S", "area": "career"},
            {"id": "t2", "status": "done", "description": "Y", "impact": "high", "urgency": "high", "size": "S", "area": "career"},
            {"id": "t3", "status": "open", "description": "Z", "impact": "high", "urgency": "high", "size": "S", "area": "career"},
        ]}
        # AA tier → red plain-color label.
        cards = render_actions(state, plain_color_labels={"red": "lab_red"}, exclude_2plus1_ids={"t3"})
        ids = [c.pfc_id for c in cards]
        self.assertEqual(ids, ["t1"])
        self.assertEqual(cards[0].label_names, ["_plain:red"])
        # Title format: "<emoji> <TIER> (<SIZE>) - <description>"
        self.assertEqual(cards[0].name, "🔴 AA (S) - X")

    def test_render_actions_excludes_project_tasks(self):
        from trello_render import render_actions
        state = {
            "projects": [{"id": "p1", "name": "P1", "active": True}],
            "tasks": [
                {"id": "t1", "status": "open", "description": "standalone", "impact": "high", "urgency": "high", "size": "S", "area": "career", "project": "none"},
                {"id": "t2", "status": "open", "description": "linked", "impact": "high", "urgency": "high", "size": "S", "area": "career", "project": "p1"},
            ],
        }
        cards = render_actions(state, plain_color_labels={"red": "lab_red"})
        self.assertEqual([c.pfc_id for c in cards], ["t1"])
        self.assertEqual(cards[0].list_name, "✅ Actions")

    def test_render_project_actions_groups_by_active_project(self):
        from trello_render import render_project_actions
        state = {
            "projects": [
                {"id": "p1", "name": "Sample Course", "active": True},
                {"id": "p2", "name": "Paused Thing", "active": False},
            ],
            "tasks": [
                {"id": "t1", "status": "open", "description": "Day 1", "impact": "high", "urgency": "high", "size": "S", "area": "career", "project": "p1"},
                {"id": "t2", "status": "open", "description": "Day 2", "impact": "high", "urgency": "high", "size": "S", "area": "career", "project": "p1"},
                {"id": "t3", "status": "open", "description": "Standalone", "impact": "low", "urgency": "low", "size": "S", "area": "career", "project": "none"},
                {"id": "t4", "status": "open", "description": "Paused project task", "impact": "high", "urgency": "high", "size": "S", "area": "career", "project": "p2"},
                {"id": "t5", "status": "done", "description": "done active", "impact": "high", "urgency": "high", "size": "S", "area": "career", "project": "p1"},
            ],
        }
        cards = render_project_actions(state, plain_color_labels={"red": "lab_red"})
        # Only t1 + t2 should render (active project, open status).
        self.assertEqual(sorted(c.pfc_id for c in cards), ["t1", "t2"])
        self.assertEqual(cards[0].list_name, "🎯 Sample Course")
        # Excludes 2+1 ids
        cards2 = render_project_actions(state, exclude_2plus1_ids={"t1"})
        self.assertEqual(sorted(c.pfc_id for c in cards2), ["t2"])

    def test_project_list_name_truncates(self):
        from trello_render import _project_list_name, _is_project_list_name, PROJECT_LIST_NAME_MAX
        short = _project_list_name("My Project")
        self.assertEqual(short, "🎯 My Project")
        self.assertTrue(_is_project_list_name(short))
        self.assertFalse(_is_project_list_name("✅ Actions"))
        long_name = "A" * 100
        truncated = _project_list_name(long_name)
        self.assertLessEqual(len(truncated), PROJECT_LIST_NAME_MAX)
        self.assertTrue(truncated.startswith("🎯 "))

    def test_render_2plus1_uses_today_focus(self):
        from trello_render import render_2plus1, _today_mt
        today = _today_mt()
        state = {
            "daily_focus": [{"date": today, "critical": ["t1"], "bonus": "t2"}],
            "tasks": [
                {"id": "t1", "status": "open", "description": "Crit", "impact": "high", "urgency": "high", "size": "S", "area": "career"},
                {"id": "t2", "status": "open", "description": "Bonus", "impact": "low", "urgency": "low", "size": "M", "area": "career"},
            ],
        }
        cards = render_2plus1(state, plain_color_labels={"red": "x", "purple": "y"})
        ids = [c.pfc_id for c in cards]
        self.assertEqual(set(ids), {"t1", "t2"})
        # Title format check
        names = {c.pfc_id: c.name for c in cards}
        self.assertEqual(names["t1"], "🔴 AA (S) - Crit")
        self.assertEqual(names["t2"], "🟣 CC (M) - Bonus")

    def test_render_supplements_active_filter(self):
        from trello_render import render_supplements, _today_mt
        today = _today_mt()
        state = {"supplements": [
            {"id": "s1", "name": "Active", "dose": "100mg", "started": "2020-01-01", "times": ["morning"]},
            {"id": "s2", "name": "Stopped", "dose": "200mg", "started": "2020-01-01", "stopped": "2024-01-01", "times": ["morning"]},
            {"id": "s3", "name": "Future", "dose": "300mg", "started": "2099-01-01", "times": ["morning"]},
        ]}
        cards = render_supplements(state)
        ids = [c.pfc_id for c in cards]
        self.assertEqual(ids, ["s1"])

    def test_render_supplements_title_has_time_prefix(self):
        from trello_render import render_supplements
        state = {"supplements": [
            {"id": "morning", "name": "Vitamin D", "dose": "5000 IU", "started": "2020-01-01", "times": ["morning"]},
            {"id": "afternoon", "name": "Phosphatidyl Serine", "dose": "100mg", "started": "2020-01-01", "times": ["afternoon"]},
            {"id": "bedtime", "name": "Magnesium", "dose": "200mg", "started": "2020-01-01", "times": ["bedtime"]},
            {"id": "multi", "name": "Magnesium", "dose": "200mg", "started": "2020-01-01", "times": ["morning", "afternoon"]},
        ]}
        cards = render_supplements(state)
        by_id = {c.pfc_id: c.name for c in cards}
        self.assertEqual(by_id["morning"], "1. Morning - Vitamin D 5000 IU")
        self.assertEqual(by_id["afternoon"], "2. Afternoon - Phosphatidyl Serine 100mg")
        self.assertEqual(by_id["bedtime"], "4. Bedtime - Magnesium 200mg")
        # Multi-time uses earliest for prefix, lists all in label
        self.assertEqual(by_id["multi"], "1. Morning, Afternoon - Magnesium 200mg")

    def test_render_last_7_days_takes_most_recent(self):
        from trello_render import render_last_7_days
        rows = [{"date": f"2026-04-{d:02d}", "rating": d % 5 + 1} for d in range(1, 30)]
        cards = render_last_7_days({"day_tracking": rows})
        self.assertEqual(len(cards), 7)
        self.assertEqual(cards[-1].pfc_id, "day-2026-04-29")

    def test_render_last_7_days_title_includes_all_metrics(self):
        from trello_render import render_last_7_days
        rows = [{"date": "2026-05-09", "rating": 4, "mood": 4, "energy": 3, "focus": 5}]
        cards = render_last_7_days({"day_tracking": rows})
        self.assertEqual(len(cards), 1)
        # Title: "<date> <day> · ⭐ N/5 · 😊 N · ⚡ N · 🎯 N" — only overall has /5
        self.assertIn("⭐ 4/5", cards[0].name)
        self.assertIn("😊 4", cards[0].name)
        self.assertIn("⚡ 3", cards[0].name)
        self.assertIn("🎯 5", cards[0].name)
        self.assertNotIn("Mood 4/5", cards[0].name)  # no /5 on these


class TestApply(unittest.TestCase):
    def test_apply_creates_calls_create_card_then_due(self):
        from trello_render import apply_creates, Card
        creates = [Card(pfc_id="t1", pfc_type="task", list_name="L", name="X", body="b",
                        label_names=["AA"], due="2026-05-10T12:00:00.000Z", due_complete=False)]
        with mpatch("trello_render.create_card") as cc, mpatch("trello_render.update_card") as uc:
            cc.return_value = {"id": "newcard"}
            apply_creates("K", "T", creates, {"L": "list_id"}, {"AA": "lab_id"})
            cc.assert_called_once()
            uc.assert_called_once()  # for due

    def test_apply_archives_calls_archive_card(self):
        from trello_render import apply_archives
        with mpatch("trello_render.archive_card") as ac:
            apply_archives("K", "T", ["c1", "c2"])
            self.assertEqual(ac.call_count, 2)


class TestCalendarRender(unittest.TestCase):
    def _evt(self, eid="e1", summary="Meeting", start="2026-05-10T10:00:00-06:00", end="2026-05-10T11:00:00-06:00", calendar="primary", location=""):
        return {
            "id": eid, "summary": summary,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
            "organizer": {"displayName": calendar},
            "location": location,
        }

    def test_render_calendar_includes_events(self):
        from trello_render import render_calendar
        events = [self._evt(eid="e1", summary="Doctor visit")]
        filters = {"exclude_titles": [], "exclude_calendars": []}
        cards = render_calendar(events, filters)
        self.assertEqual(len(cards), 1)
        self.assertIn("Doctor visit", cards[0].name)
        self.assertEqual(cards[0].pfc_id, "gcal-e1")

    def test_render_calendar_filters_titles(self):
        from trello_render import render_calendar
        events = [
            self._evt(eid="e1", summary="Standup"),
            self._evt(eid="e2", summary="Doctor visit"),
        ]
        filters = {"exclude_titles": ["Standup"], "exclude_calendars": []}
        cards = render_calendar(events, filters)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].pfc_id, "gcal-e2")

    def test_render_calendar_filters_calendars(self):
        from trello_render import render_calendar
        events = [
            self._evt(eid="e1", summary="Holiday party", calendar="US Holidays"),
            self._evt(eid="e2", summary="Real meeting", calendar="primary"),
        ]
        filters = {"exclude_titles": [], "exclude_calendars": ["US Holidays"]}
        cards = render_calendar(events, filters)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].pfc_id, "gcal-e2")

    def test_render_calendar_handles_all_day_events(self):
        from trello_render import render_calendar
        evt = {
            "id": "e1", "summary": "All day event",
            "start": {"date": "2026-05-10"},
            "end": {"date": "2026-05-11"},
            "organizer": {"displayName": "primary"},
        }
        cards = render_calendar([evt], {"exclude_titles": [], "exclude_calendars": []})
        self.assertEqual(len(cards), 1)
        self.assertIn("All day", cards[0].name)

    def test_render_calendar_handles_iso_timestamp_in_date_field(self):
        """Google Calendar MCP sometimes returns 'date' as ISO timestamp, not YYYY-MM-DD."""
        from trello_render import render_calendar
        evt = {
            "id": "e1", "summary": "All day event",
            "start": {"date": "2026-05-08T00:00:00Z"},
            "end": {"date": "2026-05-09T00:00:00Z"},
            "organizer": {"displayName": "primary"},
        }
        cards = render_calendar([evt], {"exclude_titles": [], "exclude_calendars": []})
        self.assertEqual(len(cards), 1)
        # Should render as 'Fri 05/08 (all day) · ...', not raw ISO timestamp
        self.assertIn("Fri 05/08", cards[0].name)
        self.assertIn("(all day)", cards[0].name)
        self.assertNotIn("00:00:00", cards[0].name)


class TestEmailRender(unittest.TestCase):
    def _msg(self, mid="m1", subject="Test", from_="alice@example.com", snippet="body...", tier="AA"):
        return {
            "id": mid, "subject": subject, "from": from_, "snippet": snippet, "tier": tier,
        }

    def test_render_email_top_tier_always_shows(self):
        from trello_render import render_email
        msgs = [self._msg(tier="AA")]
        cards = render_email(msgs)
        self.assertEqual(len(cards), 1)
        self.assertIn("[AA]", cards[0].name)

    def test_render_email_all_tiers_show(self):
        """All AA-CC tiers render — no fallback gating."""
        from trello_render import render_email
        msgs = [
            self._msg(mid="m1", tier="AA"),
            self._msg(mid="m2", tier="AB"),
            self._msg(mid="m3", tier="BB"),
            self._msg(mid="m4", tier="CA"),
            self._msg(mid="m5", tier="CC"),
        ]
        cards = render_email(msgs)
        ids = sorted([c.pfc_id for c in cards])
        self.assertEqual(ids, ["gmail-m1", "gmail-m2", "gmail-m3", "gmail-m4", "gmail-m5"])

    def test_render_email_unprocessed_never_shows(self):
        from trello_render import render_email
        msgs = [self._msg(mid="m1", tier=None)]
        cards = render_email(msgs)
        self.assertEqual(cards, [])

    def test_render_email_attaches_plain_color_label_when_provided(self):
        from trello_render import render_email
        msgs = [self._msg(mid="m1", tier="AA"), self._msg(mid="m2", tier="BB")]
        # AA → red, BB → yellow under the 5-bucket scheme.
        plain_labels = {"red": "lab_red", "yellow": "lab_yellow"}
        cards = render_email(msgs, plain_color_labels=plain_labels)
        by_id = {c.pfc_id: c for c in cards}
        self.assertEqual(by_id["gmail-m1"].label_names, ["_plain:red"])
        self.assertEqual(by_id["gmail-m2"].label_names, ["_plain:yellow"])

    def test_render_email_no_label_when_color_map_empty(self):
        from trello_render import render_email
        msgs = [self._msg(mid="m1", tier="AA")]
        cards = render_email(msgs)  # no plain_color_labels
        self.assertEqual(cards[0].label_names, [])


class TestAreaLifeWheelLabels(unittest.TestCase):
    def test_render_areas_attaches_color_label_by_score(self):
        from trello_render import render_areas
        state = {
            "areas": [
                {"name": "spiritual", "statement": "stmt"},
                {"name": "career", "statement": "stmt2"},
                {"name": "health", "statement": "stmt3"},
            ],
            "life_wheel": [{"date": "2026-05-01", "scores": {"spiritual": 9, "career": 5, "health": 2}}],
        }
        plain_labels = {"red": "lab_red", "yellow": "lab_yellow", "green": "lab_green"}
        cards = render_areas(state, plain_color_labels=plain_labels)
        by_id = {c.pfc_id: c for c in cards}
        # spiritual=9 → green
        self.assertEqual(by_id["area-spiritual"].label_names, ["_plain:green"])
        # career=5 → yellow
        self.assertEqual(by_id["area-career"].label_names, ["_plain:yellow"])
        # health=2 → red
        self.assertEqual(by_id["area-health"].label_names, ["_plain:red"])

    def test_render_areas_with_string_color_ratings(self):
        """Real-world life-wheel data uses string color names (red/yellow/green) directly."""
        from trello_render import render_areas
        state = {
            "areas": [
                {"name": "spiritual", "statement": "stmt"},
                {"name": "health", "statement": "stmt2"},
            ],
            "life_wheel": [{"date": "2026-05-01", "ratings": {"spiritual": "green", "health": "red"}}],
        }
        plain_labels = {"red": "lab_red", "green": "lab_green"}
        cards = render_areas(state, plain_color_labels=plain_labels)
        by_id = {c.pfc_id: c for c in cards}
        self.assertEqual(by_id["area-spiritual"].label_names, ["_plain:green"])
        self.assertEqual(by_id["area-health"].label_names, ["_plain:red"])

    def test_render_areas_no_label_without_score(self):
        from trello_render import render_areas
        state = {"areas": [{"name": "spiritual", "statement": "stmt"}]}
        cards = render_areas(state, plain_color_labels={"red": "lab_red"})
        self.assertEqual(cards[0].label_names, [])

    def test_render_areas_supports_ratings_field(self):
        """Existing life-wheel rows in user repo use 'ratings' instead of 'scores'."""
        from trello_render import render_areas
        state = {
            "areas": [{"name": "spiritual", "statement": "stmt"}],
            "life_wheel": [{"date": "2026-05-01", "ratings": {"spiritual": 8}}],
        }
        plain_labels = {"lime": "lab_lime"}
        cards = render_areas(state, plain_color_labels=plain_labels)
        self.assertEqual(cards[0].label_names, ["_plain:lime"])

    def test_render_areas_includes_life_wheel_note(self):
        """Per-area notes from life_wheel.ndjson surface in the card body."""
        from trello_render import render_areas
        state = {
            "areas": [
                {"name": "health", "statement": "Sleep, eat, move."},
                {"name": "social", "statement": "Stay connected."},
            ],
            "life_wheel": [{
                "date": "2026-05-03",
                "ratings": {"health": "red", "social": "green"},
                "notes": {"health": "Really bad sleep — need to get on top of it."},
            }],
        }
        cards = render_areas(state, plain_color_labels={"red": "lr", "green": "lg"})
        by_id = {c.pfc_id: c for c in cards}
        # Health has a note → 'Why:' line present
        self.assertIn("🔴 red", by_id["area-health"].body)
        self.assertIn("Why: Really bad sleep", by_id["area-health"].body)
        self.assertIn("Sleep, eat, move.", by_id["area-health"].body)
        # Social has no note → no 'Why:' line, just rating + statement
        self.assertIn("🟢 green", by_id["area-social"].body)
        self.assertNotIn("Why:", by_id["area-social"].body)
        self.assertIn("Stay connected.", by_id["area-social"].body)

    def test_render_areas_numeric_score_shows_slash_10(self):
        from trello_render import render_areas
        state = {
            "areas": [{"name": "career", "statement": "Build the thing."}],
            "life_wheel": [{"date": "2026-05-01", "scores": {"career": 8}}],
        }
        cards = render_areas(state, plain_color_labels={"lime": "ll"})
        self.assertIn("🟢 8/10", cards[0].body)


class TestCalendarRecurringFilter(unittest.TestCase):
    def test_render_calendar_skips_recurring_instances(self):
        from trello_render import render_calendar
        events = [
            {
                "id": "e1", "summary": "Daily Planning",
                "start": {"dateTime": "2026-05-10T09:00:00-06:00"},
                "end": {"dateTime": "2026-05-10T10:00:00-06:00"},
                "organizer": {"displayName": "Work"},
                "recurringEventId": "abc-recurring",  # ← marks as recurring instance
            },
            {
                "id": "e2", "summary": "One-time meeting",
                "start": {"dateTime": "2026-05-10T11:00:00-06:00"},
                "end": {"dateTime": "2026-05-10T11:30:00-06:00"},
                "organizer": {"displayName": "Work"},
            },
        ]
        cards = render_calendar(events, {"exclude_titles": [], "exclude_calendars": []})
        ids = [c.pfc_id for c in cards]
        self.assertEqual(ids, ["gcal-e2"])

    def test_render_calendar_sorts_chronologically(self):
        """Events from multiple calendars get interleaved in time order."""
        from trello_render import render_calendar
        events = [
            # Out-of-order input: Tuesday work, then Monday personal, then Sunday personal.
            {"id": "tue", "summary": "Tuesday work", "start": {"dateTime": "2026-05-12T10:00:00-06:00"}, "end": {"dateTime": "2026-05-12T11:00:00-06:00"}, "organizer": {"displayName": "Work"}},
            {"id": "mon", "summary": "Monday personal", "start": {"dateTime": "2026-05-11T09:00:00-06:00"}, "end": {"dateTime": "2026-05-11T10:00:00-06:00"}, "organizer": {"displayName": "Events"}},
            {"id": "sun_allday", "summary": "Sunday all-day", "start": {"date": "2026-05-10"}, "end": {"date": "2026-05-11"}, "organizer": {"displayName": "Events"}},
            {"id": "sun_timed", "summary": "Sunday timed", "start": {"dateTime": "2026-05-10T15:00:00-06:00"}, "end": {"dateTime": "2026-05-10T16:00:00-06:00"}, "organizer": {"displayName": "Events"}},
        ]
        cards = render_calendar(events, {"exclude_titles": [], "exclude_calendars": []})
        ids = [c.pfc_id for c in cards]
        # Order: Sun all-day, Sun timed (3pm), Mon (9am), Tue (10am)
        self.assertEqual(ids, ["gcal-sun_allday", "gcal-sun_timed", "gcal-mon", "gcal-tue"])


class TestRebuildMode(unittest.TestCase):
    def test_rebuild_archives_all_non_inbox_cards(self):
        from trello_render import rebuild_board
        # Mock all the Trello API calls.
        with mpatch("trello_render.list_lists") as ll, \
             mpatch("trello_render.list_cards_on_board") as lc, \
             mpatch("trello_render.archive_card") as ac:
            # Lists: Inbox + 3 dashboard lists
            ll.return_value = [
                {"id": "L_inbox", "name": "📥 Inbox", "closed": False},
                {"id": "L1", "name": "💎 Values", "closed": False},
                {"id": "L2", "name": "✅ Actions", "closed": False},
            ]
            # 4 cards on Inbox, 3 cards on dashboard lists
            lc.return_value = [
                {"id": "i1", "idList": "L_inbox"},
                {"id": "i2", "idList": "L_inbox"},
                {"id": "i3", "idList": "L_inbox"},
                {"id": "i4", "idList": "L_inbox"},
                {"id": "c1", "idList": "L1"},
                {"id": "c2", "idList": "L2"},
                {"id": "c3", "idList": "L2"},
            ]
            count = rebuild_board("K", "T", "BOARD", confirmed=True)
            self.assertEqual(count, 3)
            archived_ids = [call.args[2] for call in ac.call_args_list]
            self.assertEqual(set(archived_ids), {"c1", "c2", "c3"})
            self.assertNotIn("i1", archived_ids)

    def test_rebuild_aborts_without_confirmation(self):
        from trello_render import rebuild_board
        with mpatch("trello_render.archive_card") as ac, \
             mpatch("trello_render.list_cards_on_board") as lc, \
             mpatch("trello_render.list_lists") as ll:
            ll.return_value = []
            lc.return_value = []
            count = rebuild_board("K", "T", "BOARD", confirmed=False)
            self.assertEqual(count, 0)
            ac.assert_not_called()


class TestResetListMode(unittest.TestCase):
    def test_reset_list_archives_only_target_list(self):
        from trello_render import reset_list
        with mpatch("trello_render.list_lists") as ll, \
             mpatch("trello_render.list_cards_on_board") as lc, \
             mpatch("trello_render.archive_card") as ac:
            ll.return_value = [
                {"id": "L_a", "name": "💎 Values", "closed": False},
                {"id": "L_b", "name": "🛠️ Projects", "closed": False},
            ]
            lc.return_value = [
                {"id": "c1", "idList": "L_a"},
                {"id": "c2", "idList": "L_a"},
                {"id": "c3", "idList": "L_b"},
            ]
            count = reset_list("K", "T", "BOARD", "💎 Values", confirmed=True)
            self.assertEqual(count, 2)
            archived_ids = [call.args[2] for call in ac.call_args_list]
            self.assertEqual(set(archived_ids), {"c1", "c2"})

    def test_reset_list_refuses_inbox(self):
        from trello_render import reset_list
        with mpatch("trello_render.archive_card") as ac:
            count = reset_list("K", "T", "BOARD", "📥 Inbox", confirmed=True)
            self.assertEqual(count, 0)
            ac.assert_not_called()

    def test_reset_list_refuses_unknown_list(self):
        from trello_render import reset_list
        with mpatch("trello_render.list_lists") as ll, \
             mpatch("trello_render.archive_card") as ac:
            ll.return_value = [{"id": "L1", "name": "💎 Values", "closed": False}]
            count = reset_list("K", "T", "BOARD", "🔭 Visions Wrong Name", confirmed=True)
            self.assertEqual(count, -1)
            ac.assert_not_called()


if __name__ == "__main__":
    unittest.main()
