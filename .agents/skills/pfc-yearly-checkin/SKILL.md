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

## Step 2 — Load monthly notes for the reviewed year

```bash
ls notes/monthly/${REVIEWED_YEAR}-*.md 2>/dev/null
```

Read all available monthly notes for the reviewed year — these are the primary source material.

---

## Step 3 — Run monthly-checkin steps with the yearly window

`WINDOW_FROM` and `WINDOW_TO` are already exported. Read `.claude/skills/pfc-monthly-checkin/SKILL.md` and execute its steps 3–6 (the weekly-embedded steps + project progress review + monthly habit review + trend analysis) with the yearly window.

Skip the monthly skill's step 0 (window detection — already done), step 1–2 (monthly note context — different here), step 7 (monthly reflection questions — replaced by yearly's), step 8 (monthly summary file), and step 9 (monthly commit). The yearly checkin produces its own summary and commit.

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

## Step 7 — Passion brainstorm refresh (yearly extra)

Read `3-visions/passion-brainstorm.md`. Spend 5 minutes brainstorming:
- New items to add.
- Items completed this year — move to Done.
- Items no longer interesting — remove.

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
git add notes/yearly/ data/ 2-areas/ 5-actions/_data/ 4-projects/_data/ 6-habits/_data/ config/ 1-values/ 3-visions/
git commit -m "report: generate yearly check-in ${REVIEWED_YEAR}"
git push
```
