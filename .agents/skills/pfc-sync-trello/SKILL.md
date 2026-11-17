---
name: pfc-sync-trello
description: Process completed cards in Trello dashboard and sync to repo. Use when the user says "sync trello", "process completed", "process trello completions", "/pfc-sync-trello", or after marking cards complete from the phone widget.
---

# Sync Trello Completions

Detects cards marked complete (`dueComplete: true`) in the dashboard's interactive lists, applies the corresponding repo update, archives task cards (or cycles habit cards on next render).

## When this skill triggers

- Explicit: "sync trello", "process completed", "/pfc-sync-trello"
- Invoked at the start of the evening check-in (Step 0b) to pull widget completions into the repo, and again at the end (Step 4b) to move back uncompleted 2+1 cards and re-render

## Pre-flight

Verify `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`. If unset, this skill is a no-op.

## Workflow

1. Run sync:
   ```bash
   python3 automations/scripts/trello_writeback.py sync
   ```

2. Output is a JSON counters block. Surface to user as a one-liner, e.g.:
   ```
   🟢 Synced. 2 tasks completed · 1 habit logged
   ```

3. **Archive source emails for newly-completed tasks (fail-safe).** If `tasks_completed > 0`, find which tasks just got marked done and archive any linked source emails. Today's `task_events.ndjson` rows with `source: "trello"` are the canonical signal:

   ```bash
   TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
   YDAY=$(TZ="${LOCAL_TZ:-America/Denver}" date -d 'yesterday' '+%Y-%m-%d')
   jq -r --arg d "$TODAY" --arg y "$YDAY" \
     'select(.event == "completed" and (.timestamp == $d or .timestamp == $y) and .source == "trello") | .task_id' \
     6-tasks/_data/task_events.ndjson | sort -u | while read -r tid; do
     [ -z "$tid" ] && continue
     jq -r --arg id "$tid" 'select(.id == $id) | .source_email_thread_id // empty' \
       6-tasks/_data/tasks.ndjson
   done
   ```

   For each non-empty thread ID, remove the `INBOX` label from that thread through your email connector (e.g. `mcp__claude_ai_Gmail__unlabel_thread` with `threadId` and `labelIds: ["INBOX"]`). On success: a one-line `📧 archived <thread-id>`. On error: `🟡 email archive skipped: <error>`. Same fail-safe pattern as the surrounding steps — never block the sync on it. Skip entirely if no email connector is configured.

4. **Refresh Trello dashboard** (fail-safe). If counters show any writes (`tasks completed`, `habits logged`, or anything > 0), run a render so card state (archive tasks, cycle habit cards) reflects the repo immediately:

   ```bash
   python3 automations/scripts/trello_render.py 2>&1
   ```

   On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. Skip the render if the counters block was all-zero (nothing to reflect).

5. **Commit what the sync changed** (skip when the counters were all zero). A data file left modified blocks the web UI's writer, which refuses to commit over uncommitted edits:

   ```bash
   git add 6-tasks/_data/tasks.ndjson 6-tasks/_data/task_events.ndjson 6-tasks/_data/daily-focus.ndjson \
     7-habits/_data/habits-daily.ndjson 7-habits/_data/habits-monthly.ndjson
   git commit -m "track: trello sync $(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')" && git push
   ```

## Behavioral rules

- Idempotent: running twice has no extra effect.
- Tasks already marked done in repo just trigger archive (cleans up Trello).
- Habits with same date+habit_id already logged are no-ops.
- Inbox list never touched.
- **Completions are dated from when the card was checked, never from when the sync runs.** `trello_writeback.py` reads Trello's `dateCompleted` and converts it to local time. Dating from sync time corrupts the record whenever the two straddle local midnight — the render checks a habit card the moment the habit is logged for that day, and only the midnight rollover render unchecks it, so any writeback firing in between reads yesterday's still-checked card as a fresh completion. Anything downstream that filters these records by date must allow for a yesterday-dated write, as Step 3 does.

## Out of scope

- Manual intervention on stuck cards (use `/pfc-render-trello --reset-list` if needed)
- Card create from Trello side (one-way: dashboard write-back is only for completion state)
