---
name: pfc-supplement
description: Add, stop, list, or assess daily supplements and medications in the baseline registry. Use when the user says "I started taking X", "add supplement", "stop taking X", "discontinue Y", "show my supplements", "current regimen", "list my medications", "assess my supplements", "check my dosing", "review my regimen", "audit my stack", or similar.
---

# Supplement Registry

Manage the baseline daily registry at `data/supplements.ndjson`. Every record in this file represents a supplement or medication taken every day at the recorded dose and times, from `started` through `stopped` (or still active if `stopped` is null). A dose change is modeled as stopping the old record and adding a new active one — do not edit `dose` in place.

Schema: `config/supplement_schema.yaml`. Date-range semantics: a supplement is active on date `D` iff `started <= D AND (stopped is null OR stopped > D)`.

---

## Intents

Parse the user's request into one of four intents:

- **add** — phrases like "I started taking X", "add supplement Y", "new medication Z", "put X on the list"
- **stop** — phrases like "I stopped X", "discontinue Y", "took X off the list", "off Z now"
- **list** — phrases like "show my supplements", "current regimen", "what am I taking", "list my medications"
- **assess** — phrases like "assess my supplements", "check my dosing", "review my regimen", "audit my stack", "are my supplements right", "is this dose right for X"

Dose-change requests ("I switched from `2000 IU` to `5000 IU` on <supplement-name>") are a compound **stop + add**. Confirm with the user, then execute the two operations as separate records.

---

## Intent: add

Gather fields, confirming defaults inline rather than interrogating one at a time:

1. `name` — exact name (offer existing-name match if close)
2. `type` — `supplement` or `medication` (infer from context; confirm if unclear)
3. `dose` — free text; ask only if the user did not state it
4. `times` — one or more of `morning`, `afternoon`, `evening`, `bedtime`, `with meals`; default `["morning"]` if the user did not specify
5. `food_requirement` — one of `empty_stomach`, `with_food`, `with_fat`, `either`; null if unknown. Inline-suggest the typical answer for the named compound (e.g. fish oil → `with_fat`; most B-complex → `with_food`; free-form amino acids → `empty_stomach`) and confirm in one line rather than asking blind.
6. `purpose` — optional; skip if not offered
7. `started` — default today (`TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'`); override if the user specifies
8. `status` — always `active`

Generate the id: `supp-YYYYMMDD-NNN` where YYYYMMDD is today and NNN is the next unused sequence for today (check existing ids in the file).

Append with jq. Use `--argjson` for the nullable fields (`purpose`, `food_requirement`) so they land as JSON `null` when not provided.

```bash
jq -cn \
  --arg id "supp-YYYYMMDD-NNN" \
  --arg name "NAME" \
  --arg type "supplement" \
  --arg dose "DOSE" \
  --argjson times '["morning"]' \
  --argjson food '"with_fat"' \
  --argjson purpose '"PURPOSE"' \
  --arg started "YYYY-MM-DD" \
  '{
    id: $id,
    status: "active",
    name: $name,
    type: $type,
    dose: $dose,
    times: $times,
    food_requirement: $food,
    purpose: $purpose,
    started: $started,
    stopped: null,
    stopped_reason: null,
    notes: null
  }' >> data/supplements.ndjson
```

Pass `null` (literal) to `--argjson` for any nullable field with no value — e.g. `--argjson food 'null'` and `--argjson purpose 'null'`.

Commit and push:
```bash
git add data/supplements.ndjson
git commit -m "supplement: add [name]"
git push
```

---

## Intent: stop

1. Find the matching active record:
   ```bash
   jq -c --arg name "NAME" 'select(.status == "active" and (.name | ascii_downcase) == ($name | ascii_downcase))' data/supplements.ndjson
   ```
2. If more than one active record matches, list them with ids and ask which to stop.
3. If none match, tell the user and stop. Do not write anything.
4. Resolve the stop date — default today, override if user specified. **Future-dated stops are allowed** — if the user says "stop after tomorrow's dose" or "discontinue at end of week", set `stopped` to the day after the last dose (stopped is exclusive). The validator permits future `stopped` values; only `started` is blocked from being future-dated.
5. Capture `stopped_reason` — ask if the user hasn't provided one. Keep it brief (e.g. "no longer needed", "side effect", "doctor changed prescription"). If the user explicitly declines, set null.
6. Update in place:
   ```bash
   jq -c --arg id "SUPP_ID" --arg stopped "YYYY-MM-DD" --arg reason "REASON_OR_NULL" \
     'if .id == $id then . + {status:"stopped", stopped:$stopped, stopped_reason:($reason // null)} else . end' \
     data/supplements.ndjson > data/.jq_update.tmp \
     && mv data/.jq_update.tmp data/supplements.ndjson
   ```
   Pass `--argjson reason 'null'` (not `--arg`) when no reason is provided, so the field is JSON null.
7. Offer: "starting a replacement at a different dose?" If yes, chain into the **add** intent with the replacement.

**Dose-change chain.** If the user said "I'm switching from `2000 IU` to `5000 IU`" (or the stop prompt revealed one), execute as:
1. Stop the existing active record (this section's flow).
2. Batch both the stop update and the new active record into a single commit — stage `data/supplements.ndjson` once after both jq operations, then use the compound commit message `supplement: change dose [name] [old]→[new]`.
3. Do not commit between the stop and the add; the two records belong to the same logical change.

Commit and push (use `supplement: stop [name]`, or `supplement: change dose [name] [old]→[new]` when the stop was part of a dose-change chain):
```bash
git add data/supplements.ndjson
git commit -m "supplement: stop [name]"
git push
```

---

## Intent: list

Default view — currently active regimen, grouped by `times`:
```bash
jq -c 'select(.status == "active")' data/supplements.ndjson
```
Render as a compact Markdown table. Example output for an active regimen:

```
| Name        | Dose  | Times    | Purpose           | Started     |
|-------------|-------|----------|-------------------|-------------|
| <supplement-name> | <dose> | morning  | <purpose> | <YYYY-MM-DD>  |
```

If the user asks for the full history (including stopped records), show all records — active rows first, then stopped rows sorted by `stopped` descending:
```bash
jq -c '.' data/supplements.ndjson
```

Do not commit anything for list.

---

## Intent: assess

Walk every active record and evaluate it on four axes. Output is a markdown table plus a suggestions block. **No silent writes** — assess only writes when the user accepts a proposed `food_requirement` backfill.

### Read

```bash
jq -c 'select(.status == "active")' data/supplements.ndjson
```

### Axes to evaluate

For each compound, judge:

1. **Timing fit** — does the `times` slot match the compound's pharmacology?
   - Stimulants (prescription ADHD meds, caffeine): morning or early afternoon only; flag any dose past ~3 PM as sleep-disruptive.
   - Sleep aids and calmers (magnesium glycinate, l-theanine, phosphatidyl serine for cortisol): bedtime ✓.
   - Cognitive / cholinergic (choline donors, ALCAR, TMG): morning or midday.
   - Anti-inflammatories (turmeric, omega-3): with the largest meal of the day.
   - Fat-soluble vitamins (D, K, A, E): with a fat-containing meal.
   - Creatine: any consistent time; pharmacology is saturation-based, not timing-sensitive.

2. **Food fit** — does `food_requirement` agree with the chosen time AND with the user's actual meal pattern (e.g. a stimulant on waking is often pre-breakfast)?
   - Empty-stomach items at "with meals" → 🔴 mismatch.
   - Fat-soluble at "morning" with no breakfast fat → 🟡 absorption loss.
   - Empty-stomach items taken alongside other amino acids (whey, collagen, BCAAs, other free aminos like ALCAR or carnitine) → 🟡 absorption competition.

3. **Dose vs typical range** — recall the commonly cited adult dose range and flag clearly low or high. Examples (treat as recall, verify before acting):
   - Vitamin D-3: typical 2000–5000 IU for adults without sun.
   - Omega-3: combined EPA+DHA 1000–3000 mg/day typical.
   - Magnesium glycinate: 200–400 mg elemental.
   - Creatine: 3–5 g/day maintenance, no loading needed.
   - CDP choline: 250–500 mg/day common.
   - Acetyl L-Carnitine: 500–2000 mg/day.
   - L-Theanine: 100–400 mg.
   - Turmeric curcumin: 500–1500 mg/day with piperine or fat.
   - TMG: 500–2000 mg/day for methylation support.
   - Phosphatidyl Serine: 100–300 mg/day.

4. **Stack interactions** — surface notable pairs across the regimen:
   - Methylation/cognitive synergy: CDP choline + ALCAR + TMG.
   - Mineral competition: Calcium ↔ Magnesium ↔ Zinc ↔ Iron — separate by 2+ hours when possible.
   - Amino acid competition: ALCAR and other free aminos compete with each other and with whey/collagen at intake.
   - Sleep stack: magnesium glycinate + l-theanine + phosphatidyl serine all reinforce each other at bedtime.

### Output format

Status icons use the repo's standard circle convention: 🟢 fits / typical, 🟡 worth a look, 🔴 likely wrong.

```
| Name | Dose | Time | Food | Timing | Food fit | Dose | Notes |
|---|---|---|---|---|---|---|---|
| Vitamin D-3 + K-2 | 1000 IU / 45 mcg | morning | (unset) | 🟡 | 🔴 needs fat | 🟡 low (typical 2000–5000) | fat-soluble |
```

Below the table, two prose blocks:

**Suggested adjustments** — concrete options the user can accept. Each one specifies the operation (set food_requirement / change dose via stop+add / shift time via stop+add) and a one-line reason. Sort red-first.

**Stack notes** — cross-cutting observations that don't belong to a single row.

End with the disclaimer block (literal):

> ⚠️ **LLM judgment, not medical advice.** Typical-range numbers and timing rules are recall-based and don't account for labs, prescriptions, or individual response. Verify any dose or timing change with a doctor or your own primary sources before acting.

### Food-requirement backfill (in-place edit, allowed)

`food_requirement` is metadata about HOW to take a compound — not part of the dated dose record. This is the **one field** the skill may edit in place (everything else still requires the stop+add flow). When the user accepts backfill suggestions, batch them into a single commit:

```bash
jq -c --arg id "SUPP_ID" --arg food "with_fat" \
  'if .id == $id then . + {food_requirement: $food} else . end' \
  data/supplements.ndjson > data/.jq_update.tmp \
  && mv data/.jq_update.tmp data/supplements.ndjson
```

Repeat the jq update once per accepted record (each writes through the temp file). Then commit once:

```bash
git add data/supplements.ndjson
git commit -m "supplement: backfill food_requirement (N records)"
git push
```

Then run the Trello render fail-safe (see below).

### What assess does NOT do

- Never edits `dose`, `name`, `type`, `times`, or `purpose` in place. Dose / time / name changes require the stop+add flow.
- Never writes without explicit user approval. Even backfills are batched, shown as a diff, and confirmed.
- Never persists "reference ranges" into the repo. Recall-based numbers belong in the chat output only, with the disclaimer.
- If no backfills are accepted, assess never commits.

---

## Refresh Trello dashboard (fail-safe)

After **any successful add, stop, or assess-backfill commit**, refresh the dashboard so the `💊 Supplements` list reflects the new state immediately. List intent and a no-write assess never trigger a render.

```bash
python3 automations/scripts/trello_render.py 2>&1
```

On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set in `.env`, skip this step. For dose-change chains (stop + add), run the render once after the chained commit, not twice.

---

## Rules

- Always use `jq` — never `echo >>`, `sed`, or string concatenation for record writes.
- Auto-commit for **add** and **stop**. **List** never commits. **Assess** commits only when the user accepts a food_requirement backfill.
- `food_requirement` is the **one field** that may be edited in place. Everything else (dose, name, type, times, purpose) requires the stop+add flow.
- Always run `scripts/validate.sh` after a write and before committing. If red, revert the write.
- After every commit that touches `data/supplements.ndjson`, run the Trello render fail-safe (see section above).
