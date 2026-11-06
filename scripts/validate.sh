#!/usr/bin/env bash
# Repo validator — catches silent data/schema drift.
#
# Checks:
#   1. Every data/*.ndjson parses cleanly (catches raw echo/sed corruption)
#   2. Every .claude/skills/*/SKILL.md has valid frontmatter with name+description
#   3. tasks.ndjson conforms to config/task_schema.yaml (required fields, enums, id format)
#   4. Habit logs: habits-daily.ndjson uses declared habit_ids (active or deprecated),
#      and both habits-daily.ndjson and habits-monthly.ndjson hold one row per habit
#      per date (a duplicate row would count a habit twice in every rate)
#   5. projects.ndjson has required fields and id format
#   6. Cross-file integrity:
#      - daily-focus critical/bonus/skipped task ids exist in tasks.ndjson or tasks-archive.ndjson
#      - daily-focus uses the canonical string-array schema (no legacy object shape)
#      - project.area values exist as lowercase folders in 2-areas/
#      - habit_schema.yaml habit.area values exist as folders in 2-areas/
#      - daily habit count ≤ 14 (config/habit_schema.yaml cap)
#  12. config/onboarding.ndjson schema (feature pattern, status enum, date format)
#
# Usage: scripts/validate.sh
# Exit 0 on success, 1 on any failure. Safe to run as a pre-commit hook.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FAIL=0
fail() { echo "  ✗ $*" >&2; FAIL=1; }
ok()   { echo "  ✓ $*"; }

# ── 1. NDJSON parse ───────────────────────────────────────────────────────────
echo "[1/16] NDJSON parse validation"
for f in data/*.ndjson 3-visions/_data/*.ndjson 4-focus/_data/*.ndjson 5-projects/_data/*.ndjson 6-tasks/_data/*.ndjson 7-habits/_data/*.ndjson; do
  [ -s "$f" ] || { ok "$(basename "$f") (empty)"; continue; }
  if ! jq -e . "$f" >/dev/null 2>&1; then
    fail "$f — malformed JSON (run: jq . $f to see where)"
  else
    ok "$(basename "$f") ($(wc -l <"$f" | tr -d ' ') records)"
  fi
done

# ── 2. Skill frontmatter ──────────────────────────────────────────────────────
echo "[2/16] Skill frontmatter lint"
for dir in .agents/skills/*/; do
  skill_name=$(basename "$dir")
  f="${dir}SKILL.md"
  [ -f "$f" ] || { fail "$skill_name — missing SKILL.md"; continue; }

  first_line=$(head -1 "$f")
  if [ "$first_line" != "---" ]; then
    fail "$skill_name — SKILL.md must start with '---' frontmatter"
    continue
  fi

  name=$(awk '/^---$/{c++; next} c==1 && /^name:/{sub(/^name:[ ]*/,""); print; exit}' "$f")
  desc=$(awk '/^---$/{c++; next} c==1 && /^description:/{sub(/^description:[ ]*/,""); print; exit}' "$f")

  [ -n "$name" ] || fail "$skill_name — frontmatter missing 'name:'"
  [ -n "$desc" ] || fail "$skill_name — frontmatter missing 'description:'"

  if [ -n "$name" ] && [ "$name" != "$skill_name" ]; then
    fail "$skill_name — frontmatter name '$name' doesn't match directory"
  fi

  [ -n "$name" ] && [ -n "$desc" ] && [ "$name" = "$skill_name" ] && ok "$skill_name"
done

# ── 3. tasks.ndjson schema ────────────────────────────────────────────────────
echo "[3/16] tasks.ndjson schema"
TASKS=6-tasks/_data/tasks.ndjson
if [ -s "$TASKS" ]; then
  bad=$(jq -c '
    select(
      (.id // "" | test("^task-[0-9]{8}-[0-9]{3}$") | not) or
      ([.status] | inside(["open","done"]) | not) or
      ((.description // "") == "") or
      ([.size] | inside(["XS","S","M","L","XL"]) | not) or
      ([.location] | inside(["Home","PC","Errand","Phone","Anywhere"]) | not) or
      ([.impact] | inside(["high","medium","low"]) | not) or
      ([.urgency] | inside(["high","medium","low"]) | not) or
      ((.project // null) == null) or
      ((.created // "") == "") or
      ((.agent_doable // null) != null and
        ([.agent_doable] | inside(["yes","partly","no"]) | not)) or
      ((.depends_on // null) != null and (
        (.depends_on | type) != "array" or
        ([.depends_on[]? | test("^task-[0-9]{8}-[0-9]{3}$") | not] | any)
      ))
    ) | .id
  ' "$TASKS")
  if [ -n "$bad" ]; then
    while IFS= read -r id; do
      fail "tasks.ndjson — record $id violates schema"
    done <<< "$bad"
  else
    ok "tasks.ndjson ($(wc -l <"$TASKS" | tr -d ' ') records conform)"
  fi
fi

# ── 4. habit logs: declared ids, and one row per habit per date ───────────────
echo "[4/16] habit logs (declared habit_ids, no duplicate rows)"
HABITS=7-habits/_data/habits-daily.ndjson
SCHEMA=config/habit_schema.yaml
if [ -s "$HABITS" ] && [ -f "$SCHEMA" ]; then
  # Extract declared habit ids (active + deprecated) from YAML without extra deps
  declared=$(awk '
    /^daily_habits:/     {block="d"; next}
    /^monthly_habits:/   {block="m"; next}
    /^deprecated_habits:/{block="x"; next}
    /^[a-zA-Z_]/         {block=""}
    block && /^  - id:/  {sub(/^.*id:[ ]*/,""); print}
  ' "$SCHEMA" | tr -d '"' | sort -u)

  bad=$(jq -r '.habit_id // empty' "$HABITS" | sort -u | while read -r hid; do
    if ! grep -qxF "$hid" <<<"$declared"; then
      echo "$hid"
    fi
  done)

  if [ -n "$bad" ]; then
    while IFS= read -r hid; do
      fail "habits-daily.ndjson — undeclared habit_id: $hid (add to habit_schema.yaml)"
    done <<< "$bad"
  else
    ok "habits-daily.ndjson ($(wc -l <"$HABITS" | tr -d ' ') records, all habit_ids declared)"
  fi
fi

# Two rows for the same habit on the same date make the surfaces disagree: the run in
# web_data.py keeps the last row for a date, while focus_status.habit_rate counts every
# completed row, so a duplicate raises the rate without lengthening the run.
for f in 7-habits/_data/habits-daily.ndjson 7-habits/_data/habits-monthly.ndjson; do
  [ -s "$f" ] || continue
  dupes=$(jq -r '[.habit_id, .date] | @tsv' "$f" | sort | uniq -d)
  if [ -n "$dupes" ]; then
    while IFS=$'\t' read -r hid hdate; do
      fail "$(basename "$f") — two rows for $hid on $hdate (keep one; the rate and the run read duplicates differently)"
    done <<< "$dupes"
  else
    ok "$(basename "$f") (one row per habit per date)"
  fi
done

# ── 5. projects.ndjson schema ─────────────────────────────────────────────────
echo "[5/16] projects.ndjson schema"
PROJECTS=5-projects/_data/projects.ndjson
if [ -s "$PROJECTS" ]; then
  bad=$(jq -c '
    select(
      (.id // "" | test("^proj-[0-9]{8}-[0-9]{3}$") | not) or
      ((.name // "") == "") or
      (.active == null) or
      ((.area // "") == "") or
      (.total_parts == null) or
      (.completed_parts == null) or
      ((.created // "") == "")
    ) | .id
  ' "$PROJECTS")
  if [ -n "$bad" ]; then
    while IFS= read -r id; do
      fail "projects.ndjson — record $id violates schema"
    done <<< "$bad"
  else
    ok "projects.ndjson ($(wc -l <"$PROJECTS" | tr -d ' ') records conform)"
  fi

  # Active-project runaway backstop. Deliberately high: a project is just a
  # group of tasks that belong together, and several can sit open while only a
  # few get worked at a time. The scarcity layer is 4-focus/, not this file.
  active=$(jq -c 'select(.active == true)' "$PROJECTS" | wc -l | tr -d ' ')
  if [ "$active" -gt 12 ]; then
    fail "projects.ndjson — $active active projects (backstop is 12; prune or pause some)"
  else
    ok "projects.ndjson — $active active projects (≤12)"
  fi
fi

# ── 6. Cross-file integrity ──────────────────────────────────────────────────
echo "[6/16] Cross-file integrity"

FOCUS=6-tasks/_data/daily-focus.ndjson
ARCHIVE=6-tasks/_data/tasks-archive.ndjson

# 6a. daily-focus schema: critical is string-array, bonus is string or null,
#     skipped is an optional string-array, calendar_events is an optional object of
#     {task_id: {event_id, start, end}}.
if [ -s "$FOCUS" ]; then
  bad_shape=$(jq -c '
    select(
      (.critical | type != "array") or
      ([.critical[]? | type] | unique | . != [] and . != ["string"]) or
      ((.bonus // null) != null and (.bonus | type) != "string") or
      ((.skipped // null) != null and (
        (.skipped | type) != "array" or
        ([.skipped[] | type] | unique | . != [] and . != ["string"])
      )) or
      ((.calendar_events // null) != null and (
        (.calendar_events | type) != "object" or
        ([.calendar_events | to_entries[] | .value
          | (.event_id // "") == "" or (.start // "") == "" or (.end // "") == ""
         ] | any)
      ))
    ) | .date
  ' "$FOCUS")
  if [ -n "$bad_shape" ]; then
    while IFS= read -r d; do
      fail "daily-focus.ndjson — record dated $d has non-canonical shape (critical must be string[], bonus string or null, skipped string[] or absent, calendar_events object or absent)"
    done <<< "$bad_shape"
  else
    ok "daily-focus.ndjson — all records use canonical string schema"
  fi

  # 6b. daily-focus task_ids must resolve to a task in live or archive
  jq -r '.id' 6-tasks/_data/tasks.ndjson "$ARCHIVE" 2>/dev/null | sort -u > /tmp/.validate-task-ids
  dangling=$(jq -r '(.critical[]?), (.bonus // empty), (.skipped[]?)' "$FOCUS" \
             | sort -u \
             | while read -r tid; do
                 [ -z "$tid" ] && continue
                 grep -qxF "$tid" /tmp/.validate-task-ids || echo "$tid"
               done)
  rm -f /tmp/.validate-task-ids
  if [ -n "$dangling" ]; then
    while IFS= read -r tid; do
      fail "daily-focus.ndjson — references unknown task id: $tid"
    done <<< "$dangling"
  else
    ok "daily-focus.ndjson — all referenced task ids resolve"
  fi
fi

# 6c. project.area values must match a 2-areas/ folder (lowercase)
if [ -s "$PROJECTS" ] && [ -d "2-areas" ]; then
  bad_area=$(jq -r '.area' "$PROJECTS" | sort -u | while read -r a; do
    [ -z "$a" ] && continue
    [ -d "2-areas/$a" ] || echo "$a"
  done)
  if [ -n "$bad_area" ]; then
    while IFS= read -r a; do
      fail "projects.ndjson — project.area '$a' has no matching folder in 2-areas/ (areas must be lowercase folder names)"
    done <<< "$bad_area"
  else
    ok "projects.ndjson — all project.area values match 2-areas/ folders"
  fi
fi

# 6d. habit.area values in habit_schema.yaml must match 2-areas/ folder
if [ -f "$SCHEMA" ] && [ -d "2-areas" ]; then
  habit_areas=$(awk '
    /^daily_habits:/     {block="d"; next}
    /^monthly_habits:/   {block="m"; next}
    /^[a-zA-Z_]/         {block=""}
    block && /^    area:/ {sub(/^.*area:[ ]*/,""); print}
  ' "$SCHEMA" | tr -d '"' | sort -u)
  bad_habit_area=""
  while IFS= read -r a; do
    [ -z "$a" ] && continue
    [ -d "2-areas/$a" ] || bad_habit_area+="$a"$'\n'
  done <<< "$habit_areas"
  bad_habit_area=$(printf '%s' "$bad_habit_area" | sed '/^$/d')
  if [ -n "$bad_habit_area" ]; then
    while IFS= read -r a; do
      fail "habit_schema.yaml — habit.area '$a' has no matching folder in 2-areas/"
    done <<< "$bad_habit_area"
  else
    ok "habit_schema.yaml — all habit.area values match 2-areas/ folders"
  fi
fi

# 6e. daily habit count ≤ 14 (config/habit_schema.yaml cap)
if [ -f "$SCHEMA" ]; then
  daily_count=$(awk '
    /^daily_habits:/     {block="d"; next}
    /^monthly_habits:/   {block="m"; next}
    /^deprecated_habits:/{block="x"; next}
    /^[a-zA-Z_]/         {block=""}
    block=="d" && /^  - id:/ {c++}
    END {print c+0}
  ' "$SCHEMA")
  if [ "$daily_count" -gt 14 ]; then
    fail "habit_schema.yaml — $daily_count active daily habits (max 14)"
  else
    ok "habit_schema.yaml — $daily_count active daily habits (≤14)"
  fi
fi

# 6f. task.area (when set) must match a 2-areas/ folder
if [ -s "$TASKS" ] && [ -d "2-areas" ]; then
  bad_task_area=$(jq -r 'select((.area // null) != null) | .area' "$TASKS" | sort -u | while read -r a; do
    [ -z "$a" ] && continue
    [ -d "2-areas/$a" ] || echo "$a"
  done)
  if [ -n "$bad_task_area" ]; then
    while IFS= read -r a; do
      fail "tasks.ndjson — task.area '$a' has no matching folder in 2-areas/"
    done <<< "$bad_task_area"
  else
    ok "tasks.ndjson — all task.area values match 2-areas/ folders"
  fi
fi

# 6g. task depends_on references must resolve to a known task id; no self-reference
if [ -s "$TASKS" ]; then
  jq -r '.id' "$TASKS" "$ARCHIVE" 2>/dev/null | sort -u > /tmp/.validate-all-task-ids

  self_ref=$(jq -r 'select(.id as $sid | (.depends_on // []) | any(. == $sid)) | .id' "$TASKS")
  if [ -n "$self_ref" ]; then
    while IFS= read -r id; do
      fail "tasks.ndjson — $id has depends_on referencing itself"
    done <<< "$self_ref"
  fi

  dangling_deps=$(jq -r '
    select((.depends_on // []) | length > 0)
    | .id as $sid | .depends_on[]
    | "\($sid)|\(.)"
  ' "$TASKS" | while IFS='|' read -r sid dep; do
    grep -qxF "$dep" /tmp/.validate-all-task-ids || echo "$sid references unknown $dep"
  done)
  rm -f /tmp/.validate-all-task-ids

  if [ -n "$dangling_deps" ]; then
    while IFS= read -r line; do
      fail "tasks.ndjson — depends_on: $line"
    done <<< "$dangling_deps"
  elif [ -z "$self_ref" ]; then
    ok "tasks.ndjson — all depends_on references resolve and none are self-referential"
  fi
fi

# 6h. active persona resolves to a section in config/personas.md
PERSONA_CFG=config/persona.yaml
PERSONA_REG=config/personas.md
if [ -f "$PERSONA_CFG" ] && [ -f "$PERSONA_REG" ]; then
  active_persona=$(grep -E '^active:' "$PERSONA_CFG" | head -1 | sed -E 's/^active:[[:space:]]*//; s/[[:space:]]*#.*//; s/^["'\'']//;s/["'\'']$//')
  if [ -z "$active_persona" ]; then
    fail "persona.yaml — missing 'active:' field"
  elif [ "$active_persona" = "none" ]; then
    ok "persona.yaml — active: none (persona disabled)"
  elif grep -qE "^## $active_persona$" "$PERSONA_REG"; then
    ok "persona.yaml — active persona '$active_persona' resolves to personas.md"
  else
    fail "persona.yaml — active persona '$active_persona' has no '## $active_persona' section in personas.md"
  fi
fi

# ── 7. findings.ndjson schema + cross-file ─────────────────────────────────────
echo "[7/16] findings.ndjson schema + cross-file"
FINDINGS=data/findings.ndjson
if [ -s "$FINDINGS" ]; then
  bad=$(jq -c '
    select(
      (.id // "" | test("^finding-[0-9]{8}-[0-9]{3}$") | not) or
      ([.status] | inside(["active","superseded"]) | not) or
      ((.finding // "") == "") or
      ((.domain // "") == "") or
      ([.source] | inside(["data","experience","hypothesis"]) | not) or
      ((.created // "") == "") or
      (.source == "hypothesis" and ((.source_hypothesis_id // "") == "")) or
      (.status == "superseded" and ((.superseded_by // "") == "")) or
      (.confidence != null and ([.confidence] | inside(["strong","very-strong"]) | not))
    ) | .id
  ' "$FINDINGS")
  if [ -n "$bad" ]; then
    while IFS= read -r id; do
      fail "findings.ndjson — record $id violates schema"
    done <<< "$bad"
  else
    ok "findings.ndjson ($(wc -l <"$FINDINGS" | tr -d ' ') records conform)"
  fi

  # 7a. source_hypothesis_id must resolve to a real hypothesis
  HYP=data/hypotheses.ndjson
  if [ -s "$HYP" ]; then
    jq -r '.id' "$HYP" | sort -u > /tmp/.validate-hyp-ids
    dangling_hyp=$(jq -r 'select(.source == "hypothesis") | .source_hypothesis_id' "$FINDINGS" \
                   | sort -u \
                   | while read -r hid; do
                       [ -z "$hid" ] && continue
                       grep -qxF "$hid" /tmp/.validate-hyp-ids || echo "$hid"
                     done)
    rm -f /tmp/.validate-hyp-ids
    if [ -n "$dangling_hyp" ]; then
      while IFS= read -r hid; do
        fail "findings.ndjson — source_hypothesis_id '$hid' not found in hypotheses.ndjson"
      done <<< "$dangling_hyp"
    else
      ok "findings.ndjson — all source_hypothesis_id values resolve"
    fi
  fi

  # 7b. superseded_by must resolve to another finding
  jq -r '.id' "$FINDINGS" | sort -u > /tmp/.validate-finding-ids
  dangling_sup=$(jq -r 'select(.status == "superseded") | .superseded_by' "$FINDINGS" \
                 | sort -u \
                 | while read -r fid; do
                     [ -z "$fid" ] && continue
                     grep -qxF "$fid" /tmp/.validate-finding-ids || echo "$fid"
                   done)
  rm -f /tmp/.validate-finding-ids
  if [ -n "$dangling_sup" ]; then
    while IFS= read -r fid; do
      fail "findings.ndjson — superseded_by '$fid' not found in findings.ndjson"
    done <<< "$dangling_sup"
  else
    ok "findings.ndjson — all superseded_by values resolve"
  fi
else
  ok "findings.ndjson (empty)"
fi

# ── 8. supplements.ndjson schema ──────────────────────────────────────────────
echo "[8/16] supplements.ndjson schema"
SUPP=data/supplements.ndjson
if [ -s "$SUPP" ]; then
  bad=$(jq -c '
    select(
      (.id // "" | test("^supp-[0-9]{8}-[0-9]{3}$") | not) or
      ((.name // "") == "") or
      ([.type] | inside(["supplement","medication"]) | not) or
      ((.dose // "") == "") or
      (.times | type != "array") or
      ((.times // []) | length == 0) or
      ((.times // []) - ["morning","afternoon","evening","bedtime","with meals"] | length > 0) or
      ((.food_requirement // null) != null and ([.food_requirement] | inside(["empty_stomach","with_food","with_fat","either"]) | not)) or
      ([.status] | inside(["active","stopped"]) | not) or
      ((.started // "") == "") or
      (.status == "active"  and (.stopped // null) != null) or
      (.status == "stopped" and ((.stopped // "") == "")) or
      ((.stopped // null) != null and .stopped < .started)
    ) | .id // "(no id)"
  ' "$SUPP")
  if [ -n "$bad" ]; then
    while IFS= read -r id; do
      fail "supplements.ndjson — record $id violates schema"
    done <<< "$bad"
  else
    ok "supplements.ndjson ($(wc -l <"$SUPP" | tr -d ' ') records conform)"
  fi
else
  ok "supplements.ndjson (empty)"
fi

# ── 9. insights.ndjson schema ─────────────────────────────────────────────────
echo "[9/16] insights.ndjson schema"
INSIGHTS=data/insights.ndjson
if [ -s "$INSIGHTS" ]; then
  bad=$(jq -c '
    select(
      (.id // "" | test("^insight-[0-9]{8}-[0-9]{3}$") | not) or
      ([.status] | inside(["active","archived","graduated"]) | not) or
      ((.insight // "") == "") or
      ([.source] | inside(["chat","evening-checkin","morning","weekly-review","journal","experience"]) | not) or
      ((.created // "") == "") or
      (.status == "graduated" and ((.graduated_to // "") == "")) or
      (.status == "graduated" and ((.graduated_date // "") == ""))
    ) | .id // "(no id)"
  ' "$INSIGHTS")
  if [ -n "$bad" ]; then
    while IFS= read -r id; do
      fail "insights.ndjson — record $id violates schema"
    done <<< "$bad"
  else
    ok "insights.ndjson ($(wc -l <"$INSIGHTS" | tr -d ' ') records conform)"
  fi

  # 9a. insight.area, when set, must match a 2-areas/ folder
  if [ -d "2-areas" ]; then
    bad_area=$(jq -r 'select(.area != null) | .area' "$INSIGHTS" | sort -u | while read -r a; do
      [ -z "$a" ] && continue
      [ -d "2-areas/$a" ] || echo "$a"
    done)
    if [ -n "$bad_area" ]; then
      while IFS= read -r a; do
        fail "insights.ndjson — insight.area '$a' has no matching folder in 2-areas/"
      done <<< "$bad_area"
    else
      ok "insights.ndjson — all insight.area values resolve to 2-areas/ folders"
    fi
  fi
else
  ok "insights.ndjson (empty)"
fi

# ── 10. Future-dated date-stamped fields (UTC vs local slip detection) ───────
echo "[10/16] No future-dated records (catches UTC vs local-tz date slips)"
LOCAL_TZ="${LOCAL_TZ:-America/Denver}"
TODAY_MT=$(TZ="$LOCAL_TZ" date '+%Y-%m-%d')
# daily-focus may be pre-staged one day ahead (night-before 2+1), so it gets a +1 ceiling.
# GNU date wants `-d tomorrow`, BSD date (macOS) wants `-v+1d`. On macOS the GNU form
# exits non-zero and TOMORROW_MT lands empty, which fails every daily-focus record.
TOMORROW_MT=$(TZ="$LOCAL_TZ" date -d 'tomorrow' '+%Y-%m-%d' 2>/dev/null \
  || TZ="$LOCAL_TZ" date -v+1d '+%Y-%m-%d')

# tasks.ndjson — created, completed, deadline must not be > today_MT
# (deadline can legitimately be future, so skip it; created/completed cannot)
if [ -s 6-tasks/_data/tasks.ndjson ]; then
  future=$(jq -r --arg t "$TODAY_MT" \
    'select((.created // "") > $t or (.completed // "" | tostring) > $t) | "\(.id) created=\(.created // "null") completed=\(.completed // "null")"' \
    6-tasks/_data/tasks.ndjson)
  if [ -n "$future" ]; then
    while IFS= read -r line; do
      fail "tasks.ndjson — future-dated record: $line (today is $TODAY_MT MT — likely UTC vs MT slip)"
    done <<< "$future"
  else
    ok "tasks.ndjson — no future-dated created/completed"
  fi
fi

# task_events.ndjson — timestamp must not be > today_MT
# Compare only the date portion (first 10 chars) so same-day timestamps don't
# falsely flag as "future" due to the T… suffix sorting after the bare date.
if [ -s 6-tasks/_data/task_events.ndjson ]; then
  future=$(jq -r --arg t "$TODAY_MT" \
    'select(((.timestamp // "")[0:10]) > $t) | "\(.task_id // "?") timestamp=\(.timestamp)"' \
    6-tasks/_data/task_events.ndjson)
  if [ -n "$future" ]; then
    while IFS= read -r line; do
      fail "task_events.ndjson — future-dated record: $line (today is $TODAY_MT MT)"
    done <<< "$future"
  else
    ok "task_events.ndjson — no future-dated timestamps"
  fi
fi

# daily-focus.ndjson — date must not be > tomorrow_MT.
# The 2+1 may be pre-staged one night ahead (set tomorrow's focus tonight), so the
# ceiling is today+1, not today. Anything beyond tomorrow is still a date slip / typo.
if [ -s 6-tasks/_data/daily-focus.ndjson ]; then
  future=$(jq -r --arg t "$TOMORROW_MT" 'select((.date // "") > $t) | .date' 6-tasks/_data/daily-focus.ndjson)
  if [ -n "$future" ]; then
    while IFS= read -r d; do
      fail "daily-focus.ndjson — future-dated record: $d (beyond tomorrow, $TOMORROW_MT MT; the 2+1 can be pre-staged at most one day ahead)"
    done <<< "$future"
  else
    ok "daily-focus.ndjson — no future-dated records"
  fi
fi

# day-tracking.ndjson — date must not be > today_MT
if [ -s data/day-tracking.ndjson ]; then
  future=$(jq -r --arg t "$TODAY_MT" 'select((.date // "") > $t) | .date' data/day-tracking.ndjson)
  if [ -n "$future" ]; then
    while IFS= read -r d; do
      fail "day-tracking.ndjson — future-dated record: $d (today is $TODAY_MT MT)"
    done <<< "$future"
  else
    ok "day-tracking.ndjson — no future-dated records"
  fi
fi

# habits-daily.ndjson — date must not be > today_MT
if [ -s 7-habits/_data/habits-daily.ndjson ]; then
  future=$(jq -r --arg t "$TODAY_MT" 'select((.date // "") > $t) | "\(.habit_id // "?") date=\(.date)"' 7-habits/_data/habits-daily.ndjson)
  if [ -n "$future" ]; then
    while IFS= read -r line; do
      fail "habits-daily.ndjson — future-dated record: $line (today is $TODAY_MT MT)"
    done <<< "$future"
  else
    ok "habits-daily.ndjson — no future-dated records"
  fi
fi

# insights.ndjson — created, graduated_date must not be > today_MT
if [ -s data/insights.ndjson ]; then
  future=$(jq -r --arg t "$TODAY_MT" \
    'select((.created // "") > $t or (.graduated_date // "" | tostring) > $t) | "\(.id) created=\(.created // "null") graduated_date=\(.graduated_date // "null")"' \
    data/insights.ndjson)
  if [ -n "$future" ]; then
    while IFS= read -r line; do
      fail "insights.ndjson — future-dated record: $line (today is $TODAY_MT MT)"
    done <<< "$future"
  else
    ok "insights.ndjson — no future-dated created/graduated_date"
  fi
fi

# supplements.ndjson — started must not be > today_MT
# stopped MAY be future-dated to schedule planned tapers/discontinuations
# (date-range semantics: stopped is exclusive, so stopped=tomorrow means
# today is the last active day).
if [ -s data/supplements.ndjson ]; then
  future=$(jq -r --arg t "$TODAY_MT" \
    'select((.started // "") > $t) | "\(.id) started=\(.started)"' \
    data/supplements.ndjson)
  if [ -n "$future" ]; then
    while IFS= read -r line; do
      fail "supplements.ndjson — future-dated record: $line (today is $TODAY_MT MT — likely UTC vs MT slip)"
    done <<< "$future"
  else
    ok "supplements.ndjson — no future-dated started"
  fi
fi

# hypotheses.ndjson — started, last_reviewed, updated must not be > today_MT
if [ -s data/hypotheses.ndjson ]; then
  future=$(jq -r --arg t "$TODAY_MT" \
    'select((.started // "") > $t or (.last_reviewed // "" | tostring) > $t or (.updated // "" | tostring) > $t) | "\(.id) started=\(.started // "null") last_reviewed=\(.last_reviewed // "null") updated=\(.updated // "null")"' \
    data/hypotheses.ndjson)
  if [ -n "$future" ]; then
    while IFS= read -r line; do
      fail "hypotheses.ndjson — future-dated record: $line (today is $TODAY_MT MT)"
    done <<< "$future"
  else
    ok "hypotheses.ndjson — no future-dated started/last_reviewed/updated"
  fi
fi

# ── 11. hypotheses.ndjson schema ──────────────────────────────────────────────
echo "[11/16] hypotheses.ndjson schema"
HYP=data/hypotheses.ndjson
if [ -s "$HYP" ]; then
  bad=$(jq -c '
    select(
      (.id // "" | test("^hyp-[0-9]{8}-[0-9]{3}$") | not) or
      ([.status] | inside(["active","resolved-graduated","resolved-rejected","archived"]) | not) or
      ((.hypothesis // "") == "") or
      ((.domain // "") == "") or
      ((.started // "") == "") or
      (.confidence != null and ((.confidence | type) != "number" or .confidence < 0 or .confidence > 1)) or
      (.last_reviewed != null and ((.last_reviewed | type) != "string" or (.last_reviewed | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$") | not)))
    ) | .id // "(no id)"
  ' "$HYP")
  if [ -n "$bad" ]; then
    while IFS= read -r id; do
      fail "hypotheses.ndjson — record $id violates schema"
    done <<< "$bad"
  else
    ok "hypotheses.ndjson ($(wc -l <"$HYP" | tr -d ' ') records conform)"
  fi
else
  ok "hypotheses.ndjson (empty)"
fi

# ── 12. config/onboarding.ndjson schema ───────────────────────────────────────
echo "[12/16] config/onboarding.ndjson schema"
ONBOARDING=config/onboarding.ndjson
if [ ! -f "$ONBOARDING" ]; then
  ok "onboarding.ndjson (not present — skipping)"
elif [ ! -s "$ONBOARDING" ]; then
  ok "onboarding.ndjson (empty)"
else
  bad=$(jq -c '
    select(
      (.feature // "" | test("^[a-z][a-z0-9-]+/[a-z][a-z0-9-]+$") | not) or
      ([.status] | inside(["introduced","tried","dismissed"]) | not) or
      (.date // "" | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$") | not)
    ) | (.feature // "(no feature)")
  ' "$ONBOARDING")
  if [ -n "$bad" ]; then
    while IFS= read -r feat; do
      fail "onboarding.ndjson — record '$feat' violates schema (feature must match ^[a-z][a-z0-9-]+/[a-z][a-z0-9-]+$, status one of introduced/tried/dismissed, date YYYY-MM-DD)"
    done <<< "$bad"
  else
    ok "onboarding.ndjson ($(wc -l <"$ONBOARDING" | tr -d ' ') records conform)"
  fi
fi

# ── 13. revive-events.ndjson schema + cross-ref ───────────────────────────────
echo "[13/16] revive-events.ndjson schema"
REVIVE=data/revive-events.ndjson
if [ ! -s "$REVIVE" ]; then
  ok "revive-events.ndjson (empty)"
else
  bad=$(jq -c '
    select(
      (.id // "" | test("^revive-[0-9]{8}-[0-9]{3}$") | not)
      or (.date // "" | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$") | not)
      or (.item_type // "" | IN("task","project") | not)
      or ((.item_id // "") == "")
      or (.signals // [] | type != "array" or any(IN("A","B","C","D","E","F") | not))
      or (.diagnostic // null | type != "array" or any(IN("A","B","C","D","E","F","G","H") | not))
      or (.intervention // [] | type != "array" or length == 0 or any(IN("break_down","pair_stack","reschedule","boost_visibility","external_start","adjacent_input","restore_state","lower_scope","pause_archive","walk_aversion","skip") | not))
    ) | .id // "(no id)"
  ' "$REVIVE")
  if [ -n "$bad" ]; then
    while IFS= read -r id; do
      fail "revive-events.ndjson — record $id violates schema"
    done <<< "$bad"
  else
    ok "revive-events.ndjson ($(wc -l <"$REVIVE" | tr -d ' ') records conform)"
  fi

  # Future-date guard
  future_rev=$(jq -r --arg t "$TODAY_MT" \
    'select(.date > $t or (.outcome_checked != null and .outcome_checked > $t)) | .id // "(no id)"' \
    "$REVIVE")
  if [ -n "$future_rev" ]; then
    while IFS= read -r id; do
      fail "revive-events.ndjson — record $id is future-dated"
    done <<< "$future_rev"
  else
    ok "revive-events.ndjson — no future-dated records"
  fi
fi

# ── 14. focus.ndjson schema + cross-refs ──────────────────────────────────────
echo "[14/16] focus.ndjson schema"
FOCUS_FILE=4-focus/_data/focus.ndjson
if [ ! -s "$FOCUS_FILE" ]; then
  ok "focus.ndjson (empty)"
else
  bad=$(jq -c '
    select(
      (.id // "" | test("^focus-[0-9]{8}-[0-9]{3}$") | not) or
      ([.tier] | inside(["foundation","pursuit","consuming"]) | not) or
      ((.area // "") == "") or
      ((.title // "") == "") or
      ([.status] | inside(["green","yellow","red"]) | not) or
      ((.quarter // "") == "") or
      ((.created // "") == "")
    ) | .id
  ' "$FOCUS_FILE")
  if [ -n "$bad" ]; then
    while IFS= read -r id; do fail "focus.ndjson — record $id violates schema"; done <<< "$bad"
  else
    ok "focus.ndjson ($(wc -l <"$FOCUS_FILE" | tr -d ' ') records conform)"
  fi

  # area cross-ref
  bad_area=$(jq -r '.area' "$FOCUS_FILE" | sort -u | while read -r a; do
    [ -d "2-areas/$a" ] || echo "$a"
  done)
  if [ -n "$bad_area" ]; then
    while IFS= read -r a; do fail "focus.ndjson — area '$a' has no 2-areas/ folder"; done <<< "$bad_area"
  else
    ok "focus.ndjson — all area values resolve"
  fi

  # Every active foundation/pursuit must declare at least one vehicle habit.
  # A focus with no vehicle is unmeasurable — see docs/habit-mechanics.md.
  no_vehicle=$(jq -r 'select(.retired_date==null and .tier!="consuming"
                             and ((.habits // []) | length) == 0) | .title' "$FOCUS_FILE")
  if [ -n "$no_vehicle" ]; then
    fail "focus.ndjson — focus with no vehicle habit: $(echo "$no_vehicle" | tr '\n' ',')"
  else
    ok "focus.ndjson — every active foundation/pursuit declares a vehicle habit"
  fi

  # Vehicle habit ids must resolve against config/habit_schema.yaml.
  declared_habits=$(awk '/^(daily|monthly)_habits:/{f=1;next} /^[a-z_]+:/{f=0} f && /^  - id:/{print $3}' \
    config/habit_schema.yaml | tr -d '"' | sort -u)
  unknown_vehicle=$(jq -r 'select(.retired_date==null) | .habits[]?' "$FOCUS_FILE" \
    | sort -u | comm -23 - <(echo "$declared_habits"))
  if [ -n "$unknown_vehicle" ]; then
    fail "focus.ndjson — vehicle habit not declared in habit_schema.yaml: $(echo "$unknown_vehicle" | tr '\n' ',')"
  else
    ok "focus.ndjson — all vehicle habit ids resolve"
  fi

  # impact / urgency enums
  bad_enum=$(jq -r 'select(.retired_date==null
                    and (((.impact // "") | IN("high","medium","low")) and
                         ((.urgency // "") | IN("high","medium","low")) | not)) | .title' "$FOCUS_FILE")
  if [ -n "$bad_enum" ]; then
    fail "focus.ndjson — impact/urgency not in [high,medium,low]: $(echo "$bad_enum" | tr '\n' ',')"
  else
    ok "focus.ndjson — impact/urgency enums valid"
  fi

  # pursuit cap. Parked is a deliberate stop and frees a slot; red means
  # "not happening" and does NOT free one.
  pcount=$(jq -c 'select(.tier=="pursuit" and .parked!=true and .retired_date==null)' "$FOCUS_FILE" | wc -l | tr -d ' ')
  if [ "$pcount" -gt 6 ]; then
    fail "focus.ndjson — $pcount active pursuits (max 6)"
  else
    ok "focus.ndjson — $pcount active pursuits (≤6)"
  fi

  parked_count=$(jq -c 'select(.retired_date==null and .parked==true)' "$FOCUS_FILE" | wc -l | tr -d ' ')
  ok "focus.ndjson — $parked_count parked focuses (excluded from the pursuit cap)"

  # no future-dated created
  future_f=$(jq -rc --arg t "$TODAY_MT" 'select(.created > $t) | .id' "$FOCUS_FILE")
  [ -n "$future_f" ] && fail "focus.ndjson — future-dated created: $future_f" || ok "focus.ndjson — no future-dated created"
fi

# ── 15. review-ledger.ndjson schema ───────────────────────────────────────────
echo "[15/16] review-ledger.ndjson schema"
LEDGER=data/review-ledger.ndjson
if [ ! -s "$LEDGER" ]; then
  ok "review-ledger.ndjson (empty)"
else
  bad=$(jq -c 'select(
      ((.id // "") == "") or ((.label // "") == "")
      or ([.tier] | inside(["weekly","monthly","quarterly"]) | not)
      or ((.cadence_days // 0) <= 0)
      or ((.last_done // "") | test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$") | not)
    ) | .id' "$LEDGER")
  [ -n "$bad" ] && { while IFS= read -r id; do fail "review-ledger.ndjson — record $id violates schema"; done <<< "$bad"; } || ok "review-ledger.ndjson ($(wc -l <"$LEDGER" | tr -d ' ') records conform)"
  dup=$(jq -r '.id' "$LEDGER" | sort | uniq -d)
  [ -n "$dup" ] && fail "review-ledger.ndjson — duplicate id(s): $dup" || ok "review-ledger.ndjson — ids unique"
  fut=$(jq -rc --arg t "$TODAY_MT" 'select(.last_done > $t) | .id' "$LEDGER")
  [ -n "$fut" ] && fail "review-ledger.ndjson — future last_done: $fut" || ok "review-ledger.ndjson — no future last_done"
fi

# ── 16. grounding.ndjson schema ───────────────────────────────────────────────
echo "[16/16] grounding.ndjson schema"
GROUNDING=data/grounding.ndjson
if [ ! -s "$GROUNDING" ]; then
  ok "grounding.ndjson (empty)"
else
  bad=$(jq -c 'select(
      (.id // "" | test("^ground-[0-9]{8}-[0-9]{3}$") | not)
      or (((.title // "") == "") and ((.text // "") == ""))
      or ([.status] | inside(["active","retired"]) | not)
      or ((.created // "") == "")
      or (.status == "retired" and ((.retired_date // "") == ""))
    ) | .id // "(no id)"' "$GROUNDING")
  [ -n "$bad" ] && { while IFS= read -r id; do fail "grounding.ndjson — record $id violates schema"; done <<< "$bad"; } || ok "grounding.ndjson ($(wc -l <"$GROUNDING" | tr -d ' ') records conform)"
  fut=$(jq -rc --arg t "$TODAY_MT" 'select(.created > $t) | .id' "$GROUNDING")
  [ -n "$fut" ] && fail "grounding.ndjson — future-dated created: $fut" || ok "grounding.ndjson — no future-dated created"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "✅ All checks passed."
  exit 0
else
  echo "❌ Validation failed. Fix issues above before committing."
  exit 1
fi
