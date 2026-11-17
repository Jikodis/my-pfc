---
name: pfc-review
description: Do the one due rolling review as a short form in chat, apply the answers, then offer the next one. Use when the user says "review", "do a review", "next review", "catch up on reviews", "run my reviews", "/pfc-review", or "what reviews are due".
---

# Reviews, one at a time

The old weekly / monthly / quarterly rituals are a **rolling ledger** (`data/review-ledger.ndjson`), each item with a cadence and a `last_done`. The evening check-in points at up to 2 due items a night (`pfc-evening-checkin` Step 3c). This skill does them: **one review at a time**, shown as a short form the user answers in one reply, applied, stamped, and then the next due review is offered. To clear a backlog, keep saying "next". Never stack several reviews in one message.

**This skill does not define its own gate table or owning-skill map.** Which reviews are due, and which of them have something to act on, comes from the `gate()` block and due-computation in [`pfc-evening-checkin`](../pfc-evening-checkin/SKILL.md) Step 3c. Read that section each run and use it verbatim; do not paste a second copy of `gate()` here. What this skill owns is the **form table** below: the rows each review shows, the options per row, and what each answer writes.

## Step 1 — Pick the one review

Run the Step 3c block with two changes: drop the final `| head -2`, and keep only the **first** line. That is the most overdue due review whose gate is not empty (the never-done `2000-01-01` seeds sort first, because they are the most overdue). A named review (`/pfc-review life-wheel`) skips the pick and uses that id.

**If the output is empty** → print exactly `No reviews due right now.` and stop. Do not manufacture a review.

## Step 2 — Show the form, in one message

1. One line: the review's label and why it is up (the gate's reason, and how many days overdue).
2. If the ledger row has a `seen` list (rows done in an earlier sitting, see Step 4), say so ("Carrying on: 6 rows done last time") and leave those rows out.
3. Each **choices** section as a numbered table: `# | Item | Detail | Options`, with the options for that review from the form table. Show **at most 14 rows**; if there are more, say how many are left for next time.
4. Each **prompt** as a plain question.
5. One line on how to answer: by number ("1 keep, 2 drop, 3 park: too much right now"), skip any row, or say "skip this review" to stamp it without changes.

The rows come from real data: never ask the user to judge something they cannot see in the message.

## Step 3 — Apply the answers

Turn the reply into one answer per row or prompt. A row left blank is not an answer: leave that item alone. An answer that does not fit its row (an option that row does not have, a note that makes no sense for it) is skipped and listed at the end, never guessed. Then apply each answer with the owning procedure:

| Review | Form rows → options | Answer → what to write |
|---|---|---|
| `stale-task-triage` | slipped tasks and projects from `python3 automations/scripts/revive_watchlist.py --today "$TODAY"` → Keep / This week / Park / Drop, optional note | Keep → nothing. This week → task: `urgency: high` and a `deadline` of this Friday; project: give its next open task `urgency: high`. Park → task: `deferred: true` with the note (or "parked in review") as `deferred_reason`; project: `active: false`, `status: parked`. Drop → `/pfc-revive`'s `pause_archive` for that item (a task moves to the archive with `dropped` set; a project is parked). Log each change in `data/revive-events.ndjson` the way `/pfc-revive` does |
| `tasks-missing-area` | open tasks with no `area` and no project → a note | The note is the area → set `area` on the task (`jq` update, names from `2-areas/`) |
| `focus-accuracy` | every active focus from `python3 automations/scripts/focus_status.py --write` → Keep / Re-land / Lower / Park / Retire, optional note | Keep → nothing. Re-land → the note becomes `landing`. Lower → step the vehicle habit's `frequency` down (to the note's number when given, never below `ramp.starter`). Park → `/pfc-focus` § PARK. Retire → `/pfc-focus` § RETIRE. Then the forcing function below |
| `focus-repick` | every active focus → Keep / Park / Retire / Graduate; prompt: "What new focus do you want this quarter, if any?" | Per `/pfc-focus` § QUARTERLY RE-PICK. Each line of the prompt → `/pfc-focus` add, the user's words as the title |
| `vision-relevance` | the visions in `3-visions/` → Still fits / Reword / Retire, optional note | Reword → rewrite the vision's title with the note. Retire → per `3-visions/README.md` |
| `vision-activation` | the visions → Lean in / Let rest | Lean in → per `/pfc-focus` (a focus or project for it). Let rest → nothing; resting is a valid state |
| `habit-rate`, `monthly-habits` | each habit with its rate (trailing 7 days, or this month) → Keep / Reword / Easier / Drop, optional note | Keep → nothing. Reword → the note becomes `description` in `config/habit_schema.yaml`. Easier → `frequency` down by 1 (or to the note's number), never below `ramp.starter`. Drop → move the habit to `deprecated_habits` in the same file. Then the ramp rules below |
| `values-alignment` | active projects with no `values` → a note | The note's values → `values` on the project (names from `1-values/values.md`) |
| `project-progress` | active projects with percent and velocity → On track / Stuck / Park / Done, optional note | The note → a progress note on the project. Stuck → also offer `/pfc-revive` for it. Park → `active: false`, `status: parked`. Done → archive it (`/pfc-add-project`) |
| `life-wheel` | the area check-in (procedure below) → Good / Okay / Rough, optional note | Append to `2-areas/_data/area-checkins.ndjson` |
| `household-status` | each house area with its last rating → Green / Yellow / Red, optional note | One new record in `2-areas/_data/household-status.ndjson` (`{date, ratings, notes}`, `docs/data-model.md`); offer a task for each red |
| `insights-review` | active insights → Keep / Archive / Make a task | Archive → `status: archived`. Make a task → `/pfc-add-task` from it, then `status: graduated` with `graduated_to` and `graduated_date` set |
| `hypotheses-review` | active hypotheses, oldest look first → Still testing / It holds / Doesn't hold, optional note | Still testing → `last_reviewed` today. It holds → graduate to a finding (`data/AGENTS.md`). Doesn't hold → `status: resolved-rejected` with the note. Never archive on your own judgment |
| `findings-alignment` | active findings → Still holds / Superseded, optional note | Superseded → `status: superseded`, `superseded_by` from the note (a new finding if needed) |
| `day-trend-peek` | prompt: the last 7 rated days, then "What stands out, and what helped?" | Kept in the user's words (see below) |
| `trend-analysis` | run `/pfc-analyze-trends` first and show its top lines; prompts: "What pattern do you see?" and "What one thing will you try for the next month?" | Same |
| `revive-outcomes` | prompt: items revived 30+ days ago (`data/revive-events.ndjson`), "Which stuck, which slipped again?" | Same, plus `/pfc-revive` outcomes for each named item |
| `usage-audit` | run `/pfc-usage-audit` first; prompts: "Which part of the system are you not using?" and "Use it, change how often, or change or cut it?" | Same; agreed changes are logged as `/pfc-usage-audit` describes |
| `vision-brainstorm` | prompt: "Everything you want out of life right now. No filter, one per line." | Each line → `/pfc-vision-brainstorm` capture, in the user's words |
| `strengths-refresh` | prompts: "Where did your strengths carry you this quarter?" and "What drained you more than it should have?" | Update `0-me/profile.md` where the answers show it no longer fits |

**Prompt answers** are kept in the user's words, not summarized: a noticing → `/pfc-add-insight`; something to try → a task (`/pfc-add-task`); a clear change to the system → make it.

All NDJSON writes use the `jq` temp-file pattern from the owning folder's `AGENTS.md`. `config/habit_schema.yaml` is YAML: edit it with the file tools, never `jq`.

## Step 4 — Finish it: stamp, or carry over

**No rows left** (everything shown was answered or skipped, and nothing was held back by the 14-row cap) → stamp `last_done` and clear `seen`:

```bash
ID="<review-id>"
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
tmp=data/.jq_update.tmp
jq -c --arg id "$ID" --arg t "$TODAY" 'if .id==$id then (.last_done=$t | del(.seen)) else . end' \
  data/review-ledger.ndjson > "$tmp" && mv "$tmp" data/review-ledger.ndjson
```

**The review had more rows than one form holds** → do not stamp. Add the row ids this form showed to `seen`, so the next sitting starts after them and the review stays due:

```bash
ID="<review-id>"; SHOWN='["<row-id>","<row-id>"]'
tmp=data/.jq_update.tmp
jq -c --arg id "$ID" --argjson s "$SHOWN" 'if .id==$id then .seen=((.seen // []) + $s | unique) else . end' \
  data/review-ledger.ndjson > "$tmp" && mv "$tmp" data/review-ledger.ndjson
```

"Skip this review" stamps it with no other writes. A review the user walked away from without answering is not stamped.

## Step 5 — Render, commit, report, offer the next

1. Fail-safe render, skipped if `TRELLO_DASHBOARD_BOARD_ID` is not set:
   ```bash
   python3 automations/scripts/trello_render.py 2>&1 || echo "🟡 render failed (non-blocking)"
   ```
2. Auto-commit (no confirmation needed): `data/review-ledger.ndjson` plus every file the answers changed, as `checkin: review <id> YYYY-MM-DD`, then push. Use `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'` for the date.
3. One line per change and one per skipped answer: `🟢 <item> → <what changed>` / `🟡 <item> → skipped: <why>`.
4. Run Step 1 again and name the next due review in one line ("Next up: Insights review. Want it?"). Stop when the user stops.

## Procedures the answers use

Most answers map straight to a write in the table above. These three carry their own rules, because they keep habits, focuses and areas honest. Full rationale: [`docs/habit-mechanics.md`](../../../docs/habit-mechanics.md).

### `habit-rate` — show the rates, then step the ramps

Show trailing-7 completion per habit as a table first (`Habit | Done / Target | ●`), then for each habit that has a `ramp` block in `config/habit_schema.yaml`:

- **Two consecutive green weeks and `frequency < ramp.target`** → propose stepping `frequency` up by 1. This needs an explicit yes. One line: "Spanish has been green two weeks — step 2 → 3/week?"
- **One red week and `frequency > ramp.starter`** → step `frequency` down by 1 **automatically**. Do not ask. Report it after the fact in one line: "Guitar stepped 2 → 1/week."
- Never step below `ramp.starter`. Habits with no `ramp` block never step at all.

Why down is automatic and up is not: the response to "too much" is lower the bar, never push through. Asking permission to fall inserts a decision at the moment decisions cost the most.

### `focus-accuracy` — the forcing function

```bash
python3 automations/scripts/focus_status.py --write
```

Show the full set — `Code | ● | Focus | Rate | Landing` — as the form's rows, grouped by tier and sorted by code. Never ask the user to assess focuses they cannot see.

**Then the forcing function.** For each focus with `weeks_red >= 2`, the options are only the four-way choice from [`pfc-focus`](../pfc-focus/SKILL.md) § "RED TWO WEEKS RUNNING": **re-land · lower · park · retire**. There is no fifth "keep trying" option. Apply the same choice to any **supporting** vehicle habit red 2+ weeks, scoped to that habit alone — the focus itself is untouched.

Cap at **two forced choices per review.** More than two decisions in one sitting is overload; the rest surface next week. Say plainly which ones you deferred — a silent cap reads as "everything is handled."

### `life-wheel` — the area check-in

Each life area can carry items in `2-areas/_data/area-items.ndjson` (Time items take hours every week, Status items are a state to keep in mind; weight 3 = breaks if dropped, 1 = bounces). Their lights decide the area's light; the rules live in `automations/scripts/area_items.py`. Schema: `config/area_item_schema.yaml`.

1. **Show the whole set first.** Run the script and render every area worst first, each with its items, before asking anything:

   ```bash
   python3 automations/scripts/area_items.py
   ```

   Columns: `Area ● | Item | ● now | Time or Status | Hours a week | Weight | Why`. Then the plate line: committed of free waking hours.

2. **One area at a time, worst first.** For each active item with a `question` that has not ended, ask the question with three answers, **Good / Okay / Rough**, plus an optional note. One area per message, so the user answers a short list. Items with a `source` light themselves (from a habit or health data) or only supply hours: show their light and why, never ask them. A skipped item gets no write.

3. **Append each answer** (`good`, `okay` or `rough`; the note may be empty):

   ```bash
   TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
   ITEM="<item_id>"; ANSWER="<good|okay|rough>"; NOTE="<note or empty>"
   jq -cn --arg d "$TODAY" --arg i "$ITEM" --arg a "$ANSWER" --arg n "$NOTE" \
     '{date:$d, item_id:$i, answer:$a} + (if $n == "" then {} else {note:$n} end)' \
     >> 2-areas/_data/area-checkins.ndjson
   ```

4. **Ended items.** An item the script marks `ended` (its `ends` date has passed) is already out of the hours and the light. Ask once: "<title> ended on <date>. Retire it?" On yes, set `active` to `false` on that item with the `jq` temp-file pattern.

5. **Corrections to an item** (hours, weight, question, a new item, retiring one) go to `2-areas/_data/area-items.ndjson` with the same `jq` update pattern, shown to the user as the literal before and after first.

6. **Areas with no items** keep the manual rating: append one record to `2-areas/_data/life-wheel.ndjson` (`{date, ratings, notes}`, green / yellow / red per area, `docs/data-model.md`). The manual light also stays as each area's fallback while none of its items has data.

7. **Show the result:** run the script again and print each area's light before and after in one table.

## Optional: a monthly budget check

If you keep a budget, a monthly budget review fits the ledger. It is not in the seed ledger. To turn it on, add a ledger row (`{"id":"budget-check","label":"Monthly budget check","tier":"monthly","cadence_days":30,"weekday_hint":null,"last_done":"2000-01-01"}`), a `budget-check) echo "monthly budget check" ;;` branch to the Step 3c `gate()` block, a row to its owning-skill map, and a `budget-check` row to the form table above (rows: the budget lines; prompt: the one below; answers: changes made in the budgeting tool after approval). `/pfc-repo-maintenance` flags a ledger id missing from any of the three.

The form: pull last month's planned and actual amounts per budget line from your budgeting tool (through its connector when one is available; otherwise ask the user to paste or export them), plus the 3-month average per line. Show one table, worst first: `Line | Planned | Actual | 3-month average`. Propose new planned amounts, conservatively: never below the 3-month average for fixed bills; a flexible line may go below it only as a deliberate cut, said as such. Flag lines budgeted at zero that got spending, and debts paid off since last month. Prompt: "Anything that surprised you, and any line to change?" Changes are made in the budgeting tool only after the user approves them; this repo stores no money data.

## Out of scope

Running several reviews in one message, re-implementing a review workflow that belongs to an owning skill, and owning the `gate()` definition or the owning-skill map (both stay canonical in `pfc-evening-checkin` Step 3c).
