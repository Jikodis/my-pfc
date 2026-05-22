---
name: pfc-insights
description: Review captured insights and decide what to do with each (keep active, archive, or graduate to a task/project/habit). Use when the user says "show insights", "review insights", "what have I been noticing", "insight review", "my insights", or when the insights-review rolling review comes due.
---

# Review Insights

Insights live in `data/insights.ndjson` (schema: [insight_schema.yaml](../../../config/insight_schema.yaml)). They are observations the user captured throughout the week. This skill surfaces them and walks the user through triage.

## Modes

- **Browse** (default) — show all active insights, optionally filtered.
- **Recent** — only insights captured in the last 7 days. Handy for a quick pass mid-week.
- **Monthly** — only insights captured in the last 30 days, plus any older still-active ones.
- **By area / category** — filter when the user says "show me insights about sleep" or "relationship insights".

## Steps

1. **Derive date window.** Use `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'` for today.
   - Recent: `created >= today-7`
   - Monthly: `created >= today-30`
   - Browse: no date filter

2. **Load active insights:**
   ```bash
   jq -c 'select(.status == "active")' data/insights.ndjson
   ```
   For Recent / Monthly add a date filter:
   ```bash
   jq -c --arg from "YYYY-MM-DD" 'select(.status == "active" and .created >= $from)' data/insights.ndjson
   ```
   For category/area filter, add `and .category == "X"` or `and .area == "X"`.

3. **Display.** Group by area when there are 5+ insights, otherwise flat list. Format:
   ```
   <id> — <created> — [area / category] — <insight>
   ```
   Use 12-hour times if any are quoted in notes.

4. **Triage.** For each insight (or batched if many), ask the user:
   - **Keep** — leave as `active`, no change.
   - **Archive** — set `status: "archived"`. Use when no longer relevant or duplicated by a newer insight.
   - **Graduate → task** — create a task via `/pfc-add-task`, then mark the insight `status: "graduated"`, `graduated_to: "<task-id>"`, `graduated_date: today`.
   - **Graduate → project** — create a project entry in `5-projects/_data/projects.ndjson`, then graduate the insight to that proj id.
   - **Graduate → habit** — add to `config/habit_schema.yaml` (daily or monthly), then graduate to the habit_id.

5. **Update via jq** (never sed). Status change pattern:
   ```bash
   tmp=$(mktemp)
   jq -c --arg id "insight-YYYYMMDD-NNN" --arg today "YYYY-MM-DD" --arg target "task-..." \
     'if .id == $id then . + {status:"graduated", graduated_to:$target, graduated_date:$today} else . end' \
     data/insights.ndjson > "$tmp" && mv "$tmp" data/insights.ndjson
   ```
   Archive pattern:
   ```bash
   tmp=$(mktemp)
   jq -c --arg id "insight-YYYYMMDD-NNN" \
     'if .id == $id then .status = "archived" else . end' \
     data/insights.ndjson > "$tmp" && mv "$tmp" data/insights.ndjson
   ```

6. **Commit each batch:**
   ```bash
   git add data/insights.ndjson 6-actions/_data/tasks.ndjson 5-projects/_data/projects.ndjson config/habit_schema.yaml
   git commit -m "insight: triage YYYY-MM-DD"
   git push
   ```

## Display rules

- Don't summarize the user's insights — show them verbatim. Their words matter.
- Use 🟢 for active, ⚪ for archived, 🌱 for graduated when displaying mixed-status views.
- If zero active insights: print `No active insights.` and stop. Don't pad.

## Inside the rolling reviews

This skill owns the `insights-review` item in the rolling-review ledger (`data/review-ledger.ndjson`, monthly cadence). When it comes up — surfaced by `pfc-evening-checkin` Step 3c or by `/pfc-review` — run **Monthly** mode:

1. Show active insights from the last 30 days, plus any older ones still active.
2. Ask: "any to archive or graduate?"
3. Process the user's choices.
4. Return control to the calling flow, which stamps `last_done` on the ledger item.
