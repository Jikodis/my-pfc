"""The reMarkable pages: stroke parsing, the page marks, and turning a reading into writes."""
from __future__ import annotations

import json
import struct
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("PIL", reason="the reMarkable pages need Pillow (pip install pillow)")

import remarkable_lines as rl  # noqa: E402
import remarkable_pages as rp  # noqa: E402
import remarkable_sync as rs  # noqa: E402


# ---------------------------------------------------------------- a v6 file, built by hand
def _varuint(n):
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def _tag(index, kind):
    return _varuint(index << 4 | kind)


def _id(index, a=0, b=1):
    return _tag(index, 0xF) + bytes([a]) + _varuint(b)


def _line_block(points, tool=17, colour=0, argb=None, deleted=0):
    pts = b"".join(struct.pack("<ffHHBB", x, y, 0, 0, 0, 0) for x, y in points)
    value = (_tag(1, 0x4) + struct.pack("<I", tool) + _tag(2, 0x4) + struct.pack("<I", colour)
             + _tag(3, 0x8) + struct.pack("<d", 1.0) + _tag(4, 0x4) + struct.pack("<f", 0.0)
             + _tag(5, 0xC) + struct.pack("<I", len(pts)) + pts + _id(6))
    if argb is not None:
        value += _tag(8, 0x4) + struct.pack("<I", argb)
    sub = bytes([0x03]) + value
    body = _id(1) + _id(2) + _id(3) + _id(4) + _tag(5, 0x4) + struct.pack("<I", deleted)
    if not deleted:
        body += _tag(6, 0xC) + struct.pack("<I", len(sub)) + sub
    return struct.pack("<I", len(body)) + bytes([0, 1, 2, 0x05]) + body


def _other_block():
    body = b"\x01\x02\x03"
    return struct.pack("<I", len(body)) + bytes([0, 1, 1, 0x09]) + body


def _rm(*blocks):
    return rl.HEADER + b" " * (43 - len(rl.HEADER)) + b"".join(blocks)


def test_reads_strokes_and_skips_other_blocks_erasers_and_deleted():
    data = _rm(_other_block(),
               _line_block([(-810, 10), (0, 20)], colour=7),
               _line_block([(1, 1)], tool=6),  # eraser
               _line_block([(2, 2)], deleted=1),
               _line_block([(5, 5), (6, 6)], tool=18, colour=9, argb=0xFFACFF85))
    strokes = rl.read_strokes(data)
    assert len(strokes) == 2
    assert strokes[0]["colour"] == 7 and strokes[0]["points"] == [(-810.0, 10.0), (0.0, 20.0)]
    assert strokes[1]["tool"] == 18 and strokes[1]["rgb"] == "#acff85"


def test_rejects_a_file_that_is_not_v6():
    with pytest.raises(ValueError):
        rl.read_strokes(b"reMarkable .lines file, version=5          ")


def test_overlay_maps_the_centre_line_to_the_middle_of_the_page(tmp_path):
    from PIL import Image
    base = tmp_path / "base.png"
    Image.new("RGB", (1620, 2160), "white").save(base)
    out = tmp_path / "out.png"
    rl.overlay(base, [{"tool": 17, "colour": 0, "rgb": None, "points": [(0, 100), (0, 300)]}], out)
    im = Image.open(out)
    assert im.getpixel((810, 200)) == (0, 0, 0)
    assert im.getpixel((300, 200)) == (255, 255, 255)


def test_zip_page_order_reads_cpages(tmp_path):
    z = tmp_path / "doc.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("abc.content", json.dumps({"cPages": {"pages": [{"id": "p2"}, {"id": "gone", "deleted": {"timestamp": "1:2", "value": 1}}]}}))
        f.writestr("abc/p2.rm", _rm(_line_block([(0, 0), (1, 1)])))
    assert rl.page_order(z) == ["p2"]
    assert len(rl.strokes_from_zip(z)["p2"]) == 1


# ---------------------------------------------------------------- pages
HOME = {
    "date": "2025-01-04",
    "body": {"sleep_hours": 7.1, "awake_minutes": 20, "window": 30},
    "pulse": {"verdict_mark": "YELLOW", "verdict": "Steady.", "move": "Lights out on time.",
              "levers": [{"label": "REM", "value": "90m", "mark": "RED", "on": 3, "n": 30},
                         {"label": "Bedtime", "value": "10:30 PM", "mark": "GREEN", "on": 9, "n": 30}]},
    "rate_target": {"date": "2025-01-03", "unrated": True},
    "picks": {"critical": [{"id": "t1", "title": "Write the letter", "done": False},
                           {"id": "t2", "title": "Renew the passport", "done": True}],
              "bonus": {"id": "t3", "title": "Read a chapter", "done": False}},
    "needs_you": [], "handoffs": [{"id": "t9", "title": "x"}],
    "habits": [{"id": "read-15-min", "title": "Read 15 min", "cadence": "daily", "logged_today": False},
               {"id": "morning-walk", "title": "Morning walk", "cadence": "daily", "logged_today": True},
               {"id": "sleep-on-time", "title": "Sleep on time", "cadence": "daily", "auto_derived": True},
               {"id": "system-review", "title": "System review", "cadence": "monthly", "logged_today": False}],
    "week": [{"date": "2025-01-04", "events": [{"start": "2025-01-04T12:00:00-07:00", "title": "Lunch"}]}],
    "focuses": {"foundation": [{"focus_id": "f1", "title": "Sleep", "light": "red", "parked": False,
                                "primary": {"completed": 9, "target": 28}}], "pursuit": [], "consuming": []},
    "projects": {"active": [{"id": "proj-1", "name": "Project Foo", "pct": 20, "next_task": {"title": "Draft the outline"},
                             "stalled": False, "days_idle": 2}]},
    "trends": [{"name": "Mood", "light": "green", "why": "avg 4"}],
    "plate": {"free": 112, "committed": 100.0, "pct": 89},
    "areas": {"rows": [{"key": "health", "label": "Health", "light": "red", "note": "Sleep."},
                       {"key": "career", "label": "Career", "light": "green", "note": None}]},
    "household": {"rows": [{"label": "Kitchen", "light": "yellow"}, {"label": "Garage", "light": "green"}]},
    "values": ["Health", "Learning"], "question_of_day": {"text": "What matters?"},
    "anchors": [{"title": "Upstream first"}],
    "visions": [{"id": "v1", "title": "Become a great cook"}], "vision_of_day": {"id": "v1", "title": "Become a great cook"},
}


REVIEW = {"id": "project-progress", "label": "Project progress review", "tier": "monthly", "overdue_days": 3,
          "due_count": 4, "intro": "A monthly review.",
          "sections": [{"kind": "choices", "title": "Active projects", "options": ["On track", "Stuck", "Park", "Done"],
                        "rows": [{"id": "p1", "title": "Project Foo", "detail": "20% done"}], "note": True, "hint": None,
                        "more": 0},
                       {"kind": "prompt", "id": "why", "question": "What is in the way?", "lines": 3}]}


TASKS = [{"id": f"task-{n}", "description": f"Task number {n}", "code": "AB", "project_name": None,
          "area": "health", "deadline": None} for n in range(40)]


def _pages():
    return rp.build_pages(HOME, {"1 - Today": [{"at": "2025-01-04T09:00", "page": "1 - Today", "text": "Saved: rated Friday 4/4/4"}]}, review=REVIEW, tasks=TASKS)


def _kinds(page):
    return [(m["kind"], m.get("field") or m.get("id") or m.get("page")) for m in page.marks]


def test_pages_follow_the_web_order_and_list_only_what_a_pen_can_change():
    inbox, today, quarter, always, review, tasks = _pages()
    assert [p.name for p in (inbox, today, quarter, always, review, tasks)] == rp.PAGE_NAMES
    assert _kinds(inbox) == [("inbox", None)]
    # left column first: the rating rows (with the web card's optional row), the
    # daily habit still to log (logged and automatic ones have no box), the monthly
    # habit, the note box (an unrated day: Week moves under the 2+1 to make room);
    # then the open picks, each with done and swap boxes (the done pick has none)
    assert _kinds(today) == [("rating", "energy"), ("rating", "mood"), ("rating", "focus"),
                             ("rating", "hyperfocused"), ("habit", "read-15-min"),
                             ("habit", "system-review"), ("note", "Today"), ("task", "t1"), ("swap", "t1"), ("task", "t3"), ("swap", "t3")]
    assert all(m["date"] == "2025-01-03" for m in today.marks if m["kind"] == "rating")
    assert [m["kind"] for m in quarter.marks] == ["park", "note"]
    assert _kinds(always) == [("area", "health"), ("area", "career"), ("note", "Always")]
    assert _kinds(review) == [("review-skip", "project-progress"), ("review-row", "p1"), ("review-prompt", "why")]
    for page in (inbox, today, quarter, always, review):
        for m in page.marks:
            x0, y0, x1, y1 = m["box"]
            assert 0 <= x0 < x1 <= rp.W and 0 <= y0 < y1 <= rp.H, (page.name, m)


def test_suggestions_get_pick_boxes_with_the_days_picks():
    h = dict(HOME, suggested=[{"id": "s1", "title": "Fix the gate"}], pick_date="2025-01-04",
             picks=dict(HOME["picks"], critical_ids=["t1", "t2"], bonus_id="t3"))
    pick = next(m for m in rp.build_pages(h, {}, review=None, tasks=[])[1].marks if m["kind"] == "pick")
    assert (pick["id"], pick["date"], pick["critical"], pick["bonus"]) == ("s1", "2025-01-04", ["t1", "t2"], "t3")


def test_the_task_list_runs_over_several_pages_with_every_task_once():
    tasks = _pages()[5]
    assert len(tasks.pages) > 1
    ids = [m["id"] for p in tasks.pages for m in p.marks if m["kind"] == "task"]
    assert ids == [t["id"] for t in TASKS]
    first = tasks.pages[0].marks
    assert [m["kind"] for m in first[:3]] == ["task", "drop", "task-note"]
    for p in tasks.pages:
        for m in p.marks:
            x0, y0, x1, y1 = m["box"]
            assert 0 <= x0 < x1 <= rp.W and 0 <= y0 < y1 <= rp.H, m


def test_task_page_ticks_drops_and_notes():
    marks = _pages()[5].pages[0].marks
    reading = {"ratings": {}, "ticked": [0, 4], "areas": [], "notes": [], "review": {}, "other": "",
               "task_notes": {"2": "move to next week"}}
    assert [c for c, _ in rs.plan_writes(reading, marks)] == [
        ["complete-task", "task-0"], ["drop-task", "task-1"],
        ["trello-inbox", 'Note on task "Task number 0" (task-0): move to next week']]


def test_a_rated_day_has_no_rating_rows():
    h = dict(HOME, rate_target={"date": "2025-01-03", "unrated": False})
    assert not [m for m in rp.build_pages(h, {}, review=None, tasks=[])[1].marks if m["kind"] == "rating"]


def test_no_review_due_draws_an_empty_review_page():
    assert rp.build_pages(HOME, {}, review=None, tasks=[])[4].marks == []


# ---------------------------------------------------------------- reading → writes
def _spot(marks, kind, key=None):
    return next(i for i, m in enumerate(marks) if m["kind"] == kind
                and key in (None, m.get("field"), m.get("id"), m.get("page")))


def test_plan_writes_turns_a_today_reading_into_web_write_commands():
    marks = _pages()[1].marks
    reading = rs.parse_reading('Sure: {"ratings": {"energy": 4, "mood": 3, "focus": 5, '
                               '"hyperfocused": "No"}, "ticked": [%d, %d, %d, 99], "areas": [], '
                               '"notes": ["Make reading 20 minutes", " "], "other": ""}'
                               % (_spot(marks, "habit"), _spot(marks, "task", "t3"), _spot(marks, "swap", "t1")))
    assert [c for c, _ in rs.plan_writes(reading, marks)] == [
        ["rate-day", "2025-01-03", "4", "3", "5", "hyper:no"],
        ["log-habit", "read-15-min", "2025-01-04"],
        ["complete-task", "t3"],
        ["drop-pick", "2025-01-04", "t1"],
        ["trello-inbox", "From the Today page: Make reading 20 minutes"]]


def test_a_swap_and_a_suggestion_ticked_together_replace_the_pick():
    h = dict(HOME, suggested=[{"id": "s1", "title": "Fix the gate"}], pick_date="2025-01-04",
             picks=dict(HOME["picks"], critical_ids=["t1", "t2"], bonus_id="t3"))
    marks = rp.build_pages(h, {}, review=None, tasks=[])[1].marks
    reading = {"ratings": {}, "ticked": [_spot(marks, "swap", "t1"), _spot(marks, "pick", "s1")], "areas": [],
               "notes": [], "review": {}, "other": ""}
    assert [c for c, _ in rs.plan_writes(reading, marks)] == [
        ["drop-pick", "2025-01-04", "t1"], ["set-picks", "2025-01-04", "t2", "s1", "bonus:t3"]]


def test_quarter_and_always_readings():
    quarter, always = _pages()[2], _pages()[3]
    q = rs.plan_writes({"ratings": {}, "ticked": [0], "areas": [], "notes": ["Project Foo: outline drafted"],
                        "review": {}, "other": ""}, quarter.marks)
    assert [c for c, _ in q] == [["park-focus", quarter.marks[0]["id"], "on"],
                                 ["trello-inbox", "From the This quarter page: Project Foo: outline drafted"]]
    a = rs.plan_writes({"ratings": {}, "ticked": [], "areas": [{"spot": 0, "light": "Yellow", "why": "slept badly"},
                                                               {"spot": 2, "light": "red"}],
                        "notes": [], "review": {}, "other": ""}, always.marks)
    assert [c for c, _ in a] == [["set-area", "health", "yellow", "note:slept badly"]]


def test_review_answers_go_to_pfc_review_as_one_form_and_misreads_are_dropped():
    marks = _pages()[4].marks
    reading = {"ratings": {}, "ticked": [0], "areas": [], "notes": [], "other": "",
               "review": {"choices": {"1": "Stuck"}, "notes": {"1": "waiting on a reply"},
                          "prompts": {"2": "No quiet time", "7": "x"}}}
    (cmd, _), = rs.plan_writes(reading, marks)
    assert cmd[:2] == ["review", "project-progress"]
    assert json.loads(cmd[2]) == {"review": "project-progress", "choices": {"p1": "Stuck"},
                                  "notes": {"p1": "waiting on a reply"}, "prompts": {"why": "No quiet time"},
                                  "shown": ["p1"]}
    misread = dict(reading, review={"choices": {"1": "Stck"}})
    assert [c for c, _ in rs.plan_writes(misread, marks)] == [["stamp-review", "project-progress"]]


def test_a_partial_rating_is_never_saved():
    marks = _pages()[1].marks
    reading = {"ratings": {"energy": 4, "mood": None, "focus": 6}, "ticked": [], "areas": [], "notes": [],
               "review": {}, "other": ""}
    assert rs.plan_writes(reading, marks) == [(None, "rating not saved: only energy circled")]


def test_page_changed_waits_for_him_to_finish_writing():
    now = datetime(2025, 1, 4, 18, 0, tzinfo=timezone.utc)
    doc = {"modified": "2025-01-04T17:00:00Z"}
    stat = lambda mins: {"ModifiedClient": (now - timedelta(minutes=mins)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert rs.page_changed(doc, {"ModifiedClient": "2025-01-04T17:00:00Z"}, now) == "no"
    assert rs.page_changed(doc, stat(2), now) == "writing"
    assert rs.page_changed(doc, stat(20), now) == "yes"
    assert rs.page_changed(None, stat(20), now) == "no"


def test_upload_package_opens_with_the_ballpoint_on_medium(tmp_path):
    """rmapi's own PDF upload sets the fineliner as the page's last pen; the package
    carries the ballpoint instead."""
    pdf = tmp_path / "1 - Today.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    pkg = rs.rmdoc_for(pdf, tmp_path / "out")
    assert pkg.name == "1 - Today.rmdoc"
    with zipfile.ZipFile(pkg) as z:
        names = z.namelist()
        content = json.loads(z.read(next(n for n in names if n.endswith(".content"))))
        assert z.read(next(n for n in names if n.endswith(".pdf"))) == b"%PDF-1.4 test"
    assert content["fileType"] == "pdf"
    meta = content["extraMetadata"]
    assert meta["LastTool"] == "Ballpointv2" and meta["LastPen"] == "Ballpointv2"
    assert meta["LastBallpointv2Size"] == "2"


def test_free_writing_on_a_page_with_no_note_box_still_reaches_the_inbox():
    """The review page has no note box; its margin notes still reach the inbox."""
    marks = [{"kind": "review-skip", "id": "vision-activation", "label": "skip", "box": [0, 0, 1, 1]}]
    reading = rs.parse_reading(json.dumps({"notes": ["Ask me what makes each area good"],
                                           "other": "arrow pointing at row 3"}))
    cmds = [c for c, _ in rs.plan_writes(reading, marks, "4 - Review")]
    assert ["trello-inbox", "From the 4 - Review page: Ask me what makes each area good"] in cmds
    assert ["trello-inbox", "Also written on the 4 - Review page: arrow pointing at row 3"] in cmds


def test_every_page_shows_the_agent_replies_and_the_today_page_fits():
    inbox, today, quarter, always, review, tasks = _pages()
    for page in (inbox, today, quarter, always, review, *tasks.pages):
        corner = page.im.crop((rp.REPLY_X, 20, rp.REPLY_X + 90, 54))
        assert corner.convert("L").getextrema()[0] < 128, page.name  # "Agent" is drawn
    # the reply in the fixture is on the Today page
    words = today.im.crop((rp.REPLY_X, 54, rp.W - rp.M, 84)).convert("L")
    assert words.getextrema()[0] < 200
    # nothing runs off the bottom, rated or not
    for unrated in (True, False):
        h = dict(HOME, rate_target={"date": "2025-01-03", "unrated": unrated})
        page = rp.build_pages(h, {}, review=None, tasks=[])[1]
        assert page.im.crop((0, rp.H - 16, rp.W, rp.H)).convert("L").getextrema()[0] > 200


def test_replies_are_kept_per_page_and_review_questions_are_read_from_a_table(tmp_path):
    import remarkable_replies as rr
    store, now = tmp_path / "r.ndjson", datetime(2025, 1, 5, 8, 0, tzinfo=rr.TZ)
    rr.add("Today", "Saved: habit: Read 15 min", store, now)
    rr.add("4 - Review", "Saved your project-progress answers", store, now)
    assert [r["text"] for r in rr.recent("1 - Today", store, now)] == ["Saved: habit: Read 15 min"]
    assert rr.recent("1 - Today", store, now + timedelta(hours=rr.KEEP_HOURS + 1)) == []
    table = "| # | Question | Default if no answer |\n|---|---|---|\n| 1 | Which book? | The first one listed |"
    assert rr.questions(table) == [(1, "Which book?", "The first one listed")]
    m = rr.FROM.match("From the 5 - Tasks page: call first")
    assert rr.page_of(m.group(1)) == "5 - Tasks" and m.group(2) == "call first"


def test_inbox_outcomes_land_on_the_page_each_note_came_from(tmp_path):
    import remarkable_replies as rr
    from datetime import datetime
    store, now = tmp_path / "r.ndjson", datetime(2025, 1, 2, 8, 0, tzinfo=rr.TZ)
    out = ("- 🟢 From the 1 - Today page: drop reading → habit reading retired\n"
           "- 🟡 From the Review page: what about X → left (❓ which X?)\n"
           "🟢 Buy milk → task added\n"
           "a line that is not a card\n")
    assert rr.from_inbox(out, store, now) == 3
    assert [r["text"] for r in rr.recent("1 - Today", store, now)] == ['"drop reading" → habit reading retired']
    assert rr.recent("4 - Review", store, now)[0]["text"].startswith("Waiting:")
    assert rr.recent("0 - Inbox", store, now)[0]["text"] == '"Buy milk" → task added'


def test_reply_pages_match_the_drawn_pages():
    import remarkable_replies as rr
    assert rr.PAGES == rp.PAGE_NAMES
    assert rr.page_of("Today") == "1 - Today" and rr.page_of("5 - Tasks, page 3") == "5 - Tasks"


# ---------------------------------------------------------------- duplicate pages
def _cache(tmp_path, docs):
    """A minimal rmapi tree.cache: (id, name, parent, modified ms, opened ms, deleted)."""
    path = tmp_path / "tree.cache"
    path.write_text(json.dumps({"Docs": [
        {"DocumentID": i, "Metadata": {"visibleName": n, "type": "DocumentType", "parent": p,
                                       "lastModified": str(m), "lastOpened": str(o) if o else "",
                                       "deleted": d}}
        for i, n, p, m, o, d in docs]}))
    return path


def _ms(dt):
    return int(dt.timestamp() * 1000)


def test_cloud_copies_lists_every_top_level_copy_of_a_page(tmp_path, monkeypatch):
    now = datetime(2025, 1, 6, 4, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(rs, "RMAPI_CACHE", _cache(tmp_path, [
        ("a", "1 - Today", "", _ms(now), _ms(now), False),
        ("b", "1 - Today", "", _ms(now) - 1000, None, False),
        ("c", "1 - Today", "folder-id", _ms(now), None, False),   # in a folder: not a page
        ("d", "1 - Today", "", _ms(now), None, True),             # deleted
        ("e", "0 - Inbox", "", _ms(now), None, False)]))
    copies = rs.cloud_copies(["1 - Today", "0 - Inbox", "3 - Always"])
    assert [c["id"] for c in copies["1 - Today"]] == ["a", "b"]
    assert copies["1 - Today"][0]["opened"] == now and copies["1 - Today"][1]["opened"] is None
    assert [c["id"] for c in copies["0 - Inbox"]] == ["e"] and copies["3 - Always"] == []


def test_cloud_copies_is_empty_when_the_cache_cannot_be_read(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "RMAPI_CACHE", tmp_path / "missing")
    assert rs.cloud_copies(["1 - Today"]) == {}


def test_a_page_opened_or_written_on_recently_is_left_alone():
    """Redrawing a page that is open deletes it under the reader and the tablet keeps
    its own copy as a duplicate, so a page opened in the last OPEN_MINUTES waits."""
    now = datetime(2025, 1, 6, 4, 0, tzinfo=timezone.utc)
    ago = lambda mins: now - timedelta(minutes=mins)
    assert rs.busy([{"modified": ago(60), "opened": ago(rs.OPEN_MINUTES - 1)}], now) == "opened"
    assert rs.busy([{"modified": ago(rs.SETTLE_MINUTES - 1), "opened": None}], now) == "writing"
    assert rs.busy([{"modified": ago(60), "opened": ago(rs.OPEN_MINUTES + 1)}], now) is None
    assert rs.busy([{"modified": ago(60), "opened": ago(60)},
                    {"modified": ago(2), "opened": ago(60)}], now) == "writing"
    assert rs.busy([], now) is None
    # the page this script just uploaded is not new writing
    assert rs.busy([{"id": "mine", "modified": ago(1), "opened": None}], now, own_id="mine") is None
    assert rs.busy([{"id": "mine", "modified": ago(1), "opened": ago(1)}], now, own_id="mine") == "opened"


def test_each_page_picture_comes_back_out_of_an_uploaded_pdf(tmp_path):
    """A stray copy is read against its own picture, not today's drawing."""
    from PIL import Image
    ims = [Image.new("RGB", (60, 80), c) for c in ("white", "red")]
    pdf = tmp_path / "doc.pdf"
    ims[0].save(pdf, "PDF", resolution=229, save_all=True, append_images=ims[1:])
    out = rs.pdf_page_images(pdf.read_bytes(), tmp_path / "bases")
    assert len(out) == 2
    got = [Image.open(p).convert("RGB") for p in out]
    assert [g.size for g in got] == [(60, 80), (60, 80)]
    assert got[0].getpixel((30, 40))[1] > 200 and got[1].getpixel((30, 40))[1] < 60


def test_notes_already_sent_from_a_copy_are_not_sent_again():
    """A stray copy still carries ink read before it went stray; its notes stay sent once."""
    plans = [(["trello-inbox", "From the Today page: buy milk"], "inbox: buy milk"),
             (["trello-inbox", "From the Today page: book the dentist"], "inbox: book the dentist"),
             (["log-habit", "read-15-min", "2025-01-05"], "habit: Read 15 min")]
    kept = rs.drop_sent(plans, ["From the Today page: buy milk"])
    assert [c for c, _ in kept] == [["trello-inbox", "From the Today page: book the dentist"],
                                    ["log-habit", "read-15-min", "2025-01-05"]]


def test_replacing_a_page_deletes_every_copy_and_returns_the_new_id(tmp_path, monkeypatch):
    on_cloud = ["1 - Today", "1 - Today"]
    calls = []

    def fake_rmapi(*args, **kw):
        calls.append(args)
        if args[0] == "rm":
            on_cloud.remove(args[1])
        elif args[0] == "put":
            on_cloud.append("1 - Today")
        return 0, ""

    monkeypatch.setattr(rs, "rmapi", fake_rmapi)
    monkeypatch.setattr(rs, "cloud_stat", lambda n: {"ModifiedClient": "x"} if n in on_cloud else None)
    pdf = tmp_path / "1 - Today.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    modified, doc_id = rs.cloud_replace("1 - Today", pdf)
    assert on_cloud == ["1 - Today"] and modified == "x"
    assert [a[0] for a in calls] == ["rm", "rm", "put"]
    with zipfile.ZipFile(calls[-1][1]) as z:
        assert z.namelist()[0] == f"{doc_id}.content"
