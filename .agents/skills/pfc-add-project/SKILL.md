---
name: pfc-add-project
description: Add a new project to 4-projects/_data/projects.ndjson. Use when the user says "add project", "new project", "start project", "create project", or describes a new short-term project they want to formalize.
---

# Add Project

Projects are short-term efforts (1–3 months typical, max 3 active at a time). Schema: `config/project_schema.yaml`. Every project must declare an area, values, and a parts breakdown for percentage tracking.

## When this skill triggers

- Explicit: "add project", "start a new project", "new project: X"
- Inbox routing when a card title reads as a project
- During brainstorming when the user lands on a concrete bounded effort

If the user's input sounds like a single task (one action, no parts), route to `/pfc-add-task` instead.

## Required fields

- **name** (string) — project name
- **excitement** — `low` / `medium` / `high`
- **impact** — `high` / `medium` / `low`
- **urgency** — `high` / `medium` / `low`
- **area** (string) — must match a folder in `2-areas/`. Validate:
  ```bash
  ls 2-areas/ | grep -v _data
  ```
- **values** (array of strings) — must match entries in `1-values/values.md`. Read the file and offer the list.
- **total_parts** (integer) — break the project down into measurable sub-parts. If user is stuck, offer to brainstorm. Examples: "5 chapters", "3 milestones", "10 modules".

## Optional fields (ask only if natural to mention)

- **estimated_months** (number, 1–3 typical)
- **deadline** (YYYY-MM-DD)
- **vision** (slug from `3-visions/`) — offer if the project clearly serves a vision

## Steps

1. Parse project name from user input.
2. Active-limit check:
   ```bash
   ACTIVE=$(jq -c 'select(.active == true and (.status // "active") != "done")' 4-projects/_data/projects.ndjson | wc -l)
   ```
   If `ACTIVE >= 3`, ask: add as inactive (won't compete for the 3 slots) / archive an existing first / cancel. Default: add as inactive and tell the user.
3. Ask for required fields one at a time per CLAUDE.md "one question at a time" rule. Order: excitement → impact → urgency → area → values → total_parts → (optionals if natural).
4. Validate area against `2-areas/` folders. If no match, list options and re-ask.
5. Validate values against `1-values/values.md`. If a user-supplied value isn't in the list, ask whether to map to an existing value or add a new value to `values.md` (out of scope — refer them to do that separately).
6. Get today's date: `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'`
7. Generate id: `proj-YYYYMMDD-NNN` (count of existing `proj-YYYYMMDD-` ids + 1).
8. Build values JSON array: `printf '%s\n' "${VALUES[@]}" | jq -R . | jq -s .`
9. Append via jq. Required fields included; absent optionals omitted entirely (do NOT write them as null — schema treats them as `required: false`):
   ```bash
   jq -cn \
     --arg id "proj-YYYYMMDD-NNN" \
     --arg name "..." \
     --argjson active true \
     --arg excitement "..." \
     --arg impact "..." \
     --arg urgency "..." \
     --arg area "..." \
     --argjson values '[ ... ]' \
     --argjson total_parts N \
     --argjson completed_parts 0 \
     --arg created "YYYY-MM-DD" \
     '{id:$id, name:$name, active:$active, excitement:$excitement, impact:$impact, urgency:$urgency, area:$area, values:$values, total_parts:$total_parts, completed_parts:$completed_parts, created:$created}' \
     >> 4-projects/_data/projects.ndjson
   ```
   For optionals provided by user, add them with their own `--arg` / `--argjson` and include in the output object.
10. Run validator:
    ```bash
    scripts/validate.sh
    ```
    The validator enforces the 3-active limit. If it complains, the active-limit check in step 2 went wrong — investigate.
11. Commit + push:
    ```bash
    git add 4-projects/_data/projects.ndjson
    git commit -m "project: add <name>"
    git push
    ```
12. **Refresh Trello dashboard** (fail-safe)

    If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, refresh the board so the new project shows up on `🛠️ Projects` immediately.

    ```bash
    python3 automations/scripts/trello_render.py 2>&1
    ```

    On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step.

13. Confirm to user: "🟢 Saved as `proj-YYYYMMDD-NNN`. <name> · <area> · 0/<total_parts> parts."

## Output format

One-line confirmation. Include id, name, area, and starting completion (always `0/N`).
