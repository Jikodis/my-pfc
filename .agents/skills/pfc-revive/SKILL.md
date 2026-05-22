---
name: pfc-revive
description: Revive a slipped project or task. Use when the user says "revive", "what's stuck", "what's slipping", "stalled projects", or when surfacing the watchlist from the evening check-in or a review pass. NOT the same as /pfc-stuck (body-state).
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

## Step 0 — Check the body-state inputs before treating a stall as a system failure

Before diagnosing the *work*, check whether the *person* had what they needed today. Two upstream inputs gate whether any revive intervention will actually fire: **sleep** and **whether today's anchor movement happened**. If either is missing, structural fixes — breaking down, rescheduling, building an external start — tend to bounce no matter how good the diagnosis was, and you'll wrongly conclude the intervention doesn't work.

This is the same two-branch diagnosis the whole system uses: *inputs missing* is not the same failure as *system broken*, and you fix inputs first.

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
CARDIO_HABIT="morning-walk"   # ← replace with your own anchor movement habit id from config/habit_schema.yaml
SLEEP_H=$(jq -r --arg d "$TODAY" 'select(.date == $d) | .health.sleep_hours // empty' data/day-tracking.ndjson | head -1)
AWAKE_MIN=$(jq -r --arg d "$TODAY" 'select(.date == $d) | .health.awake_minutes // empty' data/day-tracking.ndjson | head -1)
CARDIO=$(jq -r --arg d "$TODAY" --arg h "$CARDIO_HABIT" \
  'select(.date == $d and (.habit_id // .habit) == $h) | .completed' 7-habits/_data/habits-daily.ndjson | head -1)
```

Read sleep as **hours AND continuity** — a night can clear the hours floor and still leave you depleted if it was fragmented (see `/pfc-stuck` Step 0). Shipped thresholds, both editable: sleep ≥ ~6h and `awake_minutes` ≤ ~30.

Decision:

- **Both inputs fine** → print `🟢 Upstream inputs clear (sleep <H>h, movement done). Proceeding with walk.` and continue.
- **One or both missing** → print:

  > 🟡 Upstream input missing: <sleep <H>h / fragmented night / no movement logged>. Revive interventions on a depleted day often don't fire. Proceed anyway / defer the walk to a better day / skip the structural items and do only the cheap ones (lower scope, pause/archive, honest exits)?

  Accept their call:
  - `proceed` → continue the normal walk; note the input state in `intervention_notes` on every event written today (e.g. `"gate: no movement"`).
  - `defer` → print `🟡 Walk deferred. Run again after decent sleep and movement.` and exit.
  - `cheap only` → continue, but in Step 3 propose only `lower_scope`, `pause_archive`, or `walk_aversion`; defer the structural fixes.

- **Input data missing entirely** (no day-tracking row yet, no habit log yet) → treat the inputs as unread: one-line warning, default to `proceed`, and flag it in `intervention_notes`.

## Flags

- `--review-outcomes` — instead of walking the watchlist, scan `data/revive-events.ndjson` for rows where `date <= today - 30 days` AND `outcome is null`, walk them with the user, and update `outcome` + `outcome_checked`.

## Workflow — standard walk

For each watchlist item, in JSON-array order:

### Step 1 — Show the item

Fetch the canonical record:

```bash
# Tasks
jq -c --arg id "<item_id>" 'select(.id == $id)' 6-actions/_data/tasks.ndjson
# Projects
jq -c --arg id "<item_id>" 'select(.id == $id)' 5-projects/_data/projects.ndjson
```

Print in chat:

```
📍 <description or project name>
   └ Signal: <detail from JSON>
   └ Project: <name> · velocity 🔴/🟡/🟢   ← only for project items, or task items whose project != "none"
```

### Step 2 — Diagnostic (multi-select A–H)

Ask exactly:

> "What's the actual block? (multi-select A–H, or 'skip')
> A — Too big / activation energy too high       [Initiation deficit]
> B — Wrong time or context                      [Implementation intention]
> C — Missing prereq or dependency               [Dependency mapping]
> D — Out of sight / kept forgetting             [Salience]
> E — Reward too distant / no payoff in sight    [Delay discounting]
> F — Aversive / feels bad                       [Behavioral activation]
> G — Not actually important anymore             [Honest exit]
> H — Couldn't switch into it / wrong gear today [Body state, not structure]"

If the user replies `skip`: go to Step 5 with `diagnostic=[]`, `intervention=["skip"]`.

**Never ask an open "what's blocking this?" question.** The A–H multi-select exists precisely so the user picks rather than generates — an open prompt asks them to hold a whole stalled project in working memory and produce an answer, which for a working-memory-limited brain reliably produces silence. Same reason the intervention below is named options, not a brainstorm.

### Step 2b — The four-way choice for a long-stalled item

When an item has already been through one revive pass and slipped again, stop diagnosing and force the decision. Show its name, last activity date, and next part inline, then exactly four options:

1. **Re-land it** — the anchor is wrong; rebuild it anchor-first per [`docs/calendar-scheduling.md`](../../../docs/calendar-scheduling.md).
2. **Lower it** — shrink the next part until it's clearable. Often the two-minute version of just its first step.
3. **Park it** — a deliberate, guilt-free stop (`deferred: true` on a task).
4. **Retire it** — it's over.

There is deliberately **no fifth "keep trying" option**. Cap at **two forced choices per run**, and say which ones you deferred. Same mechanism as a focus red two weeks running — see [`docs/habit-mechanics.md`](../../../docs/habit-mechanics.md) § The four-way choice.

Parse the multi-select (e.g. "A, F" → `["A","F"]`).

### Step 3 — Brainstorm intervention

Look up the user's diagnostic picks in the table below to seed a proposal. The defaults are starting points, not rules — propose a tailored combination based on the specific item:

| Diagnostic | Default palette suggestion |
|---|---|
| A | `break_down` + `external_start` (collapse to one tiny action, then anchor its start) |
| B | `reschedule` or `pair_stack` |
| C | `break_down` + add `depends_on` |
| D | `external_start` — **not visibility hacks.** Sticky notes, calendar squares, progress bars and "see the percentage every day" all go invisible within a couple of days for this profile, so they read as fixes without being fixes. The reliable version is an external *start signal* at a fixed time, then solitude: anchor-to-running-state is the always-available primary; a person at the start moment is a bonus when someone's genuinely available; a scheduled live event or an alarm that requires an action to dismiss are fallbacks. If the item is a dormant interest you genuinely love but never think of, use `adjacent_input` instead of forcing a practice slot. |
| E | `break_down` (closer payoff) |
| F | `walk_aversion` first (sub-questions: what specifically? when did it start? safe to lower scope?) |
| G | `lower_scope` or `pause_archive` |
| H | `restore_state` — don't restructure the task. The block is body state, not shape. |

Propose in chat in one short sentence: "Diagnostic A + F → my read: this is large-and-aversive; I'd split it into 4 chunks and ask which one is the least bad to start with. Sound right?"

User iterates ("actually, can we just lower scope") until they approve. Multiple interventions may combine — store all chosen in `intervention[]`.

### Step 4 — Commit the intervention

Apply the chosen palette items:

- **`break_down`** — invoke `/pfc-add-task` to split (or for projects, prompt for the next sub-part). New tasks get `depends_on` set to the parent's id if it's task-level breakdown.
- **`pair_stack`** — write `notes` field with the anchor: `"After <existing habit>, do <this>"`. Use `jq` update pattern.
- **`reschedule`** — invoke `/pfc-schedule-focus` for tasks, or create a Google Calendar event directly via MCP for project work blocks.
- **`external_start`** — write the trigger plan into the task's `notes`. Format: `"trigger: anchor-to <running state>"` (preferred — always available, needs nobody else), or `"trigger: person-at-start <who and when>"` (only when someone genuinely is), or `"trigger: scheduled live <event>"`, or `"trigger: action-alarm <ritual>"`. Optionally also pin it to today's 2+1 if the trigger fires today. Do NOT propose sticky notes, calendar squares, or "see the percentage every day."
- **`adjacent_input`** — for dormant interests only: something you genuinely love but that never enters your attention on its own. Propose ONE source of adjacent media (podcast, video, newsletter) attached to an existing daily anchor — audio or video only, and **no practice reminder**. The adjacent input is the entire intervention; the practice is allowed to emerge or not. The mechanism: a durable interest doesn't convert into a present-tense pull by itself, and a daily trickle of related material is what does the converting. Write the chosen source into `notes`. Worth logging as a hypothesis so you learn whether it holds for you.
- **`boost_visibility` (deprecated for diagnostic D; retained for explicit request only)** — pin to the top of today's 2+1, bump urgency. Use only if the user asks for it by name; never propose it as the default for D.
- **`lower_scope`** — for tasks: jq update `impact` / `urgency`. For projects: jq update `total_parts`.
- **`pause_archive`** — for tasks: jq update `status` to `cancelled`; do NOT set `completed`. For projects: jq update `active` to `false`.
- **`walk_aversion`** — ask the sub-questions inline; the conversation produces a different intervention from the menu (record both `walk_aversion` AND the final action in `intervention[]`).
- **`restore_state`** — no structural edits to the task or project at all. Queue the item to be retried after the next state change: movement now (if it's accessible), or a session scheduled tomorrow morning with this item pinned to the post-movement window, or a movement burst now and retry. Optionally write `"trigger: retry after movement"` into `notes`. Do NOT combine with `break_down` or `lower_scope` — the diagnosis is "right shape, wrong state," and changing the shape muddies the signal about which one it actually was. See `/pfc-stuck` for the full lever menu.
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
git add 6-actions/_data/tasks.ndjson 5-projects/_data/projects.ndjson 6-actions/_data/task_events.ndjson data/revive-events.ndjson 6-actions/_data/daily-focus.ndjson 2>/dev/null
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
- **`pause_archive` for projects requires confirmation.** Flipping `active: false` cascades — daily project status disappears from the check-ins and the project's Trello list is archived. Confirm explicitly.
- **Skip cooldown is 7 days.** Don't override on the user's request; if they want to revisit a skipped item sooner, they can manually edit `data/revive-events.ndjson`.
- **The intervention log is canonical for pattern analysis.** Don't omit the log entry even when the intervention was minimal — the absence of a row distorts future stats.

## When NOT to use

- For human body-state stuck (frozen, locked-in, foggy, tired) — use `/pfc-stuck` instead.
- For task prioritization ("what should I work on?") — use `/pfc-pick-tasks`.
- For routine stale-task triage — that's the `stale-task-triage` rolling review, which surfaces in the evening check-in or a `/pfc-review` catch-up and points *at* this skill to walk the flagged items.
