#!/usr/bin/env python3
"""
Statistical analysis of day-tracking data — what actually predicts a good day.

Four passes, in order of how much they can tell you:

  1. Linear correlation + effect size for every tracked variable.
  2. Multi-day context — yesterday's carry-over, rolling sleep debt, schedule
     variability, and a partial correlation that asks whether sleep TIMING matters
     beyond total duration.
  3. QQRT sleep threshold — an above/below-the-bar split and a composite ladder.
     A linear correlation is structurally blind to a threshold effect, so total
     hours can look flat while sleep is in fact the dominant driver.
  4. Trailing 2-night WORST night — a 4h night followed by an 8h night averages to
     "fine" and still wrecks the day. A minimum surfaces what a mean hides.

Usage:
    python3 automations/scripts/analyze_day_trends.py
"""

import json
import math
import statistics as stats_mod
import sys
from collections import defaultdict
from datetime import date as date_cls, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qqrt  # noqa: E402

REPO_ROOT    = Path(__file__).resolve().parents[2]
DAY_TRACKING = REPO_ROOT / "data/day-tracking.ndjson"
SUPPLEMENTS  = REPO_ROOT / "data/supplements.ndjson"

# ── Stats helpers (pure stdlib) ───────────────────────────────────────────────

def mean(vals):
    v = [x for x in vals if x is not None]
    return sum(v) / len(v) if v else None

def std(vals):
    v = [x for x in vals if x is not None]
    if len(v) < 2:
        return None
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))

def median(vals):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    n = len(v)
    return (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)

def pearson(xs, ys):
    """Pearson correlation between paired lists (skips pairs with None)."""
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 4:
        return None, len(pairs)
    n = len(pairs)
    sx = sum(p[0] for p in pairs)
    sy = sum(p[1] for p in pairs)
    sx2 = sum(p[0] ** 2 for p in pairs)
    sy2 = sum(p[1] ** 2 for p in pairs)
    sxy = sum(p[0] * p[1] for p in pairs)
    denom = math.sqrt((n * sx2 - sx ** 2) * (n * sy2 - sy ** 2))
    if denom == 0:
        return None, n
    return (n * sxy - sx * sy) / denom, n

def cohens_d(group_a, group_b):
    """Effect size between two groups."""
    a = [x for x in group_a if x is not None]
    b = [x for x in group_b if x is not None]
    if len(a) < 2 or len(b) < 2:
        return None
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    sa = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
    sb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
    pooled = math.sqrt((sa + sb) / 2)
    return (ma - mb) / pooled if pooled else None

def partial_correlation(xs, ys, zs):
    """Pearson r between x and y, controlling for z. Skips triples with any None."""
    triples = [(x, y, z) for x, y, z in zip(xs, ys, zs)
               if x is not None and y is not None and z is not None]
    if len(triples) < 5:
        return None, len(triples)
    xs2 = [t[0] for t in triples]
    ys2 = [t[1] for t in triples]
    zs2 = [t[2] for t in triples]
    r_xy, _ = pearson(xs2, ys2)
    r_xz, _ = pearson(xs2, zs2)
    r_yz, _ = pearson(ys2, zs2)
    if r_xy is None or r_xz is None or r_yz is None:
        return None, len(triples)
    denom = math.sqrt(max(0, (1 - r_xz ** 2) * (1 - r_yz ** 2)))
    if denom == 0:
        return None, len(triples)
    return (r_xy - r_xz * r_yz) / denom, len(triples)

def interpret_r(r):
    if r is None: return "insufficient data"
    a = abs(r)
    sign = "+" if r > 0 else "-"
    if a >= 0.5:   return f"{sign} strong"
    elif a >= 0.3: return f"{sign} moderate"
    elif a >= 0.1: return f"{sign} weak"
    else:          return "negligible"

def interpret_d(d):
    if d is None: return ""
    a = abs(d)
    direction = "higher on good days" if d > 0 else "higher on bad days"
    if a >= 0.8:   strength = "large"
    elif a >= 0.5: strength = "medium"
    elif a >= 0.2: strength = "small"
    else:          return "negligible difference"
    return f"{strength} effect — {direction}"

def bar(r, width=20):
    if r is None: return " " * width
    filled = round(abs(r) * width)
    return ("█" * filled).ljust(width)

def days_between(iso_a, iso_b):
    return (date_cls.fromisoformat(iso_b) - date_cls.fromisoformat(iso_a)).days

def lagged_pairs(records, key, lag=1):
    """Pairs of (prior-day value, today's rating) for consecutive-day records."""
    sorted_r = sorted(records, key=lambda r: r["date"])
    out = []
    for i in range(lag, len(sorted_r)):
        if days_between(sorted_r[i - lag]["date"], sorted_r[i]["date"]) != lag:
            continue
        prior = sorted_r[i - lag].get(key)
        rating = sorted_r[i].get("rating")
        if prior is not None and rating is not None:
            out.append((prior, rating))
    return out

def rolling_window_pairs(records, key, window, stat_fn):
    """For each record i, apply stat_fn over `key` across the consecutive window
    ending at i, paired with today's rating. Emits only when all `window` records
    are consecutive calendar days AND all have a non-null value."""
    sorted_r = sorted(records, key=lambda r: r["date"])
    out = []
    for i in range(window - 1, len(sorted_r)):
        chunk = sorted_r[i - window + 1: i + 1]
        if days_between(chunk[0]["date"], chunk[-1]["date"]) != window - 1:
            continue
        vals = [r.get(key) for r in chunk]
        if any(v is None for v in vals):
            continue
        rating = sorted_r[i].get("rating")
        if rating is None:
            continue
        out.append((stat_fn(vals), rating))
    return out

# ── Data loading ──────────────────────────────────────────────────────────────

def load_supplements():
    """Supplement records from supplements.ndjson (may be empty)."""
    if not SUPPLEMENTS.exists():
        return []
    out = []
    for line in SUPPLEMENTS.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out

def active_on(records, date, name):
    """The record for `name` active on ISO `date`, or None.
    Active on D ⇔ started <= D AND (stopped is null OR stopped > D).
    If several match, return the one with the latest `started`."""
    hits = [
        r for r in records
        if r.get("name") == name
        and r.get("started", "9999-12-31") <= date
        and (r.get("stopped") is None or r.get("stopped") > date)
    ]
    if not hits:
        return None
    return max(hits, key=lambda r: r.get("started", "9999-12-31"))

def parse_dose_mg(val):
    """Extract mg from strings like '250mg'. 0 when absent, None when unparseable."""
    if not val:
        return 0
    try:
        return float("".join(c for c in str(val) if c.isdigit() or c == "."))
    except ValueError:
        return None

def extract_health(h):
    """Normalized health fields from either the flat or the legacy nested schema."""
    sleep = h.get("sleep") if isinstance(h.get("sleep"), dict) else {}
    stages = sleep.get("stages_minutes") or h.get("sleep_stages") or {}
    rhr = h.get("resting_heart_rate") if isinstance(h.get("resting_heart_rate"), dict) else {}
    rhr_bpm = rhr.get("bpm") if isinstance(rhr, dict) else (rhr if isinstance(rhr, (int, float)) else None)
    azm_raw = h.get("active_zone_minutes")
    azm = azm_raw.get("total_minutes") if isinstance(azm_raw, dict) else azm_raw
    return {
        "sleep_hours": h.get("sleep_hours") if h.get("sleep_hours") is not None else sleep.get("total_hours"),
        "sleep_deep":  h.get("sleep_deep_minutes")  if h.get("sleep_deep_minutes")  is not None else stages.get("deep"),
        "sleep_rem":   h.get("sleep_rem_minutes")   if h.get("sleep_rem_minutes")   is not None else stages.get("rem"),
        "sleep_light": h.get("sleep_light_minutes") if h.get("sleep_light_minutes") is not None else stages.get("light"),
        "awake_min":   h.get("awake_minutes") if h.get("awake_minutes") is not None else (sleep.get("awake_minutes") if isinstance(sleep, dict) else None) or stages.get("wake"),
        "awakenings_count": h.get("awakenings_count"),
        "resting_hr":  h.get("resting_hr_bpm") if h.get("resting_hr_bpm") is not None else rhr_bpm,
        "azm":         azm,
        # Recovery metrics — daily readouts that are not sleep.
        "hrv_ms":      h.get("hrv_ms"),
        "spo2":        h.get("spo2_avg_pct"),
        "resp_rate":   h.get("respiratory_rate_bpm"),
        "skin_temp_dev": (
            round(h["skin_temp_nightly_c"] - h["skin_temp_baseline_c"], 2)
            if h.get("skin_temp_nightly_c") is not None and h.get("skin_temp_baseline_c") is not None
            else None
        ),
        "vo2max":      h.get("vo2max"),
        # Tracked workouts (device-recorded exercise sessions). Distinct from AZM: a
        # session carries type, intensity, and start time. `azm_outside_workouts` is
        # total AZM minus session AZM — it holds UNTRACKED workouts, walking, and
        # chores as well as an elevated resting heart rate, so it is NOT a stress
        # or anxiety measure.
        "workout_azm":      h.get("workout_azm"),
        "workout_vig_min":  h.get("workout_vigorous_minutes"),
        # workout_minutes is DELIBERATELY NOT a correlation variable. A watch timer
        # that is started and never stopped can overstate a 25-minute session as 90,
        # and calories and avg_hr_bpm inflate with it. Only the zone-based fields and
        # the heart-rate-derived length (row_duration.py) survive an un-stopped timer.
        # Do not add duration back in.
        "workout_real_min": h.get("workout_real_minutes"),
        "workout_count":    h.get("workout_count"),
        "azm_outside":      h.get("azm_outside_workouts"),
        "first_workout":    h.get("first_workout_time"),
        "workout_types":    [w.get("type") for w in (h.get("workouts") or [])],
        "bedtime":     h.get("sleep_bedtime")   or h.get("bedtime")   or (sleep.get("bedtime")   if isinstance(sleep, dict) else None),
        "wake_time":   h.get("sleep_wake_time") or h.get("wake_time") or (sleep.get("wake_time") if isinstance(sleep, dict) else None),
    }

def fmt_clock(m):
    """Signed minutes past midnight → 12-hour AM/PM clock string."""
    if m is None:
        return "n/a"
    total = int(round(m))
    if total < 0:
        total = (24 * 60) + total
    total = total % (24 * 60)
    h, mm = divmod(total, 60)
    return f"{h % 12 or 12}:{mm:02d} {'AM' if h < 12 else 'PM'}"

def load_records():
    records = []
    for line in DAY_TRACKING.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("rating") is None:
            continue  # skip records with no rating
        h = r.get("health") or {}
        hx = extract_health(h)
        # `exercised` = did your keystone workout at all today, at any time. It
        # supersedes any time-boxed flag (a `morning_movement`-style field) — the
        # narrower question threw away every workout that happened later in the day.
        # Legacy field is read as a fallback so old records still count.
        exercised = r.get("exercised")
        if exercised is None:
            exercised = r.get("morning_movement")
        records.append({
            "date":         r["date"],
            "rating":       r["rating"],
            # Sleep
            "sleep_hours":  hx["sleep_hours"],
            "sleep_deep":   hx["sleep_deep"],
            "sleep_rem":    hx["sleep_rem"],
            "sleep_light":  hx["sleep_light"],
            "awake_min":    hx["awake_min"],
            "awakenings":   hx["awakenings_count"],
            # Recovery
            "resting_hr":   hx["resting_hr"],
            "hrv_ms":       hx["hrv_ms"],
            "spo2":         hx["spo2"],
            "resp_rate":    hx["resp_rate"],
            "skin_temp_dev": hx["skin_temp_dev"],
            "azm":          hx["azm"],
            # Tracked workouts
            "workout_azm":     hx["workout_azm"],
            "workout_vig_min": hx["workout_vig_min"],
            "workout_real_min": hx["workout_real_min"],
            "azm_outside":     hx["azm_outside"],
            "workout_session": (1 if hx["workout_count"] else 0) if hx["workout_count"] is not None else None,
            "workout_start_min": qqrt.wake_offset_minutes(hx["first_workout"], r["date"]),
            "workout_types":   hx["workout_types"],
            # Sleep timing (continuous: signed minutes from midnight)
            "bedtime_min":  qqrt.bedtime_offset_minutes(hx["bedtime"], r["date"]),
            "wake_min":     qqrt.wake_offset_minutes(hx["wake_time"], r["date"]),
            # Self-reported
            "exercised":    (1 if exercised else 0) if exercised is not None else None,
            "hyperfocused": (1 if r.get("hyperfocused") else 0) if r.get("hyperfocused") is not None else None,
            "sick":         1 if r.get("sick") else 0,
            "energy":       r.get("energy"),
            "focus":        r.get("focus"),
            "mood":         r.get("mood"),
            # Physiology composite: energy + focus, mood EXCLUDED. Mood measures
            # general well-being, which is a different construct from the body's
            # sleep response — so it's dropped from the sleep outcome, not because
            # any day is "contaminated". None when the components were never
            # captured.
            "physiology":   ((r.get("energy") + r.get("focus")) / 2.0
                             if r.get("energy") is not None and r.get("focus") is not None else None),
        })
    return records

# ── Analysis ──────────────────────────────────────────────────────────────────

VARIABLES = {
    "sleep_hours":  "Sleep hours",
    "sleep_deep":   "Deep sleep (min)",
    "sleep_rem":    "REM sleep (min)",
    "sleep_light":  "Light sleep (min)",
    "awake_min":    "Awake during sleep (min)",
    "awakenings":   "Awakenings (count)",
    "bedtime_min":  "Bedtime (min from midnight)",
    "wake_min":     "Wake time (min past midnight)",
    "resting_hr":   "Resting heart rate (bpm)",
    "hrv_ms":       "Heart-rate variability (ms)",
    "spo2":         "Blood oxygen (%)",
    "resp_rate":    "Breathing rate (per min)",
    "skin_temp_dev": "Skin temp vs baseline (°C)",
    "azm":          "Active zone minutes",
    "workout_azm":     "Workout AZM (tracked sessions)",
    "workout_vig_min": "Vigorous+peak minutes (tracked)",
    "workout_real_min": "Workout minutes (heart-rate derived)",
    "azm_outside":     "AZM outside tracked workouts",
    "workout_session": "Tracked a workout",
    "workout_start_min": "First workout start (min past midnight)",
    "exercised":    "Keystone workout (any time)",
    "hyperfocused": "Hyperfocused / inflexible",
    "sick":         "Sick day",
    "energy":       "Energy rating (1-5)",
    "focus":        "Focus rating (1-5)",
    "mood":         "Mood rating (1-5)",
}

def analyze(records):
    ratings = [r["rating"] for r in records]
    good = [r for r in records if r["rating"] >= 4]
    bad  = [r for r in records if r["rating"] <= 2]
    mid  = [r for r in records if r["rating"] == 3]

    results = {}
    for key, label in VARIABLES.items():
        vals = [r.get(key) for r in records]
        r_val, n = pearson(vals, ratings)
        d_val = cohens_d([r.get(key) for r in good], [r.get(key) for r in bad])
        results[key] = {
            "label":      label,
            "r":          r_val,
            "n":          n,
            "d":          d_val,
            "good_mean":  mean([r.get(key) for r in good]),
            "bad_mean":   mean([r.get(key) for r in bad]),
            "all_mean":   mean(vals),
            "all_median": median(vals),
        }

    ranked = sorted(
        [(k, v) for k, v in results.items() if v["r"] is not None],
        key=lambda x: abs(x[1]["r"]),
        reverse=True,
    )
    return results, ranked, good, bad, mid, ratings


def print_gate_gradient(records):
    """Ordinal pass: each factor's mean inside EVERY rating bucket, classified by
    the SHAPE of its movement across the scale.

    Why this pass exists: the good-vs-bad split throws away the middle of your data
    and cannot tell a dial from a switch. Two very different factors look identical
    to a correlation:

      GRADIENT — climbs steadily across every bucket. A dose-response dial: nudge it
                 and you move up the scale. Worth a daily surface (a habit, a pulse
                 lever), because every increment pays.
      GATE     — flat across the low and middle buckets, then jumps only at the top.
                 A pass/fail condition your best days clear, not something to trend
                 toward. Surface it as a checkbox, and expect it to come along once
                 the gradient levers are in range.

    The test is where the movement LANDS (the share of total span in the final
    step), not raw monotonicity — a front-flat factor is technically monotonic."""
    by = defaultdict(list)
    for r in records:
        by[r["rating"]].append(r)
    buckets = sorted(by)
    if len(buckets) < 3:
        print("\n── GATE vs GRADIENT ─────────────────────────────────────────")
        print("  Need at least 3 distinct rating buckets — keep logging.")
        return

    factors = [
        ("deep sleep", "sleep_deep", True), ("REM", "sleep_rem", True),
        ("sleep hours", "sleep_hours", True), ("awake min", "awake_min", False),
        ("awakenings", "awakenings", False), ("bedtime", "bedtime_min", False),
        ("wake time", "wake_min", False), ("HRV", "hrv_ms", True),
        ("resting HR", "resting_hr", False), ("blood oxygen", "spo2", True),
    ]
    print("\n── GATE vs GRADIENT (mean per rating bucket) ────────────────")
    print(f"  buckets: {'  '.join(str(b) for b in buckets)}")
    print(f"  {'factor':<14} {'means':<34} class")
    print(f"  {'-'*62}")
    for label, key, higher_is_better in factors:
        means = []
        for b in buckets:
            vals = [r.get(key) for r in by[b] if r.get(key) is not None]
            means.append(mean(vals))
        seq = [m for m in means if m is not None]
        if len(seq) < 3:
            continue
        mono_up = all(seq[i] <= seq[i + 1] for i in range(len(seq) - 1))
        mono_dn = all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1))
        clean = (mono_up and higher_is_better) or (mono_dn and not higher_is_better)
        span = abs(seq[-1] - seq[0])
        top_share = abs(seq[-1] - seq[-2]) / span if span else 0
        if span == 0:                     kind = "flat"
        elif clean and top_share <= 0.55: kind = "GRADIENT"
        elif top_share >= 0.5:            kind = "GATE"
        else:                             kind = "noisy"
        shown = "  ".join(f"{m:6.1f}" if m is not None else "     —" for m in means)
        print(f"  {label:<14} {shown:<34} {kind} (top-step {top_share:.0%})")
    print("  GRADIENT → a dial worth a daily surface · GATE → a pass/fail condition")
    print("  flat / noisy → report honestly as a non-driver; do NOT promote it to a lever.")


def print_report(records):
    n_total = len(records)
    results, ranked, good, bad, mid, ratings = analyze(records)

    print(f"\n{'='*62}")
    print(f"  DAY TRACKER TREND ANALYSIS")
    print(f"  {n_total} days  |  Good (4-5): {len(good)}  |  Mid (3): {len(mid)}  |  Bad (1-2): {len(bad)}")
    print(f"  Avg rating: {mean(ratings):.2f}  |  Range: {min(ratings)}–{max(ratings)}")
    print(f"{'='*62}")

    # ── Correlation rankings ──
    print(f"\n── CORRELATION WITH DAY RATING (Pearson r) ──────────────────")
    print(f"  {'Variable':<28} {'r':>6}  {'Strength':<18} {'n':>3}")
    print(f"  {'-'*57}")
    for key, v in ranked:
        print(f"  {v['label']:<28} {v['r']:>+.3f}  {bar(v['r'], 14)}  {interpret_r(v['r']):<18} {v['n']:>3}")

    # ── Good vs bad day profiles ──
    print(f"\n── GOOD DAYS (4-5) vs BAD DAYS (1-2) ───────────────────────")
    print(f"  {'Variable':<28} {'Good':>7}  {'Bad':>7}  {'Diff':>7}  Effect")
    print(f"  {'-'*68}")
    for key, label in VARIABLES.items():
        v = results[key]
        gm, bm = v["good_mean"], v["bad_mean"]
        if gm is None or bm is None:
            continue
        print(f"  {label:<28} {gm:>7.1f}  {bm:>7.1f}  {gm - bm:>+7.1f}  {interpret_d(v['d'])}")

    # ── Top predictors ──
    print(f"\n── TOP PREDICTORS ───────────────────────────────────────────")
    printable = [
        (k, v) for k, v in ranked
        if v["r"] is not None and abs(v["r"]) >= 0.15
        and v["good_mean"] is not None and v["bad_mean"] is not None
    ][:5]
    for i, (key, v) in enumerate(printable, 1):
        print(f"  {i}. {v['label']}")
        print(f"     r={v['r']:+.3f} — good days avg {v['good_mean']:.1f}, bad days avg {v['bad_mean']:.1f}")
        print(f"     → {interpret_d(v['d'])}")

    # ── Gate vs gradient ──
    print_gate_gradient(records)

    # ── Sleep breakdown ──
    print(f"\n── SLEEP BREAKDOWN ──────────────────────────────────────────")
    for key in ["sleep_hours", "sleep_deep", "sleep_rem", "awake_min", "awakenings"]:
        v = results[key]
        if v["all_mean"] is None:
            continue
        gm = f"{v['good_mean']:.1f}" if v["good_mean"] is not None else "n/a"
        bm = f"{v['bad_mean']:.1f}" if v["bad_mean"] is not None else "n/a"
        print(f"  {v['label']:<28}  overall avg: {v['all_mean']:.1f}  |  good: {gm}  |  bad: {bm}")

    # ── Keystone-workout breakdown ──
    ex_records = [r for r in records if r.get("exercised") is not None]
    if ex_records:
        print(f"\n── KEYSTONE WORKOUT BREAKDOWN ──────────────────────────────")
        print(f"  (self-reported: did it happen at all, at any time of day)")
        did   = [r["rating"] for r in ex_records if r["exercised"] == 1]
        skipped = [r["rating"] for r in ex_records if r["exercised"] == 0]
        print(f"  {'Bucket':<14} {'n':>3}  {'avg rating':>11}  {'good%':>6}  {'bad%':>6}")
        print(f"  {'-'*48}")
        for label, group in [("did it", did), ("skipped", skipped)]:
            if not group:
                continue
            good_pct = 100 * sum(1 for x in group if x >= 4) / len(group)
            bad_pct  = 100 * sum(1 for x in group if x <= 2) / len(group)
            print(f"  {label:<14} {len(group):>3}  {sum(group)/len(group):>11.2f}  {good_pct:>5.0f}%  {bad_pct:>5.0f}%")
        d = cohens_d(did, skipped)
        if d is not None:
            print(f"  Effect size (Cohen's d): {d:+.2f} — {interpret_d(d)}")

    # ── Tracked workout breakdown ──
    # Self-reported `exercised` and a device-tracked session measure DIFFERENT things:
    # one is intent, the other is what the watch recorded. They disagree whenever you
    # work out without starting a session, so both are kept and a finding must say
    # which one it rests on. A day with no tracked session is NOT evidence of rest.
    wk_records = [r for r in records if r.get("workout_session") is not None]
    if wk_records:
        print(f"\n── TRACKED WORKOUT BREAKDOWN ───────────────────────────────")
        print(f"  (device-recorded sessions only — untracked workouts land in the")
        print(f"   'no session' bucket, so treat that bucket as mixed, not as rest)")
        tracked   = [r["rating"] for r in wk_records if r["workout_session"] == 1]
        untracked = [r["rating"] for r in wk_records if r["workout_session"] == 0]
        print(f"  {'Bucket':<14} {'n':>3}  {'avg rating':>11}  {'good%':>6}  {'bad%':>6}")
        print(f"  {'-'*48}")
        for label, group in [("session", tracked), ("no session", untracked)]:
            if not group:
                continue
            good_pct = 100 * sum(1 for x in group if x >= 4) / len(group)
            bad_pct  = 100 * sum(1 for x in group if x <= 2) / len(group)
            print(f"  {label:<14} {len(group):>3}  {sum(group)/len(group):>11.2f}  {good_pct:>5.0f}%  {bad_pct:>5.0f}%")
        d = cohens_d(tracked, untracked)
        if d is not None:
            print(f"  Effect size (Cohen's d): {d:+.2f} — {interpret_d(d)}")

        hard = [r["rating"] for r in wk_records if (r.get("workout_vig_min") or 0) >= 10]
        easy = [r["rating"] for r in wk_records
                if r["workout_session"] == 1 and (r.get("workout_vig_min") or 0) < 10]
        if len(hard) >= 3 and len(easy) >= 3:
            print(f"\n  Intensity (within tracked sessions):")
            print(f"    {'>=10 vigorous min':<20} n={len(hard):>3}  avg {sum(hard)/len(hard):.2f}")
            print(f"    {'<10 vigorous min':<20} n={len(easy):>3}  avg {sum(easy)/len(easy):.2f}")
            d = cohens_d(hard, easy)
            if d is not None:
                print(f"    Effect size (Cohen's d): {d:+.2f} — {interpret_d(d)}")

        morning = [r["rating"] for r in wk_records
                   if r.get("workout_start_min") is not None and r["workout_start_min"] < 600]
        later   = [r["rating"] for r in wk_records
                   if r.get("workout_start_min") is not None and r["workout_start_min"] >= 600]
        if len(morning) >= 3 and len(later) >= 3:
            print(f"\n  Timing (first session of the day):")
            print(f"    {'before 10 AM':<20} n={len(morning):>3}  avg {sum(morning)/len(morning):.2f}")
            print(f"    {'10 AM or later':<20} n={len(later):>3}  avg {sum(later)/len(later):.2f}")
            d = cohens_d(morning, later)
            if d is not None:
                print(f"    Effect size (Cohen's d): {d:+.2f} — {interpret_d(d)}")

        by_type = {}
        for r in wk_records:
            for t in set(r.get("workout_types") or []):
                by_type.setdefault(t, []).append(r["rating"])
        typed = {t: v for t, v in by_type.items() if len(v) >= 3}
        if typed:
            print(f"\n  By exercise type (days including that type, n>=3):")
            for t, group in sorted(typed.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
                print(f"    {str(t).replace('_', ' ').title():<20} n={len(group):>3}  avg {sum(group)/len(group):.2f}")

    # ── Sleep timing ──
    timing_records = [r for r in records if r.get("bedtime_min") is not None or r.get("wake_min") is not None]
    if timing_records:
        print(f"\n── SLEEP TIMING ────────────────────────────────────────────")
        print(f"  (timing is load-bearing alongside duration: 7 hours from 11 PM is")
        print(f"   not 7 hours from 2 AM, even with identical stage minutes)")
        print(f"  {'Metric':<14} {'all':>10}  {'good days':>10}  {'bad days':>10}  {'n':>3}")
        print(f"  {'-'*55}")

        def line(label, key):
            all_v  = [r.get(key) for r in records]
            good_v = [r.get(key) for r in good]
            bad_v  = [r.get(key) for r in bad]
            n = sum(1 for v in all_v if v is not None)
            print(f"  {label:<14} {fmt_clock(mean(all_v)):>10}  {fmt_clock(mean(good_v)):>10}  "
                  f"{fmt_clock(mean(bad_v)):>10}  {n:>3}")

        line("Bedtime", "bedtime_min")
        line("Wake time", "wake_min")

        # Bedtime buckets (signed minutes from midnight).
        bt_buckets = {"before 10:30 PM": [], "10:30-11:30 PM": [], "11:30-12:30 AM": [], "after 12:30 AM": []}
        for r in records:
            bt = r.get("bedtime_min")
            if bt is None:
                continue
            if bt < -90:   bt_buckets["before 10:30 PM"].append(r["rating"])
            elif bt < -30: bt_buckets["10:30-11:30 PM"].append(r["rating"])
            elif bt < 30:  bt_buckets["11:30-12:30 AM"].append(r["rating"])
            else:          bt_buckets["after 12:30 AM"].append(r["rating"])
        bt_total = sum(len(v) for v in bt_buckets.values())
        if bt_total:
            print(f"\n  Bedtime buckets:")
            print(f"  {'Bucket':<22} {'n':>3}  {'avg rating':>11}")
            for label, rs in bt_buckets.items():
                if rs:
                    print(f"  {label:<22} {len(rs):>3}  {sum(rs)/len(rs):>11.2f}")

        wk_buckets = {"before 6:30 AM": [], "6:30-7:30 AM": [], "7:30-8:30 AM": [], "after 8:30 AM": []}
        for r in records:
            wk = r.get("wake_min")
            if wk is None:
                continue
            if wk < 390:   wk_buckets["before 6:30 AM"].append(r["rating"])
            elif wk < 450: wk_buckets["6:30-7:30 AM"].append(r["rating"])
            elif wk < 510: wk_buckets["7:30-8:30 AM"].append(r["rating"])
            else:          wk_buckets["after 8:30 AM"].append(r["rating"])
        if sum(len(v) for v in wk_buckets.values()):
            print(f"\n  Wake-time buckets:")
            print(f"  {'Bucket':<22} {'n':>3}  {'avg rating':>11}")
            for label, rs in wk_buckets.items():
                if rs:
                    print(f"  {label:<22} {len(rs):>3}  {sum(rs)/len(rs):>11.2f}")

        if bt_total < 7:
            print(f"\n  ⚠️  Timing data is thin ({bt_total} days). Run "
                  f"google_health_backfill.py --all to populate older records.")

    # ── Multi-day context ──
    print(f"\n── MULTI-DAY CONTEXT ───────────────────────────────────────")
    print(f"  (today's rating isn't only about today — sleep debt, prior-day")
    print(f"   spillover, and schedule variability all land here)")

    print(f"\n  Lagged (yesterday → today's rating):")
    print(f"  {'Predictor':<32} {'r':>7}  {'n':>3}  Strength")
    print(f"  {'-'*56}")
    for key, label in [
        ("sleep_hours",  "Yesterday's sleep hours"),
        ("rating",       "Yesterday's day rating"),
        ("bedtime_min",  "Yesterday's bedtime"),
        ("exercised",    "Yesterday's keystone workout"),
        ("hyperfocused", "Yesterday's hyperfocus"),
    ]:
        pairs = lagged_pairs(records, key, lag=1)
        if len(pairs) < 4:
            print(f"  {label:<32} {'n/a':>7}  {len(pairs):>3}  insufficient consecutive-day pairs")
            continue
        r, n = pearson([p[0] for p in pairs], [p[1] for p in pairs])
        if r is None:
            print(f"  {label:<32} {'n/a':>7}  {n:>3}  no variance")
        else:
            print(f"  {label:<32} {r:>+.3f}  {n:>3}  {interpret_r(r)}")

    print(f"\n  Rolling 3-day sleep debt (relative to a {qqrt.NEED_HOURS}h target):")
    debt_pairs = rolling_window_pairs(records, "sleep_hours", window=3,
                                      stat_fn=lambda vs: sum(v - qqrt.NEED_HOURS for v in vs))
    if len(debt_pairs) >= 5:
        r, n = pearson([p[0] for p in debt_pairs], [p[1] for p in debt_pairs])
        sorted_debt = sorted(debt_pairs)
        worst_third = sorted_debt[:len(sorted_debt) // 3] or sorted_debt[:1]
        best_third  = sorted_debt[-(len(sorted_debt) // 3):] or sorted_debt[-1:]
        print(f"    r={r:+.3f}  n={n}  {interpret_r(r)}")
        print(f"    Worst-debt third: avg rating {sum(p[1] for p in worst_third)/len(worst_third):.2f}"
              f"  (debt sum {worst_third[0][0]:+.1f}h..{worst_third[-1][0]:+.1f}h)")
        print(f"    Best-rest third:  avg rating {sum(p[1] for p in best_third)/len(best_third):.2f}"
              f"  (debt sum {best_third[0][0]:+.1f}h..{best_third[-1][0]:+.1f}h)")
    else:
        print(f"    insufficient consecutive 3-day windows (n={len(debt_pairs)})")

    print(f"\n  7-day bedtime variability (schedule steadiness):")
    var_pairs = rolling_window_pairs(records, "bedtime_min", window=7,
                                     stat_fn=lambda vs: stats_mod.pstdev(vs) if len(vs) >= 2 else 0.0)
    if len(var_pairs) >= 5:
        r, n = pearson([p[0] for p in var_pairs], [p[1] for p in var_pairs])
        sorted_var = sorted(var_pairs)
        steady  = sorted_var[:len(sorted_var) // 3] or sorted_var[:1]
        varied  = sorted_var[-(len(sorted_var) // 3):] or sorted_var[-1:]
        print(f"    r={r:+.3f}  n={n}  {interpret_r(r)}")
        print(f"    Steadiest third: avg rating {sum(p[1] for p in steady)/len(steady):.2f}"
              f"  (spread {steady[0][0]:.0f}..{steady[-1][0]:.0f} min)")
        print(f"    Most variable third: avg rating {sum(p[1] for p in varied)/len(varied):.2f}"
              f"  (spread {varied[0][0]:.0f}..{varied[-1][0]:.0f} min)")
    else:
        print(f"    insufficient consecutive 7-day windows (n={len(var_pairs)})")

    print(f"\n  Partial correlation — does bedtime matter beyond total sleep?")
    r_raw, _ = pearson([r.get("bedtime_min") for r in records], [r.get("rating") for r in records])
    r_part, n_part = partial_correlation(
        [r.get("bedtime_min") for r in records],
        [r.get("rating") for r in records],
        [r.get("sleep_hours") for r in records],
    )
    if r_raw is not None and r_part is not None:
        print(f"    Raw     r(bedtime → rating)               = {r_raw:+.3f}")
        print(f"    Partial r(bedtime → rating | sleep_hours) = {r_part:+.3f}  (n={n_part})")
        ratio = abs(r_part) / abs(r_raw) if r_raw else 0
        if ratio < 0.5:
            verdict = "→ bedtime's effect is mostly mediated by total sleep duration"
        elif ratio > 0.8:
            verdict = "→ bedtime has an independent effect beyond total sleep — TIMING matters on its own"
        else:
            verdict = "→ bedtime has a partly-independent effect (timing + duration both contribute)"
        print(f"    {verdict}")
    else:
        print(f"    insufficient data (n={n_part or 0})")

    wd_buckets = defaultdict(list)
    for r in records:
        wd_buckets[date_cls.fromisoformat(r["date"]).strftime("%A")].append(r["rating"])
    if wd_buckets:
        print(f"\n  Day-of-week effect:")
        print(f"  {'Day':<12} {'n':>3}  {'avg rating':>11}")
        print(f"  {'-'*30}")
        for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
            if day in wd_buckets:
                vals = wd_buckets[day]
                print(f"  {day:<12} {len(vals):>3}  {sum(vals)/len(vals):>11.2f}")

    # ── QQRT sleep threshold ──
    print_qqrt_section(records)

    # ── Legend ──
    print(f"\n── LEGEND ───────────────────────────────────────────────────")
    print(f"  n = number of days with data for this variable")
    print(f"      (higher n = more reliable; anything below ~7 is thin).")
    print(f"  r = Pearson correlation with day rating, range -1 to +1.")
    print(f"      +1 = perfectly moves together, 0 = no relationship,")
    print(f"      -1 = perfectly opposite. Bands used above:")
    print(f"        |r| ≥ 0.5  strong     |r| ≥ 0.3  moderate")
    print(f"        |r| ≥ 0.1  weak       |r| < 0.1  negligible")
    print(f"  Effect size (Cohen's d): size of the gap between good and bad days.")
    print(f"      large ≥ 0.8 | medium ≥ 0.5 | small ≥ 0.2 | negligible < 0.2")
    print(f"  Partial r controls for a confounder: r(X→Y | Z) is the X→Y signal")
    print(f"      with Z's contribution removed. If partial r is far below raw r,")
    print(f"      the original signal was mostly Z in disguise.")
    print(f"  Correlation ≠ causation. Small n means 'watch this', not 'proven'.")

    print(f"\n{'='*62}\n")


def print_qqrt_section(records):
    """QQRT threshold, composite ladder, sleep debt, and trailing-2-night worst night.

    Total sleep hours often reads FLAT against day rating, which invites the wrong
    conclusion that sleep doesn't matter. The real effect is usually a THRESHOLD:
    a night either clears the Quantity + Quality + Timing bars or it doesn't, and a
    linear correlation cannot see that shape. This section splits above/below the
    bar and ladders the composite instead.

    OUTCOME: the physiology composite (energy + focus, mood EXCLUDED) where it was
    captured, else the stored rating. Mood is the event-contaminated component."""
    print(f"\n── QQRT SLEEP THRESHOLD ─────────────────────────────────────")
    print(f"  (good sleep = Quantity + Quality + Timing crossing a bar, not just")
    print(f"   total hours. Regularity is computed and tracked, not scored.)")
    print(f"  OUTCOME = energy+focus composite where available, else the rating.")
    print(f"  'good' = outcome >= 4.")

    def target(r):
        p = r.get("physiology")
        return p if p is not None else r.get("rating")

    # Every day counts. No day is excluded for having had something happen in it
    # (there is no `life_event` field): events are a normal, frequent part of a
    # life, and dropping event days biases the sample toward uneventful ones.
    # The mood-vs-physiology split above is the only separation that happens here.
    qq = list(records)

    by_date = {}
    for r in qq:
        try:
            by_date[date_cls.fromisoformat(r["date"])] = r
        except ValueError:
            pass

    def eff(r):
        return qqrt.efficiency(r.get("sleep_hours"), r.get("awake_min"))

    mid_by_date = {d: qqrt.sleep_midpoint(rec.get("bedtime_min"), rec.get("wake_min"))
                   for d, rec in by_date.items()}

    elig = [r for r in qq if r.get("sleep_hours") is not None
            and eff(r) is not None and r.get("bedtime_min") is not None]

    strict = lambda r: (r["sleep_hours"] >= qqrt.QUANTITY_MIN_HOURS  # noqa: E731
                        and eff(r) >= qqrt.QUALITY_MIN_EFFICIENCY
                        and r["bedtime_min"] <= qqrt.TIMING_ASLEEP_BY_MIN)
    loose = lambda r: (r["sleep_hours"] >= qqrt.QUANTITY_MIN_HOURS - 0.5  # noqa: E731
                       and eff(r) >= qqrt.QUALITY_MIN_EFFICIENCY - 1.0)

    for label, fn in [
        (f"STRICT  (>={qqrt.QUANTITY_MIN_HOURS}h & eff>={qqrt.QUALITY_MIN_EFFICIENCY:.0f}% & "
         f"bed<={fmt_clock(qqrt.TIMING_ASLEEP_BY_MIN)})", strict),
        (f"LOOSE   (>={qqrt.QUANTITY_MIN_HOURS - 0.5}h & eff>={qqrt.QUALITY_MIN_EFFICIENCY - 1:.0f}%)", loose),
    ]:
        above = [target(r) for r in elig if fn(r) and target(r) is not None]
        below = [target(r) for r in elig if not fn(r) and target(r) is not None]
        if above and below:
            pa = 100 * sum(1 for x in above if x >= 4) / len(above)
            pb = 100 * sum(1 for x in below if x >= 4) / len(below)
            print(f"\n  {label}")
            print(f"    above: n={len(above):>2}  avg {sum(above)/len(above):.2f}  %good(>=4) {pa:.0f}%")
            print(f"    below: n={len(below):>2}  avg {sum(below)/len(below):.2f}  %good(>=4) {pb:.0f}%")
            print(f"    delta avg {sum(above)/len(above) - sum(below)/len(below):+.2f}"
                  f"  |  delta %good {pa - pb:+.0f}pts")

    if elig:
        n_above = sum(1 for r in elig if strict(r))
        print(f"\n  Days above the strict bar: {n_above}/{len(elig)} = {100*n_above/len(elig):.0f}%")
        print(f"    (if that share is low, most days cluster BELOW threshold — which is")
        print(f"     exactly why simple averages look flat. The threshold effect lives")
        print(f"     in the rare above-bar days, not in the linear correlation.)")

    ladder = defaultdict(list)
    for r in qq:
        if target(r) is None:
            continue
        try:
            d = date_cls.fromisoformat(r["date"])
        except ValueError:
            continue
        win = qqrt.regularity_window(mid_by_date, d)
        lv = qqrt.levers(r.get("sleep_hours"), r.get("awake_min"),
                         r.get("sleep_deep"), r.get("bedtime_min"), win)
        ladder[lv["score"]].append(target(r))
    if ladder:
        print(f"\n  QQRT score (Quantity + Quality + Timing) → avg outcome:")
        print(f"  {'levers':<8} {'n':>3}  {'avg':>11}  {'%good(>=4)':>11}")
        print(f"  {'-'*40}")
        for s in sorted(ladder):
            v = ladder[s]
            pg = 100 * sum(1 for x in v if x >= 4) / len(v)
            print(f"  {s}/3{'':<5} {len(v):>3}  {sum(v)/len(v):>11.2f}  {pg:>10.0f}%")
        print(f"  (Q=>={qqrt.QUANTITY_MIN_HOURS}h · Q=efficiency>={qqrt.QUALITY_MIN_EFFICIENCY:.0f}%"
              f" & deep>={qqrt.QUALITY_MIN_DEEP_PCT:.0f}% · T=asleep by "
              f"{fmt_clock(qqrt.TIMING_ASLEEP_BY_MIN)}. Tune these in config/automation_config.yaml.)")

    # ── Sleep debt (companion predictor, not a score lever) ──
    hours_by_date = {d: rec.get("sleep_hours") for d, rec in by_date.items()}
    debt_pairs = []
    for r in qq:
        if target(r) is None:
            continue
        try:
            d = date_cls.fromisoformat(r["date"])
        except ValueError:
            continue
        dbt = qqrt.sleep_debt(hours_by_date, d)
        if dbt is not None:
            debt_pairs.append((dbt["avg_shortfall_min"], target(r)))
    if len(debt_pairs) > 5:
        med = stats_mod.median([x for x, _ in debt_pairs])
        lo = [y for x, y in debt_pairs if x <= med]
        hi = [y for x, y in debt_pairs if x > med]
        print(f"\n  Sleep debt ({qqrt.DEBT_WINDOW_NIGHTS}-night avg nightly shortfall vs "
              f"{qqrt.NEED_HOURS}h target):")
        print(f"    low debt (<={med:.0f}m):  n={len(lo):>2}  avg {sum(lo)/len(lo):.2f}"
              f"  %good {100*sum(1 for x in lo if x>=4)/len(lo):.0f}%")
        print(f"    high debt (>{med:.0f}m):  n={len(hi):>2}  avg {sum(hi)/len(hi):.2f}"
              f"  %good {100*sum(1 for x in hi if x>=4)/len(hi):.0f}%")
        print(f"    (this is the 'looks good on paper' detector: a long, continuous")
        print(f"     night taken while still in debt underperforms an identical night")
        print(f"     taken rested. The per-day number is persisted as qqrt.sleep_debt.)")

    # ── Trailing 2-night WORST night ──
    print(f"\n  Trailing 2-night WORST night (min sleep hours) vs outcome:")
    min_pairs = []
    for r in qq:
        if target(r) is None or r.get("sleep_hours") is None:
            continue
        try:
            d = date_cls.fromisoformat(r["date"])
        except ValueError:
            continue
        prev = by_date.get(d - timedelta(days=1))
        if prev and prev.get("sleep_hours") is not None:
            min_pairs.append((min(r["sleep_hours"], prev["sleep_hours"]), target(r)))
    if len(min_pairs) >= 5:
        r_min, n_min = pearson([p[0] for p in min_pairs], [p[1] for p in min_pairs])
        worst = [p[1] for p in min_pairs if p[0] < 6.0]
        ok    = [p[1] for p in min_pairs if p[0] >= 6.0]
        print(f"    r={r_min:+.3f}  n={n_min}  {interpret_r(r_min)}")
        if worst and ok:
            print(f"    any night <6h in the last 2: avg {sum(worst)/len(worst):.2f}  (n={len(worst)})")
            print(f"    both nights >=6h:            avg {sum(ok)/len(ok):.2f}  (n={len(ok)})")
        print(f"    (a rolling AVERAGE hides a 4h+8h split; the minimum surfaces it)")
    else:
        print(f"    insufficient consecutive 2-day windows (n={len(min_pairs)})")

    print(f"\n  NOTE: a day rating is multi-causal, so this whole section measures")
    print(f"  against a physiology outcome (energy+focus, mood dropped) — mood tracks")
    print(f"  general well-being, a different thing from the body's sleep response.")
    print(f"  No day is excluded for what happened in it; every day counts.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    records = load_records()
    if len(records) < 5:
        print("Not enough rated records for analysis (need at least 5).")
        return
    print_report(records)

    # Also write a JSON summary for programmatic use.
    results, ranked, good, bad, mid, ratings = analyze(records)
    summary = {
        "n_total": len(records),
        "n_good": len(good),
        "n_bad": len(bad),
        "avg_rating": mean(ratings),
        "top_predictors": [
            {
                "variable": v["label"],
                "r": round(v["r"], 3),
                "good_mean": round(v["good_mean"], 1) if v["good_mean"] is not None else None,
                "bad_mean":  round(v["bad_mean"], 1) if v["bad_mean"] is not None else None,
                "effect_size": interpret_d(v["d"]),
            }
            for k, v in ranked[:5] if v["r"] is not None
        ],
    }
    (REPO_ROOT / "data/day_trend_analysis.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
