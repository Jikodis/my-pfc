"""Canonical QQRT sleep-composite logic — the single source of truth.

QQRT = **Q**uantity + **Q**uality + **R**egularity + **T**iming. It exists because
total sleep hours alone is a weak predictor: a linear correlation is structurally
blind to a *threshold* effect, where a night either clears a bar or it doesn't.

    SCORE = Quantity + Quality + Timing   (0–3)

**Regularity is computed and stored but NOT scored.** Regularity only becomes
measurable once you have a stretch of consistent nights to compare against; until
then it is noise in a score. Track it, watch it improve, and add it to the score
yourself (edit `score` below) once your own data shows it separating good days
from bad ones.

**Sleep debt is a companion number, not a score lever.** It is reported alongside
the score rather than folded into it — low debt tends to beat high debt at the
same score, and folding it in would require a hand-picked threshold.

Both `analyze_day_trends.py` (on the fly) and `backfill_qqrt.py` (persists a
`qqrt` object onto every day-tracking record) import from here, so the bars are
defined exactly once and cannot drift.

TUNE THESE. Every number below is a **generic starting default**, not a
prescription — general adult sleep guidance, not your physiology. Run
`/pfc-analyze-trends` once you have ~6 weeks of rated days: its gate/gradient
pass prints each factor's mean per rating bucket, which is exactly the evidence
you need to move a bar. Override without editing this file by adding a
`health.sleep` block to `config/automation_config.yaml` (see that file).

Clock convention: all clock values are "signed minutes from midnight" —
11:00 PM = -60, 12:30 AM = +30, 7:00 AM = +420.
"""
import statistics
from datetime import datetime, timedelta
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "automation_config.yaml"

_DEFAULTS = {
    # ── Scored levers ─────────────────────────────────────────────────────────
    # Quantity: general adult guidance is 7–9 hours.
    "quantity_min_hours": 7.0,
    # Quality: sleep efficiency (asleep ÷ time in bed) plus a deep-sleep floor.
    # 90% efficiency is the usual "good sleep" line; deep sleep normally runs
    # 13–23% of total. Raise the efficiency bar if almost every night clears it.
    "quality_min_efficiency_pct": 90.0,
    "quality_min_deep_pct": 15.0,
    # Timing: asleep by this clock time. Default midnight — deliberately loose.
    # Signed minutes from midnight: -60 = 11:00 PM, 0 = midnight, +30 = 12:30 AM.
    "timing_asleep_by_min": 0,
    # ── Regularity (computed, not scored) ─────────────────────────────────────
    # Spread of your sleep MIDPOINT (halfway between onset and waking) across a
    # trailing window. A tight midpoint is the single best marker of a stable
    # circadian rhythm — better than bedtime alone, which ignores wake time.
    "regularity_window_nights": 14,
    "regularity_min_nights": 7,
    "regularity_max_spread_min": 60.0,
    # ── Sleep debt (companion) ────────────────────────────────────────────────
    # `need_hours` is an OPERATIONAL TARGET, not a biological-need claim — you
    # cannot pin true need from chronically-restricted data. 8.0 is the middle of
    # the general 7–9 band. If your own best-rated days cluster lower, set it to
    # the top of that cluster: a target you never reach reads "always maxed" and
    # stops being actionable.
    #
    # The formula is deliberately one-sided (surplus sleep earns no credit),
    # uniformly weighted, and exits only by window roll-off. Simple beats clever
    # here — decay curves and surplus credit move the number very little while
    # making it much harder to reason about.
    "need_hours": 8.0,
    "debt_window_nights": 14,
    "debt_min_nights": 5,
}


def _load_config():
    """Merge `health.sleep` from config/automation_config.yaml over the defaults.

    Silent fallback to defaults when PyYAML is missing, the file is absent, or
    the block isn't there — the module must never fail to import over config."""
    cfg = dict(_DEFAULTS)
    try:
        import yaml  # noqa: PLC0415 — optional dependency
        raw = yaml.safe_load(CONFIG_PATH.read_text()) or {}
        for k, v in ((raw.get("health") or {}).get("sleep") or {}).items():
            if k in cfg and v is not None:
                cfg[k] = v
    except Exception:  # noqa: BLE001 — config is optional by design
        pass
    return cfg


CONFIG = _load_config()

QUANTITY_MIN_HOURS = float(CONFIG["quantity_min_hours"])
QUALITY_MIN_EFFICIENCY = float(CONFIG["quality_min_efficiency_pct"])
QUALITY_MIN_DEEP_PCT = float(CONFIG["quality_min_deep_pct"])
TIMING_ASLEEP_BY_MIN = float(CONFIG["timing_asleep_by_min"])

WINDOW_NIGHTS = int(CONFIG["regularity_window_nights"])
REG_MIN_NIGHTS = int(CONFIG["regularity_min_nights"])
REG_SD_MAX_MIN = float(CONFIG["regularity_max_spread_min"])

NEED_HOURS = float(CONFIG["need_hours"])
DEBT_WINDOW_NIGHTS = int(CONFIG["debt_window_nights"])
DEBT_MIN_NIGHTS = int(CONFIG["debt_min_nights"])


def efficiency(sleep_hours, awake_min):
    """Sleep efficiency percent: time asleep / (asleep + awake). None if missing."""
    if sleep_hours is None or awake_min is None:
        return None
    sm = sleep_hours * 60.0
    return 100.0 * sm / (sm + awake_min) if (sm + awake_min) else None


def deep_pct(sleep_hours, deep_min):
    """Deep sleep as a percent of total sleep. None if inputs missing."""
    if not sleep_hours or deep_min is None:
        return None
    return 100.0 * deep_min / (sleep_hours * 60.0)


def _offset_minutes(iso, record_date):
    """Minutes from midnight of record_date for an ISO timestamp (signed)."""
    if not iso or not record_date:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        midnight = datetime.fromisoformat(record_date + "T00:00:00")
        if dt.tzinfo:
            midnight = midnight.replace(tzinfo=dt.tzinfo)
        return (dt - midnight).total_seconds() / 60
    except Exception:  # noqa: BLE001 — malformed timestamp is a data gap, not a crash
        return None


def bedtime_offset_minutes(bedtime_iso, record_date):
    """Sleep-onset clock as signed minutes from midnight (before midnight = negative)."""
    return _offset_minutes(bedtime_iso, record_date)


def wake_offset_minutes(wake_iso, record_date):
    """Wake clock as signed minutes from midnight."""
    return _offset_minutes(wake_iso, record_date)


def sleep_midpoint(bedtime_min, wake_min):
    """Clock time (signed minutes from midnight) halfway between sleep onset and
    waking. e.g. asleep 11:00 PM (-60), awake 7:00 AM (+420) -> +180 = 3:00 AM."""
    if bedtime_min is None or wake_min is None:
        return None
    return (bedtime_min + wake_min) / 2.0


def regularity_window(mid_by_date, d, window=WINDOW_NIGHTS):
    """Sleep-midpoint values present in the `window` nights ending on d (inclusive)."""
    out = []
    for i in range(window):
        m = mid_by_date.get(d - timedelta(days=i))
        if m is not None:
            out.append(m)
    return out


def sleep_debt(hours_by_date, d, need=NEED_HOURS, window=DEBT_WINDOW_NIGHTS):
    """Rolling sleep debt over the `window` nights ending on d (inclusive).

    Returns {need_hours, nights, avg_shortfall_min, cumulative_hours} or None if
    fewer than DEBT_MIN_NIGHTS of data. Shortfall per night = max(0, need - hours);
    `avg_shortfall_min` is the headline number ("averaging X min short of target")."""
    present = [hours_by_date.get(d - timedelta(days=i)) for i in range(window)]
    present = [h for h in present if h is not None]
    if len(present) < DEBT_MIN_NIGHTS:
        return None
    deficits = [max(0.0, need - h) for h in present]
    return {
        "need_hours": need,
        "nights": len(present),
        "avg_shortfall_min": int(round(statistics.mean(deficits) * 60)),
        "cumulative_hours": round(sum(deficits), 1),
    }


def levers(sleep_hours, awake_min, deep_min, bedtime_min, midpoint_window):
    """Evaluate the QQRT levers for one night.

    Returns a dict:
      quantity / quality / timing : bool  — scored levers
      regularity : bool                   — computed, NOT in score
      regularity_stdev_min : int | None   — midpoint spread (minutes)
      regularity_eligible : bool          — enough nights to judge regularity
      score : int 0-3                     — quantity + quality + timing
    """
    eff = efficiency(sleep_hours, awake_min)
    dp = deep_pct(sleep_hours, deep_min)
    q_quant = sleep_hours is not None and sleep_hours >= QUANTITY_MIN_HOURS
    q_qual = (
        eff is not None
        and eff >= QUALITY_MIN_EFFICIENCY
        and (dp is None or dp >= QUALITY_MIN_DEEP_PCT)
    )
    t_time = bedtime_min is not None and bedtime_min <= TIMING_ASLEEP_BY_MIN

    reg_n = len(midpoint_window)
    reg_eligible = reg_n >= REG_MIN_NIGHTS
    reg_sd = statistics.pstdev(midpoint_window) if reg_n >= 2 else None
    r_reg = reg_eligible and reg_sd is not None and reg_sd <= REG_SD_MAX_MIN

    return {
        "quantity": q_quant,
        "quality": q_qual,
        "timing": t_time,
        "regularity": r_reg,
        "regularity_stdev_min": int(round(reg_sd)) if reg_sd is not None else None,
        "regularity_eligible": reg_eligible,
        "score": int(q_quant) + int(q_qual) + int(t_time),
    }
