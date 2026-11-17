#!/usr/bin/env python3
"""Reduce Google Health `exercise` dataPoints to the day-level workout fields
stored in `day-tracking.ndjson` → `health`.

Defined once here and shared by `google_health_fetch.py` and
`google_health_backfill.py` so the two paths cannot drift (same pattern as
`sleep_reduce.py`).

Why workouts are tracked separately from Active Zone Minutes
------------------------------------------------------------
`active_zone_minutes` is a single daily number that mixes a hard workout with a
stressful afternoon at an elevated heart rate — it cannot tell them apart, which
makes it a weak trend variable. A tracked session carries what AZM cannot:
exercise type, start time, duration, average heart rate, and time in each heart-
rate zone. Those are the variables worth testing against energy and day rating.

IMPORTANT — what `azm_outside_workouts` is NOT
----------------------------------------------
It is total AZM minus the AZM earned inside tracked sessions. That remainder is a
mix of **untracked workouts**, walking, yard work, chores, and a genuinely
elevated resting heart rate. It is NOT a stress or anxiety measure and must never
be reported as one. If you exercise without starting a session on the watch, that
whole workout lands in this bucket. Only the tracked-session fields describe
deliberate exercise.
"""

from datetime import datetime, timedelta

__all__ = ["reduce_exercise", "exercise_fields", "EMPTY_EXERCISE", "UNKNOWN_EXERCISE"]

EMPTY_EXERCISE = {
    "workouts": [],
    "workout_count": 0,
    "workout_minutes": 0,
    "workout_azm": 0,
    "workout_vigorous_minutes": 0,
    # Stamped by row_duration.apply_to_health after the raw archive lands, not here —
    # deriving it needs the per-minute heart-rate stream, which this reducer never sees.
    "workout_real_minutes": 0,
    "first_workout_time": None,
}

# Used when the exercise endpoint failed — every field null, so a fetch error is
# never mistaken for a genuine zero-workout day.
UNKNOWN_EXERCISE = {k: None for k in EMPTY_EXERCISE}


def _secs(value):
    """Google Health durations are strings like '1613s'. Returns int seconds."""
    if value is None:
        return 0
    try:
        return int(str(value).rstrip("s") or 0)
    except (TypeError, ValueError):
        return 0


def _num(value):
    if value is None:
        return None
    try:
        return round(float(value))
    except (TypeError, ValueError):
        return None


def _fmt_offset(seconds):
    sign = "-" if seconds < 0 else "+"
    seconds = abs(seconds)
    return f"{sign}{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"


def _local_iso(interval):
    """Session start as a local-time ISO 8601 string, using the offset the device
    recorded (`startUtcOffset`), so a 6:30 AM workout reads 06:30 regardless of the
    server's timezone."""
    start = interval.get("startTime")
    if not start:
        return None
    try:
        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    except ValueError:
        return None
    offset = _secs(interval.get("startUtcOffset"))
    return (dt + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%S") + _fmt_offset(offset)


def reduce_exercise(points, local_tz=None):  # noqa: ARG001 — tz kept for signature parity
    """dataPoints from the `exercise` data type → day-level workout fields.

    Returns EMPTY_EXERCISE's shape when the day has no tracked sessions, so a
    zero-workout day is recorded as a real zero rather than a null (a null would be
    indistinguishable from "the fetch failed").
    """
    sessions = []
    for point in points or []:
        ex = point.get("exercise") or {}
        interval = ex.get("interval") or {}
        metrics = ex.get("metricsSummary") or {}
        zones = metrics.get("heartRateZoneDurations") or {}
        sessions.append({
            "type": ex.get("exerciseType"),
            "name": ex.get("displayName"),
            "start": _local_iso(interval),
            "minutes": round(_secs(ex.get("activeDuration")) / 60),
            "azm": int(metrics.get("activeZoneMinutes") or 0),
            "avg_hr_bpm": _num(metrics.get("averageHeartRateBeatsPerMinute")),
            "vigorous_minutes": round(
                (_secs(zones.get("vigorousTime")) + _secs(zones.get("peakTime"))) / 60
            ),
            "calories": _num(metrics.get("caloriesKcal")),
        })

    if not sessions:
        return dict(EMPTY_EXERCISE)

    sessions.sort(key=lambda s: s["start"] or "")
    return {
        "workouts": sessions,
        "workout_count": len(sessions),
        "workout_minutes": sum(s["minutes"] for s in sessions),
        "workout_azm": sum(s["azm"] for s in sessions),
        "workout_vigorous_minutes": sum(s["vigorous_minutes"] for s in sessions),
        "first_workout_time": sessions[0]["start"],
    }


def exercise_fields(points, total_azm):
    """Workout fields plus `azm_outside_workouts`, ready to merge into a `health` block.

    `points` is None when the exercise endpoint failed (everything null), and [] when
    the day genuinely had no tracked session (zeros). `total_azm` is the day's whole-day
    Active Zone Minutes, which already includes session AZM.
    """
    if points is None:
        return dict(UNKNOWN_EXERCISE, azm_outside_workouts=None)
    fields = reduce_exercise(points)
    fields["azm_outside_workouts"] = (
        max(0, total_azm - fields["workout_azm"]) if total_azm is not None else None
    )
    return fields
