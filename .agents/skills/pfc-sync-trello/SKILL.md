---
name: pfc-sync-trello
description: Process completed cards in Trello dashboard and sync to repo. Use when the user says "sync trello", "process completed", "process trello completions", "/pfc-sync-trello", or after marking cards complete from the phone widget.
---

# Sync Trello Completions

Detects cards marked complete (`dueComplete: true`) in the dashboard's interactive lists, applies the corresponding repo update, archives task cards (or cycles habit cards on next render).

## When this skill triggers

- Explicit: "sync trello", "process completed", "/pfc-sync-trello"
- Invoked at the end of evening-checkin (Phase C wires this in)
- Invoked at start of morning-checkin to clean up yesterday's leftover state

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

3. **Refresh Trello dashboard** (fail-safe). If counters show any writes (`tasks completed`, `habits logged`, or anything > 0), run a render so card state (archive tasks, cycle habit cards) reflects the repo immediately:

   ```bash
   python3 automations/scripts/trello_render.py 2>&1
   ```

   On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. Skip the render if the counters block was all-zero (nothing to reflect).

## Behavioral rules

- Idempotent: running twice has no extra effect.
- Tasks already marked done in repo just trigger archive (cleans up Trello).
- Habits with same date+habit_id already logged are no-ops.
- Inbox list never touched.

## Out of scope

- Manual intervention on stuck cards (use `/pfc-render-trello --reset-list` if needed)
- Card create from Trello side (one-way: dashboard write-back is only for completion state)
