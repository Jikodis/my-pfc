---
name: pfc-weekly-checkin
description: Run the weekly check-in workflow. Use when the user says "weekly checkin", "weekly check-in", "weekly review", "week in review", or "review my week".
---

# Weekly Check-in

When running a weekly check-in:

1. **Gather context** (use jq/grep, not full file reads):

   First, fix a window so missing-day skips can't pull prior-period records into this-period math:

   ```bash
   # WINDOW_FROM / WINDOW_TO can be set by a calling cadence (monthly/yearly checkin)
   # to expand the review window. Default: rolling 7 days ending today.
   WINDOW_FROM="${WINDOW_FROM:-$(TZ="${LOCAL_TZ:-America/Denver}" date -d '6 days ago' '+%Y-%m-%d')}"
   WINDOW_TO="${WINDOW_TO:-$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')}"
   ```

   - Open tasks: `jq -c 'select(.status == "open")' 5-actions/_data/tasks.ndjson`
   - Tasks completed in window: `jq -c --arg from "$WINDOW_FROM" --arg to "$WINDOW_TO" 'select(.completed != null and .completed >= $from and .completed <= $to)' 5-actions/_data/tasks.ndjson`
   - Daily focus records: `jq -c --arg from "$WINDOW_FROM" --arg to "$WINDOW_TO" 'select(.date >= $from and .date <= $to)' 5-actions/_data/daily-focus.ndjson`
     - Count distinct `.date` values and note `N days with focus set / days_in_window` — if the user skipped morning planning some days, the denominator for completion-rate math MUST be the number of focus-set days, not days_in_window.
   - Daily habit completions: `jq -c --arg from "$WINDOW_FROM" --arg to "$WINDOW_TO" 'select(.date >= $from and .date <= $to)' 6-habits/_data/habits-daily.ndjson`
     - For each habit: `completed = count where .completed == true`; `skipped = count where .skipped == true`; `rate = completed / max(1, target_frequency - skipped)`. Skipped days (explicit N/A, e.g. travel) drop out of both numerator and denominator.
   - Monthly habit completions: `jq -c --arg from "$WINDOW_FROM" --arg to "$WINDOW_TO" 'select(.date >= $from and .date <= $to)' 6-habits/_data/habits-monthly.ndjson`
   - Day tracking data: `jq -c --arg from "$WINDOW_FROM" --arg to "$WINDOW_TO" 'select(.date >= $from and .date <= $to)' data/day-tracking.ndjson`
     - Note `N days rated / days_in_window`. Averages should divide by rated days, not days_in_window.
   - Daily notes for the window: read `notes/daily/` files dated between `$WINDOW_FROM` and `$WINDOW_TO`
   - Active projects: `jq -c 'select(.active == true)' 4-projects/_data/projects.ndjson`
   - Values: read `1-values/values.md`
   - Habit schema: read `config/habit_schema.yaml`

2. **Summarize the week:**
   - Tasks and ops completed vs. opened
   - Daily focus completion rate (how many critical/bonus items hit)
   - Habit completion rates vs. target frequency
   - Energy/focus/rating trends from check-in data
   - Active project progress (completion %)
   - Calendar highlights (if connector available)
   - Email backlog (if Gmail connector available)

3. **Values Alignment Check**

   This is the most important section. The goal: ensure your work reflects who you are.

   **For each active project:**
   - Read its `area` and `values` fields
   - Read the area statement from `2-areas/{area}/statement.md`
   - Show: Project → Area → "Does this project honor the area statement?"
   - Show: Project → Values served → cross-reference with `1-values/values.md`
   - Flag any project missing `area` or `values` fields

   **For each active habit (from `config/habit_schema.yaml`):**
   - Show: Habit → Area → Values served
   - Flag any habit missing `area` or `values`

   **Tasks missing area or project:**
   - List any open high-impact tasks where both `project` and `area` are unset.
   - Surface them informationally — these will naturally get picked up via daily focus over time. Do NOT push a triage pass to assign area/project unless the user asks for one.

   **Alignment questions to surface:**
   - Is there any project you're working on that doesn't clearly serve an area statement or a value? If so: cut it, defer it, or update your values/statements.
   - Is there any area of life with NO active projects or habits serving it? That gap may be intentional or worth noting.
   - Are any of your top values (read from `1-values/values.md`) not represented in what you're actively doing this week?

   **Vision Progress Check** (the layer above projects)

   For each active vision in `3-visions/` (files with `status: active` in frontmatter, excluding `_template.md`, `README.md`, `passion-brainstorm.md`):

   ```bash
   for v in 3-visions/*.md; do
     base=$(basename "$v" .md)
     case "$base" in _template|README|passion-brainstorm) continue ;; esac
     status=$(awk '/^---$/{c++; next} c==1 && /^status:/{print $2; exit}' "$v")
     [ "$status" = "active" ] || continue
     slug=$(awk '/^---$/{c++; next} c==1 && /^name:/{print $2; exit}' "$v")
     area=$(awk '/^---$/{c++; next} c==1 && /^area:/{print $2; exit}' "$v")
     # Linked projects (vision: matches slug)
     linked_projects=$(jq -c --arg s "$slug" 'select(.active==true and .vision==$s) | .name' 4-projects/_data/projects.ndjson 2>/dev/null | wc -l)
     # Linked habits (vision: matches slug, in habit_schema.yaml)
     linked_habits=$(grep -c "^[[:space:]]*vision:[[:space:]]*$slug[[:space:]]*$" config/habit_schema.yaml 2>/dev/null || echo 0)
     echo "vision:$slug area=$area linked_projects=$linked_projects linked_habits=$linked_habits"
   done
   ```

   Surface each active vision with its linked projects and habits. Flag visions with zero linked projects AND zero linked habits — that's drift (a vision pointed at no leading indicators).

   Ask: any active vision that no longer represents direction? → mark `status: paused` or `status: abandoned`. Any leading indicator missing? → propose a new project or habit linked via `vision: <slug>`.

4. **Insights Triage**

   Insights (`data/insights.ndjson`) are personal observations captured during the review window. Surface active ones in the window and let the user decide what to do with each.

   ```bash
   jq -c --arg from "$WINDOW_FROM" --arg to "$WINDOW_TO" 'select(.status == "active" and .created >= $from and .created <= $to)' data/insights.ndjson
   ```

   For each insight, ask: keep / archive / graduate to (task | project | habit). Apply choices using the patterns in `pfc-insights`. If the user wants to graduate, route through `/pfc-add-task` or the project/habit definition flow first, then update the insight record with `status: "graduated"`, `graduated_to: <id>`, `graduated_date: today`.

   If zero insights captured in this window, output one line: "No insights captured in this window." and move on.

5. **Hypotheses Touch Pass**

   Hypotheses (`data/hypotheses.ndjson`) are open experiments. Unlike insights, they don't enter or exit weekly — they sit on the file accumulating evidence until they graduate to a finding, get rejected, or are archived. The touch pass keeps the user's belief in each one current and surfaces stale ones.

   Load all active hypotheses:
   ```bash
   jq -c 'select(.status == "active")' data/hypotheses.ndjson
   ```

   For each one, display in a compact row:
   ```
   <id> — confidence=<value or "—"> — last_reviewed=<date or "never"> — <hypothesis claim>
   ```

   Flag stale rows with 🟡 when `last_reviewed` is null or > 30 days ago. Flag with 🔴 when `last_reviewed` is > 60 days ago.

   Walk through each active hypothesis with the user:
   - **Confidence** — what's your current belief, 0.0–1.0? Acceptable to leave as null if genuinely unknown, but prefer setting a value once you have any signal.
   - **Evidence to add?** — anything observed this week that supports or weakens the hypothesis?
   - **Status change?** — keep active, mark `resolved-graduated` (with a new finding written), `resolved-rejected`, or `archived`.

   Update each touched record via `jq` (never sed). Always set `last_reviewed: today`, even if nothing else changed — the touch itself is the point. Update `confidence` if changed. Update `updated` only when content (protocol/evidence/mechanism) changed:
   ```bash
   TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
   jq -c --arg id "hyp-YYYYMMDD-NNN" --arg today "$TODAY" --argjson conf 0.7 \
     'if .id == $id then . + {confidence: $conf, last_reviewed: $today} else . end' \
     data/hypotheses.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp data/hypotheses.ndjson
   ```

   **Graduation reminder.** If a confidence value reaches ≥ 0.85 with multiple reviews behind it, ask: "ready to graduate this to a finding?" — that's the `source: "experience"` path (no n≥30 required, user judgment is the bar). If yes, write the new finding via the `pfc-add-insight`-style jq append pattern, then mark the hypothesis `status: "resolved-graduated"` with `updated: today`.

   If zero active hypotheses, output one line: "No active hypotheses." and move on.

6. **Findings Alignment Check**

   Findings (`data/findings.ndjson`) are durable insights that should shape ongoing decisions. Surface anything in the user's current life at odds with them.

   Load active findings:
   ```bash
   jq -c 'select(.status == "active")' data/findings.ndjson
   ```

   For each active finding:
   - Read the finding's claim and domain.
   - Scan for tension against:
     - `1-values/` — values that contradict the finding.
     - Active records in `4-projects/_data/projects.ndjson` — any project direction at odds with the finding.
     - `config/habit_schema.yaml` — habits present or absent inconsistent with the finding (e.g. a finding about sleep primacy but no sleep-related habit tracked).
     - Window entries of `data/day-tracking.ndjson` (`$WINDOW_FROM`–`$WINDOW_TO`) — behavior inconsistent with the finding.
   - If a tension exists, report: the finding + what seems misaligned + suggested action (adjust habit, update value, revisit project, **or** consider superseding the finding if life has moved on).

   If no conflicts are found, output a single line: "No findings misalignments detected." and move on.

   This is an agent-judgment pass, not a mechanical scan.

7. **Ask the user:**
   - What went well?
   - What didn't go well?
   - Any values or area statements that felt violated or neglected this week?
   - Any priorities to adjust for next week?

8. **Update life wheel** (`2-areas/_data/life-wheel.ndjson`):
   - Show the most recent entry for reference.
   - Ask the user to rate each life area (1–10) for this week.
   - Append a new record with today's date via `jq -cn`.

9. **Archive completed tasks** (if `5-actions/_data/tasks.ndjson` exceeds ~200 lines or contains many done tasks):
   ```bash
   jq -c 'select(.status == "done")' 5-actions/_data/tasks.ndjson >> 5-actions/_data/tasks-archive.ndjson
   jq -c 'select(.status != "done")' 5-actions/_data/tasks.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 5-actions/_data/tasks.ndjson
   ```

10. **Generate a weekly summary** at `notes/weekly/YYYY-WNN.md`

11. **Sync Trello dashboard** (fail-safe)

    If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, refresh the dashboard so the board reflects post-archive, post-life-wheel state. Mirrors the evening-checkin pattern.

    ```bash
    python3 automations/scripts/trello_render.py 2>&1
    ```

    On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step entirely.

12. Commit: `git add notes/weekly/ data/ 2-areas/_data/ 5-actions/_data/ && git commit -m "report: generate weekly check-in YYYY-MM-DD" && git push`

---

## Paused sections — re-enable when relevant

### Household status

Skipped during weekly check-in while household upkeep is handled separately. Re-enable by inserting this step before "Update life wheel" if circumstances change. Data file `2-areas/_data/household-status.ndjson` is preserved.

```text
**Update household status** (`2-areas/_data/household-status.ndjson`):
- Show the most recent entry for reference: jq -s 'last' 2-areas/_data/household-status.ndjson
- Ask the user for a fresh rating per room (red/yellow/green).
- Append a new record via jq -cn:
  - Define your rooms during onboarding — see `/pfc-onboarding define-rooms`. Replace `room_a, room_b` in the snippet below with your room list.
  jq -cn --arg date "YYYY-MM-DD" \
    '{date:$date, ratings:{room_a:"…",room_b:"…"}, notes:{}, logged_at:"YYYY-MM-DDT00:00:00-06:00"}' \
    >> 2-areas/_data/household-status.ndjson
```
