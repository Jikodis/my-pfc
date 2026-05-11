---
name: pfc-add-insight
description: Capture a personal insight, revelation, or noticing into data/insights.ndjson. Use when the user says "insight", "I noticed", "I realized", "revelation", "I think I figured out", "capture this thought", "save this insight", or shares a reflective observation worth keeping.
---

# Add Insight

Insights are observations / revelations / noticings the user wants to keep but that aren't yet ready to become a task, project, or habit. They live in `data/insights.ndjson`. Schema: [insight_schema.yaml](../../../config/insight_schema.yaml).

## When this skill triggers

- Explicit: "save this as an insight", "capture insight", "add insight"
- Reflective language: "I noticed that…", "I realized…", "it occurred to me…", "I think the pattern is…", "revelation:"
- The user shares a one-shot observation that's bigger than a task but not yet actionable

If the user's statement is clearly a task, project, or habit, route to the right skill instead and offer to also save the underlying insight.

## Required fields

- **insight** (string) — the observation itself, one to a few sentences. Capture the user's words; only lightly clean for clarity.
- **source** — usually `"chat"`. Use `"evening-checkin"`, `"morning"`, `"weekly-review"` if invoked from inside one of those flows.

## Optional fields (ask if not obvious)

- **area** — which life area it serves. Must match a folder in `2-areas/`. If the insight is clearly cross-cutting or meta, leave null.
- **category** — free-form tag the user has used before, or one they suggest. Common: `sleep`, `process`, `identity`, `energy-management`, `relationship`, `family`, `focus`, `psychology`. Reuse existing categories where possible:
  ```bash
  jq -r 'select(.category != null) | .category' data/insights.ndjson | sort -u
  ```
- **notes** — extra context or links the user provided.

If the user's input is terse (one-liner) and area/category aren't obvious, default to null on both. Don't grill them.

## Steps

1. Parse the insight text from the user's input. Strip speech filler ("I think…", "you know…") only if it's clearly filler — when in doubt, keep their wording.
2. Quick duplicate check (do not skip):
   ```bash
   # Use 2-3 distinctive words from the new insight
   jq -c --arg kw "KEYWORD" 'select(.status != "archived" and (.insight | test($kw; "i")))' data/insights.ndjson
   ```
   If a near-duplicate exists, show it and ask: use existing / add new / cancel.
3. Get today's date: `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'`
4. Generate id: `insight-YYYYMMDD-NNN` (count existing `insight-YYYYMMDD-` ids + 1).
5. Append via jq:
   ```bash
   jq -cn \
     --arg id "insight-YYYYMMDD-NNN" \
     --arg insight "..." \
     --argjson area '"AREA_OR_NULL"' \
     --argjson category '"CATEGORY_OR_NULL"' \
     --arg source "chat" \
     --arg created "YYYY-MM-DD" \
     --argjson notes 'null' \
     '{id:$id, status:"active", insight:$insight, area:$area, category:$category, source:$source, created:$created, graduated_to:null, graduated_date:null, notes:$notes}' \
     >> data/insights.ndjson
   ```
   For the nullable fields, pass `--argjson` with `'null'` (no quotes) when absent, or `'"value"'` (with inner quotes) when present.
6. Commit and push:
   ```bash
   git add data/insights.ndjson
   git commit -m "insight: add [first 6-8 words of insight]"
   git push
   ```
7. **Refresh Trello dashboard** (fail-safe)

   If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, refresh the board so the new insight shows up on `💡 Insights` immediately.

   ```bash
   python3 automations/scripts/trello_render.py 2>&1
   ```

   On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step.

8. After saving, ask one short follow-up: "Does this point at a task, project, or habit? Or just sit for now?" — if the user answers with action intent, route to `/pfc-add-task`, project creation, or `config/habit_schema.yaml` and then graduate the insight (see `pfc-insights`).

## Don't

- Don't auto-graduate an insight into a task without asking.
- Don't fill in `area`/`category` from inference if the user didn't mention them — leave null. Better empty than wrong.
- Don't overwrite the user's wording with your own paraphrase.
