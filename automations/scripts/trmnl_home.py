"""
TRMNL screens that mirror the web home page (`/`), one screen per band.

Every builder here reads `home_data.build_home` — the same call the web page makes — and
reshapes one band for e-ink: flat lists, ASCII only, lights spelled out as
`STATUS_WORD` words, worst first. So the wall and the page can never disagree on a
number. Shaping lives here; the Liquid only prints.

Band → plugin (the playlist order matches the page, top to bottom):

    Values          pfc-values
    Areas           pfc-areas          life wheel + household
    Visions         pfc-visions
    Focuses         pfc-focus
    Projects        pfc-projects
    Body first      pfc-pulse          today's levers + nights on target over 30 days
    Tasks           pfc-today          today's 2+1, tomorrow's after 6 PM, what needs you
    Habits          pfc-habits
    Trends          pfc-trends         how the days turned out (inputs live in Body first)
    Front of mind   pfc-front-of-mind  (trmnl_push.build_pfc_front_of_mind)
    Week            pfc-week           (trmnl_push.build_pfc_week)
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
TIER_LABELS = [("foundation", "Foundations"), ("pursuit", "Active Pursuits"), ("consuming", "Currently Consuming")]


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


def _home(env, today):
    """The page's data for `today` at the current local clock time (the evening switch
    at about 6 PM depends on it)."""
    import home_data
    tz = ZoneInfo(env.get("LOCAL_TZ", "America/Denver"))
    now = datetime.combine(date.fromisoformat(today), datetime.now(tz).time().replace(microsecond=0))
    return home_data.build_home(env, now)


def _base(h, title):
    return {"title": title, "date": _short_date(h["date"])}


# ── Values ────────────────────────────────────────────────────────────────────


def values_payload(h):
    q = h.get("question_of_day")
    return {**_base(h, "Values"),
            "horizon": "Always: what everything else is judged against.",
            "values": [_txt(v) for v in h["values"]],
            "values_line": _txt(" - ".join(h["values"])),
            "question": _txt(q["text"], 220) if q else ""}


def build_pfc_values(env, today):
    return values_payload(_home(env, today))


# ── Areas ─────────────────────────────────────────────────────────────────────


def _light_group(label, snap, note_limit):
    rows = [{"label": _txt(r["label"]), "status": _word(r["light"]), "note": _txt(r.get("note"), note_limit)}
            for r in snap["rows"]]
    return {"label": label,
            "rated": f"rated {_short_date(snap['date'])}" if snap["date"] else "never rated",
            "stale": bool(snap["stale"]),
            "rows": rows,
            "red": sum(1 for r in snap["rows"] if r["light"] == "red"),
            "yellow": sum(1 for r in snap["rows"] if r["light"] == "yellow"),
            "green": sum(1 for r in snap["rows"] if r["light"] == "green")}


def areas_payload(h):
    return {**_base(h, "Areas"),
            "horizon": "Always: the parts of life that are never done.",
            "groups": [_light_group("Life wheel", h["areas"], 90), _light_group("Household", h["household"], 90)]}


def build_pfc_areas(env, today):
    return areas_payload(_home(env, today))


# ── Visions ───────────────────────────────────────────────────────────────────


def visions_payload(h):
    vod = h.get("vision_of_day")
    return {**_base(h, "Visions"),
            "horizon": "Years: where I'm headed, no deadlines.",
            "visions": [{"title": _txt(v["title"], 60), "today": bool(vod and vod["id"] == v["id"])}
                        for v in h["visions"]],
            "count": len(h["visions"]),
            "today_title": _txt(vod["title"]) if vod else "",
            "today_value": _txt(vod.get("value")) if vod else ""}


def build_pfc_visions(env, today):
    return visions_payload(_home(env, today))


# ── Focuses ───────────────────────────────────────────────────────────────────


def focus_payload(h):
    tiers = []
    for key, label in TIER_LABELS:
        rows = []
        for f in h["focuses"].get(key) or []:
            p = f.get("primary") or {}
            rows.append({"title": _txt(f["title"], 60),
                         "status": "PARKED" if f.get("parked") else _word(f["light"]),
                         "progress": f"{p['completed']} of {p['target']}" if p.get("target") else ""})
        tiers.append({"label": label, "rows": rows, "count": len(rows)})
    return {**_base(h, "Focuses"),
            "horizon": "A quarter: what I'm actually on now.",
            "repick": ("All six pursuit slots are full and one has been red four weeks or more. Time to re-pick."
                       if h["repick_nudge"] else ""),
            "tiers": tiers}


def build_pfc_focus(env, today):
    return focus_payload(_home(env, today))


# ── Projects ──────────────────────────────────────────────────────────────────


def projects_payload(h):
    # pct feeds a `w--[Ncqw]` width class, which only exists for whole numbers 0-100.
    active = [{"name": _txt(p["name"], 60), "pct": max(0, min(100, int(round(p["pct"] or 0)))),
               "next": _txt(p["next_task"]["title"], 110) if p.get("next_task") else ""}
              for p in h["projects"]["active"]]
    other = h["projects"]["other"]
    return {**_base(h, "Projects"),
            "horizon": "One to three months: short projects with a finish line.",
            "active": active,
            "count": len(active),
            "on_deck": sum(1 for p in other if p["status"] == "on-deck"),
            "parked": sum(1 for p in other if p["status"] == "parked")}


def build_pfc_projects(env, today):
    return projects_payload(_home(env, today))


# ── Body first ────────────────────────────────────────────────────────────────


def body_payload(h):
    b, pulse = h["body"], h.get("pulse") or {}
    if b["sleep_hours"] is None:
        sleep = "no sleep data yet"
    else:
        sleep = f"{b['sleep_hours']} hours" + (f", {b['awake_minutes']} minutes awake" if b["awake_minutes"] is not None else "")
    levers = [{"label": _txt(lv["label"]), "status": lv["mark"], "value": _txt(lv["value"]),
               "target": _txt(lv["target"].split(",")[0]),
               "month": f"{lv['on']} of {lv['n']}" if lv.get("on") is not None else ""}
              for lv in pulse.get("levers") or []]
    label = _txt(b["exercise_label"])
    return {**_base(h, "Body first"),
            "horizon": "Today: sleep and exercise decide what today can hold.",
            "sleep": sleep,
            "broken_night": bool(b["broken_night"]),
            "exercise_label": label,
            "exercise": "Yes, done today." if b["exercised"] else "Not yet.",
            "exercise_status": _word(b["exercise_light"]),
            "exercise_month": f"{label.lower()} on {b['exercised_days']} of the last {b['window']} days",
            "verdict_status": pulse.get("verdict_mark") or "NO DATA",
            "verdict": _txt(pulse.get("verdict"), 120),
            "move": _txt(pulse.get("move"), 160),
            "single_pick": "Lower the bar today: one pick, not 2+1." if h["single_pick"] else "",
            "levers": levers,
            "window": b["window"]}


def build_pfc_body(env, today):
    return body_payload(_home(env, today))


# ── Tasks ─────────────────────────────────────────────────────────────────────


def _pick_rows(picks):
    if not picks:
        return []
    rows = [{"title": _txt(p["title"], 110), "done": bool(p["done"]), "kind": f"Pick {i}"}
            for i, p in enumerate(picks["critical"], 1)]
    if picks.get("bonus"):
        rows.append({"title": _txt(picks["bonus"]["title"], 110), "done": bool(picks["bonus"]["done"]),
                     "kind": "Bonus"})
    return rows


def tasks_payload(h):
    needs = [{"title": _txt(n["title"], 110),
              "why": _txt(f"{n['why']} {_short_date(n['date'])}" if n.get("date") else n["why"])}
             for n in h["needs_you"]]
    picks = _pick_rows(h["picks"])
    return {**_base(h, "Tasks"),
            "horizon": "A day: today's 2+1.",
            "picks": picks,
            "picks_note": "" if picks else ("No picks were set today." if h["evening"] else "No picks set yet. Set them on the web page."),
            "done": sum(1 for p in picks if p["done"]),
            "total": len(picks),
            "evening": bool(h["evening"]),
            "tomorrow_label": f"Tomorrow, {_short_date(h['pick_date'])}" if h["evening"] else "",
            "tomorrow": _pick_rows(h["tomorrow_picks"]) if h["evening"] else [],
            "single_pick": bool(h["single_pick"]),
            "needs_you": needs,
            "handoffs": [_txt(t["title"], 90) for t in h["handoffs"]]}


def build_pfc_today(env, today):
    return tasks_payload(_home(env, today))


# ── Habits ────────────────────────────────────────────────────────────────────


def _habit_state(r):
    if r["auto_derived"]:
        return "Automatic"
    if r["logged_today"]:
        return "Logged today"
    if r["logged_yesterday"]:
        return "Logged yesterday"
    return "Not logged"


def habits_payload(h):
    groups = []
    for cadence, label in (("daily", "Daily"), ("monthly", "Monthly")):
        rows = [{"title": _txt(r["title"], 40), "state": _habit_state(r), "done": bool(r["logged_today"])}
                for r in h["habits"] if r["cadence"] == cadence]
        rows.sort(key=lambda r: r["state"] != "Not logged")  # not logged first, page order kept within
        if rows:
            groups.append({"label": label, "rows": rows,
                           "logged": sum(1 for r in rows if r["done"]), "count": len(rows),
                           "not_logged": sum(1 for r in rows if r["state"] == "Not logged")})
    return {**_base(h, "Habits"), "horizon": "A day or a month: today's reps.", "groups": groups}


def build_pfc_habits(env, today):
    return habits_payload(_home(env, today))


# ── Trends ────────────────────────────────────────────────────────────────────


def trends_payload(h):
    return {**_base(h, "Trends"),
            "horizon": "The last 30 days: how the days turned out, worst first.",
            "rows": [{"name": _txt(t["name"]), "status": _word(t["light"]), "why": _txt(t["why"])}
                     for t in h["trends"]]}


def build_pfc_trends(env, today):
    return trends_payload(_home(env, today))
