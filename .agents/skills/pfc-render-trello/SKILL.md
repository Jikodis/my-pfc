---
name: pfc-render-trello
description: Render the PFC system to the Trello dashboard board. Use when the user says "render trello", "render dashboard", "sync trello", "update dashboard", "/pfc-render-trello", or after a major repo change that should be reflected on the board.
---

# Render Trello Dashboard

Mirror PFC repo state onto the Trello dashboard board. The render is idempotent: running it twice produces no changes the second time. Run on demand when you want the dashboard fresh, or it's invoked automatically by morning- and evening-checkin (Phase C).

## When this skill triggers

- Explicit: "render trello", "render dashboard", "sync trello", "update dashboard", "/pfc-render-trello"

## Pre-flight

Verify env vars set: `TRELLO_API_KEY`, `TRELLO_API_TOKEN`, `TRELLO_DASHBOARD_BOARD_ID`. If any missing, the helper prints to stderr and exits 1 — surface and stop.

## Workflow

### Step 1 — Fetch Calendar data via MCP (if Google Calendar MCP is available)

Use `mcp__claude_ai_Google_Calendar__list_events` (or your environment's equivalent) to fetch events from the user's primary + work calendars for the next 7 days starting today (`$LOCAL_TZ`). Per `docs/calendar-scheduling.md`, EXCLUDE any context-only calendars (e.g. holidays, shared community calendars) — edit `config/trello_calendar_filters.yaml` to match the calendars in your scope.

Get today's date: `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'` and end date 7 days later.

Save the results as a JSON array to `/tmp/pfc-calendar-events.json` with this shape per event. **Preserve `recurringEventId` exactly as returned by MCP** — the renderer uses it to drop recurring noise (weekly church/study groups, regular school pickups, recurring therapy, etc.) from the Week-at-a-Glance list. Omitting the field silently re-introduces recurring events to the board.

```json
[
  {
    "id": "<event id>",
    "summary": "<title>",
    "recurringEventId": "<id-of-parent-series-if-this-instance-is-recurring; omit field if event is non-recurring>",
    "start": {"dateTime": "2026-05-10T10:00:00-06:00"},
    "end": {"dateTime": "2026-05-10T11:00:00-06:00"},
    "organizer": {"displayName": "<calendar name>"},
    "location": "<optional>"
  }
]
```

If Calendar MCP is not available, skip this step. The render will skip the Calendar list with a 🟡 note.

### Step 2 — Fetch Email data via MCP (if Gmail MCP is available)

Use `mcp__claude_ai_Gmail__search_threads` (or equivalent) to query each priority tier in `in:inbox`:

- `in:inbox label:AA` → tier AA
- `in:inbox label:AB` → tier AB
- `in:inbox label:BA` → tier BA
- `in:inbox label:AC` → tier AC
- `in:inbox label:BB` → tier BB
- `in:inbox label:CA` → tier CA

For each match, get the thread's most recent message subject, sender, and a one-line snippet. Build a single JSON array combining all tiers, with this shape:

```json
[
  {"id": "<message id>", "subject": "...", "from": "...", "snippet": "...", "tier": "AA"},
  ...
]
```

The Python tier filter (AA/AB/BA always; AC/BB/CA only when no higher tier present) is applied automatically.

Save to `/tmp/pfc-email-data.json`. If Gmail MCP is unavailable, skip — render will skip the Email list with 🟡.

### Step 3 — Run the render

```bash
python3 automations/scripts/trello_render.py \
  --calendar-events /tmp/pfc-calendar-events.json \
  --email-data /tmp/pfc-email-data.json
```

Omit the flags whose data wasn't fetched in Steps 1 / 2.

### Step 4 — Watch the streaming output

Same as before:
- 📋 Loading repo state
- 🔧 Reconciling lists and labels
- 🎨 Rendering desired card sets (will note any skipped external lists)
- 🔍 Fetching current Trello state
- 📐 Diff: N creates, M updates, K archives
- ✏️ Applying ops
- 🟢 Render complete summary

On exit 0 (success): report the summary line to the user.

On exit 1 (error): surface the stderr message and stop. Likely causes: missing env var, Trello auth issue, network problem.

### Step 5 — Cleanup

Remove the temp files:
```bash
rm -f /tmp/pfc-calendar-events.json /tmp/pfc-email-data.json
```

## Drift recovery

Two destructive modes for re-establishing ground truth from repo:

### `--rebuild` — full board re-creation

Archives every card on the dashboard (except `📥 Inbox`) and re-renders from scratch.

```bash
python3 automations/scripts/trello_render.py --rebuild
```

Use when the board is meaningfully drifted (cards reorganized, lots of manual edits, lists renamed unexpectedly). The skill prompts for explicit `yes` confirmation, showing the count of cards that will be archived before proceeding.

**Warning:** existing card IDs become stale. Any external links or bookmarks pointing at specific cards break.

### `--reset-list <name>` — single-list reset

Archives all cards on one named list and re-renders just that list.

```bash
python3 automations/scripts/trello_render.py --reset-list "🛠️ Projects"
```

Use when only one list is drifted. Less invasive than `--rebuild`. Refuses to operate on `📥 Inbox`.

Same confirmation prompt as `--rebuild`.

## Behavioral rules

- **Never touches the 📥 Inbox list.** That's owned by `pfc-trello-inbox`.
- **Idempotent.** Running twice produces zero changes the second time.
- **Repo is canonical.** Any user-added card on a non-Inbox list (no pfc-id) gets archived on next render. By design.
