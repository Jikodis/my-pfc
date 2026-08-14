#!/usr/bin/env python3
"""Backfill / refresh the `qqrt` composite on every day-tracking record.

Computes the QQRT sleep score from each day's stored health data using the shared
lever logic in `qqrt.py`, and writes it as a `qqrt` object on the record:

    "qqrt": {"quantity": bool, "quality": bool, "regularity": bool,
             "timing": bool, "regularity_stdev_min": int|null,
             "regularity_eligible": bool, "score": 0-3,
             "sleep_debt": {"need_hours": float, "nights": int,
                            "avg_shortfall_min": int, "cumulative_hours": float}|null}

`null` when the day has no sleep data at all (QQRT unknowable). Idempotent and safe
to re-run any time health data changes — regularity and debt look only at *prior*
nights, so a newly fetched night never alters an earlier night's score.

Persisting the composite (rather than recomputing on read) matters for one specific
question: "this day looked good on paper but wasn't." The stored `sleep_debt` for
that exact date is the built-in answer — no hand-rolled trailing window needed.

Usage: python3 automations/scripts/backfill_qqrt.py
"""
import json
import sys
from datetime import date as date_cls
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qqrt  # noqa: E402

DT = Path(__file__).resolve().parents[2] / "data" / "day-tracking.ndjson"


def _health(r):
    """Pull the QQRT inputs from a record's health block (flat or legacy nested)."""
    h = r.get("health") or {}
    sleep = h.get("sleep") if isinstance(h.get("sleep"), dict) else {}
    stages = sleep.get("stages_minutes") or h.get("sleep_stages") or {}
    return {
        "sleep_hours": h.get("sleep_hours") if h.get("sleep_hours") is not None else sleep.get("total_hours"),
        "awake_min":   h.get("awake_minutes") if h.get("awake_minutes") is not None else stages.get("wake"),
        "deep_min":    h.get("sleep_deep_minutes") if h.get("sleep_deep_minutes") is not None else stages.get("deep"),
        "bedtime":     h.get("sleep_bedtime") or h.get("bedtime") or (sleep.get("bedtime") if isinstance(sleep, dict) else None),
        "wake":        h.get("sleep_wake_time") or h.get("wake_time") or (sleep.get("wake_time") if isinstance(sleep, dict) else None),
    }


def recompute():
    """Recompute `qqrt` on every day-tracking record in place. Returns
    {"records": N, "changed": M}. Safe to call after any health write."""
    records = []
    if DT.exists():
        with open(DT) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    if not records:
        return {"records": 0, "changed": 0}

    # Resolve each day's inputs once; build the midpoint- and hours-by-date maps
    # (for regularity and sleep debt respectively).
    mid_by_date = {}
    hours_by_date = {}
    resolved = {}
    for r in records:
        h = _health(r)
        bt = qqrt.bedtime_offset_minutes(h["bedtime"], r["date"])
        wk = qqrt.wake_offset_minutes(h["wake"], r["date"])
        resolved[r["date"]] = (h, bt)
        try:
            d = date_cls.fromisoformat(r["date"])
            mid_by_date[d] = qqrt.sleep_midpoint(bt, wk)
            hours_by_date[d] = h["sleep_hours"]
        except Exception:  # noqa: BLE001 — a malformed date is a data gap, skip it
            pass

    changed = 0
    for r in records:
        h, bt = resolved[r["date"]]
        if h["sleep_hours"] is None and bt is None:
            new = None  # no sleep data → QQRT unknowable
        else:
            d = date_cls.fromisoformat(r["date"])
            win = qqrt.regularity_window(mid_by_date, d)
            new = qqrt.levers(h["sleep_hours"], h["awake_min"], h["deep_min"], bt, win)
            new["sleep_debt"] = qqrt.sleep_debt(hours_by_date, d)
        if r.get("qqrt") != new:
            r["qqrt"] = new
            changed += 1

    tmp = DT.with_suffix(".ndjson.tmp")
    with open(tmp, "w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(DT)
    return {"records": len(records), "changed": changed}


def main():
    print(json.dumps(recompute()))


if __name__ == "__main__":
    main()
