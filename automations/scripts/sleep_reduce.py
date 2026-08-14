"""Single source of truth for reducing Google Health sleep dataPoints into the
flat sleep schema stored on `day-tracking.ndjson` → `health`.

Both `google_health_fetch.py` (one day) and `google_health_backfill.py` (history)
import `reduce_sleep()`, so the parsing — and critically the awake-time
accounting — is defined exactly once and cannot drift between the two paths.

CRITICAL — the awake-gap bug this fixes
---------------------------------------
A wearable logs a fragmented night as MULTIPLE sleep sessions with a gap between
them (asleep 9:55 PM–3:31 AM, awake, asleep again 5:10 AM–7:17 AM). The awake
time *in that gap* appears in NO session's `minutesAwake`. Two things then go
wrong at once:

  1. Summing per-session `minutesAwake` undercounts awake time on every
     fragmented night.
  2. Taking min(start) / max(end) collapses the sessions into one span that
     reads as continuous.

Together they inflate sleep efficiency, which falsely awards the QQRT Quality
lever on exactly the broken nights it should fail. If you have data fetched
before this module existed, re-derive it with
`python3 automations/scripts/google_health_backfill.py --all`.

The fix: `awake_minutes` = (sum of per-session `minutesAwake`) + (sum of the
awake gaps *between* consecutive sessions) — equivalently, all awake time inside
the bedtime→wake span. Companion fields expose the split:

  awake_intrasession_minutes : awake time inside sessions (the old value)
  sleep_awake_gap_minutes    : awake time between sessions (was silently dropped)
  sleep_sessions             : how many separate sleep logs the device recorded
  sleep_continuity           : "fragmented" if the gap >= FRAGMENT_GAP_MINUTES
"""
from datetime import datetime

# Awakenings shorter than this are micro-arousals (normal sleep noise), not real wakings.
MIN_AWAKENING_MINUTES = 4
# A total inter-session awake gap this long (minutes) marks the night fragmented.
FRAGMENT_GAP_MINUTES = 20
# Two sleep sessions separated by a gap longer than this are SEPARATE sleep
# periods (an overnight sleep and a later daytime nap), NOT one fragmented night.
# Only the primary overnight period is kept, so a nap's out-of-bed hours are never
# counted as mid-night awake time. Real mid-night wakings run well under 3h;
# daytime nap gaps run 5h+.
SEPARATE_SLEEP_GAP_MINUTES = 180


def _parse_dt(raw):
    """Parse a Google Health timestamp (Zulu or civil) to a datetime, or None."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)
    except (ValueError, TypeError):
        return None


def to_local_iso(raw, tz):
    """Convert a Google Health interval timestamp to ISO 8601 in `tz` with offset.
    Accepts a Zulu UTC string or an already-civil local string. None on failure."""
    dt = _parse_dt(raw)
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz).isoformat()
    return dt.astimezone(tz).isoformat()


def extract_awakenings(target, tz, min_minutes=MIN_AWAKENING_MINUTES):
    """From the per-stage data, return real awakenings as
    [{"start": local_iso, "minutes": int}, ...] sorted by time. An awakening is an
    AWAKE stage lasting >= min_minutes.

    The FULL-night list is stored, not a windowed count, so analysis can re-window
    it later ("awakenings after 2 AM" — the early-waking pattern a nightly total
    can never surface) without re-fetching from the API."""
    out = []
    for point in target:
        for st in point.get("sleep", {}).get("stages", []):
            if st.get("type", "").upper() != "AWAKE":
                continue
            ds, de = _parse_dt(st.get("startTime")), _parse_dt(st.get("endTime"))
            if ds is None or de is None:
                continue
            mins = round((de - ds).total_seconds() / 60)
            if mins >= min_minutes:
                out.append({"start": to_local_iso(st.get("startTime"), tz), "minutes": mins})
    out.sort(key=lambda x: x["start"] or "")
    return out


def reduce_sleep(points, tz):
    """Reduce raw Google Health sleep dataPoints into the flat sleep schema.

    Returns None when there are no sleep dataPoints at all. When points exist,
    always returns the dict (callers decide how to treat a 0-minute result).
    `tz` is the local tzinfo used for bedtime / wake / awakening timestamps."""
    if not points:
        return None

    # Prefer the sessions the device flagged `main`; some nights flag none, so fall
    # back to every returned session (this is the fragmented-night case).
    main_pts = [p for p in points if p.get("sleep", {}).get("metadata", {}).get("main")]
    target = main_pts if main_pts else points

    # One record per session, sorted by start, so they can be clustered.
    sessions = []
    for point in target:
        summary = point.get("sleep", {}).get("summary", {})
        interval = point.get("sleep", {}).get("interval", {}) or {}
        start = interval.get("civilStartTime") or interval.get("startTime")
        end = interval.get("civilEndTime") or interval.get("endTime")
        sdt, edt = _parse_dt(start), _parse_dt(end)
        stages = {"deep": 0, "light": 0, "rem": 0, "wake": 0}
        _stage_key = {"DEEP": "deep", "LIGHT": "light", "REM": "rem", "AWAKE": "wake"}
        for s in summary.get("stagesSummary", []):
            key = _stage_key.get(s.get("type", "").upper())
            if key:
                stages[key] += int(s.get("minutes", 0) or 0)
        sessions.append({
            "point": point, "start": start, "end": end, "sdt": sdt, "edt": edt,
            "asleep": int(summary.get("minutesAsleep", 0) or 0),
            "awake": int(summary.get("minutesAwake", 0) or 0),
            "stages": stages,
        })
    sessions.sort(key=lambda s: s["sdt"] or datetime.max.replace(tzinfo=None))

    # Cluster consecutive sessions; a gap > SEPARATE_SLEEP_GAP starts a new cluster
    # (a nap, not part of this night). Keep the cluster with the most time asleep as
    # "the night" — naps and their out-of-bed hours are dropped.
    clusters, cur = [], []
    for s in sessions:
        if cur and s["sdt"] and cur[-1]["edt"]:
            if (s["sdt"] - cur[-1]["edt"]).total_seconds() / 60 > SEPARATE_SLEEP_GAP_MINUTES:
                clusters.append(cur)
                cur = []
        cur.append(s)
    if cur:
        clusters.append(cur)
    night = max(clusters, key=lambda c: sum(x["asleep"] for x in c)) if clusters else []

    total_asleep = sum(s["asleep"] for s in night)
    total_awake_intra = sum(s["awake"] for s in night)
    stages = {k: sum(s["stages"][k] for s in night) for k in ("deep", "light", "rem", "wake")}
    starts = [s["start"] for s in night if s["start"]]
    ends = [s["end"] for s in night if s["end"]]

    # Awake time BETWEEN consecutive sessions of the night — the part naive parsing
    # drops. (Gaps to dropped naps are excluded by construction.)
    inter_gap = 0.0
    for i in range(len(night) - 1):
        if night[i]["edt"] and night[i + 1]["sdt"]:
            gap = (night[i + 1]["sdt"] - night[i]["edt"]).total_seconds() / 60
            if gap > 0:
                inter_gap += gap
    inter_gap = int(round(inter_gap))
    awake_total = total_awake_intra + inter_gap

    awakenings = extract_awakenings([s["point"] for s in night], tz)
    return {
        "sleep_minutes":              total_asleep,
        "sleep_hours":                round(total_asleep / 60, 1),
        "awake_minutes":              awake_total,
        "awake_intrasession_minutes": total_awake_intra,
        "sleep_awake_gap_minutes":    inter_gap,
        "sleep_sessions":             len(night),
        "sleep_continuity":           "fragmented" if inter_gap >= FRAGMENT_GAP_MINUTES else "continuous",
        "sleep_deep_minutes":         stages["deep"],
        "sleep_rem_minutes":          stages["rem"],
        "sleep_light_minutes":        stages["light"],
        "sleep_bedtime":              to_local_iso(min(starts), tz) if starts else None,
        "sleep_wake_time":            to_local_iso(max(ends), tz) if ends else None,
        "awakenings":                 awakenings,
        "awakenings_count":           len(awakenings),
    }
