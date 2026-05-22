---
name: pfc-review
description: Catch up on all currently-due rolling reviews at once — the uncapped counterpart to the evening check-in's 2-per-night drip. Use when the user says "review", "catch up on reviews", "run my reviews", "/pfc-review", or "what reviews are due".
---

# Review Catch-up

Runs the **same rolling-review ledger** as `pfc-evening-checkin` Step 3c (`data/review-ledger.ndjson`) but with **no cap** — every currently-due, gate-non-empty item surfaces in one deliberate pass instead of the ≤2/night drip. Use it when reviews have piled up and the user wants to clear the backlog in one sitting.

**This skill does not define its own gate table.** The due-computation and the per-id `gate()` function are canonical in [`pfc-evening-checkin`](../pfc-evening-checkin/SKILL.md) Step 3c. Open that section and read it before running this skill — you need the exact `gate()` case block and the due-computation `jq` from there. Do not paste a second copy of `gate()` into this file or reconstruct one from memory; when Step 3c's gate table changes, this skill's behavior changes with it because it re-reads the source each run.

## What's different from the evening drip

| | `pfc-evening-checkin` Step 3c | `pfc-review` (this skill) |
|---|---|---|
| Cap | ≤2 surfaced per run | **No cap** — every due + gated item |
| Order | Most-overdue-first across all tiers | **Tier order**: weekly → monthly → quarterly (most-overdue-first within each tier) |
| When it runs | Automatically, every evening check-in | On demand, when the user asks to catch up |
| Gate table + due math | Canonical there | **Same exact logic** — referenced, not copied |
| Stamping | Only items the user engages with | Same rule — never a due-but-empty-gate item, never an ignored one |
| Depth | Points at the owning skill | Offers to run the owning skill right then |

## Step 1 — Compute due + gated candidates, no cap, tier-ordered

Run the exact `gate()` function and due-computation defined in `pfc-evening-checkin` Step 3c (the `TODAY=…` / `gate() { case "$1" in … }` / the `jq -rc` due-age query piped through `gate`). Use that block verbatim, with exactly two changes:

1. Drop the `| head -2` at the end — keep every gate-non-empty line.
2. Change the final ordering from "most-overdue-first across everything" to **tier order**: all `weekly` items first (most-overdue-first within the group), then `monthly`, then `quarterly`. Collect the uncapped `id / label / tier / reason` output into a temp list and re-sort it in the shell by a tier-rank key (`weekly=0, monthly=1, quarterly=2`) with the overdue-days as the secondary key — don't touch the shared `gate()` definition to do it.

**If the output is empty** → print exactly `No reviews due right now.` and skip to Step 3. Do not manufacture a review.

## Step 2 — Walk every surfaced item, tier by tier, and stamp

For each surfaced `id → label → tier → reason`, in the tier order from Step 1:

1. Print one line: the label, why it's up (`reason`), and the skill or action that owns it — use the **same owning-skill map** as `pfc-evening-checkin` Step 3c section 2. Read it from there rather than paraphrasing it from memory.
2. Since this is a deliberate catch-up (unlike the passive evening drip), **offer to run the owning skill right then**, one item at a time. Let the user work through as many as they want in this sitting.
3. **Stamp `last_done` for each item the user engaged with** — ran the owning skill, or explicitly said "done" / "skip it this cycle" — using the same atomic pattern as Step 3c section 3:

```bash
ID="<engaged-id>"
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
tmp=data/.jq_update.tmp
jq -c --arg id "$ID" --arg t "$TODAY" 'if .id==$id then .last_done=$t else . end' \
  data/review-ledger.ndjson > "$tmp" && mv "$tmp" data/review-ledger.ndjson
```

Do **not** stamp an item the user skipped past without engaging — it stays due and re-surfaces next time, whether that's tonight's check-in or the next `/pfc-review`. Never stamp a due-but-empty-gate item; those never surfaced in Step 1 to begin with.

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

A review pass is like a check-in — auto-commit, no confirmation needed.

```bash
git add data/review-ledger.ndjson
git commit -m "checkin: catch up on reviews YYYY-MM-DD"
git push
```

Use the `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'` value for `YYYY-MM-DD`, per the repo-wide date rule. Add any files the individual reviews changed (life wheel, projects, insights, tasks) to the same commit.

## Out of scope

This skill does not re-implement any review workflow — like the evening drip, it notices what's due and hands off to the owning skill. It does not own the `gate()` definition, the owning-skill map, or the due-computation math; all three stay canonical in `pfc-evening-checkin` Step 3c. Change them there and this skill picks the change up automatically.
