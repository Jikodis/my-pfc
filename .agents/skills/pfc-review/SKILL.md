---
name: pfc-review
description: Catch up on all currently-due rolling reviews at once. Use when the user says "review", "catch up on reviews", "run my reviews", "/pfc-review", or "what reviews are due".
---

# Review Catch-up

The old weekly / monthly / quarterly rituals are gone. Their review work is a **rolling ledger** (`data/review-ledger.ndjson`) with a cadence per item. Two places surface it:

| | The home page tour (its What needs you step) | `pfc-review` (this skill) |
|---|---|---|
| Cap | At most 1, and only when nothing urgent is listed | **No cap**: every due and gated item |
| Which item | `_due_review` in `automations/scripts/home_data.py`: never done first, then most overdue (cadence only, no gate) | Due items whose gate below is non-empty, in tier order |
| Stamping | Tapping the item stamps it (`web_write.py stamp-review`) | Only items the user engages with |

This file is the one home of the gate table and the owning-skill map. `REVIEW_SKILLS` in `home_data.py` carries the same map for the tour's button; change both together.

**What this skill is NOT:** it does not re-implement any review workflow. Each surfaced item points at the **owning skill**, and since the user asked to catch up, offer to run it right then.

## Step 1 — Compute due and gated candidates, no cap, tier-ordered

Paste this whole block. It defines the gates, computes due items, keeps the gate-non-empty ones, and prints them weekly first, then monthly, then quarterly. Every gate fails safe to empty (missing file or script error: no crash, the item just doesn't surface).

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')

gate() {  # echoes a short reason if there's something to act on; empty otherwise
  case "$1" in
    stale-task-triage) python3 automations/scripts/revive_watchlist.py --today "$TODAY" 2>/dev/null | jq -e 'length > 0' >/dev/null 2>&1 && echo "slipped items" ;;
    tasks-missing-area) jq -c 'select(.status=="open" and ((.area//null)==null) and ((.project//"none")=="none"))' 6-tasks/_data/tasks.ndjson 2>/dev/null | grep -q . && echo "tasks missing area" ;;
    focus-accuracy) jq -c 'select(.tier=="pursuit" and .retired_date==null and ((.landing//"")==""))' 4-focus/_data/focus.ndjson 2>/dev/null | grep -q . && echo "pursuit missing landing" || echo "weekly focus eyeball" ;;
    vision-relevance) ls 3-visions/*.md 2>/dev/null | grep -qv "README\|_template\|AGENTS\|CLAUDE" && echo "eyeball one vision" ;;
    habit-rate) echo "check trailing-7 habit rates" ;;
    values-alignment) jq -c 'select(.active==true and ((.values//[])|length==0))' 5-projects/_data/projects.ndjson 2>/dev/null | grep -q . && echo "project missing values" ;;
    day-trend-peek) [ "$(jq -rc 'select(.rating!=null)|.date' data/day-tracking.ndjson 2>/dev/null | tail -7 | wc -l)" -ge 5 ] && echo "trend peek" ;;
    life-wheel) echo "rate life areas" ;;
    household-status) [ -f 2-areas/_data/household-status.ndjson ] && echo "rate house areas" ;;
    project-progress) jq -c 'select(.active==true)' 5-projects/_data/projects.ndjson 2>/dev/null | grep -q . && echo "review active projects" ;;
    vision-activation) echo "lean-in / let-rest per vision" ;;
    monthly-habits) grep -q "monthly_habits:" config/habit_schema.yaml 2>/dev/null && echo "monthly habit rates" ;;
    insights-review) jq -c 'select(.status=="active")' data/insights.ndjson 2>/dev/null | grep -q . && echo "unreviewed insights" ;;
    findings-alignment) jq -c 'select(.status=="active")' data/findings.ndjson 2>/dev/null | grep -q . && echo "cross-check active findings" ;;
    trend-analysis) echo "deeper trend pass" ;;
    revive-outcomes) echo "revive outcomes ≥30d" ;;
    usage-audit) echo "usage check" ;;
    hypotheses-review) CUT=$(date -d '14 days ago' '+%Y-%m-%d' 2>/dev/null || date -v-14d '+%Y-%m-%d'); jq -c --arg c "$CUT" 'select(.status=="active" and ((.last_reviewed // "") < $c))' data/hypotheses.ndjson 2>/dev/null | grep -q . && echo "active hypotheses not reviewed in 14d" ;;
    focus-repick|vision-brainstorm|strengths-refresh) echo "quarter turned" ;;
  esac
}

# Emit "overdue_days<TAB>id<TAB>label<TAB>tier" for items past cadence, most-overdue first,
# then keep only gate-non-empty items. No cap: every one surfaces.
jq -rc --arg t "$TODAY" '
  ( ($t | strptime("%Y-%m-%d") | mktime) as $now
  | (.last_done | strptime("%Y-%m-%d") | mktime) as $ld
  | (($now - $ld) / 86400 | floor) as $age
  | select($age >= .cadence_days)
  | [ ($age - .cadence_days), .id, .label, .tier ] | @tsv )
' data/review-ledger.ndjson | sort -rn -k1,1 | \
while IFS=$'\t' read -r overdue id label tier; do
  reason=$(gate "$id")
  [ -n "$reason" ] && printf '%s\t%s\t%s\t%s\n' "$id" "$label" "$tier" "$reason"
done > /tmp/pfc-review-due.tsv

# Tier order: weekly, then monthly, then quarterly; within a tier the most-overdue order above is kept.
for t in weekly monthly quarterly; do awk -F'\t' -v t="$t" '$3==t' /tmp/pfc-review-due.tsv; done
```

**If the output is empty** → print exactly `No reviews due right now.` and skip straight to Step 3 (render). Do not manufacture a review.

## Step 2 — Walk every surfaced item, tier by tier, and stamp

For each surfaced `id → label → tier → reason`, in the order from Step 1:

1. Print one line: the label, why it's up (`reason`), and the skill or action to run, from this map:

| id | Owning skill / action to point at |
|---|---|
| `stale-task-triage` | `/pfc-revive` — walk the slipped watchlist |
| `tasks-missing-area` | assign an area to the flagged open tasks (edit `tasks.ndjson` / `/pfc-add-task` shape) |
| `focus-accuracy` | `/pfc-focus` — derived lights + landings; the four-way choice for anything red 2+ weeks (Step 2b) |
| `vision-relevance` | open one file in `3-visions/` and sanity-check it still fits |
| `habit-rate` | show trailing-7 completion per habit (from `7-habits/_data/habits-daily.ndjson`), then step any `ramp` frequencies (Step 2b) |
| `values-alignment` | add `values` to the flagged active project(s) in `projects.ndjson` |
| `day-trend-peek` | quick eyeball of the last 7 day ratings (light `/pfc-analyze-trends`) |
| `life-wheel` | rate the life areas (updates `2-areas/_data/life-wheel.ndjson`) |
| `household-status` | rate each house area (updates `2-areas/_data/household-status.ndjson`); create tasks for anything red |
| `project-progress` | `/pfc-summarize-project` per active project |
| `vision-activation` | `/pfc-focus` — lean-in / let-rest per vision |
| `monthly-habits` | show monthly-habit completion (`7-habits/_data/habits-monthly.ndjson`) |
| `insights-review` | `/pfc-insights` — triage active insights |
| `findings-alignment` | cross-check active findings (`data/findings.ndjson`) against values, projects, and habits; supersede anything life has moved past |
| `hypotheses-review` | review active hypotheses in `data/hypotheses.ndjson` — update `last_reviewed`; graduate to a finding if the bar is met (n≥30/\|r\|≥0.3/p<0.01, or a clear lived-experience pattern). **Never auto-archive** — surface for a look, the user decides |
| `trend-analysis` | `/pfc-analyze-trends` — full statistical pass |
| `revive-outcomes` | `/pfc-revive --review-outcomes` — outcomes of revived items ≥30d old |
| `usage-audit` | `/pfc-usage-audit` — is the system being used: data freshness, logging gaps, unused surfaces |
| `focus-repick` | `/pfc-focus` — quarterly re-pick |
| `vision-brainstorm` | `/pfc-vision-brainstorm` — dump what you want, then triage into visions / projects / focuses / habits |
| `strengths-refresh` | re-read `0-me/profile.md` (and any deeper personality / psychology files) and update what no longer fits |

2. Offer to run the owning skill or action right then, one item at a time. Let the user work through as many as they want in this sitting. Keep it soft: observation plus the one low-friction next step.
3. **Stamp `last_done` for each item the user engaged with** (ran the owning skill or action, or explicitly said "done" / "skip it this cycle"), one call per id:

```bash
ID="<engaged-id>"
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
tmp=data/.jq_update.tmp
jq -c --arg id "$ID" --arg t "$TODAY" 'if .id==$id then .last_done=$t else . end' \
  data/review-ledger.ndjson > "$tmp" && mv "$tmp" data/review-ledger.ndjson
```

Do **not** stamp an item the user skipped past without engaging: it stays due and re-surfaces next time (in the tour or the next `/pfc-review`). Never stamp a due-but-empty-gate item; it never surfaced.

## Step 2b — Two items carry their own procedure

Most ledger items just point at an owning skill. These two do real work here, because they are the mechanism that keeps habits and focuses honest. Full rationale: [`docs/habit-mechanics.md`](../../../docs/habit-mechanics.md).

### `habit-rate` — show the rates, then step the ramps

Show trailing-7 completion per habit as a table first (`Habit | Done / Target | ●`), then for each habit that has a `ramp` block in `config/habit_schema.yaml`:

- **Two consecutive green weeks and `frequency < ramp.target`** → propose stepping `frequency` up by 1. This needs an explicit yes. One line: "Spanish has been green two weeks — step 2 → 3/week?"
- **One red week and `frequency > ramp.starter`** → step `frequency` down by 1 **automatically**. Do not ask. Report it after the fact in one line: "Guitar stepped 2 → 1/week."
- Never step below `ramp.starter`. Habits with no `ramp` block never step at all.

Frequency edits go to `config/habit_schema.yaml` — it is YAML, not NDJSON, so edit it with the file tools, **not** `jq`.

Why down is automatic and up is not: the response to "too much" is lower the bar, never push through. Asking permission to fall inserts a decision at the moment decisions cost the most.

### `focus-accuracy` — the forcing function

```bash
python3 automations/scripts/focus_status.py --write
```

Show the full set — `Code | ● | Focus | Rate | Landing` — as a table, grouped by tier and sorted by code. Never ask the user to assess focuses they cannot see.

**Then the forcing function.** For each focus with `weeks_red >= 2`, run the four-way choice from [`pfc-focus`](../pfc-focus/SKILL.md) § "RED TWO WEEKS RUNNING": **re-land · lower · park · retire**. There is no fifth "keep trying" option. Apply the same choice to any **supporting** vehicle habit red 2+ weeks, scoped to that habit alone — the focus itself is untouched.

Cap at **two forced choices per review.** More than two decisions in one sitting is overload; the rest surface next week. Say plainly which ones you deferred — a silent cap reads as "everything is handled."

## Step 3 — Fail-safe Trello render

```bash
python3 automations/scripts/trello_render.py 2>&1 || echo "🟡 render failed (non-blocking)"
```

Any error logs 🟡 and continues — never blocks the commit. Skip entirely if `TRELLO_DASHBOARD_BOARD_ID` is not set.

## Step 4 — Commit

A review pass is a data write: auto-commit, no confirmation needed.

```bash
git add data/review-ledger.ndjson
git commit -m "checkin: catch up on reviews YYYY-MM-DD"
git push
```

Use the `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'` value for `YYYY-MM-DD`, per the repo-wide date rule. Add any files the individual reviews changed (life wheel, projects, insights, tasks) to the same commit.

## Out of scope

This skill does not re-implement any of the review workflows: it notices what's due and offers to hand off to the owning skill.
