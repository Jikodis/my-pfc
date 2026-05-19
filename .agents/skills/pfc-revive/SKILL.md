---
name: pfc-revive
description: Revive a slipped project or task. Use when the user says "revive", "what's stuck", "what's slipping", "stalled projects", or when surfacing the watchlist from morning or weekly check-ins. NOT the same as /pfc-stuck (body-state).
---

# Revive Slipped Work

A slippage-intervention skill. Generates a watchlist of slipped tasks/projects, walks each with a multi-select diagnostic, brainstorms a tailored intervention, and logs the result for pattern analysis.

**This is distinct from `pfc-stuck`.** pfc-stuck handles the human (frozen, locked-in, foggy, tired). pfc-revive handles the work (project losing momentum, task aging out, repeated 2+1 carry-forwards).

## Pre-flight

Generate today's watchlist:

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
python3 automations/scripts/revive_watchlist.py --today "$TODAY"
```

Each row in the JSON output has shape:
```json
{"item_type": "task" | "project", "item_id": "...", "signals": ["C","D"], "detail": "open 47 days, high-impact"}
```

If the array is empty: print `🟢 Nothing slipping today.` and exit.

## Flags

- `--review-outcomes` — instead of walking the watchlist, scan `data/revive-events.ndjson` for rows where `date <= today - 30 days` AND `outcome is null`, walk them with the user, and update `outcome` + `outcome_checked`.

## Workflow — standard walk

For each watchlist item, in JSON-array order:

### Step 1 — Show the item

Fetch the canonical record:

```bash
# Tasks
jq -c --arg id "<item_id>" 'select(.id == $id)' 5-actions/_data/tasks.ndjson
# Projects
jq -c --arg id "<item_id>" 'select(.id == $id)' 4-projects/_data/projects.ndjson
```

Print in chat:

```
📍 <description or project name>
   └ Signal: <detail from JSON>
   └ Project: <name> · velocity 🔴/🟡/🟢   ← only for project items, or task items whose project != "none"
```

### Step 2 — Diagnostic (multi-select A–G)

Ask exactly:

> "What's the actual block? (multi-select A–G, or 'skip')
> A — Too big / activation energy too high       [Initiation deficit]
> B — Wrong time or context                      [Implementation intention]
> C — Missing prereq or dependency               [Dependency mapping]
> D — Out of sight / kept forgetting             [Salience]
> E — Reward too distant / no payoff in sight    [Delay discounting]
> F — Aversive / feels bad                       [Behavioral activation]
> G — Not actually important anymore             [Honest exit]"

If the user replies `skip`: go to Step 5 with `diagnostic=[]`, `intervention=["skip"]`.

Parse the multi-select (e.g. "A, F" → `["A","F"]`).

### Step 3 — Brainstorm intervention

Look up the user's diagnostic picks in the table below to seed a proposal. The defaults are starting points, not rules — propose a tailored combination based on the specific item:

| Diagnostic | Default palette suggestion |
|---|---|
| A | `break_down` |
| B | `reschedule` or `pair_stack` |
| C | `break_down` + add `depends_on` |
| D | `boost_visibility` (full palette: pin to 2+1 top, calendar block, sticky, notes, urgency bump) |
| E | `break_down` (closer payoff) |
| F | `walk_aversion` first (sub-questions: what specifically? when did it start? safe to lower scope?) |
| G | `lower_scope` or `pause_archive` |

Propose in chat in one short sentence: "Diagnostic A + F → my read: this is large-and-aversive; I'd split it into 4 chunks and ask which one is the least bad to start with. Sound right?"

User iterates ("actually, can we just lower scope") until they approve. Multiple interventions may combine — store all chosen in `intervention[]`.

### Step 4 — Commit the intervention

Apply the chosen palette items:

- **`break_down`** — invoke `/pfc-add-task` to split (or for projects, prompt for the next sub-part). New tasks get `depends_on` set to the parent's id if it's task-level breakdown.
- **`pair_stack`** — write `notes` field with the anchor: `"After <existing habit>, do <this>"`. Use `jq` update pattern.
- **`reschedule`** — invoke `/pfc-schedule-focus` for tasks, or create a Google Calendar event directly via MCP for project work blocks.
- **`boost_visibility`** — for "pin to 2+1 top": edit today's `daily-focus.ndjson` row to put this task first in `critical`. For "bump urgency": jq update on tasks.ndjson. Other sub-options (sticky, notes-field reminder, calendar block) handled inline.
- **`lower_scope`** — for tasks: jq update `impact` / `urgency`. For projects: jq update `total_parts`.
- **`pause_archive`** — for tasks: jq update `status` to `cancelled`; do NOT set `completed`. For projects: jq update `active` to `false`.
- **`walk_aversion`** — ask the sub-questions inline; the conversation produces a different intervention from the menu (record both `walk_aversion` AND the final action in `intervention[]`).
- **`skip`** — no edits.

After applying, capture a one-line `intervention_notes` describing what was actually done (the specific chunks created, the calendar block, the new field values, etc.).

### Step 5 — Log the revive event

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
# Next sequence number for today
N=$(jq -r --arg t "$TODAY" 'select(.date == $t) | .id' data/revive-events.ndjson 2>/dev/null | wc -l | tr -d ' ')
SEQ=$(printf "%03d" $((N + 1)))
DATE_STAMP=$(echo "$TODAY" | tr -d '-')

jq -cn \
  --arg id "revive-${DATE_STAMP}-${SEQ}" \
  --arg date "$TODAY" \
  --arg item_type "task" \
  --arg item_id "task-..." \
  --argjson signals '["D"]' \
  --argjson diagnostic '["A","F"]' \
  --argjson intervention '["break_down","reschedule"]' \
  --arg notes "Split into 4 chunks; first chunk dropped on Tue 9am block" \
  '{id:$id, date:$date, item_type:$item_type, item_id:$item_id, signals:$signals, diagnostic:$diagnostic, intervention:$intervention, intervention_notes:$notes, outcome:null, outcome_checked:null}' \
  >> data/revive-events.ndjson
```

### Step 6 — Commit (per item, single push at end is fine)

After walking the full watchlist, batch-commit any task/project edits + the revive-events appends:

```bash
git add 5-actions/_data/tasks.ndjson 4-projects/_data/projects.ndjson 5-actions/_data/task_events.ndjson data/revive-events.ndjson 5-actions/_data/daily-focus.ndjson 2>/dev/null
git commit -m "system: pfc-revive — walk YYYY-MM-DD (N items)"
git push
```

End-of-walk recap:

```
🔁 Revive walk done.
- Walked: N items
- Interventions: <count per type, e.g. break_down ×2, pair_stack ×1>
- Skipped (cooldown started): M
```

## Workflow — `--review-outcomes`

Run when the user says "review revive outcomes", or as a periodic check-in. Walks rows where `date <= today - 30 days` AND `outcome is null`.

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
CUTOFF=$(TZ="${LOCAL_TZ:-America/Denver}" date -d "$TODAY - 30 days" '+%Y-%m-%d')
jq -c --arg c "$CUTOFF" 'select(.date <= $c and .outcome == null)' data/revive-events.ndjson
```

For each row:

1. Show the original item + diagnostic + intervention.
2. Fetch current state of the item (`tasks.ndjson` / `projects.ndjson`, including `tasks-archive.ndjson` for completed tasks).
3. Ask: "Outcome on this revive? `still_open` / `completed` / `archived` / `re_slipped`?"
4. Update the row in place:

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
jq -c --arg id "revive-..." --arg outcome "completed" --arg today "$TODAY" \
  'if .id == $id then . + {outcome: $outcome, outcome_checked: $today} else . end' \
  data/revive-events.ndjson > data/.jq_update.tmp \
  && mv data/.jq_update.tmp data/revive-events.ndjson
```

5. Commit at end:

```bash
git add data/revive-events.ndjson
git commit -m "system: pfc-revive — outcome review YYYY-MM-DD"
git push
```

## Behavioral rules

- **Never edit a task/project field without first showing the user the exact diff.** Even though the user has standing approval to act-first on most edits, slippage interventions touch impact/urgency/status fields where over-eagerness damages the system.
- **`pause_archive` for projects requires confirmation.** Flipping `active: false` cascades — daily project status disappears from morning + evening check-ins. Confirm explicitly.
- **Skip cooldown is 7 days.** Don't override on the user's request; if they want to revisit a skipped item sooner, they can manually edit `data/revive-events.ndjson`.
- **The intervention log is canonical for pattern analysis.** Don't omit the log entry even when the intervention was minimal — the absence of a row distorts future stats.

## When NOT to use

- For human body-state stuck (frozen, locked-in, foggy, tired) — use `/pfc-stuck` instead.
- For task prioritization ("what should I work on?") — use `/pfc-pick-tasks`.
- For weekly stale-task triage — that's the existing `/pfc-weekly-checkin` step; pfc-revive runs *after* triage in weekly.
