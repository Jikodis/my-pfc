---
name: pfc-monthly-checkin
description: Run the monthly check-in workflow. Use when the user says "monthly checkin", "monthly check-in", "monthly review", or "month in review".
---

# Monthly Check-in

Reviews the most recently completed calendar month. Run on the first Sunday of the new month (or any time during the new month).

---

## Step 0 — Determine the reviewed month and window

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
# REVIEWED_MONTH = previous calendar month (YYYY-MM)
REVIEWED_MONTH=$(TZ="${LOCAL_TZ:-America/Denver}" date -d "$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-15') -1 month" '+%Y-%m')
# Window covers the full reviewed month
export WINDOW_FROM="${REVIEWED_MONTH}-01"
export WINDOW_TO=$(TZ="${LOCAL_TZ:-America/Denver}" date -d "${WINDOW_FROM} +1 month -1 day" '+%Y-%m-%d')
echo "Reviewing $REVIEWED_MONTH (window: $WINDOW_FROM to $WINDOW_TO)"
```

If today is `2026-05-08`, this sets `REVIEWED_MONTH=2026-04`, `WINDOW_FROM=2026-04-01`, `WINDOW_TO=2026-04-30`.

---

## Step 1 — Load prior-month context

```bash
PRIOR_MONTH=$(date -d "${REVIEWED_MONTH}-15 -1 month" '+%Y-%m')
PRIOR_NOTE="notes/monthly/${PRIOR_MONTH}.md"
[ -f "$PRIOR_NOTE" ] && echo "Prior month note: $PRIOR_NOTE"
```

If the prior monthly note exists, read it for trend comparison context. If it doesn't, note that this is the first monthly checkin.

---

## Step 2 — Load weekly notes for the reviewed month

```bash
ls notes/weekly/*.md 2>/dev/null
```

For each file `notes/weekly/YYYY-WNN.md`, determine whether the week overlaps `[WINDOW_FROM, WINDOW_TO]` (any day of the week falls within the reviewed month). Read those notes — they're the primary source material.

---

## Step 3 — Run weekly-checkin steps with the monthly window

`WINDOW_FROM` and `WINDOW_TO` are already exported. Read `.claude/skills/pfc-weekly-checkin/SKILL.md` and execute its steps 1–9 with the current values. The queries will scope to the reviewed month; the life-wheel update, insights triage, hypotheses touch, findings alignment, and values alignment all run over the full month.

Skip step 10 (weekly summary generation) and step 11 (commit) — this monthly checkin will produce its own summary and commit.

---

## Step 4 — Project progress review (monthly extra)

For each active project in `4-projects/_data/projects.ndjson`:

```bash
jq -c 'select(.active == true)' 4-projects/_data/projects.ndjson
```

For each project:
- Read the project markdown file at the top of `4-projects/`.
- Show: completion %, current blockers, velocity (parts/day) with estimated completion vs. deadline.
- Ask:
  - Is the excitement level still accurate? (1–5)
  - Any blocker that warrants pausing or swapping the project?
  - Should `total_parts` change based on what we've learned?

Update project records via `jq` if the user requests changes.

---

## Step 5 — Monthly habit review (monthly extra)

```bash
jq -c --arg from "$WINDOW_FROM" --arg to "$WINDOW_TO" 'select(.date >= $from and .date <= $to)' 6-habits/_data/habits-monthly.ndjson
```

For each monthly habit in `config/habit_schema.yaml` (entries under the `monthly:` key):
- Show: completion count vs. target frequency for the reviewed month.
- Ask: keep, adjust target frequency, or retire?

If the user adjusts a target frequency, update `config/habit_schema.yaml`.

---

## Step 6 — Trend analysis (monthly extra)

Invoke `/pfc-analyze-trends` and surface its report. The trend analysis reads `data/day-tracking.ndjson` and finds correlates of high vs. low days. Note any new or reinforced patterns from this month.

---

## Step 7 — Synthesize and ask reflection questions

Using the prior-month note + this month's weekly notes + the data above, synthesize:
- What stood out about this month vs. last month?
- What patterns are worth carrying forward?
- What's drifting?

Ask the user:
- What went well this month?
- What didn't go well?
- Any priorities to adjust for next month?
- Any project, habit, or area to add/pause/retire?

---

## Step 8 — Generate monthly summary

Write a markdown file at `notes/monthly/${REVIEWED_MONTH}.md` with sections:
- Overview (one paragraph)
- Numbers (tasks completed, day-rating average, habit rates)
- Project progress
- Patterns observed (trend analysis highlights)
- Reflection (user's answers to step 7)
- Carry-forward (anything to act on next month)

---

## Step 9 — Sync Trello dashboard (fail-safe)

If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, refresh the dashboard so the board reflects post-archive, post-life-wheel, post-project-update state. Mirrors the evening-checkin pattern.

```bash
python3 automations/scripts/trello_render.py 2>&1
```

On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step entirely.

---

## Step 10 — Commit

```bash
git add notes/monthly/ data/ 2-areas/_data/ 5-actions/_data/ 4-projects/_data/ 6-habits/_data/ config/
git commit -m "report: generate monthly check-in ${REVIEWED_MONTH}"
git push
```
