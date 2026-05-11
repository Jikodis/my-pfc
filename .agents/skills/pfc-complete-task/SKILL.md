---
name: pfc-complete-task
description: Mark a task as complete. Use when the user says "done", "complete", "finished", "mark done", or similar.
---

# Complete Task

All tasks live in `5-actions/_data/tasks.ndjson`.

1. Parse the task description or ID from the user's input.
2. Search for open matches with jq:
   ```bash
   jq -c 'select(.status == "open" and (.description | test("keyword"; "i")))' 5-actions/_data/tasks.ndjson
   ```
3. If multiple matches, show the user and ask which one.
4. Update status in place:
   ```bash
   jq -c 'if .id == "TASK_ID" then . + {status:"done", completed:"YYYY-MM-DD"} else . end' \
     5-actions/_data/tasks.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 5-actions/_data/tasks.ndjson
   ```
5. Append completion event to `5-actions/_data/task_events.ndjson`:
   ```bash
   jq -cn --arg id "TASK_ID" --arg ts "YYYY-MM-DD" \
     '{task_id:$id, event:"completed", timestamp:$ts}' \
     >> 5-actions/_data/task_events.ndjson
   ```
6. If this task is in today's `daily-focus.ndjson` record, update the focus record's `completed` array (or `bonus_completed`):
   ```bash
   TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
   jq -c --arg d "$TODAY" --arg id "TASK_ID" '
     if .date == $d then
       if (.critical // [] | index($id)) then .completed = ((.completed // []) + [$id] | unique)
       elif .bonus == $id then .bonus_completed = true
       else . end
     else . end' 5-actions/_data/daily-focus.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 5-actions/_data/daily-focus.ndjson
   ```

7. **REQUIRED — do not skip.** Update any matching calendar events on today's primary calendar so the `✅` prefix appears on the title. Without this, the write-path is broken and the calendar will silently drift out of sync with `tasks.ndjson`. Scope is today only — past/future days are not touched. See `docs/calendar-scheduling.md` §Completion sync for the full rules. In brief:
   a. Derive date variables (if not already set in step 6):
      ```bash
      TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
      TOMORROW=$(TZ="${LOCAL_TZ:-America/Denver}" date -d "$TODAY +1 day" '+%Y-%m-%d')
      ```
      Then call `mcp__claude_ai_Google_Calendar__list_events` for today's primary calendar with:
      - `timeMin`: `${TODAY}T00:00:00`
      - `timeMax`: `${TOMORROW}T00:00:00`
      - `timeZone`: `"${LOCAL_TZ:-America/Denver}"`
      - `orderBy`: `startTime`
      - `calendarId`: omit (defaults to primary)
   b. For every returned event whose `summary` contains `[TASK_ID]` literally:
      - If the summary already starts with `✅ `, skip (idempotent).
      - Otherwise call `mcp__claude_ai_Google_Calendar__update_event` with `summary: "✅ " + current_summary`. Leave `startTime`, `endTime`, `description`, and `colorId` unchanged.
   c. If the MCP call fails, print `⚠️ calendar update skipped: <error>` and continue — the task is still `done` in `tasks.ndjson`.

   Example title transition:
   - Before: `⭐ [AA-S] Process inbox backlog [task-20260412-001]`
   - After:  `✅ ⭐ [AA-S] Process inbox backlog [task-20260412-001]`

8. Commit: `task: complete [short description]`
9. Push and confirm.

10. **Refresh Trello dashboard** (fail-safe)

    If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, refresh the board so the completed task drops off `✅ Actions` and `✅ 2+1` immediately.

    ```bash
    python3 automations/scripts/trello_render.py 2>&1
    ```

    On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step.

IMPORTANT: Do NOT read entire task files into context. Use jq for all searches and writes — never `grep`/`sed` for structured edits.
