---
name: pfc-focus
description: View, add, park, or retire Current Focus items — the capped, traffic-lit list of what the user is actively pursuing this quarter. Use when the user says "show my focus", "current focus", "add a focus", "park X", "pause X", "graduate X to a foundation", "retire focus", "re-pick focuses", or "what am I focusing on right now".
---

# Current Focus

Manage `4-focus/_data/focus.ndjson` — the **Focus** altitude of VAVFPAH. Four altitudes stack under each Area (Area → Vision → Focus → Habit); this skill owns Focus: the scarce, capped, traffic-lit set of what's actively being pursued **this quarter**. Human-facing intro: [`../../../4-focus/README.md`](../../../4-focus/README.md).

## Model (hold this exactly)

- **Three tiers** (config: `config/focus.yaml`):
  - 🧱 **Foundations** — always-on keystones (soft cap ~4). Almost always 🟢.
  - 🎯 **Active Pursuits** — this quarter's push (**hard cap 6**).
  - 🎧 **Currently Consuming** — book (1) · podcasts (3) · audiobook (1), via `medium`.
- **Traffic light** `status`: **DERIVED, never hand-typed.** `python3 automations/scripts/focus_status.py` computes it from the primary vehicle habit's trailing-28-day rate — 🟢 ≥70% · 🟡 40–69% · 🔴 <40%. 🔴 means **not happening**, not "paused."
- **Parked** `parked: true`: a deliberate, guilt-free stop. Shows 🅿️, excluded from the pursuit cap and from the forcing function. This is what "paused" means here; `red` does not.
- **Vehicles** `habits: [...]`: ordered habit ids from `config/habit_schema.yaml`. The **first is primary and drives the light**; the rest are supporting — displayed, but they do not set the headline. Every active foundation/pursuit must have at least one; `scripts/validate.sh` fails otherwise. A focus with no vehicle is a wish.
- **Impact / urgency** `impact` + `urgency` (`high|medium|low`), shown as a two-letter code with impact first: `AA` … `CC`. A tie-breaker on short days — a `BB` focus yields to an `AA` focus without being deleted.
- **Horizon**: a quarter. Re-picked quarterly; `quarter` field = `YYYY-QN`.
- **Area backbone**: every focus names one `area` matching a `2-areas/` folder. `link` (nearest real parent: vision slug / habit id / project id) is optional — one hop up, recorded only when real, never invented. `link` points **up**; `habits` points **down**. Both may be set.
- **Landing** (`landing`): the *when / where / trigger*, anchored to an already-running state plus a place and a starting ritual — not a bare clock time. A pursuit with no landing is a wish; flag it.
- **Graduation**: a pursuit that has become automatic → move `tier` to `foundation` (frees a pursuit slot). Finished or abandoned → set `retired_date`.

## Date + id derivation (run first for any write)

```bash
D=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
M=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%-m'); Q="$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y')-Q$(( (M-1)/3 + 1 ))"
N=$(printf "%03d" $(( $(grep -c "\"focus-${D//-/}-" 4-focus/_data/focus.ndjson) + 1 )))
ID="focus-${D//-/}-$N"
```

## VIEW ("show my focus", "what am I focusing on")

```bash
python3 automations/scripts/focus_status.py
```

Render grouped by tier in order 🧱 → 🎯 → 🎧, sorted by `code` within each tier (red first as a tiebreak), each header showing `count / cap`. One table per tier: `Code | ● | Title | Rate | Landing`, where `●` is 🟢/🟡/🔴 or 🅿️ for parked, and `Rate` is `<completed> of <target> (<pct>%)` from the primary vehicle.

Show supporting vehicles as an indented line under their focus — they are not cosmetic. Flag in one line each, never a paragraph:

- any focus with `weeks_red >= 2` → the four-way choice below
- any **supporting** vehicle red for 2+ weeks → the same choice applied to that habit alone; the focus is untouched
- any pursuit with no landing

Warn 🟡 if active pursuits (non-parked, non-retired) > 6, or a `medium` exceeds its cap (book 1 / podcast 3 / audiobook 1). Never truncate — curate by parking or retiring.

## ADD ("add a focus", "make X a pursuit")

Gather: `tier`, `area` (must be a `2-areas/` folder), `title`, **`habits`** (at least one for foundation/pursuit — first is primary; if no habit exists yet, create one in `config/habit_schema.yaml` first, with a `ramp` block), **`impact`** and **`urgency`** (`high|medium|low`), optional `link` (nearest real parent), optional `medium` (consuming only), optional `landing`. `status` is derived, not gathered. **Before adding a `pursuit`, check the cap:**

```bash
pcount=$(jq -c 'select(.tier=="pursuit" and .parked!=true and .retired_date==null)' 4-focus/_data/focus.ndjson | wc -l | tr -d ' ')
```

If `pcount` is already 6, do NOT silently exceed — surface the conflict, show the current 6, and ask the user to retire one, pause one, or graduate one to a foundation first. Scarcity is the feature.

For a pursuit, ask for the **landing** before writing: what's already running when this fires, where does it happen, what starts it. If the user can't name one, add the focus anyway but mark it in chat as landing-less so the weekly drift check catches it.

Append (derive `ID` / `D` / `Q` first). `link`, `landing`, and `medium` become `null` when the shell variable is empty — use `if … then null else … end`, **never** `select(.!="")`, which emits an empty stream and silently drops the whole record:

```bash
jq -cn --arg id "$ID" --arg tier "$tier" --arg area "$area" --arg title "$title" \
  --arg medium "$medium" --arg status "green" --arg q "$Q" --arg landing "$landing" \
  --arg lt "$link_type" --arg lr "$link_ref" --arg created "$D" \
  --arg impact "$impact" --arg urgency "$urgency" --argjson habits "$habits_json" '
  {id:$id, tier:$tier, area:$area, title:$title,
   medium:(if $medium=="" then null else $medium end),
   link:(if $lr=="" then null else {type:$lt, ref:$lr} end),
   status:$status, quarter:$q,
   landing:(if $landing=="" then null else $landing end),
   habits:$habits, impact:$impact, urgency:$urgency, parked:false,
   created:$created, retired_date:null, notes:null}' >> 4-focus/_data/focus.ndjson
```

`habits_json` is a JSON array string, e.g. `habits_json='["practice-guitar"]'`. `status` is seeded `green` and immediately overwritten by the first `focus_status.py --write`.

Verify the append landed (`tail -1 4-focus/_data/focus.ndjson | jq .`) before reporting success — a malformed `jq -cn` writes nothing at all rather than erroring.

## PARK / UNPARK ("pause X", "X is going again")

`status` is derived and cannot be hand-set — `focus_status.py --write` overwrites it every check-in. To deliberately stop a focus, park it:

```bash
tmp=data/.jq_update.tmp
jq -c --arg id "$ID" --argjson p true 'if .id==$id then .parked=$p else . end' \
  4-focus/_data/focus.ndjson > "$tmp" && mv "$tmp" 4-focus/_data/focus.ndjson
```

Unpark with `--argjson p false`. Parking frees a pursuit slot; letting a focus go red does not. Refer to the focus by title in chat; resolve its id with `jq -r 'select(.title|test("<words>";"i")) | .id' 4-focus/_data/focus.ndjson`.

## RED TWO WEEKS RUNNING — the four-way choice

Fires from the weekly `focus-accuracy` review when `weeks_red >= 2`, or on demand. Present the focus with its code, rate, and landing inline — never make the user recall them — then exactly four options. There is deliberately **no fifth "keep trying" option**; that is the whole mechanism.

1. **Re-land it** — the anchor is wrong. Rebuild it anchor-first per `docs/calendar-scheduling.md` (name the running state it bends out of, then the place, then the clock).
2. **Lower it to something real** — drop `ramp.starter` on the primary vehicle in `config/habit_schema.yaml`. The bar was never clearable.
3. **Park it** — `parked: true`. Deliberate, guilt-free, frees a pursuit slot.
4. **Retire it** — set `retired_date`. It's over.

Apply the same four options to any **supporting** vehicle habit red 2+ weeks, scoped to that habit alone — the focus itself is untouched. Cap at **two forced choices per session**; the rest surface next week.

Do not editorialize about the red. State the number, give the four options, take the answer. Full rationale: [`docs/habit-mechanics.md`](../../../docs/habit-mechanics.md) § The four-way choice.

## GRADUATE ("that's automatic now → foundation")

Change tier (frees a pursuit slot):

```bash
tmp=data/.jq_update.tmp
jq -c --arg id "$ID" 'if .id==$id then .tier="foundation" else . end' \
  4-focus/_data/focus.ndjson > "$tmp" && mv "$tmp" 4-focus/_data/focus.ndjson
```

## RETIRE ("retire X", "drop X")

```bash
tmp=data/.jq_update.tmp
jq -c --arg id "$ID" --arg d "$D" 'if .id==$id then .retired_date=$d else . end' \
  4-focus/_data/focus.ndjson > "$tmp" && mv "$tmp" 4-focus/_data/focus.ndjson
```

Retired focuses stay in the file (history) but drop out of the render and the caps.

## QUARTERLY RE-PICK ("re-pick focuses")

The deliberate swap — the one moment the list is allowed to change wholesale.

1. Run `focus_status.py` first and show the full set — code, light, rate, landing — before asking anything; never make the user assess focuses they can't see.
2. For each pursuit, take one decision: **keep** · **park** · **retire** · **graduate to a Foundation** (easing is the ramp's job now, not a hand-set yellow). Re-confirm `impact` and `urgency` on each — the ranking is data and it drifts.
3. Confirm the Foundations still hold — anything that has stopped being automatic goes back to a pursuit or gets retired.
4. Build or refresh each surviving pursuit's **landing** against the calendar and `0-me/schedule-patterns.md`. Name the anchor (the already-running state it bends out of) before any clock time — see `docs/calendar-scheduling.md` § The anchor rule.
5. Update `quarter` on every kept focus to the new `YYYY-QN`.
6. Respect the hard cap of 6 pursuits at the end of the pass. If the new list has 7, the pass isn't finished.

## After any write — fail-safe render

```bash
python3 automations/scripts/trello_render.py 2>&1 || echo "🟡 Trello render failed (non-blocking)"
```

Any error logs 🟡 and continues; it never blocks the write. Skip entirely if `TRELLO_DASHBOARD_BOARD_ID` is not set in `.env`. Then:

```bash
scripts/validate.sh
git add 4-focus/_data/focus.ndjson
git commit -m "focus: <action>"
git push
```

Focus edits auto-commit — same class as habit and task logging.

## Out of scope

- Daily 2+1 task picks — that's `daily-focus.ndjson` and `/pfc-pick-tasks`, a different thing entirely despite the shared word.
- Creating calendar events. The landing is a written anchor; if the user wants it on the calendar, hand off to `/pfc-schedule-focus` and follow `docs/calendar-scheduling.md`.
