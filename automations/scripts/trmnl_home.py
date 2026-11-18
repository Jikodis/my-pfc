"""
TRMNL screens that mirror the web home page (`/`), one screen per band.

Every builder here reads `home_data.build_home` — the same call the web page makes — and
reshapes one band for e-ink: flat lists, ASCII only, lights spelled out as
`STATUS_WORD` words. So the wall and the page can never disagree on a number. Shaping
lives here; the Liquid only prints.

Each screen reads like its web band: one headline first, then only the rows that need
a look, worst first, with everything on target folded into a count (the page's
`<details>` folds). Row caps keep a screen readable across a room.

Band → plugin (the playlist order matches the page, top to bottom: Today, then
This quarter, then Always):

    Body first      pfc-pulse          verdict, three stats, levers off target
    The 2+1         pfc-today          the why line, the picks, what needs you
    Habits          pfc-habits         logged count, what is still to log
    Week            pfc-week           seven days, three events each
    Focuses         pfc-focus          red count, the tiers with greens folded
    Projects        pfc-projects       active projects, percent and next task
    Trends          pfc-trends         the last 30 days, greens folded
    Areas           pfc-areas          the plate, life wheel worst first, household count
    Values          pfc-values         the values in rank order, question of the day
    Visions         pfc-visions        today's vision, the rest as a list
    Front of mind   pfc-front-of-mind  the anchors
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TIER_LABELS = [("foundation", "Foundations"), ("pursuit", "Active Pursuits"), ("consuming", "Currently Consuming")]
LIGHT_ORDER = {"red": 0, "yellow": 1, "green": 2}

# Row caps: what a full view shows before the rest becomes "N more".
LEVER_ROWS = 4
NEEDS_ROWS = 3
PROJECT_ROWS = 3
AREA_ROWS = 6
WEEK_EVENTS = 3  # the web Week band shows three a day, the rest folded


def _word(light):
    import trmnl_push
    return trmnl_push.STATUS_WORD.get(light or "", "NO DATA")


def _txt(text, limit=None):
    """ASCII-safe (e-ink has no glyphs for curly quotes, dashes, arrows) and clipped."""
    import trmnl_push
    s = trmnl_push._ascii(text or "")
    s = (s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
         .replace("…", "..."))
    s = s.encode("ascii", "ignore").decode()
    if limit and len(s) > limit:
        s = s[: limit - 3].rstrip() + "..."
    return s


def _short_date(iso):
    if not iso:
        return ""
    d = date.fromisoformat(iso[:10])
    return f"{WEEKDAYS[d.weekday()]} {MONTHS[d.month - 1]} {d.day}"


def _clock(iso):
    """12-hour time from an ISO datetime, or `All day` for a date-only event."""
    if not iso:
        return "All day"
    t = datetime.fromisoformat(iso)
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _home(env, today):
    """The page's data for `today` at the current local clock time (the evening switch
    at about 6 PM depends on it)."""
    import home_data
    tz = ZoneInfo(env.get("LOCAL_TZ", "America/Denver"))
    now = datetime.combine(date.fromisoformat(today), datetime.now(tz).time().replace(microsecond=0))
    return home_data.build_home(env, now)


def _base(h, title):
    return {"title": title, "date": _short_date(h["date"])}


def _worst_first(rows, light):
    return sorted(rows, key=lambda r: LIGHT_ORDER.get(light(r), -1))  # no light reads as needing a look


# ── Body first ────────────────────────────────────────────────────────────────


def body_payload(h):
    b, pulse = h["body"], h.get("pulse") or {}
    levers = pulse.get("levers") or []
    off = [lv for lv in levers if lv["mark"] != "GREEN"]
    rows = [{"label": _txt(lv["label"]), "status": lv["mark"], "value": _txt(lv["value"]),
             "target": _txt(lv["target"].split(",")[0]),
             "month": f"{lv['on']} of {lv['n']}" if lv.get("on") is not None else ""}
            for lv in off[:LEVER_ROWS]]
    return {**_base(h, "Body first"),
            "verdict_status": pulse.get("verdict_mark") or "NO DATA",
            "verdict": _txt(pulse.get("verdict") or "Sleep and exercise decide what today can hold.", 90),
            "move": _txt(pulse.get("move"), 120),
            "broken_night": bool(b["broken_night"]),
            "sleep": "No data" if b["sleep_hours"] is None else f"{b['sleep_hours']} h",
            "awake": "" if b["awake_minutes"] is None else f"{b['awake_minutes']} min",
            # The exercise habit (trmnl_push.EXERCISE_HABIT_ID), done today or not.
            "exercise_label": _txt(pulse.get("exercise_label") or "Exercise"),
            "exercise": "Done" if pulse.get("exercise_done") else "Not yet",
            "has_levers": bool(levers),
            "levers": rows,
            "levers_more": max(len(off) - LEVER_ROWS, 0),
            "on_target": len(levers) - len(off),
            "window": b["window"]}


def build_pfc_body(env, today):
    return body_payload(_home(env, today))


# ── The 2+1 ───────────────────────────────────────────────────────────────────


def _pick_rows(picks, overdue):
    if not picks:
        return []
    out = [(f"Pick {i}", p) for i, p in enumerate(picks["critical"], 1)]
    if picks.get("bonus"):
        out.append(("Bonus", picks["bonus"]))
    return [{"kind": kind, "title": _txt(p["title"], 90), "done": bool(p["done"]),
             # An overdue pick carries its date here instead of a second row under What needs you.
             "note": overdue.get(p["title"]) or _txt(" > ".join(p.get("why") or []), 60)}
            for kind, p in out]


def tasks_payload(h):
    overdue = {n["title"]: _txt(f"{n['why']} {_short_date(n['date'])}" if n.get("date") else n["why"])
               for n in h["needs_you"]}
    picks = _pick_rows(h["picks"], overdue)
    shown = {p["title"] for p in (h["picks"] or {}).get("critical", [])} | (
        {h["picks"]["bonus"]["title"]} if h["picks"] and h["picks"].get("bonus") else set())
    needs = [{"title": _txt(n["title"], 80), "why": overdue[n["title"]]}
             for n in h["needs_you"] if n["title"] not in shown]
    if h.get("due_review"):
        needs.append({"title": _txt(f"Review due: {h['due_review']['label']}", 80), "why": ""})
    look = h.get("tour_look")
    if look:
        needs.append({"title": _txt(f"Look at: {look['title']}", 80), "why": _txt(look.get("detail"))})
    fod = h.get("focus_of_day")
    why = " > ".join(_txt(x) for x in ([fod["title"], fod.get("vision"), fod.get("value")] if fod else []) if x)
    return {**_base(h, "The 2+1"),
            "why": why,
            "picks": picks,
            "picks_note": "" if picks else ("No picks were set today." if h["evening"] else "No picks set yet."),
            "done": sum(1 for p in picks if p["done"]),
            "total": len(picks),
            "evening": bool(h["evening"]),
            "tomorrow_label": f"Tomorrow, {_short_date(h['pick_date'])}" if h["evening"] else "",
            "tomorrow": _pick_rows(h["tomorrow_picks"], {}) if h["evening"] else [],
            "needs": needs[:NEEDS_ROWS],
            "needs_more": max(len(needs) - NEEDS_ROWS, 0),
            "handoffs": len(h["handoffs"])}


def build_pfc_today(env, today):
    return tasks_payload(_home(env, today))


# ── Habits ────────────────────────────────────────────────────────────────────


def habits_payload(h):
    daily = [r for r in h["habits"] if r["cadence"] == "daily"]
    monthly = [r for r in h["habits"] if r["cadence"] == "monthly"]
    todo = [{"title": _txt(r["title"], 32), "yesterday": bool(r["logged_yesterday"])}
            for r in daily if not r["logged_today"] and not r["auto_derived"]]
    month_todo = [_txt(r["title"], 32) for r in monthly if not r["logged_today"] and not r["auto_derived"]]
    return {**_base(h, "Habits"),
            "logged": sum(1 for r in daily if r["logged_today"]),
            "count": len(daily),
            "todo": todo,
            "automatic": sum(1 for r in daily if r["auto_derived"] and not r["logged_today"]),
            "monthly_logged": sum(1 for r in monthly if r["logged_today"]),
            "monthly_count": len(monthly),
            "monthly_todo": ", ".join(month_todo)}


def build_pfc_habits(env, today):
    return habits_payload(_home(env, today))


# ── Week ──────────────────────────────────────────────────────────────────────


def week_payload(h):
    days = []
    for d in h["week"]:
        evs = d["events"]
        days.append({"label": "Today" if d["date"] == h["date"] else _short_date(d["date"]),
                     "events": [{"time": _clock(e["start"]), "title": _txt(e["title"], 22)} for e in evs[:WEEK_EVENTS]],
                     "more": max(len(evs) - WEEK_EVENTS, 0)})
    return {**_base(h, "Week"), "days": days}


def build_pfc_week(env, today):
    return week_payload(_home(env, today))


# ── Focuses ───────────────────────────────────────────────────────────────────


def focus_payload(h):
    live = [f for f in h["focus"] if not f.get("parked")]
    tiers = []
    for key, label in TIER_LABELS:
        rows = h["focuses"].get(key) or []
        look = _worst_first([f for f in rows if not f.get("parked") and f["light"] != "green"], lambda f: f["light"])
        out = []
        for f in look:
            p = f.get("primary") or {}
            out.append({"title": _txt(f["title"], 50), "status": _word(f["light"]),
                        "progress": f"{p['completed']} of {p['target']}" if p.get("target") else "",
                        "weeks": f"red {f['weeks_red']} weeks" if f.get("weeks_red", 0) >= 2 else ""})
        tiers.append({"label": label, "rows": out,
                      "green": sum(1 for f in rows if not f.get("parked") and f["light"] == "green"),
                      "parked": sum(1 for f in rows if f.get("parked"))})
    return {**_base(h, "Focuses"),
            "red": sum(1 for f in live if f["status"] == "red"),
            "live": len(live),
            "repick": ("All six pursuit slots are full and one has been red four weeks or more. Time to re-pick."
                       if h["repick_nudge"] else ""),
            "tiers": tiers}


def build_pfc_focus(env, today):
    return focus_payload(_home(env, today))


# ── Projects ──────────────────────────────────────────────────────────────────


def projects_payload(h):
    active = h["projects"]["active"]
    # pct feeds a `w--[Ncqw]` width class, which only exists for whole numbers 0-100.
    rows = [{"name": _txt(p["name"], 50), "pct": max(0, min(100, int(round(p["pct"] or 0)))),
             "next": _txt(p["next_task"]["title"], 70) if p.get("next_task") else "",
             "idle": (("stalled, " if p.get("stalled") else "") + f"idle {p['days_idle']} days")
             if p.get("days_idle") is not None else ""}
            for p in active[:PROJECT_ROWS]]
    return {**_base(h, "Projects"),
            "count": len(active),
            "stalled": sum(1 for p in active if p.get("stalled")),
            "active": rows,
            "more": max(len(active) - PROJECT_ROWS, 0),
            "other": len(h["projects"]["other"])}


def build_pfc_projects(env, today):
    return projects_payload(_home(env, today))


# ── Trends ────────────────────────────────────────────────────────────────────


def trends_payload(h):
    rows = _worst_first(h["trends"], lambda t: t["light"])
    return {**_base(h, "Trends"),
            "rows": [{"name": _txt(t["name"]), "status": _word(t["light"]), "why": _txt(t["why"], 60)}
                     for t in rows if t["light"] != "green"],
            "green": [_txt(t["name"]) for t in rows if t["light"] == "green"],
            "count": len(rows)}


def build_pfc_trends(env, today):
    return trends_payload(_home(env, today))


# ── Areas ─────────────────────────────────────────────────────────────────────


def _plate(plate):
    """The plate line (area_items.py's hours), or None without area items."""
    if not plate:
        return None
    return {"status": _word(plate["light"]), "committed": f"{plate['committed']:g}", "free": f"{plate['free']:g}",
            "pct": max(0, min(100, int(plate["pct"]))) if plate.get("pct") is not None else None}


def areas_payload(h):
    # The life-wheel rows carry the computed area lights (items rolled up, else the
    # manual light), the same lights as the web Areas band.
    a, hh = h["areas"], h.get("household") or {"rows": [], "stale": False}  # empty while parked
    look = _worst_first([r for r in a["rows"] if r["light"] != "green"], lambda r: r["light"])
    rooms = _worst_first([r for r in hh["rows"] if r["light"] != "green"], lambda r: r["light"])
    return {**_base(h, "Areas"),
            "plate": _plate(h.get("plate")),
            "checked": f"checked {_short_date(a['date'])}" if a["date"] else "never rated",
            "stale": bool(a["stale"]),
            "green": sum(1 for r in a["rows"] if r["light"] == "green"),
            "count": len(a["rows"]),
            "rows": [{"label": _txt(r["label"]), "status": _word(r["light"]),
                      "detail": _txt(r.get("why"), 60)}
                     for r in look[:AREA_ROWS]],
            "more": max(len(look) - AREA_ROWS, 0),
            "rooms_green": sum(1 for r in hh["rows"] if r["light"] == "green"),
            "rooms_count": len(hh["rows"]),
            "rooms_stale": bool(hh["stale"]),
            "rooms_look": _txt(", ".join(r["label"] for r in rooms), 110)}


def build_pfc_areas(env, today):
    return areas_payload(_home(env, today))


# ── Values ────────────────────────────────────────────────────────────────────


def values_payload(h):
    q = h.get("question_of_day")
    return {**_base(h, "Values"),
            "values": [_txt(v) for v in h["values"]],
            "question": _txt(q["text"], 200) if q else ""}


def build_pfc_values(env, today):
    return values_payload(_home(env, today))


# ── Visions ───────────────────────────────────────────────────────────────────


def visions_payload(h):
    vod = h.get("vision_of_day")
    return {**_base(h, "Visions"),
            "today_title": _txt(vod["title"], 80) if vod else "",
            "today_value": _txt(vod.get("value")) if vod else "",
            "others": [_txt(v["title"], 60) for v in h["visions"] if not (vod and v["id"] == vod["id"])],
            "count": len(h["visions"])}


def build_pfc_visions(env, today):
    return visions_payload(_home(env, today))


# ── Front of mind ─────────────────────────────────────────────────────────────


def front_of_mind_payload(h):
    anchors = [_txt(a["title"], 110) for a in h["anchors"]]
    return {**_base(h, "Front of mind"),
            "anchors": anchors,
            "count": len(anchors),
            # Up to three anchors fill the screen as a poster; more fall back to a list.
            "poster": len(anchors) <= 3}


def build_pfc_front_of_mind(env, today):
    return front_of_mind_payload(_home(env, today))
