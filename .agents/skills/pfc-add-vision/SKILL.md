---
name: pfc-add-vision
description: Add a new vision to 3-visions/. Use when the user says "add vision", "new vision", "create vision", "capture this vision", or describes a long-term direction they want to formalize.
---

# Add Vision

A **vision** sits between Areas and the Focus layer in VAVFPAH. It expresses direction without a SMART deadline. See [`../../../3-visions/README.md`](../../../3-visions/README.md) and [`../../../0-me/working-with-me.md`](../../../0-me/working-with-me.md) § Long-term vision for the why.

## When to use

- User says "I want to become an X" / "I want to..." in a way that's bigger than a project
- User says "add vision," "new vision," "capture vision"
- User describes a direction that's clearly larger than 1-3 months but they resist a deadline framing

## Constraints to enforce

- Each vision belongs to **one** area (must match a folder under `2-areas/`).
- **0–2 visions per area** at any time. If the area already has 2 active visions, flag and ask whether to retire one.
- **No deadline field, ever.** If the user offers a deadline, redirect to leading indicators.
- Status starts `active`. Other valid values: `paused`, `fulfilled`, `abandoned`.

## Steps

1. **Check the area.** Confirm or ask which area in `2-areas/` this vision serves. If the area doesn't exist, flag — visions need an area home.

2. **Check vision count for that area.**
   ```bash
   AREA="<area-name>"
   grep -l "^area: $AREA$" 3-visions/*.md 2>/dev/null | xargs -r grep -l "^status: active$" 2>/dev/null | wc -l
   ```
   If ≥ 2, surface the existing active visions for that area and ask whether to retire one before adding.

3. **Draft first — don't interrogate.** Articulating a statement, a why, and a "fulfilled looks like" from a blank page is the single hardest step in this flow, and a question-by-question interview is the slowest way through it. So do **not** ask the parts below as a Q&A. Instead: read `1-values/values.md`, `2-areas/<area>/statement.md`, any `raw` records in `3-visions/_data/vision-brainstorm.ndjson`, and `0-me/profile.md`, then **write a complete first draft of every field**, create the file, show it, and ask only for edits or confirmation. People react to a concrete draft far more easily than they generate one from zero. The list below is the *structure to fill in the draft*, not a question script — only fall back to asking when a field genuinely can't be inferred from the user's files.
   - **Slug** — short kebab-case identifier (e.g. `learn-language-x`). Suggest one based on the title; let the user confirm.
   - **Title** — plain-words name in the H1.
   - **Statement** — one sentence, what does this vision look like when it's true?
   - **Why it matters** — connection to values + motivators. Reference [`1-values/values.md`](../../../1-values/values.md).
   - **Fulfilled looks like** — concrete fingerprint by which they'll know it's done.
   - **Locus of control** — `inside` / `outside` / `mixed`, with a brief description. Push back if the user wants to set a deadline; ask instead what habits and projects increase probability.
   - **Leading indicators** — habits and projects that move probability up. List even when outcome is partly external. These are the things to actually do.
   - **Linked** (optional, can defer) — project ids, habit ids.

4. **Get today's date:** `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'`

5. **Write the file** at `3-visions/<slug>.md` using the structure in `3-visions/_template.md`. Frontmatter must contain `name`, `area`, `status: active`, `created: YYYY-MM-DD`. **Never include a deadline field.**

6. **Validate:** `scripts/validate.sh` — confirm nothing broke.

7. **Commit and push:**
   ```bash
   git add 3-visions/<slug>.md
   git commit -m "vision: add <slug>"
   git push
   ```

8. **Refresh Trello dashboard** (fail-safe)

   If `TRELLO_DASHBOARD_BOARD_ID` is set in `.env`, refresh the board so the new vision shows up on `🔭 Visions` immediately.

   ```bash
   python3 automations/scripts/trello_render.py 2>&1
   ```

   On error: print `🟡 Trello render failed (non-blocking): <error>` and continue. If `TRELLO_DASHBOARD_BOARD_ID` is NOT set, skip this step.

## Pushback patterns

- User offers a deadline ("by 2027 I want to...") → redirect: "deadlines aren't part of vision shape. What are the habits and projects that move probability up?"
- User can't articulate "fulfilled looks like" — and your draft didn't land either → that's a flag the vision is too vague. Either narrow it or capture it as a brainstorm record instead (via `/pfc-vision-brainstorm`).
- User wants to add a 3rd vision to an area that already has 2 → ask which existing vision to retire (`fulfilled`, `paused`, `abandoned`) before adding.

## Reference

- Folder: `3-visions/`
- Template: `3-visions/_template.md`
- README: `3-visions/README.md`
- Brainstorm that feeds visions: `/pfc-vision-brainstorm`
- The quarter-horizon layer below a vision: `/pfc-focus` (`4-focus/README.md`)
- Long-form rationale: `0-me/working-with-me.md` § Long-term vision
