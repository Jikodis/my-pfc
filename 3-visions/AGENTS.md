# Agents — visions folder

Folder-scoped operational rules for any agent reading or writing in `3-visions/`. Cross-cutting rules live in the repo-root `AGENTS.md`.

## File summary

| Path | Shape | Mutability |
|---|---|---|
| `<slug>.md` | One vision per file | Mutable; edit when state changes (active → paused → fulfilled → abandoned) |
| `_template.md` | Starter shape for new visions | Read-only template |
| `_data/vision-brainstorm.ndjson` | The brainstorm that feeds vision creation — one record per idea | Mutable; written via `/pfc-vision-brainstorm` |

Visions themselves have no NDJSON registry — each is a markdown file with metadata (area, status, locus of control, leading indicators) in its front matter. The *brainstorm* that feeds them **is** NDJSON: one record per idea with a `status` (`raw` / `promoted` / `done` / `dropped`) and a `became` lineage pointer. Write it through `jq` and the atomic temp-file pattern, never a raw append or a `sed` edit.

## Hard rules

1. **No deadline field, ever.** Visions express direction, not delivery dates. If a user describes a vision with a deadline ("be promoted to Staff Engineer by Q3 2027"), redirect — what they have is a SMART goal, which belongs in `5-projects/` or as a task, not as a vision. This is the strongest pushback in the system.

2. **0–2 active visions per area.** Most areas should have zero. When the user adds a third, surface the cap and ask which existing vision becomes `paused` or `abandoned`.

3. **Each vision belongs to exactly one area.** The `area:` field must match a folder under `2-areas/`.

4. **Locus of control matters.** Outside-control visions (depends on other people, market, luck) get *leading indicators* only, never deadlines. Inside-control visions (skill-building, habit-formation) can carry a rough horizon but still no hard deadline. `/pfc-add-vision` walks the user through this distinction.

5. **Draft, don't interrogate.** When adding a vision, read the user's values, the area statement, and their `raw` brainstorm records, then write a complete first draft of every field and ask only for edits. A blank-page Q&A about "what does fulfilled look like" is the slowest possible path to a vision file.

6. **Drift is about relevance, not link count.** An active vision with zero linked projects, focuses, or habits is resting, not drifting — the caps elsewhere in the system guarantee most visions are bare at any moment. The real drift signal is a vision that no longer represents where the user wants to go.

## Vision-link queries

Projects, habits, and focuses may point at a vision slug. When reviewing a vision:

```bash
# Projects linked to a vision
jq -c --arg v "vision-slug" 'select(.vision == $v)' 5-projects/_data/projects.ndjson

# Current Focus items linked to a vision
jq -c --arg v "vision-slug" 'select(.link != null and .link.type=="vision" and .link.ref==$v)' 4-focus/_data/focus.ndjson

# Habits are defined in config/habit_schema.yaml (YAML, not NDJSON) — use a yaml parser, not jq.
```

## See also

- Repo-root [`AGENTS.md`](../AGENTS.md) § Long-term vision — design rationale and interaction patterns.
- [`README.md`](README.md) — human-facing intro.
- [`../4-focus/README.md`](../4-focus/README.md) — the quarter-horizon layer one hop below.
- `/pfc-add-vision` and `/pfc-vision-brainstorm` — the canonical write paths.
