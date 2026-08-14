# Agents — focus folder

Folder-scoped operational rules for the **Focus** layer (VAVFPAH position 4, between Visions and Projects). Cross-cutting rules live in the repo-root `AGENTS.md`.

## File summary

| Path | Shape | Mutability |
|---|---|---|
| `_data/focus.ndjson` | One Current Focus per line (tier · area · status · habits · landing) | Mutable in place (`parked`, `tier`, `retired_date`; `status` is written only by `focus_status.py --write`); managed by `/pfc-focus` |

Schema: `config/focus_schema.yaml`. Tier caps: `config/focus.yaml`. Validated by `scripts/validate.sh`.

## The model

- **Three tiers** (`config/focus.yaml`): 🧱 **Foundations** (soft ~4 — always-on keystones), 🎯 **Active Pursuits** (**hard cap 6** — this quarter's push), 🎧 **Currently Consuming** (per-medium: book 1 · podcast 3 · audiobook 1).
- **Traffic light** `status`: **DERIVED** by `automations/scripts/focus_status.py` from the primary vehicle habit's trailing-28-day rate — 🟢 ≥70% · 🟡 40–69% · 🔴 <40%. Red means **not happening**; a deliberate stop is `parked: true` (excluded from the pursuit cap and the forcing function).
- **Vehicles** `habits: [...]`: ordered habit ids; the first is primary and drives the light. Required for every active foundation/pursuit (validated); `consuming` may be `[]`.
- **Impact / urgency**: `high|medium|low` each, rendered as a two-letter code (`AA`…`CC`, impact first) that sorts every focus surface.
- **Horizon**: a quarter. Re-picked quarterly; the `quarter` field is `YYYY-QN`.
- **Area backbone**: every focus names exactly one `area` matching a `2-areas/` folder. The optional `link` points at the nearest real parent (vision slug / habit id / project id) — one hop up, recorded only when real, never invented.
- **Landing** (`landing`): the *when / where / trigger* — anchored to an already-running state plus a place and a starting ritual, not a bare clock time. A pursuit with no landing is a wish; the reviews flag it.
- **Graduation**: a pursuit that has become automatic → move `tier` to `foundation` (frees a pursuit slot). Finished or abandoned → set `retired_date`.

## Hard rules

1. **All structured writes go through `jq`** with the atomic temp pattern: `… > data/.jq_update.tmp && mv data/.jq_update.tmp 4-focus/_data/focus.ndjson`. Never a raw append or a `sed` edit.
2. **The pursuit cap is enforced on add, soft-enforced at render.** Before adding a `pursuit`, count active (non-parked, non-retired) pursuits; at 6, surface the conflict and make the user retire, park, or graduate one. The Trello render shows everything and warns 🟡 when over cap — never silent-truncate.
2b. **Never hand-edit `status`.** It is derived; `focus_status.py --write` overwrites it on every check-in. To stop a focus deliberately, set `parked: true`.
3. **Date stamps use the local timezone**: `TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d'` for `created` and `retired_date`, and the same clock for deriving `quarter`.
4. **Retired records stay in the file.** Set `retired_date`; do not delete lines. History is what makes the quarterly re-pick honest.

## See also

- Repo-root [`AGENTS.md`](../AGENTS.md) § Area → Vision → Focus → Habit.
- [`docs/data-model.md`](../docs/data-model.md) — full field reference.
- [`README.md`](README.md) — human-facing intro.
