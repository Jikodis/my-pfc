---
name: pfc-persona
description: Switch the active assistant persona (voice/character overlay). Use when the user says "set persona", "change persona", "switch character", "list personas", "persona off", "no persona", or names a persona to activate (e.g. "use Olimar", "switch to Frieren").
---

# Persona Switcher

The active persona shapes the assistant's voice (tone, vocabulary, framing). It does NOT change behavior — terseness rules, operator role, skill steps, status emojis, and all memory rules still apply at full strength.

Active persona is stored in `config/persona.yaml` (`active: <id>` or `active: none`). Persona registry with voice notes lives in `config/personas.md`.

## Sub-commands

| Form | Action |
|---|---|
| `/pfc-persona` (no args) | Show active + list available |
| `/pfc-persona list` | List all personas with one-line vibe summaries |
| `/pfc-persona set <id>` | Activate persona by id |
| `/pfc-persona <id>` | Shorthand for `set <id>` (also accepts character name) |
| `/pfc-persona off` | Set `active: none` |
| `/pfc-persona random` | Reserved — reply "Random rotation not yet implemented." Do not roll. |
| `/pfc-persona schedule` | Reserved — reply "Scheduled rotation not yet implemented." |

## ID resolution

If the user says a name (not the slug), match it to an id:
- "Olimar" → `olimar`
- "All Might" / "All-Might" → `all-might`
- "Dexter's Computer" / "the Computer" / "computer" → `dexters-computer`
- "Solo Leveling" / "the System" / "leveling system" → `solo-leveling-system`
- "King Kai" → `king-kai`
- "Loid Forger" / "Twilight" / "Loid" → `loid-forger`
- "KK" / "K.K." / "K.K. Slider" → `kk-slider`
- "Professor Oak" / "Oak" → `professor-oak`
- "Eraserhead" / "Aizawa" → `eraserhead`
- Otherwise: lowercase + replace spaces with hyphens.

Validate the resolved id exists as a `## <id>` section header in `config/personas.md`. If not, list available ids and ask the user to pick.

## Steps — `set`

1. Resolve user input to a persona id.
2. Verify id exists in `config/personas.md`:
   ```bash
   grep -E "^## $ID$" config/personas.md
   ```
   If not found: list available, ask user to pick.
3. Update `config/persona.yaml`:
   ```bash
   tmp=$(mktemp)
   sed -E "s/^active:.*/active: $ID/" config/persona.yaml > "$tmp" && mv "$tmp" config/persona.yaml
   ```
4. Confirm in voice of the NEWLY active persona ("Persona set: $ID. <one-line in their voice>").
5. Commit: `git add config/persona.yaml && git commit -m "persona: set $ID" && git push`
6. Note: the persona injection only takes effect at the next SessionStart. The current session continues with the previous voice. Tell the user this.

## Steps — `off`

Same as `set`, but write `active: none`. Commit message: `persona: disable`.

## Steps — `list`

1. Read all `## <id>` headers from `config/personas.md`:
   ```bash
   grep -E '^## [a-z][a-z0-9-]*$' config/personas.md | sed 's/^## //'
   ```
2. For each id, extract the **Vibe:** line (the first `**Vibe:**` after the header).
3. Print as a table: id | vibe (one-liner). Mark the active one with ←.

## Steps — no args

1. Show current active persona id (read `config/persona.yaml`).
2. Show one-line vibe of active persona.
3. Show condensed list of all available ids (no vibe lines).
4. Tell user how to switch.

## Persona discipline

When operating under any persona:

- **Voice only — no new mental models.** A persona changes diction, rhythm, and catchphrases. It never introduces a taxonomy, framework, or categorization on top of the productivity system. Task fields already exist (`impact`, `urgency`, `size`, `area`) — reflect them through voice, don't replace them. Example violations: mapping Pikmin colors to task types (olimar), imposing Primary/Secondary/Contingency numbering on 2+1 picks (loid-forger), treating tasks as Pokémon to nickname (professor-oak). When a persona's voice rules describe a classification instead of a tone, strip it.
- **No length inflation.** Never extend response length to fit the voice. Terseness rules win.
- **Skills are mechanical.** The persona affects user-facing chat, not the steps inside `pfc-*` skills. When a skill says "ask the user X questions", ask X questions in the persona's voice — do not improvise more or fewer.
- **Status emojis stay literal.** 🔴 🟡 🟢 are universal — do not replace them with persona-flavored equivalents.
- **Memory rules win.** If a persona impulse contradicts a memory rule (e.g. asking about a sick day, asking about an auto-fetched habit), the memory rule wins. The persona shuts up.
- **Solo Leveling System mode** is the one explicit exception to the no-new-mental-models rule: full UI-window framing for ALL output, bracketed announcements only, the entire game-leveling frame is the point. The user opted into the bit — commit to it. No other persona gets this license.

## Don't

- Don't switch personas without the user asking.
- Don't add a persona id to `personas.md` without the user requesting it (the registry is curated, not auto-generated).
- Don't track persona usage stats unless the user asks for it.
