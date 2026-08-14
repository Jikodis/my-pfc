"""Daily Pulse — the at-a-glance "is my body set up for a good day?" readout.

ONE source of truth for the pulse thresholds, verdict, and per-lever fix, shared
by every consumer (the Trello render, an e-ink dashboard payload, the evening
check-in). Any surface that shows the pulse imports from here; nothing re-derives
a threshold locally, because two copies of a band drift the moment you tune one.

What it is
----------
Each **lever** is one measurable thing from last night, scored against a
three-tier band: 🟢 in range · 🟡 close · 🔴 out. Levers carry a **tier**:

  CRITICAL — levers that separate a genuinely great day from a merely fine one.
  MODERATE — levers worth watching that don't (yet) move the verdict.

The **verdict** is a single sentence computed from the CRITICAL levers. The
**move** is the one concrete thing to do tonight — the highest-priority
out-of-range lever's fix, so the readout ends in an action rather than a number.

Earning a slot: a metric that does NOT separate your good days from your average
days does not belong on the pulse, however interesting it looks. Run
`/pfc-analyze-trends` (the gate/gradient pass) and drop any lever whose spread
across your rating buckets is negligible — a pulse full of flat metrics trains
you to ignore it.

TUNE THESE. Every band below is a **generic starting default** from general adult
sleep guidance — not your physiology, and not a target you have to hit. Override
without editing this file by adding a `health.pulse` block to
`config/automation_config.yaml`; ground the new numbers in your own bucket means
from `/pfc-analyze-trends`.
"""
import datetime as _dt
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "automation_config.yaml"

# lever id → (green, amber). `better_low` levers pass at <= the band; the rest at >=.
_DEFAULT_BANDS = {
    "continuity":  (20, 40),      # minutes awake during the night (lower is better)
    "rem":         (90, 75),      # REM minutes — roughly 20–25% of a 7h night
    "hours":       (7.5, 7.0),    # total sleep hours — general guidance is 7–9
    "debt":        (30, 60),      # trailing sleep debt, avg minutes short per night
    "deep":        (75, 60),      # deep sleep minutes — roughly 13–23% of total
    "awakenings":  (1, 3),        # real wakings (micro-arousals already filtered out)
    "bedtime":     (-60, 0),      # asleep by 11:00 PM / by midnight (signed min from midnight)
    "wake":        (420, 450),    # awake by 7:00 AM / 7:30 AM (minutes past midnight)
    "qqrt":        (2, 1),        # QQRT composite score, 0–3
}

# How many CRITICAL levers must be green for a 🟢 verdict. An absolute count, not a
# proportion, so adding or removing a lever doesn't silently move the bar.
_DEFAULT_VERDICT_MIN_GREEN = 3


def _load_config():
    cfg = {"bands": dict(_DEFAULT_BANDS), "verdict_min_critical_green": _DEFAULT_VERDICT_MIN_GREEN}
    try:
        import yaml  # noqa: PLC0415 — optional dependency
        raw = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        block = (raw.get("health") or {}).get("pulse") or {}
        for lid, band in (block.get("levers") or {}).items():
            if lid in cfg["bands"] and isinstance(band, dict):
                cfg["bands"][lid] = (band.get("green", cfg["bands"][lid][0]),
                                     band.get("amber", cfg["bands"][lid][1]))
        if block.get("verdict_min_critical_green") is not None:
            cfg["verdict_min_critical_green"] = int(block["verdict_min_critical_green"])
    except Exception:  # noqa: BLE001 — config is optional by design
        pass
    return cfg


CONFIG = _load_config()
BANDS = CONFIG["bands"]
VERDICT_MIN_CRITICAL_GREEN = CONFIG["verdict_min_critical_green"]


# ── Lever construction ────────────────────────────────────────────────────────

def _light(val, green, amber, better_low):
    if val is None:
        return "⚪"
    if better_low:
        return "🟢" if val <= green else ("🟡" if val <= amber else "🔴")
    return "🟢" if val >= green else ("🟡" if val >= amber else "🔴")


def _gap(val, green, amber, better_low, fmt):
    """How far the lever is from the NEXT tier up, e.g. ', 12m to yellow'.

    Showing only the green target makes a red read as a flat fail: 6.8h of sleep is
    12 minutes under the yellow floor, which is 'nearly', not 'no'. Returns '' when
    green or unknown. Deliberately words, not colour emoji — this string can reach
    an e-ink screen with no emoji font."""
    if val is None:
        return ""
    if better_low:
        if val <= green:
            return ""
        tgt, tier = (amber, "yellow") if val > amber else (green, "green")
        return f", {fmt(val - tgt)} to {tier}"
    if val >= green:
        return ""
    tgt, tier = (amber, "yellow") if val < amber else (green, "green")
    return f", {fmt(tgt - val)} to {tier}"


# Gap formatters — how a lever's distance-to-next-tier reads in its own unit.
_GAP_MIN = lambda d: f"{round(d)}m"          # noqa: E731 — minute-valued levers
_GAP_HRS = lambda d: f"{round(d * 60)}m"     # noqa: E731 — hours stored, gap shown in minutes
_GAP_CNT = lambda d: f"{round(d)}×"          # noqa: E731 — awakenings
_GAP_PTS = lambda d: f"{round(d)} pt"        # noqa: E731 — QQRT score


def _lever(lid, tier, rank, label, val, disp, better_low, target, gap_fmt):
    """One pulse lever tuple:
    (id, tier, tier_rank, label, display, target_text, status).
    Thresholds come from BANDS, so each lever's numbers are written exactly once."""
    green, amber = BANDS[lid]
    return (lid, tier, rank, label, disp,
            target + _gap(val, green, amber, better_low, gap_fmt),
            _light(val, green, amber, better_low))


def _clock(iso, signed):
    """(minutes, 12-hour display) from an ISO datetime. signed=True → an evening
    time is negative (bedtime); signed=False → plain minutes from midnight (wake)."""
    if not iso:
        return None, "—"
    try:
        t = _dt.datetime.fromisoformat(iso)
    except Exception:  # noqa: BLE001
        return None, "—"
    m = t.hour * 60 + t.minute
    m_val = m - 1440 if (signed and m > 720) else m
    hh = t.hour % 12 or 12
    return m_val, f"{hh}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _fmt_clock_target(minutes):
    """Signed minutes from midnight → a '10:45 PM' style target label."""
    total = int(minutes) % (24 * 60)
    h, m = divmod(total, 60)
    return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def pulse_levers(rec):
    """Pulse lever tuples for ONE day-tracking record.

    Reads the flat `health` block plus the persisted `qqrt` composite. Missing
    inputs produce a ⚪ lever rather than a crash — a gap is not a failure."""
    h = rec.get("health") or {}
    q = rec.get("qqrt") or {}
    sd = q.get("sleep_debt") or {}
    bt_min, bt_disp = _clock(h.get("sleep_bedtime"), True)
    wake_min, wake_disp = _clock(h.get("sleep_wake_time"), False)
    awake = h.get("awake_minutes")
    awk = h.get("awakenings_count")
    deep = h.get("sleep_deep_minutes")
    rem = h.get("sleep_rem_minutes")
    sh = h.get("sleep_hours")
    debt = sd.get("avg_shortfall_min")
    score = q.get("score")
    return [
        _lever("continuity", "CRITICAL", 0, "Continuity (awake)", awake,
               f"{awake}m" if awake is not None else "—", True, f"≤{BANDS['continuity'][0]}m", _GAP_MIN),
        _lever("rem", "CRITICAL", 0, "REM", rem,
               f"{rem}m" if rem is not None else "—", False, f"≥{BANDS['rem'][0]}m", _GAP_MIN),
        _lever("hours", "CRITICAL", 0, "Sleep hours", sh,
               f"{sh}h" if sh is not None else "—", False, f"≥{BANDS['hours'][0]}h", _GAP_HRS),
        _lever("debt", "CRITICAL", 0, "Trailing sleep debt", debt,
               f"{debt}m/night" if debt is not None else "—", True, f"≤{BANDS['debt'][0]}m", _GAP_MIN),
        _lever("deep", "CRITICAL", 0, "Deep sleep", deep,
               f"{deep}m" if deep is not None else "—", False, f"≥{BANDS['deep'][0]}m", _GAP_MIN),
        _lever("awakenings", "MODERATE", 1, "Awakenings", awk,
               f"{awk}×" if awk is not None else "—", True, f"≤{BANDS['awakenings'][0]}×", _GAP_CNT),
        _lever("bedtime", "MODERATE", 1, "Bedtime", bt_min, bt_disp, True,
               f"≤{_fmt_clock_target(BANDS['bedtime'][0])}", _GAP_MIN),
        _lever("wake", "MODERATE", 1, "Wake time", wake_min, wake_disp, True,
               f"≤{_fmt_clock_target(BANDS['wake'][0])}", _GAP_MIN),
        _lever("qqrt", "MODERATE", 1, "QQRT score", score,
               f"{score}/3" if score is not None else "—", False, f"≥{BANDS['qqrt'][0]}", _GAP_PTS),
    ]


# Per-lever remediation — the concrete "when this is off, do THIS". Reused by the
# tonight's-move line and any trend view. `{v}` interpolates the lever's value.
# Edit the wording freely; these are generic sleep-hygiene moves, not medical advice.
PULSE_FIX = {
    "debt":       "Bank sleep — carrying {v} of trailing debt; an earlier bedtime compounds it down over ~2 weeks.",
    "bedtime":    "Get horizontal earlier — the cheapest lever you fully control, and it feeds hours, REM and debt at once.",
    "wake":       "Alarm ~20 min earlier plus light on your eyes at wake (blinds open, or step outside) to pull the whole rhythm forward.",
    "continuity": "Cool room, phone out of reach, something calm to drop back off with — continuity is environment, not willpower.",
    "awakenings": "Woke {v} — hunt the disruptor: noise, light leak, a warm room, dry air, or late fluids. Kill the likeliest one.",
    "deep":       "Protect the first three hours — no alcohol, no late heavy meal, steady bedtime; deep sleep concentrates early in the night.",
    "rem":        "REM is back-loaded into the last third of the night, so an earlier bedtime buys more of it than anything else.",
    "hours":      "Short night — fix the bedtime, not the wake time.",
}

# Order for picking the single most-useful fix right now (most actionable first).
PULSE_FIX_PRIORITY = ["debt", "bedtime", "wake", "continuity", "awakenings", "deep", "hours", "rem"]


def pulse_snapshot(rows):
    """Latest record's levers + verdict + tonight's move — the entry point every
    consumer calls.

    `rows` is the parsed `data/day-tracking.ndjson` list. Returns
    {date, levers, verdict: {status, text}, move}, or None when no record has sleep
    data yet."""
    dated = sorted([r for r in rows if r.get("date")], key=lambda r: r["date"])
    rec = None
    for r in reversed(dated):
        h = r.get("health") or {}
        if h.get("sleep_hours") is not None or r.get("qqrt"):
            rec = r
            break
    if rec is None:
        return None

    levers = pulse_levers(rec)
    status_by = {lv[0]: lv[6] for lv in levers}
    disp_by = {lv[0]: lv[4] for lv in levers}

    crit = [lv for lv in levers if lv[1] == "CRITICAL"]
    crit_green = sum(1 for lv in crit if lv[6] == "🟢")
    debt_red = status_by.get("debt") == "🔴"
    if crit_green >= VERDICT_MIN_CRITICAL_GREEN and not debt_red:
        verdict = {"status": "🟢", "text": "Primed — the setup for a great day is in range."}
    elif crit_green >= VERDICT_MIN_CRITICAL_GREEN - 1 and not debt_red:
        verdict = {"status": "🟡", "text": "Borderline — a good day is reachable, a great one is a stretch."}
    else:
        verdict = {"status": "🔴", "text": "Depleted — lower today's ceiling and recover first."}

    move = "You're in the zone — just protect tonight (bed early, phone out of reach)."
    for lid in PULSE_FIX_PRIORITY:
        if status_by.get(lid) in ("🟡", "🔴"):
            move = PULSE_FIX[lid].replace("{v}", disp_by.get(lid, ""))
            break
    return {"date": rec["date"], "levers": levers, "verdict": verdict, "move": move}


def pulse_history(rows, n=7):
    """Per-lever status series over the last `n` dated records that have sleep data.

    Returns {dates, order, series: {id: {label, target, target_plain, tier,
    statuses[], last_disp}}} or None. One lever off once is noise; off five nights
    running is the finding — which is the whole reason the pulse keeps a short
    history instead of only today.

    `target` carries the distance-to-next-tier suffix that `_lever` appends, which
    describes the LATEST night only — meaningless on a multi-day trend, where it
    reads as if the gap were a property of the window. `target_plain` is the bare
    threshold, for callers rendering a window rather than a night."""
    days = sorted(
        [r for r in rows if r.get("date") and (r.get("health") or {}).get("sleep_hours") is not None],
        key=lambda r: r["date"],
    )[-n:]
    if not days:
        return None
    order, series = [], {}
    for rec in days:
        for lid, tier, _rank, label, disp, target, status in pulse_levers(rec):
            if lid not in series:
                order.append(lid)
                series[lid] = {"label": label, "target": target, "tier": tier,
                               "statuses": [], "last_disp": disp}
            series[lid]["statuses"].append(status)
            series[lid]["last_disp"] = disp
            series[lid]["target"] = target
            # The gap suffix is the only comma `_lever` ever introduces.
            series[lid]["target_plain"] = target.split(", ")[0]
    return {"dates": [r["date"] for r in days], "order": order, "series": series}


def pulse_window_status(statuses):
    """Roll one lever's per-day statuses over a window into a single 🟢/🟡/🔴.

    A window needs its own verdict — a count alone ("9/30") doesn't say whether
    that is fine or a problem, and the nightly light describes last night only.
    Red reuses the chronic-miss bar already in force (off on ≥ half the window);
    green demands on-target on ≥ two-thirds of it; everything between is yellow.
    The two bars cannot both be true. ⚪ only when the window is empty."""
    n = len(statuses)
    if not n:
        return "⚪"
    on = sum(1 for x in statuses if x == "🟢")
    off = sum(1 for x in statuses if x in ("🟡", "🔴"))
    if off * 2 >= n:
        return "🔴"
    return "🟢" if on * 3 >= n * 2 else "🟡"


def chronic_misses(hist, max_items=2):
    """Levers that were off (🟡/🔴) on at least half the history window, worst first.
    Returns [(off_count, lever_id, series_entry, fix_text)]."""
    if not hist:
        return []
    ndays = len(hist["dates"])
    thresh = (ndays + 1) // 2
    out = []
    for lid in hist["order"]:
        s = hist["series"][lid]
        off = sum(1 for x in s["statuses"] if x in ("🟡", "🔴"))
        if off >= thresh:
            out.append((off, lid, s, PULSE_FIX.get(lid, "").replace("{v}", s["last_disp"])))
    out.sort(key=lambda x: -x[0])
    return out[:max_items]


def print_pulse_history(rows, n=7):
    """Compact per-lever trend for a check-in: a status sparkline per lever, then
    the chronic misses with their concrete fix.

    `rows` is the parsed `data/day-tracking.ndjson` list. Printed rather than
    returned — this is the terminal/chat view; screen surfaces call
    `pulse_history` and shape their own output.
    """
    hist = pulse_history(rows, n)
    if not hist:
        print("No pulse history — no dated records with sleep data.")
        return
    dates = hist["dates"]
    ndays = len(dates)
    print(f"Daily Pulse trend — last {ndays} days ({dates[0]} → {dates[-1]}), oldest→newest")
    print(f"   (counts are days ON TARGET out of {ndays} — higher is better)")
    for lid in hist["order"]:
        s = hist["series"][lid]
        on = sum(1 for x in s["statuses"] if x == "🟢")
        roll = pulse_window_status(s["statuses"])
        print(f"  {roll} {s['label']:<20} {on}/{ndays} on target  {''.join(s['statuses'])}")

    # Chronic misses are *detected* on off-days but *reported* as on-days —
    # every number shown runs the same direction (high is good).
    chronic = chronic_misses(hist)
    print()
    if chronic:
        thresh = (ndays + 1) // 2
        print(f"Chronic misses (on target under {ndays - thresh + 1} of {ndays}) — get back on track:")
        for off, _lid, s, fix in chronic:
            on = sum(1 for x in s["statuses"] if x == "🟢")
            print(f"  🔴 {s['label']} — on target only {on}/{ndays}. {fix}")
    else:
        print("No chronic misses — the pulse is holding steady.")
