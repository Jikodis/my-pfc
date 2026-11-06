# Agents — areas folder

Folder-scoped operational rules for any agent reading or writing in `2-areas/`. Cross-cutting rules live in the repo-root `AGENTS.md`.

## File summary

| Path | Shape | Mutability |
|---|---|---|
| `<area>/` | One folder per life area | Add/remove freely *before* data references the area; constrained after |
| `<area>/statement.md` | Built up over time | Mutable |
| `_data/life-wheel.ndjson` | Monthly area ratings | Append-only per month |
| `_data/household-status.ndjson` | Monthly household-area ratings | Append-only per month |

## Hard rules

1. **Area folder names are the canonical area-identifier set.** Every `area:` field in `tasks.ndjson`, `projects.ndjson`, `habit_schema.yaml`, `insights.ndjson`, and elsewhere must resolve to a folder under `2-areas/`. Validator enforces this at commit time.

2. **Before deleting an area folder**, check for inbound references:
   ```bash
   AREA="legal"
   echo "tasks:"; jq -c --arg a "$AREA" 'select(.area == $a)' 6-tasks/_data/tasks.ndjson
   echo "projects:"; jq -c --arg a "$AREA" 'select(.area == $a)' 5-projects/_data/projects.ndjson
   echo "insights:"; jq -c --arg a "$AREA" 'select(.area == $a)' data/insights.ndjson
   echo "habits:"; grep -c "area: $AREA" config/habit_schema.yaml || echo 0
   echo "visions:"; grep -l "area:.*$AREA" 3-visions/*.md 2>/dev/null || true
   ```
   If anything references the area, fix those references first (re-assign to a different area, or delete the records too) before removing the folder.

3. **On a fresh install (no references yet), deletion is free.** Surface this to the user during `/pfc-onboarding areas/areas` — pruning is healthier than aspiration, and the early window is the easiest time to prune.

4. **Renames are file moves + reference rewrites.** `mv 2-areas/old 2-areas/new` then update every `area: old` to `area: new`. Validator catches missed refs.

## Area notes — the per-area second brain

Each area folder doubles as a **second brain** for that area of life: a freeform store for anything worth keeping and pulling back later. **Any content type belongs here** — this is deliberately not a "book notes" folder. For example:

- Notes on a book, talk, course, or framework
- Clippings or notes from a web article
- Your own freeform thoughts and ideas, with no external source at all
- A manual or spec sheet for something you own
- Reference lists — contact details, account numbers, measurements
- Running lists: gift ideas, restaurants to try, questions to ask at the next appointment

Do not assume a note needs an external source or a "key takeaways" structure. Much of what lands here originates in the user's own head and is whatever shape they want it to be. They will ask for it back later in exactly those terms: "what were my notes on that book?", "my gift-ideas list", "where's the manual I saved?"

### Capture

Write a markdown file at `<area>/<kebab-slug>.md`. Lead with a title and a **`Captured: YYYY-MM-DD`** line (local date, per the root date rule). Add a **Source** line only when there actually is one. Otherwise let the body be whatever the content is — prose, a list, a table, a raw dump.

**Keep the user's own framing and wording.** Do not synthesize, reword, restructure, or "improve" their phrasing. These are their notes, in their vocabulary, and the whole retrieval value depends on the words being the ones they'd search for. An agent-rewritten note is a different note. Where an external source needs summarizing, summarize the *source* and keep their commentary verbatim and clearly separated.

### Index

Add a row to that area's `<area>/CLAUDE.md` Contents table (`File | Title | What it is`). **That table is the area's retrieval index — a note that isn't in the table is effectively lost**, because the first thing any agent reads when asked "what did I save about X" is the table, not the directory listing.

Area folders ship without a `CLAUDE.md`. Create it lazily, the first time a note lands in that area:

```markdown
# <Area> — notes index

Second-brain notes for this area. Every note file gets a row here.

| File | Title | What it is |
|---|---|---|
| `<slug>.md` | <title> | <one line> |
```

These are directory READMEs, not `@AGENTS.md` import shims — the area folders have no `AGENTS.md` of their own, and the folder-scoped rules you're reading now cover all of them.

### Retrieve

When the user asks for something they stored:

- **Area known** → read that area's `CLAUDE.md` Contents table first, then open the matching file.
- **Area unknown** → search across all areas, then read the hits:
  ```bash
  grep -ril "<term>" 2-areas/*/*.md
  ```
- **Nothing matches** → say so plainly and offer to search adjacent areas, rather than reconstructing an answer from general knowledge. A confidently-invented "note" is worse than a miss.

## Append patterns

```bash
# Life-wheel monthly rating
THIS_MONTH=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m')
jq -cn --arg m "$THIS_MONTH" --arg a "career" --argjson r 7 \
  '{month:$m, area:$a, rating:$r}' >> 2-areas/_data/life-wheel.ndjson
```

## See also

- [`README.md`](README.md) — human-facing intro + customization recipes.
- Repo-root [`AGENTS.md`](../AGENTS.md) § System structure — VAVFPTH framing.
