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
        desc = "---\npfc-id: task-20250511-001\npfc-type: task\n---\n\nBody here\nLine 2"
        result = parse_pfc_frontmatter(desc)
        self.assertEqual(result["pfc-id"], "task-20250511-001")
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
            list_name="✅ Tasks", name="Do thing", body="impact:high",
            label_names=["AA"], due="2025-05-11T12:00:00.000Z", due_complete=False,
        )
        self.assertEqual(c.pfc_id, "task-001")
        self.assertEqual(c.list_name, "✅ Tasks")
        self.assertEqual(c.label_names, ["AA"])

    def test_card_equality(self):
        a = Card("t1", "task", "Tasks", "X", "", [], None, False)
        b = Card("t1", "task", "Tasks", "X", "", [], None, False)
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
        old = _card("t1", list_name="✅ Tasks")
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
    """The board's lists sit in the web page's order, right after 📥 Inbox."""

    def _lists(self):
        return [{"id": "L0", "name": "📥 Inbox", "pos": 100},
                {"id": "L1", "name": "💎 Values", "pos": 200},
                {"id": "L2", "name": "🔭 Visions", "pos": 300}]

    def test_ensure_lists_in_order_changes_nothing(self):
        from trello_render import ensure_lists
        with mpatch("trello_render.list_lists", return_value=self._lists()), \
             mpatch("trello_render.create_list") as cl, mpatch("trello_render.update_list") as ul:
            result = ensure_lists("K", "T", "BOARD", ["💎 Values", "🔭 Visions"])
        self.assertEqual(result, {"💎 Values": "L1", "🔭 Visions": "L2"})
        cl.assert_not_called()
        ul.assert_not_called()

    def test_ensure_lists_creates_a_missing_list_in_its_place(self):
        from trello_render import ensure_lists, LIST_POS_STEP
        lists = self._lists()[:2]
        with mpatch("trello_render.list_lists", return_value=lists), \
             mpatch("trello_render.create_list", return_value={"id": "Lnew"}) as cl, \
             mpatch("trello_render.update_list") as ul:
            result = ensure_lists("K", "T", "BOARD", ["💎 Values", "🔭 Visions"])
        self.assertEqual(result["🔭 Visions"], "Lnew")
        cl.assert_called_once_with("K", "T", "BOARD", "🔭 Visions", pos=100 + 2 * LIST_POS_STEP)
        ul.assert_called_once_with("K", "T", "L1", pos=100 + LIST_POS_STEP)

    def test_ensure_lists_moves_lists_out_of_order(self):
        from trello_render import ensure_lists, LIST_POS_STEP
        with mpatch("trello_render.list_lists", return_value=self._lists()), \
             mpatch("trello_render.create_list") as cl, mpatch("trello_render.update_list") as ul:
            ensure_lists("K", "T", "BOARD", ["🔭 Visions", "💎 Values"])
        cl.assert_not_called()
        self.assertEqual(sorted(c.args[2:] + (c.kwargs["pos"],) for c in ul.call_args_list),
                         [("L1", 100 + 2 * LIST_POS_STEP), ("L2", 100 + LIST_POS_STEP)])

    def test_board_order_follows_the_web_page(self):
        from trello_render import ALL_LIST_NAMES
        self.assertEqual(ALL_LIST_NAMES, [
            "🦸 Body first", "✅ The 2+1", "☀️ Habits", "🗓️ Week",
            "🎯 Focuses", "🛠️ Projects", "📈 Trends",
            "🧭 Areas", "💎 Values", "🔭 Visions", "🧠 Front of mind",
            "✅ Tasks"])


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
        state = {"values": "# Top Values\n\n1. Honesty\n2. Courage\n3. Curiosity\n"}
        cards = render_values(state)
        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[0].name, "1. Honesty")
        self.assertEqual(cards[0].pfc_id, "value-1")

    def test_render_tasks_excludes_done_and_2plus1(self):
        from trello_render import render_tasks
        state = {"tasks": [
            {"id": "t1", "status": "open", "description": "X", "impact": "high", "urgency": "high", "size": "S", "area": "career"},
            {"id": "t2", "status": "done", "description": "Y", "impact": "high", "urgency": "high", "size": "S", "area": "career"},
            {"id": "t3", "status": "open", "description": "Z", "impact": "high", "urgency": "high", "size": "S", "area": "career"},
        ]}
        # AA tier → red plain-color label.
        cards = render_tasks(state, plain_color_labels={"red": "lab_red"}, exclude_2plus1_ids={"t3"})
        ids = [c.pfc_id for c in cards]
        self.assertEqual(ids, ["t1"])
        self.assertEqual(cards[0].label_names, ["_plain:red"])
        # Title format: "<emoji> <TIER> (<SIZE>) - <description>"
        self.assertEqual(cards[0].name, "🔴 AA (S) - X")

    def test_render_tasks_holds_every_task_in_rotation_in_one_list(self):
        from trello_render import render_tasks
        state = {
            "projects": [{"id": "p1", "name": "Build course", "active": True},
                         {"id": "p2", "name": "Paused Thing", "active": False}],
            "tasks": [
                {"id": "task-20250102-001", "status": "open", "description": "standalone", "impact": "low", "urgency": "low", "size": "S", "area": "career", "project": "none"},
                {"id": "task-20250103-001", "status": "open", "description": "Day 1", "impact": "high", "urgency": "high", "size": "S", "area": "career", "project": "p1"},
                {"id": "task-20250104-001", "status": "open", "description": "paused", "impact": "high", "urgency": "high", "size": "S", "area": "career", "project": "p2"},
                {"id": "task-20250105-001", "status": "open", "description": "parked", "impact": "high", "urgency": "high", "size": "S", "area": "career", "deferred": True},
                {"id": "task-20250106-001", "status": "done", "description": "done", "impact": "high", "urgency": "high", "size": "S", "area": "career", "project": "p1"},
                {"id": "task-20250107-001", "status": "open", "description": "Picked", "impact": "high", "urgency": "high", "size": "S", "area": "career"},
            ],
        }
        cards = render_tasks(state, plain_color_labels={"red": "lab_red"}, exclude_2plus1_ids={"task-20250107-001"})
        self.assertEqual({c.pfc_id for c in cards}, {"task-20250102-001", "task-20250103-001"})
        self.assertEqual({c.list_name for c in cards}, {"✅ Tasks"})
        by_id = {c.pfc_id: c for c in cards}
        self.assertEqual(by_id["task-20250103-001"].name, "🔴 AA (S) - Day 1 · Build course")
        self.assertEqual(by_id["task-20250102-001"].name, "🟣 CC (S) - standalone")

    def test_render_tasks_orders_by_priority_then_age(self):
        from trello_render import render_tasks
        def task(tid, impact, urgency):
            return {"id": tid, "status": "open", "description": tid, "impact": impact, "urgency": urgency,
                    "size": "S", "area": "career"}
        state = {"projects": [], "tasks": [task("task-20250302-001", "low", "low"),
                                            task("task-20250202-002", "high", "medium"),
                                            task("task-20250202-001", "high", "medium"),
                                            task("task-20250402-001", "high", "high")]}
        cards = sorted(render_tasks(state), key=lambda c: c.pos)
        self.assertEqual([c.pfc_id for c in cards],
                         ["task-20250402-001", "task-20250202-001", "task-20250202-002", "task-20250302-001"])

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

    def test_render_2plus1_one_critical_with_null_bonus(self):
        from trello_render import render_2plus1, _today_mt
        state = {
            "daily_focus": [{"date": _today_mt(), "critical": ["t1"], "bonus": None,
                             "completed": [], "bonus_completed": False}],
            "tasks": [{"id": "t1", "status": "open", "description": "Only", "impact": "high",
                       "urgency": "high", "size": "S", "area": "career"}],
        }
        cards = render_2plus1(state, plain_color_labels={"red": "x", "purple": "y"})
        self.assertEqual([c.pfc_id for c in cards], ["t1"])

class TestApply(unittest.TestCase):
    def test_apply_creates_calls_create_card_then_due(self):
        from trello_render import apply_creates, Card
        creates = [Card(pfc_id="t1", pfc_type="task", list_name="L", name="X", body="b",
                        label_names=["AA"], due="2025-05-11T12:00:00.000Z", due_complete=False)]
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


class TestCalendarFilters(unittest.TestCase):
    """config/trello_calendar_filters.yaml, applied by calendar_event_excluded: the web
    Week band, the Trello 🗓️ Week list and the TRMNL week screen all filter with it."""

    def _kept(self, events, filters):
        from trello_render import calendar_event_excluded
        return [e["id"] for e in events if not calendar_event_excluded(e, filters)]

    def _evt(self, eid, summary, calendar="primary", **extra):
        return {"id": eid, "summary": summary, "start": {"dateTime": "2025-05-11T10:00:00-06:00"},
                "end": {"dateTime": "2025-05-11T11:00:00-06:00"}, "organizer": {"displayName": calendar}, **extra}

    def test_filters_titles(self):
        events = [self._evt("e1", "Standup"), self._evt("e2", "Doctor visit")]
        self.assertEqual(self._kept(events, {"exclude_titles": ["Standup"]}), ["e2"])

    def test_filters_calendars(self):
        events = [self._evt("e1", "Holiday party", "US Holidays"), self._evt("e2", "Real meeting")]
        self.assertEqual(self._kept(events, {"exclude_calendars": ["US Holidays"]}), ["e2"])

    def test_keeps_recurring_instances(self):
        """Recurrence alone is NOT a reason to hide an event (changed 2025-08-05): most
        real commitments are recurring series, and dropping them blanked the week."""
        events = [self._evt("e1", "Lunch with a friend", recurringEventId="abc"), self._evt("e2", "One-time meeting")]
        self.assertEqual(self._kept(events, {}), ["e1", "e2"])

    def test_hides_pfc_scaffolding_by_title(self):
        events = [self._evt("e1", "PFC - 2+1 anchor (afternoon block)", recurringEventId="abc"),
                  self._evt("e2", "Book club - monthly", recurringEventId="def")]
        self.assertEqual(self._kept(events, {"exclude_titles": ["2+1"]}), ["e2"])

    def test_known_weekly_pattern_hidden_but_its_one_off_still_shows(self):
        """The pattern is known, the EXCEPTION to it is news. Same title, opposite verdicts."""
        events = [self._evt("series", "Standing weekly call", recurringEventId="weekly-series"),
                  self._evt("oneoff", "Friend Visit (One off)")]
        self.assertEqual(self._kept(events, {"exclude_titles_when_recurring": ["Standing weekly call"]}), ["oneoff"])

    def test_prefix_filter_hides_tasks_and_routines(self):
        events = [self._evt("t", "T:Sign up For Gym Class"), self._evt("r", "Routine - evening reset"),
                  self._evt("keep", "Submit Expense Report")]
        self.assertEqual(self._kept(events, {"exclude_prefixes": ["T:", "Routine - "]}), ["keep"])


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
                {"id": "L2", "name": "✅ Tasks", "closed": False},
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


class TestRenderFocusTitles(unittest.TestCase):
    def _state(self):
        return {
            "focus": [
                {"id": "focus-1", "tier": "pursuit", "area": "career",
                 "title": "Weekly build night", "impact": "high",
                 "urgency": "high", "parked": False, "status": "green",
                 "habits": ["course-unit"], "retired_date": None,
                 "landing": "one unit out of the workday start", "link": None},
                {"id": "focus-2", "tier": "pursuit", "area": "recreation",
                 "title": "Guitar", "impact": "medium", "urgency": "medium",
                 "parked": False, "status": "red",
                 "habits": ["stretch-daily"], "retired_date": None,
                 "landing": None, "link": None},
                {"id": "focus-3", "tier": "foundation", "area": "relationship",
                 "title": "Weekly friend call", "impact": "high",
                 "urgency": "medium", "parked": True, "status": "green",
                 "habits": ["weekly-friend-call"], "retired_date": None,
                 "landing": None, "link": None},
            ],
            "focus_status": [],
        }

    def test_title_leads_with_the_impact_urgency_code(self):
        from trello_render import render_focus
        cards = render_focus(self._state())
        by_id = {c.pfc_id: c for c in cards}
        self.assertTrue(by_id["focus-1"].name.startswith("AA "))
        self.assertTrue(by_id["focus-2"].name.startswith("BB "))

    def test_parked_focus_shows_the_parked_marker_not_a_light(self):
        from trello_render import render_focus
        cards = render_focus(self._state())
        parked = next(c for c in cards if c.pfc_id == "focus-3")
        self.assertIn("🅿️", parked.name)
        self.assertNotIn("🟢", parked.name)

    def test_pursuits_sort_by_code_within_their_tier(self):
        from trello_render import render_focus
        cards = [c for c in render_focus(self._state())
                 if c.pfc_id in ("focus-1", "focus-2")]
        self.assertEqual([c.pfc_id for c in cards], ["focus-1", "focus-2"])

    def test_foundations_render_before_pursuits(self):
        from trello_render import render_focus
        ids = [c.pfc_id for c in render_focus(self._state())]
        self.assertLess(ids.index("focus-3"), ids.index("focus-1"))

    def test_body_carries_primary_and_supporting_rates(self):
        from trello_render import render_focus
        state = self._state()
        state["focus_status"] = [{
            "focus_id": "focus-1", "status": "green", "weeks_red": 0,
            "primary": {"habit_id": "course-unit", "completed": 3,
                        "target": 4, "rate": 0.75},
            "supporting": [{"habit_id": "extra", "completed": 1,
                            "target": 4, "rate": 0.25}],
        }]
        card = next(c for c in render_focus(state) if c.pfc_id == "focus-1")
        self.assertIn("Rate: 3 of 4 (75%) via course-unit", card.body)
        self.assertIn("also 1 of 4 (25%) via extra", card.body)

    def test_two_red_weeks_adds_the_forcing_function_line(self):
        from trello_render import render_focus
        state = self._state()
        state["focus_status"] = [{
            "focus_id": "focus-2", "status": "red", "weeks_red": 3,
            "primary": {"habit_id": "stretch-daily", "completed": 0,
                        "target": 4, "rate": 0.0},
            "supporting": [],
        }]
        card = next(c for c in render_focus(state) if c.pfc_id == "focus-2")
        self.assertIn("red 3 weeks running", card.body)


if __name__ == "__main__":
    unittest.main()


from trello_render import load_calendar_cache


class TestCalendarCacheFallback(unittest.TestCase):
    """The nightly systemd timer has no MCP access, so it cannot fetch Calendar
    and was skipping 🗓️ Week entirely — the list only refreshed when
    a live session ran. The cache /pfc-render-trello already writes for TRMNL
    is a usable second source: a slightly older week beats a blank one.
    """

    def _cache(self, tmpdir, fetched_at, events):
        import json
        p = Path(tmpdir) / "calendar-cache.json"
        p.write_text(json.dumps({"fetched_at": fetched_at, "events": events}))
        return p

    def _evt(self, eid, start_date):
        return {"id": eid, "summary": f"Event {eid}",
                "start": {"dateTime": f"{start_date}T10:00:00-06:00"},
                "end": {"dateTime": f"{start_date}T11:00:00-06:00"}}

    def test_missing_file_returns_none(self):
        events, note = load_calendar_cache(Path("/nonexistent/cache.json"),
                                           today="2025-08-29")
        self.assertIsNone(events)
        self.assertIn("no calendar cache", note.lower())

    def test_malformed_file_returns_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "calendar-cache.json"
            p.write_text("{not json")
            events, note = load_calendar_cache(p, today="2025-08-29")
            self.assertIsNone(events)
            self.assertIn("unreadable", note.lower())

    def test_stale_cache_returns_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = self._cache(td, "2025-08-11T22:00:00-06:00",
                            [self._evt("a", "2025-08-13")])
            events, note = load_calendar_cache(p, today="2025-08-29")
            self.assertIsNone(events)
            self.assertIn("stale", note.lower())

    def test_fresh_cache_returns_future_events_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = self._cache(td, "2025-08-27T22:00:00-06:00", [
                self._evt("past", "2025-08-27"),
                self._evt("today", "2025-08-29"),
                self._evt("future", "2025-08-31"),
            ])
            events, note = load_calendar_cache(p, today="2025-08-29")
            self.assertIsNotNone(events)
            ids = sorted(e["id"] for e in events)
            self.assertEqual(ids, ["future", "today"])
            self.assertIn("2025-08-27", note)

    def test_all_day_events_use_start_date(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = self._cache(td, "2025-08-28T22:00:00-06:00", [
                {"id": "allday-past", "summary": "Past",
                 "start": {"date": "2025-08-28"}, "end": {"date": "2025-08-29"}},
                {"id": "allday-future", "summary": "Future",
                 "start": {"date": "2025-08-30"}, "end": {"date": "2025-08-31"}},
            ])
            events, note = load_calendar_cache(p, today="2025-08-29")
            self.assertEqual([e["id"] for e in events], ["allday-future"])

    def test_cache_with_no_future_events_returns_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = self._cache(td, "2025-08-28T22:00:00-06:00",
                            [self._evt("old", "2025-08-21")])
            events, note = load_calendar_cache(p, today="2025-08-29")
            self.assertIsNone(events)
            self.assertIn("no upcoming", note.lower())


class TestRenderHabitsForPhone(unittest.TestCase):
    """Habit cards are tapped on a phone: short titles, a running count, and no
    card for a habit the system measures itself."""

    def _state(self, daily, logs, monthly=None, monthly_logs=None):
        return {"habit_schema": {"daily": daily, "monthly": monthly or []},
                "habits_daily": logs, "habits_monthly": monthly_logs or []}

    def test_daily_title_uses_short_name_and_trailing_week_count(self):
        from trello_render import render_daily_habits
        daily = [{"id": "walk", "name": "20+ minute walk, any time",
                  "short": "Walk 20+ min", "frequency": 3, "area": "health"}]
        logs = [{"habit_id": "walk", "date": "2025-11-04", "completed": True},
                {"habit_id": "walk", "date": "2025-11-06", "completed": True},
                # outside the trailing 7 days ending 11-09
                {"habit_id": "walk", "date": "2025-11-03", "completed": True}]
        with patch("trello_render._today_mt", return_value="2025-11-10"):
            cards = render_daily_habits(self._state(daily, logs))
        self.assertEqual(cards[0].name, "Walk 20+ min: 2/3 past 7 days")
        self.assertFalse(cards[0].due_complete)

    def test_daily_falls_back_to_description_without_short(self):
        from trello_render import render_daily_habits
        daily = [{"id": "read", "name": "Read 15 minutes", "frequency": 7, "area": "growth"}]
        logs = [{"habit_id": "read", "date": "2025-11-10", "completed": True}]
        with patch("trello_render._today_mt", return_value="2025-11-10"):
            cards = render_daily_habits(self._state(daily, logs))
        self.assertEqual(cards[0].name, "Read 15 minutes: 1/7 past 7 days")
        self.assertTrue(cards[0].due_complete)

    def test_skipped_nights_lower_the_target(self):
        from trello_render import render_daily_habits
        daily = [{"id": "stretch", "name": "Evening stretch", "frequency": 3, "area": "family"}]
        logs = [{"habit_id": "stretch", "date": d, "completed": False, "skipped": True}
                for d in ("2025-11-07", "2025-11-08", "2025-11-09", "2025-11-10")]
        with patch("trello_render._today_mt", return_value="2025-11-10"):
            cards = render_daily_habits(self._state(daily, logs))
        # 3 available nights at 3/week -> round(3/7*3) = 1
        self.assertEqual(cards[0].name, "Evening stretch: 0/1 past 7 days")

    def test_auto_derived_habit_gets_no_card(self):
        from trello_render import render_daily_habits
        daily = [{"id": "sleep", "name": "Asleep before 11", "frequency": 7,
                  "area": "health", "auto_derived": True}]
        with patch("trello_render._today_mt", return_value="2025-11-10"):
            self.assertEqual(render_daily_habits(self._state(daily, [])), [])

    def test_monthly_title_uses_short_name(self):
        from trello_render import render_monthly_habits
        monthly = [{"id": "pottery", "name": "Pottery class night (any class counts)",
                    "short": "Pottery night", "frequency": 3, "area": "recreation"}]
        logs = [{"habit_id": "pottery", "date": "2025-11-04", "completed": True}]
        with patch("trello_render._today_mt", return_value="2025-11-10"):
            cards = render_monthly_habits(self._state([], [], monthly, logs))
        self.assertEqual(cards[0].name, "Pottery night: 1/3 this month")

    def test_auto_derived_monthly_habit_gets_no_card(self):
        from trello_render import render_monthly_habits
        monthly = [{"id": "pottery", "name": "Pottery night", "frequency": 3, "area": "recreation",
                    "auto_derived": True},
                   {"id": "clean", "name": "Deep clean", "frequency": 1, "area": "household"}]
        with patch("trello_render._today_mt", return_value="2025-11-10"):
            cards = render_monthly_habits(self._state([], [], monthly, []))
        self.assertEqual([c.pfc_id for c in cards], ["habit-monthly-clean"])

    def test_schema_loader_passes_short_and_auto_derived(self):
        from trello_render import _load_habit_schema
        daily = {h["id"]: h for h in _load_habit_schema()["daily"]}
        self.assertIn("morning-walk", daily)
        self.assertEqual({"short", "auto_derived"} - set(daily["morning-walk"]), set())
