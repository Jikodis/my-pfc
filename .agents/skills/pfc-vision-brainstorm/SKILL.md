---
name: pfc-vision-brainstorm
description: Run or process a vision brainstorm — the free-form "dump everything you want" exercise that feeds visions, projects, tasks, and habits. Use when the user says "vision brainstorm", "brainstorm my visions", "let's brainstorm what I want", "dump my goals", or wants to capture or triage what they want out of life.
---

# Vision Brainstorm

The brainstorm is the generative exercise upstream of the whole VAVFPTH chain — a no-judgment dump of everything the user wants to become, do, see, or have happen. Each idea is stored as one record in `3-visions/_data/vision-brainstorm.ndjson` so it carries a lifecycle (`raw → promoted / done / dropped`) and a lineage (`became` → the vision or project it graduated into). See [`../../../3-visions/README.md`](../../../3-visions/README.md) § Vision brainstorm.

## When to use

- "vision brainstorm", "brainstorm my visions / goals", "dump what I want"
- A quarterly, annual, or on-demand generative session
- When the user wants to triage existing brainstorm records (promote / mark done / drop)

## Mode A — Capture (the dump)

The exercise: **5 minutes, no judging, no limits** — what to become / do / see / have happen. Keep capture frictionless: the user dumps free-form (chat, voice, a paste); **you** write the records. The user never authors JSON.

1. Let them dump. Do **not** interrupt to categorize mid-flow — the point is to empty the mind. Judgment comes later.
2. Get today's date: `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'`
3. Generate ids `vb-YYYYMMDD-NNN` (count existing `vb-YYYYMMDD-` ids + 1).
4. Infer `area` only where it's obvious (must match a `2-areas/` folder); leave `null` when unclear — don't grill.
5. Default `status:"raw"`, `became:null`. Append via `jq`:
   ```bash
   jq -cn --arg id "vb-YYYYMMDD-NNN" --arg text "<the idea, in their words>" --arg created "YYYY-MM-DD" \
     --argjson area '"AREA_OR_NULL"' \
     '{id:$id, text:$text, created:$created, area:$area, status:"raw", became:null, note:null}' \
     >> 3-visions/_data/vision-brainstorm.ndjson
   ```
   Nullable fields: pass `'null'` (no quotes) when absent, `'"value"'` (inner quotes) when present.
6. After the dump, reflect the full list back **grouped by area**, then ask which one or two are worth pursuing now (the "pick a couple" step). Don't force promotion — `raw` is a valid resting state.

## Mode B — Triage / promote

Walk the records the user names (or all `raw` ones) and update status + lineage:

- **Promote** — it becomes a vision / focus / project / task / habit. Set `status:"promoted"` and `became:{type, ref}`, then route to the right skill: `/pfc-add-vision`, `/pfc-focus`, `/pfc-add-project`, `/pfc-add-task`. Respect the caps that apply — **0–2 visions per area**, **6 active pursuits** in the Focus layer, the 12-active project backstop.
- **Done** — it's already true. `status:"done"` plus a short `note`.
- **Dropped** — not wanted. `status:"dropped"`.

Update in place (never raw-edit the file):

```bash
jq -c 'if .id=="vb-YYYYMMDD-NNN" then .status="promoted" | .became={type:"vision",ref:"<slug>"} else . end' \
  3-visions/_data/vision-brainstorm.ndjson > data/.jq_update.tmp \
  && mv data/.jq_update.tmp 3-visions/_data/vision-brainstorm.ndjson
```

Show what's still latent any time:

```bash
jq -c 'select(.status=="raw")' 3-visions/_data/vision-brainstorm.ndjson
```

## Constraints

- **Capture is judgment-free.** Never call an idea unrealistic during a dump. Triage is a separate, later step.
- **Don't auto-promote.** Promoting to a vision, focus, or project is the user's call — surface candidates, let them choose.
- **One idea per record.** Split a compound dump only when the user clearly means two distinct things; otherwise keep their framing.
- **`became` points forward** to the slug or id it graduated into, so the lineage stays queryable.

## Commit

1. `scripts/validate.sh`
2. Commit + push:
   ```bash
   git add 3-visions/_data/vision-brainstorm.ndjson
   git commit -m "vision-brainstorm: <capture N ideas | triage>"
   git push
   ```
3. **Refresh Trello dashboard** (fail-safe, only if `TRELLO_DASHBOARD_BOARD_ID` is set) — `python3 automations/scripts/trello_render.py 2>&1`. On error print `🟡 Trello render failed (non-blocking): <error>` and continue. Brainstorm records have no Trello list of their own; this just keeps the rest of the board fresh after the commit.

## Reference

- Data: `3-visions/_data/vision-brainstorm.ndjson`
- README: `3-visions/README.md` § Vision brainstorm
- Promotion targets: `/pfc-add-vision`, `/pfc-focus`, `/pfc-add-project`, `/pfc-add-task`
