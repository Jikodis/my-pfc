# `data/health-raw/` — comprehensive raw health archive

One gzipped JSON file per local day: `YYYY-MM-DD.json.gz`.

This is the **insurance layer**. `data/day-tracking.ndjson` stores the handful of
derived day-level metrics the system actually analyses today (sleep hours, stage
minutes, resting heart rate, Active Zone Minutes, workouts, recovery metrics).
This folder stores **everything else** — the full, unflattened API responses — so a
question you haven't thought of yet is never blocked by what you chose to compute
today.

It exists because **intraday data cannot be backfilled indefinitely**. Providers
keep per-minute streams and sleep stages for a limited window (sleep stages age
out after roughly a year). Whatever isn't captured while it's live is gone. Daily
summaries you can re-fetch later; the fine-grained streams you cannot.

## What's in a file

```
{
  "date": "YYYY-MM-DD",
  "fetched_at_utc": "…Z",       # used to decide whether the day is final
  "tz": "America/Denver",        # the local day boundary used
  "schema_note": "…",
  "counts": { "<type>": <n>, … },  # points captured per data type
  "errors": { "<type>": "…", … },  # per-type failures, if any
  "types":  { "<type>": [ …raw dataPoints… ], … }
}
```

Captured types: sleep (with stages), daily summaries (heart-rate variability,
heart-rate zones, blood oxygen, breathing rate, resting heart rate, sleep
temperature, VO2 max), sample streams (heart rate, intraday variability and blood
oxygen, breathing rate, weight, body fat), and interval streams (steps, distance,
active energy, Active Zone Minutes, exercise).

## Two design decisions worth knowing

**Heart rate is downsampled to 1-minute means** (key `heart-rate-1min`, each entry
`{t, bpm, n}` where `n` is how many raw samples fed the mean). The raw stream
arrives at roughly 2-second resolution — about 34,000 points and 11 MB per day,
some 4 GB a year, which would hit GitHub's repo-size limit long before it answered
a question. One minute is the standard intraday granularity. **Every other stream
is kept at full resolution.**

**A file is rewritten until the day closes, then never again.** A capture taken
mid-day is a partial snapshot; anything logged later that day (an afternoon
workout, Active Zone Minutes accrued through the evening) is missing from it. Any
later run re-fetches the day until one capture lands after local midnight, at
which point the file is final. Without that rule the file's mere existence would
make every later pass skip it, permanently freezing a half-day snapshot.

## Commands

```bash
# Yesterday (also runs automatically inside auto_fetch_health.py)
python3 automations/scripts/google_health_raw.py

# A specific day, or a range
python3 automations/scripts/google_health_raw.py 2026-05-08
python3 automations/scripts/google_health_raw.py --range 2026-05-01 2026-05-31

# Force a re-capture of a day already marked final
python3 automations/scripts/google_health_raw.py 2026-05-08 --force
```

Reading one back:

```bash
python3 -c "
import gzip, json
d = json.load(gzip.open('data/health-raw/2026-05-08.json.gz', 'rt'))
print(d['counts'])
print(d['types']['heart-rate-1min'][:3])
"
```

## Notes

- Files are committed. Roughly a few hundred KB per day gzipped, dominated by the
  per-minute heart-rate series.
- Days before you set this up will simply be absent — that's a gap, not an error.
  Daily summaries for those days are still available via
  `google_health_backfill.py`.
- Nothing in the system *requires* this folder. Delete it and every skill still
  works; you only lose the ability to ask within-day questions later.
