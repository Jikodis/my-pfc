---
name: pfc-system-health
description: Audit the productivity system for maintenance issues — the plumbing, not the content. Use when the user says "system health", "check the system", "is the system working", "audit the system", or "plumbing check". This is NOT /pfc-status (which is the life content view).
---

# System Health

Audit the productivity system for maintenance issues — not what's in it, but whether the plumbing is working. This is NOT /pfc-status (life content view). This is the meta-check.

Run all checks, then output a sorted table and a prioritized action list. No questions, no interaction.

---

## Step 1 — Run all checks

Execute these bash commands to gather data:

```bash
# Dates
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
CUTOFF_5YR=$(date -d '5 years ago' '+%Y-%m-%d' 2>/dev/null || echo "$TODAY")
CUTOFF_35D=$(date -d '35 days ago' '+%Y-%m-%d' 2>/dev/null || echo "$TODAY")
CUTOFF_8D=$(date -d '8 days ago' '+%Y-%m-%d' 2>/dev/null || echo "$TODAY")
CUTOFF_30D=$(date -d '30 days ago' '+%Y-%m-%d' 2>/dev/null || echo "$TODAY")
CUTOFF_7D=$(date -d '7 days ago' '+%Y-%m-%d' 2>/dev/null || echo "$TODAY")

echo "=== FOUNDATION ==="
echo "Values count: $(grep -c '^[0-9]' 1-values/values.md 2>/dev/null || echo 0)"

for d in 2-areas/*/; do
  area=$(basename "$d")
  [ -f "$d/statement.md" ] && echo "statement:OK:$area" || echo "statement:MISSING:$area"
done

for f in 2-areas/*/statement.md; do
  area=$(basename "$(dirname "$f")")
  last=$(git log -1 --format="%as" -- "$f" 2>/dev/null)
  [ -z "$last" ] && echo "freshness:UNCOMMITTED:$area" && continue
  [ "$last" \< "$CUTOFF_5YR" ] && echo "freshness:STALE:$area ($last)" || echo "freshness:OK:$area"
done

echo "=== PROJECTS ==="
jq -r 'select(.active==true) | "\(.id)|\(.name)|\(.completed_parts)|\(.total_parts)|\(.created)"' 4-projects/_data/projects.ndjson

echo "=== HABITS (DAILY) ==="
DAILY_IDS=$(awk '/^daily_habits:/{flag=1;next} /^[a-z_]+:/{flag=0} flag && /^  - id:/{print $3}' config/habit_schema.yaml | tr -d '"')
DAILY_COUNT=$(echo "$DAILY_IDS" | grep -c .)
echo "daily_defined:$DAILY_COUNT"
# Logging-gap signal: most recent log entry across ALL daily habits.
# Distinguishes "user stopped logging" from "user logged a miss" — these are different problems.
DAILY_LAST_LOG=$(jq -r '.date' 6-habits/_data/habits-daily.ndjson 2>/dev/null | sort -u | tail -1)
echo "daily_last_log:${DAILY_LAST_LOG:-never}"
for h in $DAILY_IDS; do
  [ -z "$h" ] && continue
  ENTRIES=$(jq -c --arg h "$h" --arg from "$CUTOFF_7D" --arg to "$TODAY" \
    'select((.habit==$h or .habit_id==$h) and .date>=$from and .date<=$to)' \
    6-habits/_data/habits-daily.ndjson 2>/dev/null | wc -l)
  COMPLETED=$(jq -c --arg h "$h" --arg from "$CUTOFF_7D" --arg to "$TODAY" \
    'select((.habit==$h or .habit_id==$h) and .completed==true and .date>=$from and .date<=$to)' \
    6-habits/_data/habits-daily.ndjson 2>/dev/null | wc -l)
  echo "habit_log:$h:entries=$ENTRIES:completed=$COMPLETED"
done
# Duplicate detection (same habit_id + same date, >1 entry)
DUPES=$(jq -r '[(.habit_id // .habit), .date] | @tsv' 6-habits/_data/habits-daily.ndjson 2>/dev/null | \
  sort | uniq -c | awk '$1 > 1 {print $2 " on " $3 " (x"$1")"}')
echo "daily_dupes:$(echo "$DUPES" | grep -c . 2>/dev/null || echo 0)"
[ -n "$DUPES" ] && echo "$DUPES"

echo "=== HABITS (MONTHLY) ==="
MONTHLY_IDS=$(awk '/^monthly_habits:/{flag=1;next} /^[a-z_]+:/{flag=0} flag && /^  - id:/{print $3}' config/habit_schema.yaml | tr -d '"')
MONTHLY_COUNT=$(echo "$MONTHLY_IDS" | grep -c .)
echo "monthly_defined:$MONTHLY_COUNT"
CURRENT_MONTH=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m')
# Logging-gap signal: most recent log entry across ALL monthly habits this month.
MONTHLY_LAST_LOG=$(jq -r --arg m "$CURRENT_MONTH" 'select(.month==$m or (.date[:7]==$m)) | .date // .month' \
  6-habits/_data/habits-monthly.ndjson 2>/dev/null | sort -u | tail -1)
echo "monthly_last_log:${MONTHLY_LAST_LOG:-none-this-month}"
for h in $MONTHLY_IDS; do
  [ -z "$h" ] && continue
  ENTRIES=$(jq -c --arg h "$h" --arg m "$CURRENT_MONTH" \
    'select((.habit==$h or .habit_id==$h) and (.month==$m or (.date[:7]==$m)))' \
    6-habits/_data/habits-monthly.ndjson 2>/dev/null | wc -l)
  COMPLETED=$(jq -c --arg h "$h" --arg m "$CURRENT_MONTH" \
    'select((.habit==$h or .habit_id==$h) and .completed==true and (.month==$m or (.date[:7]==$m)))' \
    6-habits/_data/habits-monthly.ndjson 2>/dev/null | wc -l)
  echo "monthly_log:$h:entries=$ENTRIES:completed=$COMPLETED"
done

echo "=== DAY TRACKING ==="
for i in $(seq 6 -1 0); do
  d=$(date -d "$i days ago" '+%Y-%m-%d' 2>/dev/null)
  [ -z "$d" ] && continue
  RATING=$(jq -r --arg d "$d" 'select(.date==$d) | .rating // "null"' data/day-tracking.ndjson 2>/dev/null | tail -1)
  echo "track:$d:$RATING"
done
echo "=== TASK HYGIENE ==="
PHANTOM=$(jq -c 'select(.status=="open" and .completed != null)' 5-actions/_data/tasks.ndjson 2>/dev/null | wc -l)
echo "phantom_tasks:$PHANTOM"
TASK_LINES=$(wc -l < 5-actions/_data/tasks.ndjson)
echo "task_lines:$TASK_LINES"
OVERDUE=$(jq -r --arg c "$CUTOFF_7D" \
  'select(.status=="open" and .deadline!=null and .deadline<$c) | "\(.id): \(.description)"' \
  5-actions/_data/tasks.ndjson 2>/dev/null)
echo "overdue_tasks:$(echo "$OVERDUE" | grep -c . 2>/dev/null || echo 0)"
[ -n "$OVERDUE" ] && echo "$OVERDUE"

echo "=== REVIVE WATCHLIST ==="
# Slippage signals across tasks, projects, and habits.
# Helper exits non-zero on real bug; zero with a JSON array (possibly empty) otherwise.
REVIVE_OUT=$(python3 automations/scripts/revive_watchlist.py --today "$TODAY" 2>&1)
REVIVE_RC=$?
if [ "$REVIVE_RC" -ne 0 ]; then
  echo "revive_watchlist:error:$REVIVE_OUT"
else
  REVIVE_COUNT=$(echo "$REVIVE_OUT" | jq 'length' 2>/dev/null || echo "parse-error")
  echo "revive_watchlist_count:$REVIVE_COUNT"
fi

echo "=== CADENCES ==="
REVIEW_LAST=$(ls notes/weekly/*.md 2>/dev/null | grep -v '\.gitkeep' | sort | tail -1 | sed -E 's|notes/weekly/||; s|\.md$||')
echo "weekly_review_last:${REVIEW_LAST:-never}"
# Note: household status + life wheel are owned by the weekly check-in (see pfc-weekly-checkin).
# A current weekly check-in implies both are fresh — do not check them separately here.

# Monthly checkin freshness: flag missing note past the 15th of the new month
LAST_MONTH=$(TZ="${LOCAL_TZ:-America/Denver}" date -d '1 month ago' '+%Y-%m' 2>/dev/null || TZ="${LOCAL_TZ:-America/Denver}" date -v-1m '+%Y-%m' 2>/dev/null || echo "")
DAY_OF_MONTH=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%d')
MONTHLY_NOTE_EXISTS=$([ -n "$LAST_MONTH" ] && ls "notes/monthly/${LAST_MONTH}.md" 2>/dev/null && echo "yes" || echo "no")
echo "monthly_checkin_last_month:${LAST_MONTH:-unknown}"
echo "monthly_checkin_note_exists:$MONTHLY_NOTE_EXISTS"
echo "day_of_month:$DAY_OF_MONTH"

# Yearly checkin freshness: flag missing note past Feb 15 of the new year
LAST_YEAR=$(TZ="${LOCAL_TZ:-America/Denver}" date -d '1 year ago' '+%Y' 2>/dev/null || TZ="${LOCAL_TZ:-America/Denver}" date -v-1y '+%Y' 2>/dev/null || echo "")
CURRENT_MONTH=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%m')
CURRENT_DAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%d')
YEARLY_NOTE_EXISTS=$([ -n "$LAST_YEAR" ] && ls "notes/yearly/${LAST_YEAR}.md" 2>/dev/null && echo "yes" || echo "no")
echo "yearly_checkin_last_year:${LAST_YEAR:-unknown}"
echo "yearly_checkin_note_exists:$YEARLY_NOTE_EXISTS"

echo "=== AUTOMATION ==="
[ -f config/google_health_tokens.json ] && echo "tokens:present" || echo "tokens:missing"
TRACK_LAST=$(tail -1 data/day-tracking.ndjson | jq -r '.date // "never"')
echo "day_track_last:$TRACK_LAST"

# Trello inbox card count — informational only. Skip entirely if env vars unset.
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi
if [ -n "$TRELLO_API_KEY" ] && [ -n "$TRELLO_API_TOKEN" ] && [ -n "$TRELLO_INBOX_LIST_ID" ]; then
  TRELLO_CARDS=$(python3 automations/scripts/trello_helper.py list 2>/dev/null | wc -l | tr -d ' ')
  echo "trello_inbox_cards:$TRELLO_CARDS"
else
  echo "trello_inbox_cards:skip"
fi

# Trello dashboard render freshness — informational. Stamp written by pfc-render-trello.
if [ -f data/.trello-last-render ]; then
  STAMP_EPOCH=$(date -d "$(cat data/.trello-last-render)" +%s 2>/dev/null || echo 0)
  NOW_EPOCH=$(date +%s)
  AGE_HOURS=$(( (NOW_EPOCH - STAMP_EPOCH) / 3600 ))
  echo "trello_dashboard_age_hours:$AGE_HOURS"
else
  echo "trello_dashboard_age_hours:never"
fi

echo "=== SUPPLEMENTS ==="
SUPP=data/supplements.ndjson
if [ -s "$SUPP" ]; then
  ACTIVE_SUPP=$(jq -c 'select(.status == "active")' "$SUPP" | wc -l | tr -d ' ')
  echo "active_supplements:$ACTIVE_SUPP"
  jq -r 'select(.status == "active") | "supp_active:\(.name) \(.dose) (\(.times | join(",")))"' "$SUPP"
else
  echo "active_supplements:0"
fi

echo "=== INSIGHTS ==="
INS=data/insights.ndjson
if [ -s "$INS" ]; then
  ACTIVE_INS=$(jq -c 'select(.status == "active")' "$INS" | wc -l | tr -d ' ')
  echo "active_insights:$ACTIVE_INS"
  LAST_INS=$(jq -r 'select(.status == "active") | .created' "$INS" | sort | tail -1)
  echo "last_insight_created:${LAST_INS:-never}"
else
  echo "active_insights:0"
  echo "last_insight_created:never"
fi

echo "=== VISIONS ==="
# Active visions and their leading-indicator coverage. A vision with zero
# linked projects AND zero linked habits is drifting.
for v in 3-visions/*.md; do
  [ -f "$v" ] || continue
  base=$(basename "$v" .md)
  case "$base" in _template|README|passion-brainstorm) continue ;; esac
  status=$(awk '/^---$/{c++; next} c==1 && /^status:/{print $2; exit}' "$v")
  [ "$status" = "active" ] || continue
  slug=$(awk '/^---$/{c++; next} c==1 && /^name:/{print $2; exit}' "$v")
  area=$(awk '/^---$/{c++; next} c==1 && /^area:/{print $2; exit}' "$v")
  linked_projects=$(jq -c --arg s "$slug" 'select(.active==true and .vision==$s)' 4-projects/_data/projects.ndjson 2>/dev/null | wc -l)
  linked_habits=$(grep -c "^[[:space:]]*vision:[[:space:]]*$slug[[:space:]]*$" config/habit_schema.yaml 2>/dev/null || echo 0)
  echo "vision:$slug:area=$area:projects=$linked_projects:habits=$linked_habits"
done

echo "=== HYPOTHESES ==="
HYP=data/hypotheses.ndjson
if [ -s "$HYP" ]; then
  ACTIVE_HYP=$(jq -c 'select(.status == "active")' "$HYP" | wc -l | tr -d ' ')
  echo "active_hypotheses:$ACTIVE_HYP"
  # Emit both started and last_reviewed so the eval step can flag stale touches.
  # last_reviewed is the primary aging signal (review-driven, not time-driven).
  jq -r 'select(.status == "active") | "hyp_touch:\(.id):started=\(.started // "unknown"):last_reviewed=\(.last_reviewed // "never")"' "$HYP"
else
  echo "active_hypotheses:0"
fi
```

---

## Step 2 — Evaluate each check

Use this table to determine status for each result:

| Check | OK | WARN | FAIL |
|---|---|---|---|
| Values | count > 0 | — | count = 0 or file missing |
| Area statements | all present | — | any missing |
| Area freshness | all < 5yr old | any 3–5yr | any > 5yr |
| Active projects | count ≤ 3 | — | count > 3 |
| Project progress | all have progress, or <30d old | active project 0% and 30–60d old | active project 0% and > 60d old |
| Daily habits defined | count > 0 | — | count = 0 |
| Daily habit logging gap | last log ≤ 2d ago | last log 3–5d ago | last log > 5d ago or never |
| Daily habit logged (each) | ≥ 1 completion last 7d, OR 0 entries last 7d (logging-gap covers it — do NOT double-flag) | ≥ 1 entry but 0 completions last 7d (genuine misses recorded — review whether habit still fits) | — (a stalled log is logging-gap, not habit failure) |
| Daily habit duplicates | 0 duplicates | 1–2 duplicates | 3+ duplicates |
| Monthly habits defined | count > 0 | count = 0 | — |
| Monthly habit logging gap | ≥ 1 entry this month, OR < 7 days into month | 7–20 days into month with 0 entries | > 20 days into month with 0 entries |
| Monthly habit logged (each) | ≥ 1 completion this month, OR 0 entries this month (logging-gap covers it) | ≥ 1 entry but 0 completions this month | — |
| Day tracking coverage | all 7 days rated | 1–2 days missing | 3+ days missing |
| AZM auto-log | last log ≤ 3d ago | last log 4–7d ago | last log > 7d or never |
| Phantom task dates | 0 tasks | 1–3 tasks | > 3 tasks |
| Task volume | < 150 lines | 150–199 lines | ≥ 200 lines |
| Overdue tasks | 0 tasks | 1–2 tasks | 3+ tasks |
| Revive watchlist freshness | exit 0, 0 items ("Nothing slipping right now.") | exit 0, 1–5 items ("Some slippage — walk via `/pfc-revive` when convenient.") | exit non-zero (real bug — surface stderr), OR exit 0 with ≥ 6 items ("Heavy slippage — triage thresholds may need adjustment, or batch through `/pfc-revive` now.") |
| Weekly review | last ≤ 8d ago | last 9–14d ago | never or > 14d |
| Monthly checkin note | note exists for last month, OR day-of-month ≤ 15 | note missing and day-of-month > 15 | — |
| Yearly checkin note | note exists for last year, OR not yet Feb 15 of current year | note missing and current date ≥ Feb 15 | — |
| Health tokens | present | — | missing |
| Active insights | — | > 20 unreviewed for 30+ days | — (no hard cap) |
| Insight freshness | last created ≤ 14d ago, or zero ever | 14–30d ago | > 30d ago (likely capture has stalled) |
| Active hypotheses | — | 1–3 active | > 3 active |
| Hypothesis touch (each) | last_reviewed ≤ 30d ago | last_reviewed 30–60d ago, OR null (never reviewed) | last_reviewed > 60d ago |
| Active supplements count | ≥ 1 | — | 0 (registry empty likely means drift if user normally takes supplements) |
| Active vision linked indicators | ≥ 1 linked project OR ≥ 1 linked habit | — | 0 linked (vision drifting — no leading indicators) |
| Trello inbox cards | informational only | — | — (never fails; see "Trello inbox" reporting note below) |
| Trello dashboard freshness | last render ≤ 24h ago, or never | last render > 24h ago | — (never fails; informational) |

### Trello inbox

If `TRELLO_API_KEY`, `TRELLO_API_TOKEN`, and `TRELLO_INBOX_LIST_ID` are all set in `.env`, run:

```bash
python3 automations/scripts/trello_helper.py list 2>/dev/null | wc -l
```

Report:
- 🟢 0 cards: "Trello inbox: empty."
- 🟡 1–9 cards: "Trello inbox: N cards waiting. Run `/pfc-trello-inbox` to process."
- 🟡 10+ cards: "Trello inbox: N cards waiting (backlog growing)."

Skip the check entirely if any of the three env vars is missing — that's not a health failure, just means the user hasn't set up Trello capture.

### Trello dashboard freshness

If `data/.trello-last-render` exists, surface its age in hours (set by `pfc-render-trello` after each successful render). Report:
- 🟢 `trello_dashboard_age_hours` ≤ 24: "Trello dashboard: rendered N hours ago."
- 🟡 `trello_dashboard_age_hours` > 24: "Trello dashboard: last rendered N hours ago. Run `/pfc-render-trello` to refresh."
- 🟢 `never`: "Trello dashboard: never rendered (not configured or first run pending)."

Never fails. The dashboard is a derived view — staleness means the view drifts from the canonical repo, which is recoverable by a single render.

---

## Step 3 — Output table

Display sorted: FAIL rows first, then WARN, then OK.

```
| Status   | Category    | Check                  | Detail                        | Action                              |
|----------|-------------|------------------------|-------------------------------|-------------------------------------|
| 🔴 FAIL  | Cadences    | Weekly check-in        | Never completed               | Run /pfc-weekly-checkin             |
| 🟡 WARN  | Habits      | <bedtime-habit>   | 0 completions this week       | Log manually with /pfc-log-habit    |
| 🟢 OK    | Foundation  | Values                 | 11 values defined             | —                                   |
```

Always prepend the status with the matching circle emoji: 🔴 FAIL, 🟡 WARN, 🟢 OK.

---

## Step 4 — Summary line

```
System Health: X OK  |  Y WARN  |  Z FAIL
```

---

## Step 5 — Action list

If any WARN or FAIL items exist, output a prioritized numbered list.

Sort order: FAIL items first (by ease of fix — quick wins before time-intensive), then WARN items.

Format each item with the matching circle emoji:
```
1. [🔴 FAIL] Weekly check-in — run /pfc-weekly-checkin (last: never)
2. [🔴 FAIL] Phantom task dates — 10 open tasks have a completed date set; ask Claude to clean them
3. [🟡 WARN] Habit not logged — "<bedtime-habit>" has 0 completions this week
```

---

## Step 6 — Diagnose: input-side vs. system-side

For each WARN/FAIL item, propose a diagnosis. The system is not always at fault — but it sometimes is. Pick the right framing before suggesting a fix. Reference: `0-me/working-with-me.md` § System diagnosis.

| Diagnosis | Meaning | Action shape |
|---|---|---|
| **Input-side** | System is fine; the user just hasn't been doing the inputs (exercise, sleep, eating, meds). | Restore the input. Not a system tweak. |
| **System-side** | Even with inputs healthy, the check is failing. The shape, threshold, or cadence is wrong. | Propose a tweak — different cadence, different threshold, different shape. |
| **Mixed** | Both could apply. | Surface both, let the user pick. |

Append the diagnosis to each action item:

```
1. [🔴 FAIL] Daily habit "<habit>" — 0 completions in 7 days
   Diagnosis: input-side (habit was skipped). Suggest a 5-minute version today; offer /pfc-stuck if there's resistance.
2. [🟡 WARN] Project progress on "X" — 0% in 35d
   Diagnosis: mixed. Could be input-side (no time/energy) or system-side (project poorly scoped). Ask which.
```

This turns audit data into an actionable suggestion rather than a flat report. Don't default to either "system is fine" or "system needs overhaul" — diagnose explicitly. **Allow in-the-moment system tweaks** when sleep / exercise / state are off; flexibility wins over rigidity in those windows.

---

## Action reference

| Check | Fail/Warn action |
|---|---|
| Values missing | Recreate 1-values/values.md with your top values |
| Area statement missing | Ask Claude to draft one, then review |
| Area statement stale | Update the statement.md for that area |
| Too many active projects | Archive or move one project to planned status |
| Stale active project (0%, old) | Ask: progress it, pause it, or cut it? |
| No daily habits defined | Add to config/habit_schema.yaml |
| Daily habit logging gap (no entries N+ days) | Run /pfc-evening-checkin or /pfc-log-habit. **Do NOT backfill `completed:false` for the silent days** — absence is not a miss. |
| Daily habit logged but 0 completions | Run /pfc-pick-tasks or /pfc-weekly-checkin — habit may have stalled or no longer fit; review fit, not the user. |
| Daily habit duplicates | Ask Claude to dedupe 6-habits/_data/habits-daily.ndjson by (habit_id, date) |
| No monthly habits defined | Add to config/habit_schema.yaml under `monthly_habits:` or accept empty |
| Monthly habit logging gap | Run /pfc-log-habit when one happens this month |
| Monthly habit logged but 0 completions | Review in /pfc-weekly-checkin — habit may need to be cut or rescoped |
| Day tracker gaps | Run /pfc-log-day for each missing date |
| Auto-logged habit not logging | Run `python3 automations/scripts/auto_log_habits.py` to test; check tokens (no habits currently use auto_log) |
| Phantom task dates | Ask Claude to strip completed field from open tasks |
| Task volume near threshold | Ask Claude to archive completed tasks |
| Overdue tasks | Review each: complete, reschedule, or delete |
| Revive watchlist — 1–5 items slipping | Run `/pfc-revive` when convenient to walk the watchlist and triage each item |
| Revive watchlist — ≥ 6 items slipping | Batch through `/pfc-revive` now, or revisit the signal thresholds in `automations/scripts/revive_watchlist.py` if the volume looks systemic rather than real slippage |
| Revive watchlist — helper errored | Capture stderr and investigate `automations/scripts/revive_watchlist.py` — real bug, not a data issue |
| No weekly review | Run /pfc-weekly-checkin |
| Monthly checkin note missing (past mid-month) | Run /pfc-monthly-checkin — note should exist for last month by the 15th of the new month |
| Yearly checkin note missing (past Feb 15) | Run /pfc-yearly-checkin — note should exist for last year by Feb 15 of the new year |
| Health tokens missing | Run `python3 automations/scripts/google_health_auth.py` |
| Active hypotheses > 3 | Review in /pfc-weekly-checkin; resolve stale ones (graduate, reject, or archive) |
| Hypothesis last_reviewed > 60d ago | Run /pfc-weekly-checkin (Hypotheses Touch Pass) — set fresh confidence, add any new evidence, or move to resolved-rejected/archived |
| Hypothesis last_reviewed null or 30–60d ago | Touch on next /pfc-weekly-checkin — no urgency, but the belief is going un-stated |
| Insight capture stalled | Run `/pfc-insights` to review; capture is bottlenecked — nothing's been noticed lately, or capture habit has lapsed |
| Many old active insights | Run `/pfc-insights` to triage — archive what's gone stale, graduate what's actionable |
| Active supplements = 0 | Registry has drifted from reality; run /pfc-supplement and add current items |
| Active vision with 0 linked indicators | Either retire the vision (set `status: paused` or `abandoned` in the vision file) or add a project/habit with `vision: <slug>` so the vision has a leading indicator |
| Trello inbox cards waiting | Run `/pfc-trello-inbox` to walk the cards and route each one |
