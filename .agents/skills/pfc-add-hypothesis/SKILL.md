---
name: pfc-add-hypothesis
description: Capture a testable hypothesis into data/hypotheses.ndjson. Use when the user says "add hypothesis", "new hypothesis", "I want to test X", "hypothesis:", "I think X causes Y, want to track it", or describes a claim they want to test against their data.
---

# Add Hypothesis

Hypotheses are testable claims about the user's life or biology. They live in `data/hypotheses.ndjson`. A hypothesis graduates to a finding when supporting data meets the bar (n ≥ 30, |r| ≥ 0.3, p < 0.01) — see `docs/data-model.md`. This skill captures the hypothesis at creation time; rich fields (`protocol`, `mechanism`, `evidence`, `findings`, `notes`) get added later through normal editing.

## When this skill triggers

- Explicit: "add hypothesis", "save as hypothesis", "track this hypothesis"
- Reflective: "I want to test whether X", "I bet X causes Y", "hypothesis:", "claim:"
- During inbox routing when a card title reads as a testable claim

If the user's input is clearly an insight (observation, no testable claim) route to `/pfc-add-insight` instead.

## Required fields

- **hypothesis** (string) — the testable claim itself, one to a few sentences. Keep the user's wording.
- **domain** (string) — short tag. Reuse existing domains:
  ```bash
  jq -r '.domain' data/hypotheses.ndjson | sort -u
  ```
  Common: `caffeine`, `exercise-timing`, `sleep`, `nutrition`. (Examples — pick your own.) Suggest a reuse before creating a new one.

## Optional at creation (ask only if user volunteered the info)

- **origin** (string) — what observation triggered the hypothesis
- **mechanism** (string) — proposed why
- **related_hypotheses** (array of `hyp-*` ids)

If the user is terse and only gave the claim, do not grill them — set optional fields to `null`. Rich fields can be filled in later.

## Steps

1. Parse hypothesis text from user input.
2. Duplicate check on a 2–3 distinctive keyword from the new hypothesis:
   ```bash
   jq -c --arg kw "KEYWORD" 'select(.status != "archived" and (.hypothesis | test($kw; "i")))' data/hypotheses.ndjson
   ```
   If a near-duplicate exists, show it and ask: extend existing / add new / cancel.
3. Get today's date: `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'`
4. Generate id: `hyp-YYYYMMDD-NNN` where NNN is one greater than the count of existing `hyp-YYYYMMDD-` ids:
   ```bash
   COUNT=$(grep -c "\"id\":\"hyp-YYYYMMDD-" data/hypotheses.ndjson || echo 0)
   ```
5. Append via jq. For absent optional fields, pass `--argjson` with `'null'` (no inner quotes); for present ones, pass `--argjson` with `'"value"'`:
   ```bash
   jq -cn \
     --arg id "hyp-YYYYMMDD-NNN" \
     --arg hypothesis "..." \
     --arg domain "..." \
     --arg started "YYYY-MM-DD" \
     --argjson origin 'null' \
     --argjson mechanism 'null' \
     --argjson related '[]' \
     '{id:$id, status:"active", hypothesis:$hypothesis, domain:$domain, started:$started, confidence:null, last_reviewed:null, origin:$origin, mechanism:$mechanism, related_hypotheses:$related}' \
     >> data/hypotheses.ndjson
   ```
6. Run validator:
   ```bash
   scripts/validate.sh
   ```
7. Commit + push:
   ```bash
   git add data/hypotheses.ndjson
   git commit -m "hypothesis: add <short title>"
   git push
   ```
8. **Refresh Trello dashboard** (fail-safe)

   If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, refresh the board so the new hypothesis shows up on `🧪 Hypothesis` immediately.

   ```bash
   python3 automations/scripts/trello_render.py 2>&1
   ```

   On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step.

9. Confirm to user: "🟢 Saved as `hyp-YYYYMMDD-NNN`. Domain: <domain>."

## Output format

One-line confirmation. Show the id so the user can reference it later.
