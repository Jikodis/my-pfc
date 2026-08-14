---
name: pfc-render-trello
description: Render the PFC system to the Trello dashboard board. Use when the user says "render trello", "render dashboard", "sync trello", "update dashboard", "/pfc-render-trello", or after a major repo change that should be reflected on the board.
---

# Render Trello Dashboard

Mirror PFC repo state onto the Trello dashboard board. The render is idempotent: running it twice produces no changes the second time. Run on demand when you want the dashboard fresh, or it's invoked automatically by the evening check-in (Step 4b) and `/pfc-review`.

## When this skill triggers

- Explicit: "render trello", "render dashboard", "sync trello", "update dashboard", "/pfc-render-trello"

## Pre-flight

Verify env vars set: `TRELLO_API_KEY`, `TRELLO_API_TOKEN`, `TRELLO_DASHBOARD_BOARD_ID`. If any missing, the helper prints to stderr and exits 1 — surface and stop.

## Workflow

### Step 1 — Fetch Calendar data via MCP (if Google Calendar MCP is available)

Use `mcp__claude_ai_Google_Calendar__list_events` (or your environment's equivalent) to fetch events from the user's primary + work calendars for the next 7 days starting today (`$LOCAL_TZ`). Per `docs/calendar-scheduling.md`, EXCLUDE any context-only calendars (e.g. holidays, shared community calendars) — edit `config/trello_calendar_filters.yaml` to match the calendars in your scope.

Get today's date: `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'` and end date 7 days later.

Save the results as a JSON array to `/tmp/pfc-calendar-events.json` with this shape per event.

**Fetch every event, recurring instances included, and preserve `recurringEventId` exactly as returned by the connector.** Recurring is not by itself a reason to hide something — most real commitments are recurring series (standing lunches, classes, therapy, an office day), and dropping them all leaves the week surface blank. But the field is still load-bearing: `config/trello_calendar_filters.yaml` has an `exclude_titles_when_recurring` list that hides the *series* of a known weekly pattern while letting a **one-off with the same title** through, because the exception to the pattern is the most useful thing the screen can show. Drop the field and every one-off silently disappears.

```json
[
  {
    "id": "<event id>",
    "summary": "<title>",
    "start": {"dateTime": "2026-05-10T10:00:00-06:00"},
    "end": {"dateTime": "2026-05-10T11:00:00-06:00"},
    "organizer": {"displayName": "<calendar name>"},
    "location": "<optional>"
  }
]
```

If Calendar MCP is not available, skip this step. The render will skip the Calendar list with a 🟡 note.

### Step 2 — Run the render

Email is NOT rendered to a dashboard list. Labeled inbox emails become tasks via `pfc-email-triage` Step 0 (run daily by the evening check-in), and those show up as ordinary Action cards. To refresh them, run `/pfc-email-triage`, not this skill.

```bash
python3 automations/scripts/trello_render.py \
  --calendar-events /tmp/pfc-calendar-events.json
```

Omit the calendar flag if Step 1 didn't fetch (the render then skips the Calendar list with a 🟡 note).

### Step 3 — Watch the streaming output

- 📋 Loading repo state
- 🔧 Reconciling lists and labels
- 🎨 Rendering desired card sets (notes any skipped external list, and any soft-cap warning — Front of Mind over 10 anchors, Current Focus over 6 active pursuits)
- 🔍 Fetching current Trello state
- 📐 Diff: N creates, M updates, K archives
- ✏️ Applying ops
- 🟢 Render complete summary

On exit 0 (success): report the summary line to the user.

On exit 1 (error): surface the stderr message and stop. Likely causes: missing env var, Trello auth issue, network problem.

### Step 4 — Cleanup

Remove the temp file:
```bash
rm -f /tmp/pfc-calendar-events.json
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

## Local-only mode — pulse trend

`--pulse-history [n]` needs no Trello credentials and touches no board. It prints the last `n` days (default 7) of Superman Pulse lever statuses as 🟢/🟡/🔴 sparklines plus chronic-miss flags, for the evening check-in to read.

```bash
python3 automations/scripts/trello_render.py --pulse-history 7
```

Both this trend and the `🦸 Superman Pulse` list read their thresholds, verdict, and per-lever fixes from `automations/scripts/pulse.py` — the single source of truth. Tune levers there, never in the render.

## Behavioral rules

- **Never touches the 📥 Inbox list.** That's owned by `pfc-trello-inbox`.
- **Idempotent.** Running twice produces zero changes the second time.
- **Repo is canonical.** Any user-added card on a non-Inbox list (no pfc-id) gets archived on next render. By design.
- **Soft caps warn, never truncate.** 🧠 Front of Mind over `GROUNDING_CAP` (10) anchors and 🎯 Current Focus over 6 active pursuits both log a 🟡 line and render everything anyway. Surface the warning to the user and suggest retiring one — never silently drop a card.
- **`🎯 Current Focus` is not a project list.** Per-active-project lists share the `🎯 ` prefix; the render exempts this one name so it isn't archived as a stale project list.
