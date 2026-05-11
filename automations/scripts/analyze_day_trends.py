#!/usr/bin/env python3
"""
Statistical analysis of day-tracking data.
Finds the strongest predictors of good vs bad days.

Usage:
    python3 automations/scripts/analyze_day_trends.py
"""

import json
import math
from pathlib import Path
from collections import defaultdict

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

# ── Data loading ──────────────────────────────────────────────────────────────

def load_supplements():
    """Return a list of supplement records from supplements.ndjson (may be empty)."""
    if not SUPPLEMENTS.exists():
        return []
    out = []
    for line in SUPPLEMENTS.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out

def active_on(records, date, name):
    """
    Return the record for `name` that was active on ISO `date`, or None.
    Active on D ⇔ started <= D AND (stopped is null OR stopped > D).
    If multiple records match (shouldn't happen for well-formed data), return the
    one with the latest `started`.
    """
    hits = [
        r for r in records
        if r.get("name") == name
        and r.get("started", "9999-12-31") <= date
        and (r.get("stopped") is None or r.get("stopped") > date)
    ]
    if not hits:
        return None
    return max(hits, key=lambda r: r.get("started", "9999-12-31"))

def _parse_cdp_legacy(val):
    """Extract mg from strings like '250mg', '150mg', or return 0 if None."""
    if not val:
        return 0
    try:
        return float("".join(c for c in str(val) if c.isdigit() or c == "."))
    except:
        return None

def extract_health(h):
    """Pull normalized health fields from either the flat or nested schema."""
    sleep = h.get("sleep") if isinstance(h.get("sleep"), dict) else {}
    stages = sleep.get("stages_minutes") or {}
    rhr = h.get("resting_heart_rate") if isinstance(h.get("resting_heart_rate"), dict) else {}
    azm_raw = h.get("active_zone_minutes")
    azm = azm_raw.get("total_minutes") if isinstance(azm_raw, dict) else azm_raw
    return {
        "sleep_hours": h.get("sleep_hours") if h.get("sleep_hours") is not None else sleep.get("total_hours"),
        "sleep_deep":  h.get("sleep_deep_minutes")  if h.get("sleep_deep_minutes")  is not None else stages.get("deep"),
        "sleep_rem":   h.get("sleep_rem_minutes")   if h.get("sleep_rem_minutes")   is not None else stages.get("rem"),
        "sleep_light": h.get("sleep_light_minutes") if h.get("sleep_light_minutes") is not None else stages.get("light"),
        "awake_min":   h.get("awake_minutes") if h.get("awake_minutes") is not None else sleep.get("awake_minutes"),
        "resting_hr":  h.get("resting_hr_bpm") if h.get("resting_hr_bpm") is not None else rhr.get("bpm"),
        "azm":         azm,
    }

def load_records():
    supplements = load_supplements()
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
        # Supplement-specific lookup removed for template.
        # To re-enable: pick a supplement name from data/supplements.ndjson, e.g.
        #   cdp = active_on(supplements, r['date'], '<your supplement>')
        #   cdp_dose = (cdp or {}).get('dose')
        records.append({
            "date":         r["date"],
            "rating":       r["rating"],
            # Sleep
            "sleep_hours":  hx["sleep_hours"],
            "sleep_deep":   hx["sleep_deep"],
            "sleep_rem":    hx["sleep_rem"],
            "sleep_light":  hx["sleep_light"],
            "awake_min":    hx["awake_min"],
            "resting_hr":   hx["resting_hr"],
            "azm":          hx["azm"],
            # Supplements (raw + parsed) — derived from supplements registry.
            # Add per-supplement columns here once you register supplements.
            "hyperfocused": (1 if r.get("hyperfocused") else 0) if r.get("hyperfocused") is not None else None,
            "sick":         1 if r.get("sick") else 0,
            # Subjective (if present)
            "energy":       r.get("energy"),
            "focus":        r.get("focus"),
            "mood":         r.get("mood"),
        })
    return records

# ── Analysis ──────────────────────────────────────────────────────────────────

VARIABLES = {
    "sleep_hours":  "Sleep hours",
    "sleep_deep":   "Deep sleep (min)",
    "sleep_rem":    "REM sleep (min)",
    "sleep_light":  "Light sleep (min)",
    "awake_min":    "Awake during sleep (min)",
    "resting_hr":   "Resting heart rate (bpm)",
    "azm":          "Active zone minutes",
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
        vals = [r[key] for r in records]
        r_val, n = pearson(vals, ratings)
        d_val = cohens_d(
            [r[key] for r in good],
            [r[key] for r in bad]
        )
        good_mean = mean([r[key] for r in good])
        bad_mean  = mean([r[key] for r in bad])
        all_mean  = mean(vals)
        results[key] = {
            "label":      label,
            "r":          r_val,
            "n":          n,
            "d":          d_val,
            "good_mean":  good_mean,
            "bad_mean":   bad_mean,
            "all_mean":   all_mean,
            "all_median": median(vals),
        }

    # Sort by absolute correlation
    ranked = sorted(
        [(k, v) for k, v in results.items() if v["r"] is not None],
        key=lambda x: abs(x[1]["r"]),
        reverse=True
    )
    return results, ranked, good, bad, mid, ratings

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
        r = v["r"]
        strength = interpret_r(r)
        b = bar(r, 14)
        print(f"  {v['label']:<28} {r:>+.3f}  {b}  {strength:<18} {v['n']:>3}")

    # ── Good vs bad day profiles ──
    print(f"\n── GOOD DAYS (4-5) vs BAD DAYS (1-2) ───────────────────────")
    print(f"  {'Variable':<28} {'Good':>7}  {'Bad':>7}  {'Diff':>7}  Effect")
    print(f"  {'-'*68}")
    for key, label in VARIABLES.items():
        v = results[key]
        gm = v["good_mean"]
        bm = v["bad_mean"]
        if gm is None or bm is None:
            continue
        diff = gm - bm
        d_interp = interpret_d(v["d"])
        print(f"  {label:<28} {gm:>7.1f}  {bm:>7.1f}  {diff:>+7.1f}  {d_interp}")

    # ── Top predictors summary ──
    print(f"\n── TOP PREDICTORS ───────────────────────────────────────────")
    top = [(k, v) for k, v in ranked if v["r"] is not None and abs(v["r"]) >= 0.15][:5]
    for i, (key, v) in enumerate(top, 1):
        r   = v["r"]
        gm  = v["good_mean"]
        bm  = v["bad_mean"]
        direction = "more" if r > 0 else "less"
        if gm is not None and bm is not None:
            print(f"  {i}. {v['label']}")
            print(f"     r={r:+.3f} — good days avg {gm:.1f}, bad days avg {bm:.1f}")
            print(f"     → {interpret_d(v['d'])}")

    # ── Sleep breakdown ──
    print(f"\n── SLEEP BREAKDOWN ──────────────────────────────────────────")
    for key in ["sleep_hours", "sleep_deep", "sleep_rem", "awake_min"]:
        v = results[key]
        if v["all_mean"] is None:
            continue
        print(f"  {v['label']:<28}  overall avg: {v['all_mean']:.1f}  |  good: {v['good_mean'] or 'n/a':.1f}  |  bad: {v['bad_mean'] or 'n/a':.1f}")

    # Supplement trend analysis: add your tracked supplements here
    # (read from data/supplements.ndjson and group day ratings by dose).

    # Hyperfocus × supplement cross-tab removed for template.
    # Re-add per-supplement cross-tabs once you have records.

    # ── Legend ──
    print(f"\n── LEGEND ───────────────────────────────────────────────────")
    print(f"  n = number of days with data for this variable")
    print(f"      (higher n = more reliable; anything below ~7 is thin).")
    print(f"  r = Pearson correlation with day rating, range -1 to +1.")
    print(f"      +1 = perfectly moves together, 0 = no relationship,")
    print(f"      -1 = perfectly opposite. Bands used above:")
    print(f"        |r| ≥ 0.5  strong     |r| ≥ 0.3  moderate")
    print(f"        |r| ≥ 0.1  weak       |r| < 0.1  negligible")
    print(f"  Effect size (Cohen's d): size of gap between good and bad days.")
    print(f"      large ≥ 0.8 | medium ≥ 0.5 | small ≥ 0.2 | negligible < 0.2")
    print(f"  Correlation ≠ causation. Small n means 'watch this', not 'proven'.")

    print(f"\n{'='*62}\n")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    records = load_records()
    if len(records) < 5:
        print("Not enough rated records for analysis (need at least 5).")
        return
    print_report(records)

    # Also output JSON for programmatic use
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
                "good_mean": round(v["good_mean"], 1) if v["good_mean"] else None,
                "bad_mean":  round(v["bad_mean"],  1) if v["bad_mean"]  else None,
                "effect_size": interpret_d(v["d"]),
            }
            for k, v in ranked[:5] if v["r"] is not None
        ]
    }

    out = REPO_ROOT / "data/day_trend_analysis.json"
    out.write_text(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
