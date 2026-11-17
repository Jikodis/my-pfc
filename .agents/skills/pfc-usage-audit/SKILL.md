---
name: pfc-usage-audit
description: Audit whether the system is actually being USED and producing — data freshness, logging gaps, missed-target streaks, stale reviews, surfaces nobody reads. Use when the user says "usage audit", "system health", "is the system working", "am I actually using the system", "what am I not using", "system health report", "which features am I using", or "check the system". This is NOT /pfc-repo-maintenance (machinery and docs integrity) and NOT /pfc-status (the life content view).
---

# Usage Audit

Audit whether the system is actually being *used* and producing — not what's in it (/pfc-status) and not whether the machinery is intact (/pfc-repo-maintenance). The question this skill answers: **"am I doing what the system exists to make me do — logging, reviewing, acting — and which parts have quietly gone unused?"** Renamed from `pfc-system-health`; the old trigger phrases still work.

Two parts, in this order:

1. **Feature scorecard** (Step 0): which features are used, which aren't, and whether each needs plain use, a new cadence, or a redesign. This leads the output.
2. **Plumbing checks** (Steps 1–6): data freshness, logging gaps, stale reviews. A sorted table and an action list.

No questions during the run; any decision goes in one Open questions table at the end.

---

## Step 0 — Feature scorecard

Score each feature on real use: the last 30 days, and the 60 days before that, each against what the feature asks for in that window. A daily feature asks 30 of 30; a weekly one asks about 4. Count only the user's own use: rows the system writes itself (health-fetched day records with no rating, auto-derived habits) do not count.

```bash
python3 automations/scripts/feature_use.py          # three tables: features, habits, jobs that run on their own; --json for the raw numbers
```

`feature_use.py` scores every feature this way and suggests a verdict per feature (keep / just use it / change cadence / change feature); the web UI's writes count as the user's use. Use its tables when it runs. The shell block below gives the same day counts without Python:

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
D30=$(date -d '30 days ago' '+%Y-%m-%d' 2>/dev/null || date -v-30d '+%Y-%m-%d')
D90=$(date -d '90 days ago' '+%Y-%m-%d' 2>/dev/null || date -v-90d '+%Y-%m-%d')

# Days with use, from a list of dates on stdin: "<last 30> <days 31-90>"
days() { sort -u | awk -v a="$D30" -v b="$D90" -v t="$TODAY" '$1>a && $1<=t {r++} $1>b && $1<=a {o++} END {print r+0, o+0}'; }
# Days a file was committed to (for features whose records carry no date of use)
commit_days() { git log --since="$D90" --format=%ad --date=short -- "$@" 2>/dev/null; }

echo "rating (daily):      $(jq -r 'select(.rating != null) | .date' data/day-tracking.ndjson 2>/dev/null | days)"
echo "habits (daily):      $(jq -r 'select((.source // "") | endswith("-derived") | not) | .date' 7-habits/_data/habits-daily.ndjson 2>/dev/null | days)"
echo "2+1 (daily):         $(jq -r 'select(((.critical // []) | length) > 0) | .date' 6-tasks/_data/daily-focus.ndjson 2>/dev/null | days)"
echo "reviews (weekly):    $(commit_days data/review-ledger.ndjson | days)"
echo "focus (weekly):      $(commit_days 4-focus/_data/focus.ndjson | days)"
echo "task capture:        $(jq -r '.created // empty' 6-tasks/_data/tasks.ndjson 6-tasks/_data/tasks-archive.ndjson 2>/dev/null | days)"
echo "task completion:     $(jq -r 'select(.event == "completed") | .timestamp[:10]' 6-tasks/_data/task_events.ndjson 2>/dev/null | days)"
echo "projects:            $(commit_days 5-projects/_data/projects.ndjson | days)"
echo "insights:            $(jq -r '.created // empty' data/insights.ndjson 2>/dev/null | days)"
echo "hypotheses:          $(commit_days data/hypotheses.ndjson | days)"
echo "revive:              $(jq -r '.date' data/revive-events.ndjson 2>/dev/null | days)"
echo "vision brainstorm:   $(commit_days 3-visions/_data/vision-brainstorm.ndjson | days)"
```

Each line prints two numbers: days used in the last 30, and days used in days 31–90. Turn them into rates against what the feature asks for (daily: 30 and 60; weekly: about 4 and 9). Commit days are a proxy, so say so in the report. **On-demand features** (task capture and below) have no target: report the last use only.

**Suggested verdict, from the two rates** (🟢 used ≥ 60%, 🟡 partly ≥ 20%, 🔴 unused below that):

| Suggested verdict | When | Means |
|---|---|---|
| keep | used in the last 30 days | Leave it. |
| just use it | it worked in days 31–90, or is climbing | The feature is fine; it lapsed. Restart with one small step. |
| change cadence | half-used for 90 days | The user will do it, just not that often, or not from that trigger. Lower the rhythm or move the ask to where the user already is. |
| change feature | barely used for 90 days | It isn't landing. Redesign it, merge it into something that is used, or retire it. |

The verdict is a starting point. Override it with judgment, and say why in one line:

- **Inputs before design** (Step 6): a feature that died the same week sleep or exercise fell off is input-side, not "change feature".
- **Core features** (day rating, habits, the 2+1, reviews, the focus re-pick, projects) feed the current focuses and visions. Mark them "should be using". A core feature never gets "retire"; it gets a lighter route.
- **Habits:** a red habit that feeds a focus is that focus's real problem. Two causes look the same in the data: the user does it and doesn't log it, or doesn't do it. Ask which before changing the target.
- **On-demand features** are flagged only when they have gone a full 90 days unused *and* something they exist for happened (a slipping task never revived).

**Report shape:** a one-line verdict; the scorecard table (feature, last 30 days, verdict, one-line why), core features first, red first, at most about 12 rows; the top 3 changes to make first, each a 15-minute step; then the plumbing checks.

**Log what the user decides.** Every change the user agrees to (a new cadence, a new route, a feature retired) becomes a task through `/pfc-add-task`, worded as a check: "Check whether <change> worked for <feature>", with a `deadline` about 4 weeks out. When that task comes up, ask whether it worked; if it did not, record that as an insight (`/pfc-add-insight`) so the same change is not proposed again. Read open and recently done tasks of that shape before proposing a change, so a change already being tried is not proposed twice.

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

# 2-areas/_data/ holds the life-wheel + household registries, not an area — skip it
# (and any other underscore-prefixed support folder) or it reports a phantom
# missing statement on every run.
for d in 2-areas/*/; do
  area=$(basename "$d")
  case "$area" in _*) continue ;; esac
  [ -f "$d/statement.md" ] && echo "statement:OK:$area" || echo "statement:MISSING:$area"
done

for f in 2-areas/*/statement.md; do
  area=$(basename "$(dirname "$f")")
  last=$(git log -1 --format="%as" -- "$f" 2>/dev/null)
  [ -z "$last" ] && echo "freshness:UNCOMMITTED:$area" && continue
  [ "$last" \< "$CUTOFF_5YR" ] && echo "freshness:STALE:$area ($last)" || echo "freshness:OK:$area"
done

echo "=== PROJECTS ==="
jq -r 'select(.active==true) | "\(.id)|\(.name)|\(.completed_parts)|\(.total_parts)|\(.created)"' 5-projects/_data/projects.ndjson

echo "=== HABITS (DAILY) ==="
DAILY_IDS=$(awk '/^daily_habits:/{flag=1;next} /^[a-z_]+:/{flag=0} flag && /^  - id:/{print $3}' config/habit_schema.yaml | tr -d '"')
DAILY_COUNT=$(echo "$DAILY_IDS" | grep -c .)
echo "daily_defined:$DAILY_COUNT"
# Logging-gap signal: most recent log entry across ALL daily habits.
# Distinguishes "user stopped logging" from "user logged a miss" — these are different problems.
DAILY_LAST_LOG=$(jq -r '.date' 7-habits/_data/habits-daily.ndjson 2>/dev/null | sort -u | tail -1)
echo "daily_last_log:${DAILY_LAST_LOG:-never}"
for h in $DAILY_IDS; do
  [ -z "$h" ] && continue
  ENTRIES=$(jq -c --arg h "$h" --arg from "$CUTOFF_7D" --arg to "$TODAY" \
    'select((.habit==$h or .habit_id==$h) and .date>=$from and .date<=$to)' \
    7-habits/_data/habits-daily.ndjson 2>/dev/null | wc -l)
  COMPLETED=$(jq -c --arg h "$h" --arg from "$CUTOFF_7D" --arg to "$TODAY" \
    'select((.habit==$h or .habit_id==$h) and .completed==true and .date>=$from and .date<=$to)' \
    7-habits/_data/habits-daily.ndjson 2>/dev/null | wc -l)
  echo "habit_log:$h:entries=$ENTRIES:completed=$COMPLETED"
done
# Duplicate detection (same habit_id + same date, >1 entry)
DUPES=$(jq -r '[(.habit_id // .habit), .date] | @tsv' 7-habits/_data/habits-daily.ndjson 2>/dev/null | \
  sort | uniq -c | awk '$1 > 1 {print $2 " on " $3 " (x"$1")"}')
echo "daily_dupes:$(echo "$DUPES" | grep -c . 2>/dev/null)"
[ -n "$DUPES" ] && echo "$DUPES"

# Logging blackout — days in the last 14 with NO habit record of any kind.
# This is a DIFFERENT failure from a low completion rate and must be reported
# separately. "Unlogged counts as missed" is the right rule for rate math, but on
# a blackout stretch it turns silence into a wall of red and reads as mass habit
# failure when the real problem is that nothing got logged at all.
BLACKOUT_DAYS=""
for i in $(seq 13 -1 0); do
  d=$(date -d "$i days ago" '+%Y-%m-%d' 2>/dev/null) || continue
  [ -z "$d" ] && continue
  N=$(jq -c --arg d "$d" 'select(.date==$d)' 7-habits/_data/habits-daily.ndjson 2>/dev/null | wc -l | tr -d ' ')
  [ "$N" -eq 0 ] && BLACKOUT_DAYS="$BLACKOUT_DAYS $d"
done
echo "habit_blackout_days_14d:$(echo $BLACKOUT_DAYS | wc -w | tr -d ' ')"
[ -n "$BLACKOUT_DAYS" ] && echo "habit_blackout_dates:$BLACKOUT_DAYS"
# Longest unbroken blackout run in that window — a scattered miss is not the same
# as a two-week stretch where the whole logging loop stopped.
echo "habit_blackout_longest_run:$(
  for i in $(seq 13 -1 0); do
    d=$(date -d "$i days ago" '+%Y-%m-%d' 2>/dev/null)
    n=$(jq -c --arg d "$d" 'select(.date==$d)' 7-habits/_data/habits-daily.ndjson 2>/dev/null | wc -l | tr -d ' ')
    [ "$n" -eq 0 ] && echo 0 || echo 1
  done | awk '{if($1==0){r++; if(r>m)m=r}else r=0} END{print m+0}'
)"

echo "=== HABITS (MONTHLY) ==="
MONTHLY_IDS=$(awk '/^monthly_habits:/{flag=1;next} /^[a-z_]+:/{flag=0} flag && /^  - id:/{print $3}' config/habit_schema.yaml | tr -d '"')
MONTHLY_COUNT=$(echo "$MONTHLY_IDS" | grep -c .)
echo "monthly_defined:$MONTHLY_COUNT"
CURRENT_MONTH=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m')
# Logging-gap signal: most recent log entry across ALL monthly habits this month.
MONTHLY_LAST_LOG=$(jq -r --arg m "$CURRENT_MONTH" 'select(.month==$m or (.date[:7]==$m)) | .date // .month' \
  7-habits/_data/habits-monthly.ndjson 2>/dev/null | sort -u | tail -1)
echo "monthly_last_log:${MONTHLY_LAST_LOG:-none-this-month}"
for h in $MONTHLY_IDS; do
  [ -z "$h" ] && continue
  ENTRIES=$(jq -c --arg h "$h" --arg m "$CURRENT_MONTH" \
    'select((.habit==$h or .habit_id==$h) and (.month==$m or (.date[:7]==$m)))' \
    7-habits/_data/habits-monthly.ndjson 2>/dev/null | wc -l)
  COMPLETED=$(jq -c --arg h "$h" --arg m "$CURRENT_MONTH" \
    'select((.habit==$h or .habit_id==$h) and .completed==true and (.month==$m or (.date[:7]==$m)))' \
    7-habits/_data/habits-monthly.ndjson 2>/dev/null | wc -l)
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
PHANTOM=$(jq -c 'select(.status=="open" and .completed != null)' 6-tasks/_data/tasks.ndjson 2>/dev/null | wc -l)
echo "phantom_tasks:$PHANTOM"
TASK_LINES=$(wc -l < 6-tasks/_data/tasks.ndjson)
echo "task_lines:$TASK_LINES"
OVERDUE=$(jq -r --arg c "$CUTOFF_7D" \
  'select(.status=="open" and .deadline!=null and .deadline<$c) | "\(.id): \(.description)"' \
  6-tasks/_data/tasks.ndjson 2>/dev/null)
echo "overdue_tasks:$(echo "$OVERDUE" | grep -c . 2>/dev/null)"
[ -n "$OVERDUE" ] && echo "$OVERDUE"

# Agent-doable backlog. Tasks marked agent_doable:"yes" need nobody but an agent,
# so one sitting clears them. If they pile up and age, the hand-off route is not
# being used, which is a usage failure, not a backlog failure.
AGENT_YES=$(jq -r --arg t "$TODAY" '
  select(.status == "open" and (.deferred != true) and .agent_doable == "yes" and .created != null)
  | (($t | strptime("%Y-%m-%d") | mktime) - (.created | strptime("%Y-%m-%d") | mktime)) / 86400 | floor
  ' 6-tasks/_data/tasks.ndjson 2>/dev/null)
echo "agent_doable_yes_open:$(echo "$AGENT_YES" | grep -c '[0-9]' || true)"
echo "agent_doable_yes_oldest_days:$(echo "$AGENT_YES" | sort -n | tail -1)"
# Unclassified open tasks: the field should be set at capture.
echo "agent_doable_unset:$(jq -r 'select(.status == "open" and .agent_doable == null) | .id' 6-tasks/_data/tasks.ndjson 2>/dev/null | grep -c . || true)"

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
# The daily spine is the evening check-in. The weekly/monthly/quarterly rituals are gone —
# their work is the rolling ledger (data/review-ledger.ndjson), which drips ≤2 due items
# per evening and is worked one review at a time by /pfc-review. So cadence freshness is (a) how recent
# the newest evening check-in is and (b) how backed-up the ledger is. Do NOT key off
# notes/weekly/ or notes/monthly/ — those are archival and nothing writes to them.

# Evening check-in freshness: newest day-tracking row carrying an evening rating.
EVENING_LAST=$(jq -r 'select(.rating != null) | .date' data/day-tracking.ndjson 2>/dev/null | sort | tail -1)
echo "evening_checkin_last:${EVENING_LAST:-never}"

# Rating GAPS in the trailing 14 days (today excluded: the day isn't over).
# Freshness alone hides a hole in the middle: a rating yesterday and one last week
# reads "fresh" while five days in between are unrecoverable.
RATING_GAPS=$(jq -rs --arg t "$TODAY" '
  (map(select(.rating != null) | .date) | unique) as $rated
  | [ range(1; 15) as $i
      | (($t | strptime("%Y-%m-%d") | mktime) - ($i * 86400) | strftime("%Y-%m-%d"))
      | select(. as $d | $rated | index($d) | not) ]
  | join(",")' data/day-tracking.ndjson 2>/dev/null)
echo "rating_gaps_14d_count:$(echo "$RATING_GAPS" | awk -F, '{print ($1=="" ? 0 : NF)}')"
echo "rating_gaps_14d:${RATING_GAPS:-none}"

# Rolling-review backlog. For each ledger item: days_overdue = (today - last_done) - cadence_days.
# Report how many are currently due, the worst overdue among weekly items, and the worst
# among quarterly items (a quarterly review ≥2 cadences late means a re-pick was skipped).
#
# SEED NOTE: the shipped ledger seeds last_done to the sentinel 2000-01-01, meaning
# "never run." On a fresh clone every item reads as due and the counts will be maxed.
# That is the expected first-run state, not a failure — see the eval table.
if [ -s data/review-ledger.ndjson ]; then
  LEDGER_STATS=$(jq -rc --arg t "$TODAY" '
    ($t | strptime("%Y-%m-%d") | mktime) as $now
    | (.last_done | strptime("%Y-%m-%d") | mktime) as $ld
    | (($now - $ld) / 86400 | floor) as $age
    | [ .id, .tier, .cadence_days, ($age - .cadence_days), .last_done ] | @tsv
  ' data/review-ledger.ndjson 2>/dev/null)
  LEDGER_TOTAL=$(echo "$LEDGER_STATS" | grep -c . 2>/dev/null)
  LEDGER_DUE=$(echo "$LEDGER_STATS" | awk -F'\t' '$4 >= 0' | grep -c . 2>/dev/null)
  LEDGER_NEVER=$(echo "$LEDGER_STATS" | awk -F'\t' '$5 == "2000-01-01"' | grep -c . 2>/dev/null)
  WEEKLY_MAX_OVERDUE=$(echo "$LEDGER_STATS" | awk -F'\t' '$2=="weekly"{print $4}' | sort -rn | head -1)
  # Quarterly items expressed in cadences late, so "≥2" is threshold-independent.
  QUARTERLY_MAX_CADENCES=$(echo "$LEDGER_STATS" | awk -F'\t' '$2=="quarterly" && $3>0 {printf "%d\n", $4/$3}' | sort -rn | head -1)
  echo "review_ledger_items:$LEDGER_TOTAL"
  echo "review_ledger_due_count:${LEDGER_DUE:-0}"
  echo "review_ledger_never_run:${LEDGER_NEVER:-0}"
  echo "review_ledger_weekly_max_overdue:${WEEKLY_MAX_OVERDUE:-0}"
  echo "review_ledger_quarterly_max_cadences_late:${QUARTERLY_MAX_CADENCES:-0}"
  # Name the due items so the report can point at them, most-overdue first.
  echo "$LEDGER_STATS" | awk -F'\t' '$4 >= 0 {print "review_due:" $1 ":" $2 ":overdue_days=" $4}' | sort -t= -k2 -rn
else
  echo "review_ledger_items:no-ledger"
fi

# Area check-in freshness. Every active, not-ended area item with a `question` is lit
# only by its newest answer in 2-areas/_data/area-checkins.ndjson (the life-wheel step
# of /pfc-review). Counted as answered within 31 days, so high is good; an item never
# answered counts as not fresh.
if [ -s 2-areas/_data/area-items.ndjson ]; then
  CHECKIN_STATS=$(jq -rn --arg t "$TODAY" \
    --slurpfile items 2-areas/_data/area-items.ndjson \
    --slurpfile ans <(cat 2-areas/_data/area-checkins.ndjson 2>/dev/null) '
    ($t | strptime("%Y-%m-%d") | mktime) as $now
    | ($ans | group_by(.item_id) | map({key: .[0].item_id, value: (map(.date) | max)}) | from_entries) as $last
    | [ $items[] | select(.active == true and has("question") and ((.ends // "9999-12-31") >= $t)) ] as $asked
    | [ $asked[] | select($last[.id] != null
          and ((($now - ($last[.id] | strptime("%Y-%m-%d") | mktime)) / 86400 | floor) <= 31)) ] as $fresh
    | "\($fresh | length)\t\($asked | length)\t\(($ans | map(.date) | max) // "never")"')
  echo "area_checkins_fresh:$(echo "$CHECKIN_STATS" | cut -f1)"
  echo "area_checkins_asked:$(echo "$CHECKIN_STATS" | cut -f2)"
  echo "area_checkins_last:$(echo "$CHECKIN_STATS" | cut -f3)"
else
  echo "area_checkins_fresh:no-items"
fi

# Yearly checkin freshness: flag missing note past Feb 15 of the new year
LAST_YEAR=$(TZ="${LOCAL_TZ:-America/Denver}" date -d '1 year ago' '+%Y' 2>/dev/null || TZ="${LOCAL_TZ:-America/Denver}" date -v-1y '+%Y' 2>/dev/null || echo "")
CURRENT_MONTH=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%m')
CURRENT_DAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%d')
YEARLY_NOTE_EXISTS=$([ -n "$LAST_YEAR" ] && ls "notes/yearly/${LAST_YEAR}.md" 2>/dev/null && echo "yes" || echo "no")
echo "yearly_checkin_last_year:${LAST_YEAR:-unknown}"
echo "yearly_checkin_note_exists:$YEARLY_NOTE_EXISTS"

echo "=== CLONE SYNC ==="
# "ahead" = commits nobody else can see yet; "behind" = this clone is editing stale
# copies. A healthy clone shows neither.
git fetch -q origin 2>/dev/null
echo "clone_sync:$(git status -sb 2>/dev/null | head -1)"

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
  case "$base" in _template|README|AGENTS|CLAUDE) continue ;; esac
  status=$(awk '/^---$/{c++; next} c==1 && /^status:/{print $2; exit}' "$v")
  [ "$status" = "active" ] || continue
  slug=$(awk '/^---$/{c++; next} c==1 && /^name:/{print $2; exit}' "$v")
  area=$(awk '/^---$/{c++; next} c==1 && /^area:/{print $2; exit}' "$v")
  linked_projects=$(jq -c --arg s "$slug" 'select(.active==true and .vision==$s)' 5-projects/_data/projects.ndjson 2>/dev/null | wc -l)
  linked_habits=$(grep -c "^[[:space:]]*vision:[[:space:]]*$slug[[:space:]]*$" config/habit_schema.yaml 2>/dev/null || echo 0)
  # A Current Focus item pointing at this vision is also a leading indicator —
  # counting only projects/habits would flag a vision that is actively being pursued.
  linked_focus=$(jq -c --arg s "$slug" \
    'select(.retired_date==null and (.link.type // "")=="vision" and (.link.ref // "")==$s)' \
    4-focus/_data/focus.ndjson 2>/dev/null | wc -l)
  echo "vision:$slug:area=$area:projects=$linked_projects:habits=$linked_habits:focus=$linked_focus"
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

echo "=== CURRENT FOCUS ==="
# The quarter-horizon layer: capped, traffic-lit, re-picked each quarter.
# Three things go wrong: too many pursuits (the cap is the whole point of the
# layer), a pursuit with no landing (no when/where trigger = it never starts),
# and a stale `quarter` (the re-pick never happened).
FOCUSF=4-focus/_data/focus.ndjson
if [ -s "$FOCUSF" ]; then
  PURSUITS=$(jq -c 'select(.tier=="pursuit" and .retired_date==null)' "$FOCUSF" | wc -l | tr -d ' ')
  NO_LANDING=$(jq -c 'select(.tier=="pursuit" and .retired_date==null and ((.landing // "")==""))' "$FOCUSF" | wc -l | tr -d ' ')
  CAP=$(awk '/^  pursuit:/{f=1;next} f && /cap:/{print $2; exit}' config/focus.yaml)
  CURQ="$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y')-Q$(( ($(TZ="${LOCAL_TZ:-America/Denver}" date '+%-m')-1)/3+1 ))"
  echo "focus_pursuits:$PURSUITS"
  echo "focus_pursuit_cap:${CAP:-6}"
  echo "focus_missing_landing:$NO_LANDING"
  echo "focus_current_quarter:$CURQ"
  # Quarters behind = (current year*4+q) - (record year*4+q), computed per record.
  jq -rc --arg q "$CURQ" '
    select(.retired_date==null)
    | ($q | split("-Q")) as $c
    | ((.quarter // $q) | split("-Q")) as $r
    | ((($c[0]|tonumber)*4 + ($c[1]|tonumber)) - (($r[0]|tonumber)*4 + ($r[1]|tonumber))) as $behind
    | select($behind >= 1)
    | "focus_stale:\(.id):\(.title):quarter=\(.quarter):quarters_behind=\($behind)"
  ' "$FOCUSF" 2>/dev/null
  jq -rc 'select(.tier=="pursuit" and .retired_date==null and ((.landing // "")=="")) | "focus_no_landing:\(.id):\(.title)"' "$FOCUSF"
else
  echo "focus_pursuits:none"
fi

echo "=== FRONT OF MIND ==="
# Grounding anchors are a CYCLING set — the failure mode is staleness, not volume.
# A set nobody has touched in months has stopped being "what I need in view now"
# and has quietly become wallpaper.
GRD=data/grounding.ndjson
if [ -s "$GRD" ]; then
  GRD_ACTIVE=$(jq -c 'select(.status=="active")' "$GRD" | wc -l | tr -d ' ')
  GRD_NEWEST=$(jq -r 'select(.status=="active") | .created' "$GRD" | sort | tail -1)
  GRD_CAP=$(awk '/^soft_cap:/{f=1;next} f && /active_records:/{print $2; exit}' config/grounding_schema.yaml)
  echo "grounding_active:$GRD_ACTIVE"
  echo "grounding_soft_cap:${GRD_CAP:-10}"
  echo "grounding_newest_created:${GRD_NEWEST:-never}"
else
  echo "grounding_active:0"
fi

echo "=== SUPERMAN PULSE ==="
# The pulse board (Trello 🦸 Superman Pulse + the pfc-pulse TRMNL screen) renders
# from the newest day-tracking record's `health` block. No health block anywhere
# in recent history => pulse_snapshot returns None => the board renders EMPTY with
# no error anywhere. Check renderability directly rather than inferring it.
python3 - <<'PY' 2>/dev/null || echo "pulse_renderable:check-failed"
import json, sys
from pathlib import Path
sys.path.insert(0, "automations/scripts")
rows = [json.loads(l) for l in Path("data/day-tracking.ndjson").read_text().splitlines() if l.strip()]
try:
    from pulse import pulse_snapshot
    snap = pulse_snapshot(rows)
except Exception as e:
    print(f"pulse_renderable:error:{e}"); sys.exit()
if snap is None:
    print("pulse_renderable:no (no day-tracking record carries a health block)")
else:
    print(f"pulse_renderable:yes (date={snap['date']})")
PY

echo "=== TRMNL ==="
# Only meaningful when the endpoint is actually configured. An unconfigured repo
# (no TRMNL device) skips silently — it is not a finding.
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi
if [ -n "$TRMNL_SERVE_TOKEN" ]; then
  PORT="${TRMNL_SERVE_PORT:-8765}"
  if curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
    echo "trmnl_endpoint:ok"
  else
    echo "trmnl_endpoint:unreachable (port $PORT)"
  fi
  # The endpoint serves whatever the local clone holds; pfc-repo-sync.timer is what
  # keeps that clone current. A live endpoint on a stale clone shows stale screens.
  SYNC=$(systemctl --user list-timers pfc-repo-sync.timer --no-pager 2>/dev/null | grep -c 'pfc-repo-sync' || echo 0)
  echo "trmnl_repo_sync_timer:$([ "$SYNC" -gt 0 ] && echo active || echo not-found)"
else
  echo "trmnl:not_configured"
fi

echo "=== REMARKABLE AND AI NEWS ==="
# reMarkable pages (docs/remarkable.md): each page's last upload, from
# data/.remarkable/state.json (remarkable_sync.py, every 10 minutes). The Today page
# changes at least daily, so an upload older than ~26 h means the timer or the rmapi
# sign-in broke. No state file = not set up, not a finding.
RMSTATE="data/.remarkable/state.json"
if [ -f "$RMSTATE" ]; then
  python3 - "$RMSTATE" <<'PY'
import json, sys
from datetime import datetime
s = json.load(open(sys.argv[1]))
for name, d in (s.get("docs") or {}).items():
    up = d.get("uploaded")
    if not up:
        print(f"remarkable:{name}:never")
        continue
    age = (datetime.now().astimezone() - datetime.fromisoformat(up)).total_seconds() // 3600
    print(f"remarkable:{name}:uploaded_{int(age)}h_ago")
print(f"remarkable:last_read={s.get('last_read') or 'none'}")
PY
else
  echo "remarkable:not_configured"
fi

# AI News (docs/ai-news.md): newest post kept or skipped in data/ai-news.ndjson
# (ai_news.py, daily). No new record in 14 days means a source broke or the timer
# stopped. Also list the last 30 days of skipped titles with their reasons, so a
# wrong filter shows up here.
if [ -s data/ai-news.ndjson ]; then
  AN30=$(date -d '30 days ago' '+%Y-%m-%d' 2>/dev/null || date -v-30d '+%Y-%m-%d')
  jq -rs 'max_by(.decided) | "ainews:last_decided=\(.decided)"' data/ai-news.ndjson
  jq -rs --arg c "$AN30" '[.[] | select(.decided >= $c)] |
    "ainews:30d kept=\([.[]|select(.status=="done")]|length) skipped=\([.[]|select(.status=="skipped" and .reason!="older than the first-run window")]|length) failed=\([.[]|select(.status=="failed")]|length) audio=\([.[]|select(.mp3)]|length)"' data/ai-news.ndjson
  jq -r --arg c "$AN30" 'select(.decided >= $c and .status=="skipped" and .reason!="older than the first-run window") | "ainews:skipped:\(.title) — \(.reason)"' data/ai-news.ndjson
else
  echo "ainews:not_configured"
fi

echo "=== SURFACE USE ==="
# Which parts of the system are actually being used. There is no invocation
# log, so last-write is the only available proxy — report it as a proxy, not
# as fact.
for f in 6-tasks/_data/tasks.ndjson 7-habits/_data/habits-daily.ndjson \
         7-habits/_data/habits-monthly.ndjson 4-focus/_data/focus.ndjson \
         5-projects/_data/projects.ndjson data/day-tracking.ndjson \
         data/insights.ndjson data/hypotheses.ndjson data/findings.ndjson \
         data/grounding.ndjson data/supplements.ndjson data/review-ledger.ndjson; do
  last=$(git log -1 --format="%as" -- "$f" 2>/dev/null)
  echo "surface:${last:-never}:$f"
done

echo "=== FOCUS VEHICLES ==="
# A focus red 4+ weeks running has survived two four-way choices unchanged —
# that is a decision not being made, not a habit not being done.
python3 automations/scripts/focus_status.py 2>/dev/null \
  | jq -r '.[] | select(.weeks_red >= 4) | "focus_stuck:\(.weeks_red):\(.title)"' \
  || echo "focus_stuck:unavailable"
```

### Orphaned labeled emails (Gmail connector only)

Every labeled inbox email is supposed to become a task — `pfc-email-triage` Step 0 reconciles both directions and the evening check-in runs it daily. An email carrying a priority label with no linked task means the pipeline has not run (or failed silently), and the user has decided something matters and then lost it.

**Skip this check entirely if the Gmail connector is not available** — no connector is a setup choice, not a health failure.

1. Search each tier, always with `in:inbox` (archived mail is out of scope):
   `in:inbox label:AA`, `in:inbox (label:AB OR label:BA)`, `in:inbox (label:AC OR label:BB OR label:CA)`, `in:inbox (label:BC OR label:CB)`, `in:inbox label:CC`. Collect the thread ids.
2. Collect thread ids already linked to a task, live plus archive:
   ```bash
   jq -r 'select((.source_email_thread_id // null) != null) | .source_email_thread_id' \
     6-tasks/_data/tasks.ndjson 6-tasks/_data/tasks-archive.ndjson | sort -u
   ```
3. Report labeled thread ids present in step 1 and absent from step 2 as `orphaned_labeled_emails:<count>`.

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
| Health data freshness | `day_track_last` ≤ 3d ago | 4–7d ago | > 7d ago or never (health fetch has stalled) |
| Phantom task dates | 0 tasks | 1–3 tasks | > 3 tasks |
| Task volume | < 150 lines | 150–199 lines | ≥ 200 lines |
| Overdue tasks | 0 tasks | 1–2 tasks | 3+ tasks |
| Agent-doable backlog | `agent_doable_yes_oldest_days` ≤ 30 | oldest 31–60 days | oldest > 60 days, OR `agent_doable_yes_open` ≥ 10 with oldest > 30 (nobody has to do these; the hand-off route has gone unused, so batch them) |
| Task classification coverage | `agent_doable_unset` = 0 | 1–5 unset | > 5 unset (capture is skipping the field; see `pfc-add-task`) |
| Clone sync | `clone_sync` line has no `[ahead`/`behind` marker | `[behind N]` only (run `git pull --rebase`) | `[ahead N]` or `[ahead N, behind M]` (commits stranded on this clone: `git pull --rebase && git push`) |
| Revive watchlist freshness | exit 0, 0 items ("Nothing slipping right now.") | exit 0, 1–5 items ("Some slippage — walk via `/pfc-revive` when convenient.") | exit non-zero (real bug — surface stderr), OR exit 0 with ≥ 6 items ("Heavy slippage — triage thresholds may need adjustment, or batch through `/pfc-revive` now.") |
| Evening check-in freshness | `evening_checkin_last` ≤ 2d ago | 3–5d ago | > 5d ago or never (the daily spine has lapsed — and with it the review drip) |
| Rating gaps, trailing 14d | `rating_gaps_14d_count` = 0 | 1–2 days unrated | 3+ days unrated (each is a day that is hard to reconstruct later; `scripts/hook-missing-checkin.sh` flags them at session start) |
| Area check-in freshness | `area_checkins_fresh` ≥ 75% of `area_checkins_asked` (or `no-items`) | 40–74% | < 40% (most area lights rest on answers over a month old, or none: run the `life-wheel` review in `/pfc-review`) |
| Rolling-review backlog | `review_ledger_due_count` ≤ 5 | 6+ due, OR `review_ledger_weekly_max_overdue` > 14 | `review_ledger_quarterly_max_cadences_late` ≥ 2 (a quarterly item is two full cadences past due — the re-pick was skipped, not delayed) |
| Rolling-review first run | `review_ledger_never_run` = 0 | — | — (see the fresh-clone note below; never a FAIL on its own) |
| Yearly checkin note | note exists for last year, OR not yet Feb 15 of current year | note missing and current date ≥ Feb 15 | — |
| Habit logging blackout | `habit_blackout_longest_run` ≤ 1 | run of 2–4 days with no habit records at all | run of 5+ days (the logging loop stopped; per-habit rates in this window are meaningless) |
| Current Focus — pursuit count | `focus_pursuits` ≤ `focus_pursuit_cap` | — | over cap (the scarcity cap is the point of the layer) |
| Current Focus — landings | `focus_missing_landing` = 0 | ≥ 1 pursuit with no landing (no when/where trigger, so it never starts) | — |
| Current Focus — quarter freshness | every active record's `quarter` == current | any record 1 quarter behind | any record ≥ 2 quarters behind (re-pick overdue) |
| Front of Mind — freshness | `grounding_newest_created` ≤ 60d ago | every active anchor older than 60d (the set has stopped cycling and reads as wallpaper) | — |
| Front of Mind — volume | `grounding_active` ≤ `grounding_soft_cap` | over the soft cap (curate by retiring; the renderer warns but never truncates) | — |
| Superman Pulse renderable | `pulse_renderable:yes` | `pulse_renderable:no` (the pulse board and TRMNL screen render empty, silently) | `pulse_renderable:error` (the builder itself is broken — surface the message) |
| Orphaned labeled emails | 0, or Gmail connector unavailable (skip) | 1–4 labeled inbox emails with no linked task | 5+ (the email→task pipeline is not running) |
| TRMNL endpoint | `trmnl:not_configured` (skip), or `trmnl_endpoint:ok` | `trmnl_repo_sync_timer:not-found` while the endpoint is up (live endpoint, stale clone) | `trmnl_endpoint:unreachable` while `TRMNL_SERVE_TOKEN` is set (every screen is frozen) |
| reMarkable pages freshness | `remarkable:not_configured` (skip), or every page uploaded ≤ 26h ago | a page uploaded 26–72h ago | a page uploaded > 72h ago, or `never` (the timer or the rmapi sign-in broke; the tablet shows stale pages) |
| AI News freshness | `ainews:not_configured` (skip), or `last_decided` ≤ 3d ago | 4–13d ago | ≥ 14d ago (a source broke or the timer stopped). Always print the `ainews:skipped:` lines under the table so the user can spot a wrong skip |
| Health tokens | present | — | missing |
| Active insights | — | > 20 unreviewed for 30+ days | — (no hard cap) |
| Insight freshness | last created ≤ 14d ago, or zero ever | 14–30d ago | > 30d ago (likely capture has stalled) |
| Active hypotheses | — | 1–3 active | > 3 active |
| Hypothesis touch (each) | last_reviewed ≤ 30d ago | last_reviewed 30–60d ago, OR null (never reviewed) | last_reviewed > 60d ago |
| Active supplements count | ≥ 1 | — | 0 (registry empty likely means drift if user normally takes supplements) |
| Active vision linked indicators | ≥ 1 linked project, habit, OR Current Focus item | — | 0 linked (vision drifting — no leading indicators) |
| Trello inbox cards | informational only | — | — (never fails; see "Trello inbox" reporting note below) |
| Trello dashboard freshness | last render ≤ 24h ago, or never | last render > 24h ago | — (never fails; informational) |

### Fresh clone vs. real backlog — read the ledger before you alarm

`data/review-ledger.ndjson` ships with `last_done` seeded to **2000-01-01**, the sentinel for "never run." So a brand-new clone reports every item due and `review_ledger_never_run` equal to the item count. That is the intended starting state, not a backlog.

Decide which story to tell from `review_ledger_never_run`:

- **All items never run** → this is a fresh (or freshly re-seeded) system. Report it once, informationally: "Rolling reviews: N items, none run yet — the ledger starts here. The evening check-in will drip up to 2 per night, or run `/pfc-review` to start on them one at a time now." No WARN, no FAIL.
- **Some items never run, others stamped** → the system is live and those specific items have simply never come up. Name them; WARN only if the due count also crosses the threshold above.
- **All items stamped, some overdue** → a genuine backlog. Apply the eval table normally.

Never render a fresh clone as a wall of red — it teaches the user to ignore this report.

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

### Surface use

For each `surface:` line, compute days since last write: 🟢 within 60 days · 🟡 60–120 · 🔴 past 120 or `never`.

Report as its own table — `Surface | Last written | Verdict` — and say **"possibly unused"**, never "unused". The repo keeps no invocation log; last-write is a proxy and must be labeled as one. A file can be correctly quiet: `findings.ndjson` gets a few entries a year by design, and `grounding.ndjson` changes only when the anchors change. The output is a prompt to look, not a verdict.

### Focus stuck red

For each `focus_stuck:` line: 🔴. A focus whose primary vehicle has been red 4+ weeks has already passed through two `focus-accuracy` reviews without a four-way choice being made. Name it and point at `/pfc-focus`. `focus_stuck:unavailable` is 🟡, not a failure — it means `focus_status.py` could not run.

## Step 3 — Output table

The feature scorecard (Step 0) comes first. Then this table, sorted: FAIL rows first, then WARN, then OK.

```
| Status   | Category    | Check                  | Detail                        | Action                              |
|----------|-------------|------------------------|-------------------------------|-------------------------------------|
| 🔴 FAIL  | Cadences    | Evening check-in       | Last 6 days ago               | Run /pfc-evening-checkin            |
| 🟡 WARN  | Focus       | Pursuit landings       | 2 pursuits have no landing    | Run /pfc-focus                      |
| 🟡 WARN  | Habits      | <bedtime-habit>        | 0 completions this week       | Log manually with /pfc-log-habit    |
| 🟢 OK    | Foundation  | Values                 | 11 values defined             | —                                   |
```

Always prepend the status with the matching circle emoji: 🔴 FAIL, 🟡 WARN, 🟢 OK.

---

## Step 4 — Summary line

```
Usage Audit: X OK  |  Y WARN  |  Z FAIL
```

---

## Step 5 — Action list

If any WARN or FAIL items exist, output a prioritized numbered list.

Sort order: FAIL items first (by ease of fix — quick wins before time-intensive), then WARN items.

Format each item with the matching circle emoji:
```
1. [🔴 FAIL] Evening check-in — run /pfc-evening-checkin (last: 6 days ago)
2. [🔴 FAIL] Phantom task dates — 10 open tasks have a completed date set; ask Claude to clean them
3. [🟡 WARN] Habit logging blackout — 3 straight days with no habit records; per-habit rates for that window mean nothing
4. [🟡 WARN] Habit not logged — "<bedtime-habit>" has 0 completions this week
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
| Too many active projects | Archive one project or move it to on-deck |
| Stale active project (0%, old) | Ask: progress it, park it, or cut it? |
| No daily habits defined | Add to config/habit_schema.yaml |
| Daily habit logging gap (no entries N+ days) | Run /pfc-evening-checkin or /pfc-log-habit. **Do NOT backfill `completed:false` for the silent days** — absence is not a miss. |
| Habit logging blackout (5+ straight days, no records) | Restart the loop before touching any habit: run /pfc-evening-checkin tonight. Say plainly that the per-habit rates covering the blackout are not real failures — nothing was logged, so "unlogged = missed" has nothing to measure. Do not propose cutting or rescoping habits off blackout-window data. |
| Daily habit logged but 0 completions | Run /pfc-pick-tasks, or review the habit's fit via the `habit-rate` rolling review — the habit may have stalled or no longer fit; review fit, not the user. |
| Daily habit duplicates | Ask Claude to dedupe 7-habits/_data/habits-daily.ndjson by (habit_id, date) |
| No monthly habits defined | Add to config/habit_schema.yaml under `monthly_habits:` or accept empty |
| Monthly habit logging gap | Run /pfc-log-habit when one happens this month |
| Monthly habit logged but 0 completions | Review via the `monthly-habits` rolling review (`/pfc-review`) — habit may need to be cut or rescoped |
| Day tracker gaps | Run /pfc-log-day for each missing date |
| Health fetch not writing | Run `python3 automations/scripts/auto_fetch_health.py` to test; check tokens |
| Phantom task dates | Ask Claude to strip completed field from open tasks |
| Task volume near threshold | Ask Claude to archive completed tasks |
| Overdue tasks | Review each: complete, reschedule, or delete |
| Revive watchlist — 1–5 items slipping | Run `/pfc-revive` when convenient to walk the watchlist and triage each item |
| Revive watchlist — ≥ 6 items slipping | Batch through `/pfc-revive` now, or revisit the signal thresholds in `automations/scripts/revive_watchlist.py` if the volume looks systemic rather than real slippage |
| Revive watchlist — helper errored | Capture stderr and investigate `automations/scripts/revive_watchlist.py` — real bug, not a data issue |
| Evening check-in lapsed (> 5d) | Run /pfc-evening-checkin — the daily spine drives the review drip; when it lapses, nothing surfaces and the ledger backs up |
| Rolling-review backlog (6+ due, or a weekly item > 14d overdue) | Run /pfc-review and keep saying "next" to work the backlog one review at a time, instead of waiting for 2-per-night to catch up |
| Rolling-review quarterly item ≥ 2 cadences late | Run /pfc-review — a quarterly item this late means a whole season's re-pick was skipped, not delayed (`focus-repick`, `vision-brainstorm`, `strengths-refresh`) |
| Yearly checkin note missing (past Feb 15) | Run /pfc-yearly-checkin — note should exist for last year by Feb 15 of the new year |
| Health tokens missing | Run `python3 automations/scripts/google_health_auth.py` |
| Active hypotheses > 3 | Review `data/hypotheses.ndjson` via the `hypotheses-review` rolling review (`/pfc-review`); resolve stale ones (graduate, reject, or archive) |
| Hypothesis last_reviewed > 60d ago | Run /pfc-review and take the `hypotheses-review` item — set fresh confidence, add any new evidence, or move to resolved-rejected/archived |
| Hypothesis last_reviewed null or 30–60d ago | It will come up on the next `hypotheses-review` drip — no urgency, but the belief is going un-stated |
| Current Focus over the pursuit cap | Run /pfc-focus — retire or pause a pursuit. The cap is scarcity by design; going over means everything gets a slice of nothing |
| Current Focus pursuit with no landing | Run /pfc-focus and give it a landing — a when/where/trigger anchored to an already-running state. A pursuit with no landing never starts (there is no trigger to bend the next action out of) |
| Current Focus quarter ≥ 2 behind | Run /pfc-focus for the quarterly re-pick — the list is describing a season that ended |
| Front of Mind all anchors > 60d old | Run /pfc-render-trello after curating `data/grounding.ndjson` — retire what is no longer front-of-mind and add what is. A set that never cycles goes invisible |
| Front of Mind over soft cap | Curate by retiring (`status: retired` + `retired_date`), never by truncating — the renderer shows everything and only warns |
| Superman Pulse renders empty | No recent day-tracking record carries a `health` block. Check the health fetch (`python3 automations/scripts/google_health_fetch.py`) and its timer; until one lands, the Trello pulse list and the pfc-pulse screen are blank with no error shown anywhere |
| Orphaned labeled emails | Run /pfc-email-triage — Step 0 reconciles both directions and creates the missing tasks. Recurring orphans mean the evening check-in's Step 0c is not running |
| TRMNL endpoint unreachable | `systemctl --user status pfc-trmnl-serve.service`, then `journalctl --user -u pfc-trmnl-serve -n 30`. Every screen is frozen on its last payload until it comes back |
| reMarkable pages stale | `journalctl --user -u pfc-remarkable-sync -n 50`. "rmapi ls failed" means the sign-in expired: redo `docs/remarkable.md` § Setup step 2 |
| AI News silent | `journalctl --user -u pfc-ai-news -n 50`; a `SOURCE ERROR` line names the blog whose page or feed changed (fix its entry in `config/ai_news.yaml`). Wrong skips: tighten `criteria` in the same file |
| TRMNL repo-sync timer not found | `systemctl --user list-timers pfc-repo-sync.timer`. The endpoint builds payloads from the local clone, so a missing sync timer means live screens rendering stale repo state |
| Insight capture stalled | Run `/pfc-insights` to review; capture is bottlenecked — nothing's been noticed lately, or capture habit has lapsed |
| Many old active insights | Run `/pfc-insights` to triage — archive what's gone stale, graduate what's actionable |
| Active supplements = 0 | Registry has drifted from reality; run /pfc-supplement and add current items |
| Active vision with 0 linked indicators | Either retire the vision (set `status: paused` or `abandoned` in the vision file) or add a project/habit with `vision: <slug>` so the vision has a leading indicator |
| Trello inbox cards waiting | Run `/pfc-trello-inbox` to walk the cards and route each one |

## Parked tasks (`deferred: true`)

A parked task is **not** a health problem — the user set it down on purpose, and the whole point of the field is that the system stops nudging. Never count parked tasks as stale, slipping, or overdue, and never include them in "tasks needing attention".

The one exception worth a single line: a task parked **more than 90 days** is worth surfacing once, not as a failure but as a "still want this on the books?" question. Report it, take the answer, and don't raise it again that cycle.

```bash
CUT=$(TZ="${LOCAL_TZ:-America/Denver}" date -d '90 days ago' '+%Y-%m-%d')
jq -c --arg c "$CUT" \
  'select(.status == "open" and .deferred == true and .created < $c) | {id, description, deferred_reason}' \
  6-tasks/_data/tasks.ndjson
```
