---
name: pfc-supplement
description: Add, stop, or list daily supplements and medications in the baseline registry. Use when the user says "I started taking X", "add supplement", "stop taking X", "discontinue Y", "show my supplements", "current regimen", "list my medications", or similar.
---

# Supplement Registry

Manage the baseline daily registry at `data/supplements.ndjson`. Every record in this file represents a supplement or medication taken every day at the recorded dose and times, from `started` through `stopped` (or still active if `stopped` is null). A dose change is modeled as stopping the old record and adding a new active one — do not edit `dose` in place.

Schema: `config/supplement_schema.yaml`. Date-range semantics: a supplement is active on date `D` iff `started <= D AND (stopped is null OR stopped > D)`.

---

## Intents

Parse the user's request into one of three intents:

- **add** — phrases like "I started taking X", "add supplement Y", "new medication Z", "put X on the list"
- **stop** — phrases like "I stopped X", "discontinue Y", "took X off the list", "off Z now"
- **list** — phrases like "show my supplements", "current regimen", "what am I taking", "list my medications"

Dose-change requests ("I switched from `2000 IU` to `5000 IU` on <supplement-name>") are a compound **stop + add**. Confirm with the user, then execute the two operations as separate records.

---

## Intent: add

Gather fields, confirming defaults inline rather than interrogating one at a time:

1. `name` — exact name (offer existing-name match if close)
2. `type` — `supplement` or `medication` (infer from context; confirm if unclear)
3. `dose` — free text; ask only if the user did not state it
4. `times` — one or more of `morning`, `afternoon`, `evening`, `bedtime`, `with meals`; default `["morning"]` if the user did not specify
5. `purpose` — optional; skip if not offered
6. `started` — default today (`TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'`); override if the user specifies
7. `status` — always `active`

Generate the id: `supp-YYYYMMDD-NNN` where YYYYMMDD is today and NNN is the next unused sequence for today (check existing ids in the file).

Append with jq. When a purpose was provided, use the "with purpose" template; otherwise use the "no purpose" template and the `purpose` field is literally `null`.

**With purpose:**
```bash
jq -cn \
  --arg id "supp-YYYYMMDD-NNN" \
  --arg name "NAME" \
  --arg type "supplement" \
  --arg dose "DOSE" \
  --argjson times '["morning"]' \
  --arg purpose "PURPOSE" \
  --arg started "YYYY-MM-DD" \
  '{
    id: $id,
    status: "active",
    name: $name,
    type: $type,
    dose: $dose,
    times: $times,
    purpose: $purpose,
    started: $started,
    stopped: null,
    stopped_reason: null,
    notes: null
  }' >> data/supplements.ndjson
```

**No purpose:**
```bash
jq -cn \
  --arg id "supp-YYYYMMDD-NNN" \
  --arg name "NAME" \
  --arg type "supplement" \
  --arg dose "DOSE" \
  --argjson times '["morning"]' \
  --arg started "YYYY-MM-DD" \
  '{
    id: $id,
    status: "active",
    name: $name,
    type: $type,
    dose: $dose,
    times: $times,
    purpose: null,
    started: $started,
    stopped: null,
    stopped_reason: null,
    notes: null
  }' >> data/supplements.ndjson
```

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

---

## Refresh Trello dashboard (fail-safe)

After **any successful add or stop commit**, refresh the dashboard so the `💊 Supplements` list reflects the new state immediately. List intent never triggers a render.

```bash
python3 automations/scripts/trello_render.py 2>&1
```

On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set in `.env`, skip this step. For dose-change chains (stop + add), run the render once after the chained commit, not twice.

---

## Rules

- Always use `jq` — never `echo >>`, `sed`, or string concatenation for record writes.
- Auto-commit for **add** and **stop**. **List** never commits.
- Always run `scripts/validate.sh` after a write and before committing. If red, revert the write.
- After every add/stop commit, run the Trello render fail-safe (see section above).
