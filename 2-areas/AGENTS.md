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
   echo "tasks:"; jq -c --arg a "$AREA" 'select(.area == $a)' 5-actions/_data/tasks.ndjson
   echo "projects:"; jq -c --arg a "$AREA" 'select(.area == $a)' 4-projects/_data/projects.ndjson
   echo "insights:"; jq -c --arg a "$AREA" 'select(.area == $a)' data/insights.ndjson
   echo "habits:"; grep -c "area: $AREA" config/habit_schema.yaml || echo 0
   echo "visions:"; grep -l "area:.*$AREA" 3-visions/*.md 2>/dev/null || true
   ```
   If anything references the area, fix those references first (re-assign to a different area, or delete the records too) before removing the folder.

3. **On a fresh install (no references yet), deletion is free.** Surface this to the user during `/pfc-onboarding areas/areas` — pruning is healthier than aspiration, and the early window is the easiest time to prune.

4. **Renames are file moves + reference rewrites.** `mv 2-areas/old 2-areas/new` then update every `area: old` to `area: new`. Validator catches missed refs.

## Append patterns

```bash
# Life-wheel monthly rating
THIS_MONTH=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m')
jq -cn --arg m "$THIS_MONTH" --arg a "career" --argjson r 7 \
  '{month:$m, area:$a, rating:$r}' >> 2-areas/_data/life-wheel.ndjson
```

## See also

- [`README.md`](README.md) — human-facing intro + customization recipes.
- Repo-root [`AGENTS.md`](../AGENTS.md) § System structure — VAVPAH framing.
