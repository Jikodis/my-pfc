---
name: pfc-yearly-checkin
description: Run the yearly check-in workflow. Use when the user says "yearly checkin", "yearly check-in", "annual checkin", "annual review", "yearly review", or "year in review".
---

# Yearly Check-in

Reviews the most recently completed calendar year. Run early in the new year (any time in January is normal).

---

## Step 0 — Determine the reviewed year and window

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
CURRENT_YEAR=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y')
# REVIEWED_YEAR = previous calendar year
REVIEWED_YEAR=$((CURRENT_YEAR - 1))
export WINDOW_FROM="${REVIEWED_YEAR}-01-01"
export WINDOW_TO="${REVIEWED_YEAR}-12-31"
echo "Reviewing $REVIEWED_YEAR (window: $WINDOW_FROM to $WINDOW_TO)"
```

If the user invokes this in late December and wants to wrap the current year early, ask whether to review `$CURRENT_YEAR` (incomplete) or `$REVIEWED_YEAR` (last completed). Default is `$REVIEWED_YEAR`.

---

## Step 1 — Load prior-year context

```bash
PRIOR_YEAR=$((REVIEWED_YEAR - 1))
PRIOR_NOTE="notes/yearly/${PRIOR_YEAR}.md"
[ -f "$PRIOR_NOTE" ] && echo "Prior year note: $PRIOR_NOTE"
```

Read for trend comparison if it exists.

---

## Step 2 — Load source material for the reviewed year

```bash
ls notes/daily/${REVIEWED_YEAR}-*.md 2>/dev/null | tail -20
ls notes/monthly/${REVIEWED_YEAR}-*.md 2>/dev/null   # archival only — the monthly ritual was retired
```

Read a sampling of daily notes plus any archival monthly notes that exist, and pull the reviewed year out of `data/day-tracking.ndjson` and `data/review-ledger.ndjson`. These are the primary source material for the synthesis in Step 9.

---

## Step 3 — Run the review passes with the yearly window

`WINDOW_FROM` and `WINDOW_TO` are already exported. The former weekly and monthly rituals are now the **rolling-review ledger** (`data/review-ledger.ndjson`). For the yearly check-in, run those same passes over the full-year window, unbounded by cadence — this is the year-scoped counterpart to `/pfc-review`. Stamp nothing: `last_done` tracks the daily drip, not this pass.

- **Life wheel** — rate each life area against the year (`2-areas/_data/life-wheel.ndjson`).
- **Household status** — rate each house area against the year (`2-areas/_data/household-status.ndjson`).
- **Project progress** — every project's full-year arc (`/pfc-summarize-project` per project).
- **Vision activation** — which directions got fed this year and which rested (`/pfc-focus`).
- **Habit rates** — daily + monthly completion across the year (`7-habits/_data/`).
- **Insights review** — the year's active insights (`/pfc-insights`).
- **Trend analysis** — full-year statistical pass (`/pfc-analyze-trends`).
- **Values / findings alignment** — cross-check active findings and project `values` links against the year.

The owning-skill map in `pfc-evening-checkin` Step 3c section 2 is the canonical list of review passes and the skill that owns each. Skip any cadence-stamping and the monthly-only reflection questions — the yearly reflection in Step 9 replaces them. This check-in produces its own summary and commit.

---

## Step 4 — Values review (yearly extra)

Read `1-values/values.md`. Walk through each value with the user:
- Still accurate?
- Reorder if priorities shifted?
- Add or retire any?

Update the file via Edit if changes are made.

---

## Step 5 — Area statements review (yearly extra)

For each folder in `2-areas/`, read `2-areas/{area}/statement.md`:
- Still resonate?
- Revise wording?
- Update the year tag.

---

## Step 6 — Questions review (yearly extra)

If a questions list exists (e.g., `0-me/questions.md`), revisit it:
- Remove answered ones.
- Add new ones surfaced this year.

---

## Step 7 — Vision brainstorm refresh (yearly extra)

Run `/pfc-vision-brainstorm` against `3-visions/_data/vision-brainstorm.ndjson`. Spend 5 minutes brainstorming:
- New ideas to add (status `raw`).
- Ideas that came true this year — mark `done`.
- Ideas no longer wanted — mark `dropped`.
- Ideas worth pursuing now — promote toward a vision / focus / project / task.

---

## Step 8 — Personality & psychology review (yearly extra)

Re-read `0-me/personality.md` and `0-me/core-psychology.md` (if these files exist — both are optional). Update anything that no longer reflects current self-understanding.

---

## Step 9 — Synthesize and ask reflection questions

Using the prior-year note + this year's monthly notes + the data above, synthesize:
- What stood out about the year?
- What patterns shifted vs. last year?
- What direction is emerging?

Ask the user:
- What went well this year?
- What didn't go well?
- Any vision-level direction shifts?
- Any project, area, or value updates surfaced?

---

## Step 10 — Generate yearly summary

Write a markdown file at `notes/yearly/${REVIEWED_YEAR}.md` with sections:
- Overview (one paragraph)
- Numbers (tasks completed, day-rating average, habit rates)
- Project progress (full year arc)
- Patterns observed (trend analysis highlights across the year)
- Values / area / vision shifts
- Reflection (user's answers to step 9)
- Direction for next year

---

## Step 11 — Sync Trello dashboard (fail-safe)

If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, refresh the dashboard so the board reflects post-archive, post-life-wheel, post-values/areas/visions state. Mirrors the evening-checkin pattern.

```bash
python3 automations/scripts/trello_render.py 2>&1
```

On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step entirely.

---

## Step 12 — Commit

```bash
git add notes/yearly/ data/ 2-areas/ 6-tasks/_data/ 5-projects/_data/ 7-habits/_data/ config/ 1-values/ 3-visions/
git commit -m "report: generate yearly check-in ${REVIEWED_YEAR}"
git push
```
