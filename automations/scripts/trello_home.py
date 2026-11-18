"""The Trello cards that mirror the web home page (`/`), built from `home_data.build_home`.

The render (`trello_render.render`) calls `home_data.build_home` once and hands the
result to these builders, the same dict the web page and the TRMNL screens
(`trmnl_home.py`) read, so the board can never show a different number or light.
Nothing here computes a rule; it only words and orders what home_data returns.

    🦸 Body first   the 🤖 Brief, last night's verdict, the rating card while the day
                    is unrated, the levers off target, the green ones folded
    ✅ The 2+1      the Why line around the pick cards, tomorrow's picks from the
                    evening, the hand-offs and What needs you
    🗓️ Week         one card per day of the next seven
    🛠️ Projects     the Projects band plus the project gauges, then parked and on deck
    📈 Trends       the web Trends band, the last 30 days
    🧭 Areas        the plate, each area with its items and hours, then the household
    💎 Values       the values (trello_render), then the question of the day
    🔭 Visions      today's vision, then each vision with the lights it borrows

Every card here is read-only except the rating card, and every list is held in
order with `Card.pos`, red first where it carries lights.
"""

from __future__ import annotations

from datetime import date

from home_data import STALLED_PROJECT_DAYS

from trello_render import (Card, COLOR_EMOJI, FOCUS_PARKED_MARKER, PRIORITY_TIER_EMOJI,  # noqa: F401
                           AREAS_LIST, BODY_LIST, PICKS_LIST, PROJECTS_LIST, TRENDS_LIST,
                           VALUES_LIST, VISIONS_LIST, WEEK_LIST, RATE_GROUPS, RATE_HOW, RATE_ITEMS,
                           RATE_PREFIX, _deadline_to_due, _lifewheel_color, _priority_plain_label,
                           short_day)

# The card types built from home_data. When build_home fails the render keeps the
# cards of these types as they are on the board instead of archiving them.
HOME_TYPES = frozenset({
    "brief", "pulse", "rate-day", "tomorrow", "needs-you",
    "project", "projects-other", "trend", "plate", "area", "household",
    "question", "vision", "vision-of-day",
})

LIGHT_EMOJI = {"red": "🔴", "yellow": "🟡", "green": "🟢"}
RANK = {"red": 0, "yellow": 1, "green": 2}
POS_STEP = 1024
DORMANT = "⚪"


def _dot(light):
    return LIGHT_EMOJI.get(light or "", "")


def _titled(dot, text):
    return f"{dot} {text}" if dot else text


def positioned(cards, start=1):
    """Give each card its place in the order it comes in (red first already)."""
    for i, c in enumerate(cards):
        c.pos = (i + start) * POS_STEP
    return cards


def _month_day(iso):
    d = date.fromisoformat(iso)
    return short_day(iso).split(" ", 1)[1] + (f", {d.year}" if d.year != date.today().year else "")


def _slug(text):
    return "".join(ch if ch.isalnum() else "-" for ch in text.lower()).strip("-")


# ── 🦸 Body first ──────────────────────────────────────────────────────────────

MARK_LIGHT = {"RED": "red", "YELLOW": "yellow", "GREEN": "green"}


def _lever_line(lv):
    line = f"{lv['label']}: {lv['value']} · target {lv['target']}"
    if lv.get("on") is not None and lv.get("n") is not None:
        line += f" · on target {lv['on']} of {lv['n']} nights"
    return line


def render_rate(home):
    """The web's "How was yesterday?" card, only while the day it names is unrated."""
    target = home["rate_target"]
    if not target["unrated"]:
        return []
    which = "today" if target["date"] == home["date"] else "yesterday"
    return [Card(pfc_id=f"{RATE_PREFIX}{target['date']}", pfc_type="rate-day", list_name=BODY_LIST,
                 name=f"⭐ How was {which}? {short_day(target['date'])}", body=RATE_HOW,
                 seed_checklists=[(g, list(RATE_ITEMS)) for g in RATE_GROUPS])]


def render_body(home) -> list:
    """The web Body first band: the verdict with last night's numbers, the rating card
    while the day is unrated, the levers off target worst first, and the levers on
    target folded into one card. The 🤖 Brief sits above them (pos 1)."""
    pulse, body = home.get("pulse"), home["body"]
    verdict = (pulse or {}).get("verdict") or "Sleep decides what today can hold."
    lines = []
    if pulse and pulse.get("move"):
        lines.append(f"Tonight: {pulse['move']}")
    slept = "No data" if body["sleep_hours"] is None else f"{body['sleep_hours']:g} h"
    lines.append(f"Slept: {slept}" + (f" · {body['awake_minutes']} min awake in the night"
                                       if body["awake_minutes"] is not None else ""))
    if body["broken_night"]:
        lines.append("Broken night.")
    dot = _dot(MARK_LIGHT.get((pulse or {}).get("verdict_mark")))
    cards = [Card(pfc_id="pulse-verdict", pfc_type="pulse", list_name=BODY_LIST,
                  name=_titled(dot, f"Body first: {verdict}")[:200], body="\n".join(lines))]
    cards += render_rate(home)
    levers = (pulse or {}).get("levers") or []
    off = [lv for lv in levers if lv["mark"] != "GREEN"]
    on = [lv for lv in levers if lv["mark"] == "GREEN"]
    for lv in off:
        cards.append(Card(pfc_id=f"pulse-{_slug(lv['label'])}", pfc_type="pulse", list_name=BODY_LIST,
                          name=_titled(_dot(MARK_LIGHT.get(lv["mark"])), _lever_line(lv))[:200],
                          body=f"Last night against target. Tier: {lv['tier']}."))
    if on:
        cards.append(Card(pfc_id="pulse-on-target", pfc_type="pulse", list_name=BODY_LIST,
                          name=f"🟢 {len(on)} on target last night",
                          body="\n".join(_lever_line(lv) for lv in on)))
    if not pulse:
        cards.append(Card(pfc_id="pulse-none", pfc_type="pulse", list_name=BODY_LIST,
                          name="No sleep reading yet.", body="The levers show once a night is recorded."))
    return positioned(cards, start=2)


# ── ✅ The 2+1 ─────────────────────────────────────────────────────────────────

def _pick_titles(picks):
    rows = [p["title"] for p in picks["critical"]]
    if picks.get("bonus"):
        rows.append(f"bonus {picks['bonus']['title']}")
    return rows


def render_picks(home, pick_cards) -> list:
    """The web 2+1 band: the interactive pick cards first, tomorrow's picks from the
    evening, then ONE card for everything else in the band (extra cards in a list the
    user ticks off are clutter). Its title counts what needs the user; its description
    holds What needs you, the Why line and the hand-offs."""
    cards = list(pick_cards)
    if home["evening"]:
        tomorrow = home.get("tomorrow_picks")
        when = short_day(home["pick_date"])
        if tomorrow and (tomorrow["critical"] or tomorrow.get("bonus")):
            rows = _pick_titles(tomorrow)
            cards.append(Card(pfc_id="tomorrow-picks", pfc_type="tomorrow", list_name=PICKS_LIST,
                              name=f"Tomorrow, {when}: {' · '.join(rows)}"[:200], body="\n".join(rows)))
        else:
            cards.append(Card(pfc_id="tomorrow-picks", pfc_type="tomorrow", list_name=PICKS_LIST,
                              name=f"Tomorrow, {when}: no picks set yet",
                              body="Set them on the web home page or in chat."))
    rows = [f"{n['title']} — {n['why']}" + (f" {short_day(n['date'])}" if n.get("date") else "")
            for n in home.get("needs_you") or []]
    if home.get("due_review"):
        rows.append(f"Review due: {home['due_review']['label']}")
    look = home.get("tour_look")
    if look:
        rows.append(f"Look at: {look['title']} {look.get('detail') or ''}".rstrip()
                    + (f" {short_day(look['date'])}" if look.get("date") else ""))
    parts = []
    if rows:
        parts.append("What needs you:\n" + "\n".join(f"• {r}" for r in rows))
    fod = home.get("focus_of_day")
    if fod:
        chain = " → ".join(x for x in (fod["title"], fod.get("vision"), fod.get("value")) if x)
        parts.append(f"Why: {chain}")
    if home.get("handoffs"):
        parts.append(f"An agent can do these ({len(home['handoffs'])}), hand one off on the web home page "
                     "or in chat:\n" + "\n".join(f"• {t['title']}" for t in home["handoffs"]))
    if parts:
        name = f"🔴 What needs you: {len(rows)}" if rows else "ℹ️ Why today, and hand-offs"
        cards.append(Card(pfc_id="needs-you", pfc_type="needs-you", list_name=PICKS_LIST,
                          name=name, body="\n\n".join(parts)))
    return positioned(cards)


# ── 🗓️ Week ───────────────────────────────────────────────────────────────────

WEEK_SHOWN = 3


def render_week(days, today) -> list:
    """The web Week band: one card per day of the next seven, the first three events in
    the title (the rest counted, as the web folds them) and every event in the body."""
    cards = []
    for d in days:
        events = [f"{clock(_naive(e['start'])) if e['start'] else 'All day'} {e['title']}" for e in d["events"]]
        label = "Today" if d["date"] == today else short_day(d["date"])
        if not events:
            name = f"{label}: nothing scheduled"
        else:
            more = len(events) - WEEK_SHOWN
            name = f"{label}: {' · '.join(events[:WEEK_SHOWN])}" + (f" · {more} more" if more > 0 else "")
        cards.append(Card(pfc_id=f"week-{d['date']}", pfc_type="week-day", list_name=WEEK_LIST,
                          name=name[:200], body="\n".join(events) or "Nothing scheduled.",
                          due=f"{d['date']}T12:00:00.000Z"))
    return positioned(cards)


# ── 📈 Trends ─────────────────────────────────────────────────────────────────

def render_trends(home) -> list:
    """The web Trends band: how the last 30 days turned out, red first."""
    cards = [Card(pfc_id=f"trend-{_slug(t['name'])}", pfc_type="trend", list_name=TRENDS_LIST,
                  name=_titled(_dot(t["light"]), f"{t['name']} — {t['why']}"),
                  body="The last 30 days: how the days turned out. Sleep is an input, "
                       "so it lives in 🦸 Body first, not here.")
             for t in home["trends"]]
    return positioned(cards)


# ── 🛠️ Projects ───────────────────────────────────────────────────────────────

def _idle_text(row):
    idle = row.get("days_idle")
    if idle is None:
        return None
    return f"{'stalled' if row.get('stalled') else 'idle'} {idle}d"


def _project_key(row):
    return (RANK.get(row.get("light"), 3), 0 if row.get("stalled") else 1, -(row.get("days_idle") or 0))


def render_projects(home, projects, plain_color_labels=None) -> list:
    """The web Projects band's active projects with the project gauges, red first:
    on-time light (only with a deadline), percent, pace and estimated finish, days idle.
    The priority stays as the card's label colour; the title's circle is the light."""
    plain_color_labels = plain_color_labels or {}
    raw = {p["id"]: p for p in projects}
    cards = []
    for row in sorted(home["projects"]["active"], key=_project_key):
        p = raw.get(row["id"], {})
        total, completed = p.get("total_parts") or 0, p.get("completed_parts") or 0
        bits = [f"{row['pct']}% {row['name']}"]
        if _idle_text(row):
            bits.append(_idle_text(row))
        name = _titled(_dot(row.get("light")), " · ".join(bits))
        lines = []
        if row.get("pace") is not None:
            lines.append(f"Pace: {row['pace']:g} parts a week · finish about {_month_day(row['est_finish'])}")
        else:
            lines.append("Pace: no part done yet, so no finish date.")
        if row.get("light") and p.get("deadline"):
            late = row["days_late"]
            when = (f"{-late} days before" if late < 0 else "on" if late == 0 else f"{late} days past")
            lines.append(f"On time: {_dot(row['light'])} finishes {when} the {_month_day(p['deadline'])} deadline")
        else:
            lines.append("On time: no deadline, so no on-time light.")
        if row.get("days_idle") is not None:
            lines.append(f"Idle: {row['days_idle']} days since the last task event"
                         + (f" (stalled: {STALLED_PROJECT_DAYS} or more)" if row.get("stalled") else ""))
        if row.get("next_task"):
            lines.append(f"Next: {row['next_task']['title']}")
        lines.append(f"Parts: {completed}/{total} ({row['pct']}%)")
        lines.append(f"Area: {p.get('area', '')} · Values: {', '.join(p.get('values') or [])}")
        lines.append(f"Impact: {p.get('impact')} · Urgency: {p.get('urgency')} · Excitement: {p.get('excitement')}")
        letter = {"h": "A", "m": "B", "l": "C"}
        tier = letter.get((p.get("impact") or "low")[:1].lower(), "C") + letter.get((p.get("urgency") or "low")[:1].lower(), "C")
        cards.append(Card(pfc_id=row["id"], pfc_type="project", list_name=PROJECTS_LIST, name=name[:200],
                          body="\n".join(lines),
                          label_names=_priority_plain_label(tier, plain_color_labels),
                          due=_deadline_to_due(p.get("deadline")), due_complete=False,
                          checklist=[(f"Part {i + 1}", i < completed) for i in range(total)] if total else None))
    other = home["projects"]["other"]
    if other:
        cards.append(Card(pfc_id="projects-other", pfc_type="projects-other", list_name=PROJECTS_LIST,
                          name=f"Parked and on deck ({len(other)})",
                          body="\n".join(f"{'On deck' if p['status'] == 'on-deck' else p['status'].capitalize()}: "
                                         f"{p['name']} ({p['pct']}%)" for p in other)
                               + "\n\nActivate one on the web home page or in chat."))
    return positioned(cards)


# ── 🧭 Areas ──────────────────────────────────────────────────────────────────

def _plate_card(plate):
    pct = f" ({plate['pct']}%)" if plate.get("pct") is not None else ""
    return Card(pfc_id="area-plate", pfc_type="plate", list_name=AREAS_LIST,
                name=_titled(_dot(plate["light"]), f"Plate: {plate['committed']:g} of {plate['free']:g} free hours committed{pct}"),
                body=f"Committed hours this week across the areas' time items, against free waking hours "
                     f"(168 minus sleep). Green up to 90%, yellow up to 100%, red over.")


def _item_line(i):
    bits = ["Time" if i["kind"] == "time" else "Status"]
    if i.get("hours") is not None:
        bits.append(f"{i['hours']:g} h a week")
    bits.append(f"weight {i['weight']}")
    bits.append(i["why"])
    flags = (" · stale" if i.get("stale") else "") + (" · ended" if i.get("ended") else "")
    dot = _dot(i.get("light")) or "▫️"
    return f"{dot} {i['title']} — {' · '.join(bits)}{flags}"


def render_areas(home, statements, plain_color_labels=None) -> list:
    """The web Areas band: the plate first, then each life-wheel area red first with its
    light (area_items.py's rollup, else the manual light), weekly hours and items."""
    plain_color_labels = plain_color_labels or {}
    areas = home["areas"]
    checked = f"Checked {short_day(areas['date'])}." if areas["date"] else "Never checked."
    if areas["stale"]:
        checked += " ⚠ Stale: more than a month ago."
    cards = [_plate_card(home["plate"])] if home.get("plate") else []
    for r in areas["rows"]:
        color = _lifewheel_color(r.get("light"))
        hours = f"{r['hours']:g} h a week" if r.get("hours") is not None else "no weekly hours"
        source = (f"from {len(r['items'])} items" if r.get("source") == "items"
                  else "manual light, no item has data yet" if r["items"] else "manual light")
        lines = [f"Light: {_dot(r.get('light'))} {r.get('light') or 'none'}, {source} · {hours}".replace("  ", " ")]
        if r.get("why"):
            lines.append(f"Why: {r['why']}")
        lines.append(checked)
        if r["items"]:
            lines.append("")
            lines.append("Items:")
            lines.extend(_item_line(i) for i in r["items"])
        statement = (statements.get(r["key"]) or "")[:1000]
        body = "\n".join(lines) + (f"\n\n{statement}" if statement else "")
        cards.append(Card(pfc_id=f"area-{r['key']}", pfc_type="area", list_name=AREAS_LIST,
                          name=_titled(_dot(r.get("light")), r["label"]), body=body,
                          label_names=[f"_plain:{color}"] if color and color in plain_color_labels else []))
    if home.get("household"):  # None while parked
        cards.append(_household_card(home["household"]))
    return positioned(cards)


def _household_card(snap):
    """The web Areas band's folded Household group: the count of green rooms and when
    they were rated in the title, every room worst first in the body."""
    rows = sorted(snap["rows"], key=lambda r: RANK.get(r["light"], 3))
    green = sum(1 for r in rows if r["light"] == "green")
    rated = f"rated {short_day(snap['date'])}" if snap["date"] else "never rated"
    name = f"🏠 Household: {green} of {len(rows)} rooms green · {rated}" + (" · stale" if snap["stale"] else "")
    body = "\n".join(_titled(_dot(r["light"]), r["label"]) + (f" — {r['note']}" if r.get("note") else "")
                     for r in rows)
    return Card(pfc_id="household", pfc_type="household", list_name=AREAS_LIST, name=name,
                body=body + "\n\nChange a room's light on the web home page (Areas band) or in chat.")


# ── 💎 Values ────────────────────────────────────────────────────────────────

def render_values(home, value_cards) -> list:
    """The web Values band: the numbered values, then the question of the day."""
    cards = list(value_cards)
    q = home.get("question_of_day")
    if q:
        cards.append(Card(pfc_id="question-of-day", pfc_type="question", list_name=VALUES_LIST,
                          name=f"Question of the day: {q['text']}"[:200],
                          body="Edit the questions in chat (0-me/questions.md)."))
    return positioned(cards)


# ── 🔭 Visions ────────────────────────────────────────────────────────────────

def _strip_frontmatter(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


def render_visions(home, focus_records, projects, vision_files) -> list:
    """Each active vision, wearing the lights of what sits under it: its linked focuses'
    lights and its active projects' percent. Visions are deliberately ungauged (root
    AGENTS.md, the three intention layers), so the lead circle is borrowed: the worst
    live focus light, else the worst project on-time light, else none. A vision with no
    live focus and no active project shows ⚪ dormant, a valid state."""
    links = {f["id"]: (f.get("link") or {}) for f in focus_records}
    raw = {p["id"]: p for p in projects}
    bodies = {v["slug"]: v["body"] for v in vision_files}
    entries = []
    for v in home["visions"]:
        under = [f for f in home["focus"]
                 if links.get(f["focus_id"], {}).get("type") == "vision" and links[f["focus_id"]].get("ref") == v["id"]]
        live = [f for f in under if not f.get("parked")]
        parked = [f for f in under if f.get("parked")]
        projs = [r for r in home["projects"]["active"] if raw.get(r["id"], {}).get("vision") == v["id"]]
        lights = [f["status"] for f in live if f["status"] in RANK] or [r["light"] for r in projs if r.get("light")]
        lead = min(lights, key=RANK.get) if lights else None
        if not live and not projs:
            name, rank = f"{DORMANT} {v['title']} — dormant", 5
        else:
            parts = []
            if live:
                parts.append("focus " + ", ".join(_titled(_dot(f["status"]), f["title"]) for f in live))
            if projs:
                parts.append(("project " if len(projs) == 1 else "projects ") + ", ".join(f"{r['pct']}%" for r in projs))
            name, rank = _titled(_dot(lead), f"{v['title']} — {' · '.join(parts)}"), RANK.get(lead, 4)
        lines = []
        for f in live:
            p = f.get("primary") or {}
            rate = f" · {p['completed']} of {p['target']} via {p['habit_id']}" if p.get("target") else ""
            lines.append(f"Focus {_titled(_dot(f['status']), f['title'])}{rate}")
        for f in parked:
            lines.append(f"Focus {FOCUS_PARKED_MARKER} {f['title']}: parked")
        for r in projs:
            idle = f" · {_idle_text(r)}" if _idle_text(r) else ""
            lines.append(f"Project {_titled(_dot(r.get('light')), str(r['pct']) + '% ' + r['name'])}{idle}")
        if not lines:
            lines.append("Nothing live under it: no focus and no active project. Dormant is a valid state.")
        lines.append("A vision has no light of its own; these are borrowed from what sits under it.")
        body = "\n".join(lines) + "\n\n" + _strip_frontmatter(bodies.get(v["id"], ""))[:800]
        entries.append((rank, Card(pfc_id=f"vision-{v['id']}", pfc_type="vision", list_name=VISIONS_LIST,
                                   name=name[:200], body=body.rstrip())))
    entries.sort(key=lambda e: e[0])
    cards = [c for _, c in entries]
    vod = home.get("vision_of_day")
    if vod:
        serves = f" · serves {vod['value']}" if vod.get("value") else ""
        cards.insert(0, Card(pfc_id="vision-of-day", pfc_type="vision-of-day", list_name=VISIONS_LIST,
                             name=f"Today's vision: {vod['title']}{serves}"[:200],
                             body="One vision a day, rotating, as on the web home page."))
    return positioned(cards)


# ── 🤖 Duet brief ─────────────────────────────────────────────────────────────

BRIEF_ID = "duet-brief"
BRIEF_MAX_RED = 5
PULSE_DOT = {"RED": "🔴", "YELLOW": "🟡", "GREEN": "🟢"}
BRIEF_TIERS = ("weekly", "monthly", "quarterly")


def clock(when):
    """12-hour time: 2:05 PM."""
    hour = when.hour % 12 or 12
    return f"{hour}:{when.minute:02d} {'AM' if when.hour < 12 else 'PM'}"


def _naive(iso):
    from datetime import datetime
    return datetime.fromisoformat(iso).replace(tzinfo=None)


def current_review(home):
    """The one review every surface shows now (`review_forms.current_review`), or None
    when nothing is due, nothing asks anything, or building the form fails: the brief
    then falls back to the plain count."""
    try:
        import review_forms
        return review_forms.current_review(home, home["date"])
    except Exception:
        return None


def due_reviews(home):
    """Every due review as [(days overdue or None, ledger row)], never done first, then
    most overdue (`review_forms.due_reviews`), or [] when the ledger can't be read."""
    try:
        import review_forms
        return review_forms.due_reviews(home["date"])
    except Exception:
        return []


def feature_scorecard(home):
    """The feature scorecard rows (`feature_use.build`), or [] when it fails."""
    try:
        from datetime import date
        import feature_use
        return feature_use.build(date.fromisoformat(home["date"]))["features"]
    except Exception:
        return []


def quarter_of(day):
    """2025-11-15 -> 2025-Q4."""
    return f"{day[:4]}-Q{(int(day[5:7]) - 1) // 3 + 1}"


def _overdue(days):
    return "never done" if days is None else f"{days} days overdue"


def _first_step(review):
    """The first thing the current review asks, as one line."""
    for s in review.get("sections") or []:
        if s["kind"] == "prompt":
            return s["question"]
        if s.get("rows"):
            rows = ", ".join(r["title"] for r in s["rows"][:3])
            return f"{s['title']}: {rows} ({' / '.join(s['options'])})"
    return None


def _red_items(home):
    items = [(f["title"], "focus") for f in home["focus"] if f["status"] == "red" and not f.get("parked")]
    items += [(p["name"], "project") for p in home["projects"]["active"] if p.get("light") == "red"]
    items += [(r["label"], "area") for r in home["areas"]["rows"] if r.get("light") == "red"]
    items += [(r["label"], "room") for r in (home.get("household") or {}).get("rows") or [] if r.get("light") == "red"]
    items += [(t["name"], "trend") for t in home["trends"] if t["light"] == "red"]
    return items


def render_brief(home, habits, day_tracking, now, last_sync, review=None, overdue=(),
                 focus_rows=(), features=()) -> Card:
    """One read-only card a proactive agent (Claude Duet) reads to get the whole day
    in one fetch: short labelled lines, titles never ids, 12-hour times, every number
    high-is-good, all from the same sources as the rest of the board (home_data, the
    daily habit counts). `last_sync` is the local ISO time of the last Trello-to-repo
    sync on this machine, or None. `review` is `current_review(home)`: the one review up
    now, with how overdue it is and its first question. `overdue` is `due_reviews(home)`
    (the most overdue per kind), `focus_rows` the focus registry (each focus's quarter
    tag), `features` the scorecard rows (`feature_scorecard`). The Duet routines can't
    read the repo, so every nudge's facts live here."""
    lines = []
    target = home["rate_target"]
    if target["unrated"]:
        lines.append(f"Rating: {short_day(target['date'])} not rated yet (rating card in 🦸 Body first)")
    else:
        row = next((r for r in day_tracking if r.get("date") == target["date"]), {})
        lines.append(f"Rating: {short_day(target['date'])} rated {row.get('rating')}/5")

    picks = home.get("picks")
    if picks and (picks["critical"] or picks.get("bonus")):
        rows = [(p["title"], p["done"], "") for p in picks["critical"]]
        if picks.get("bonus"):
            rows.append((picks["bonus"]["title"], picks["bonus"]["done"], "bonus "))
        done = sum(1 for _, d, _ in rows if d)
        lines.append(f"2+1 today, {done} of {len(rows)} done: "
                     + "; ".join(f"{kind}{t} ({'done' if d else 'not done'})" for t, d, kind in rows))
    else:
        lines.append("2+1 today: none set")

    if habits:
        done = sum(1 for h in habits if h["done_today"])
        undone = [h["short"] for h in habits if not h["done_today"]]
        left = f" (not ticked yet: {', '.join(undone)})" if undone else ""
        lines.append(f"Habits today: {done} of {len(habits)} done{left} · past 7 days: "
                     + ", ".join(f"{h['short']} {h['completed']}/{h['target']}" for h in habits))
    else:
        lines.append("Habits today: none to tick")

    pulse = home.get("pulse") or {}
    lines.append(f"Pulse: {PULSE_DOT.get(pulse.get('verdict_mark'), '⚪')} {pulse.get('verdict') or 'no sleep data yet'}")

    red = _red_items(home)
    if red:
        shown = "; ".join(f"{title} ({kind})" for title, kind in red[:BRIEF_MAX_RED])
        more = f" · and {len(red) - BRIEF_MAX_RED} more" if len(red) > BRIEF_MAX_RED else ""
        lines.append(f"Red: {shown}{more}")
    else:
        lines.append("Red: none")

    if review:
        kind = f"{review['tier']}, " if review.get("tier") else ""
        lines.append(f"Review now: {review['label']} ({kind}{_overdue(review.get('overdue_days'))}; "
                     f"{review['due_count']} due, done one at a time)")
        step = _first_step(review)
        if step:
            lines.append(f"First step: {step}")
    elif home["reviews_due"]:
        lines.append(f"Reviews due: {home['reviews_due']}")
    else:
        lines.append("Review now: none due")

    worst = []
    for tier in BRIEF_TIERS:
        hit = next(((days, r) for days, r in overdue if r.get("tier") == tier), None)
        if hit:
            worst.append(f"{tier} {hit[1]['label']} ({_overdue(hit[0])})")
    if worst:
        lines.append("Most overdue by kind: " + "; ".join(worst))

    live = [f for f in home.get("focus") or [] if not f.get("parked")]
    if live:
        tags = {r.get("id"): r.get("quarter") for r in focus_rows}
        now_q = quarter_of(home["date"])
        old = sorted({tags.get(f["focus_id"]) for f in live if tags.get(f["focus_id"]) not in (None, now_q)})
        when = (f" (tagged {', '.join(old)}, now {now_q}: re-pick due)" if old
                else f" (all tagged {now_q})" if tags else "")
        rank = {"red": 0, "yellow": 1, "green": 2}
        shown = sorted(live, key=lambda f: rank.get(f["status"], 3))
        lines.append(f"Focuses{when}: " + "; ".join(
            f"{PULSE_DOT.get(f['status'].upper(), '⚪')} {f['title']} ({f.get('tier') or 'focus'})" for f in shown))

    used = [f for f in features if f.get("recent") and f.get("verdict") != "on demand"]
    if used:
        lines.append("Feature use, last 30 days: " + "; ".join(
            f"{f['title']} {f['recent']['count']}/{f['recent']['expected']} ({f['verdict']})" for f in used))

    today = next((d for d in home.get("week") or [] if d["date"] == home["date"]), {"events": []})
    upcoming = [e for e in today["events"] if e["start"] and _naive(e["start"]) >= now]
    lines.append(f"Next today: {clock(_naive(upcoming[0]['start']))} {upcoming[0]['title']}" if upcoming
                 else "Next today: nothing else on the calendar")

    needs = home.get("needs_you") or []
    if needs:
        lines.append("Needs you: " + "; ".join(
            f"{n['title']} ({n['why']}{' ' + short_day(n['date']) if n.get('date') else ''})" for n in needs[:2]))
    else:
        lines.append("Needs you: nothing")

    lines.append(f"Last Trello sync: {clock(_naive(last_sync))}" if last_sync
                 else "Last Trello sync: not recorded on this machine")

    return Card(pfc_id=BRIEF_ID, pfc_type="brief", list_name=BODY_LIST,
                name=f"🤖 Brief · {short_day(home['date'])} · updated {clock(now)}",
                body="\n".join(lines), pos=1)
