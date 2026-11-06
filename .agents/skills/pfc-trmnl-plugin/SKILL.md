---
name: pfc-trmnl-plugin
description: Build, edit, preview, or deploy a TRMNL e-ink dashboard plugin from PFC repo data. Use when the user says "TRMNL", "build a TRMNL plugin", "e-ink dashboard", "put X on my TRMNL", "show my 2+1 on the display", "update the TRMNL screen", "push to TRMNL", or asks for a wall-display view of anything in the system.
---

# Build a TRMNL plugin

TRMNL is the ambient e-ink surface for the PFC system — the screen on the wall, as
opposed to Trello on the phone. This skill covers the PFC-side workflow: deciding what
goes on the screen, building the payload from repo data, and shipping it.

**The markup authority is a separate skill.** Load the **`trmnl` skill** (Claude Code
plugin `trmnl@trmnl-agent-skills`) and read its references before writing any Liquid. Do
not write TRMNL markup from general HTML instinct — the framework has hard rules (no
inline styles, no emoji, `image-dither`, no `view` wrapper) that fail silently on the
device. If the skill is missing, install it once: `claude plugin install
trmnl@trmnl-agent-skills`.

Background and the architecture decisions: [`docs/trmnl-plugins.md`](../../../docs/trmnl-plugins.md).
Folder rules: [`trmnl/AGENTS.md`](../../../trmnl/AGENTS.md).

## When this skill triggers

- "build a TRMNL plugin", "TRMNL", "e-ink dashboard", "the display"
- "put my 2+1 / habits / focus on the screen"
- "push to TRMNL", "update the TRMNL screen", "the display is stale"

## Pre-flight

| Check | Command / where |
|---|---|
| A runtime for `trmnlp` exists | `trmnl/bin/trmnlp` resolves gem → docker/podman/nerdctl |
| `TRMNL_API_KEY` set (only for push/clone) | `.env` |
| `TRMNL_SERVE_TOKEN` set (only for the polling endpoint) | `.env` on the server |
| `TRMNL_WEBHOOK_<PLUGIN>` set (only for a live webhook push) | `.env` |

Missing env vars are not a reason to stop local work — everything through
`build --png` works offline. Say which step is blocked and keep going.

## Workflow A — new plugin

### Step 1 — Decide what goes on the screen (do not skip)

A screen shows one thing. Before any scaffolding, settle:

- **What question does a glance answer?** ("What am I supposed to be doing today?")
- **Does it change day to day?** If not, it goes invisible within a couple of days and
  is the wrong candidate.
- **Is the underlying data actually there?** A screen fed by an empty NDJSON file
  renders an honest blank. Check the source first — `docs/trmnl-plugins.md` has a table
  of what each shipped screen needs.
- **What is the smallest field set that answers it?** The webhook payload cap is 2 KB.

If the user's ask is broad ("put my dashboard on TRMNL"), name two or three concrete
candidate screens and let them pick. Do not port the Trello board wholesale — Trello
has ~20 lists because tapping is cheap; a screen has one.

### Step 2 — Build the data first (HARD GATE)

TRMNL's own agent rules make this non-negotiable: never write markup against data you
have not seen. In this repo that means the payload builder comes first.

1. Write the builder and register it in `BUILDERS` in
   `automations/scripts/trmnl_push.py`. The screens mirror the web home page's bands one
   for one, so a screen for a band goes in `automations/scripts/trmnl_home.py` and reads
   `home_data.build_home` — the same data the page shows. If the number is not on the
   page yet, add it to `home_data.py` first so both surfaces get it. Only a screen with
   no band of its own (like Front of mind or Week) reads NDJSON directly in
   `trmnl_push.py`. Either way, return a flat dict.
2. Pre-digest everything — clip strings, pre-compute counts and formatted values, drop
   fields the view will not render. Nothing deeper than two levels.
3. Run it and read the output:

   ```sh
   python3 automations/scripts/trmnl_push.py <plugin> --dry-run
   ```

4. **Confirm the byte count is under the limit** and the values look right. If it is
   over, trim the builder — do not raise `TRMNL_PAYLOAD_LIMIT` (that is only correct
   on a TRMNL+ account).

Do not proceed to markup until the payload is correct.

### Step 3 — Scaffold the plugin folder

```sh
cd trmnl && bin/trmnlp init <plugin-name>
```

Or copy `trmnl/pfc-today/` as a starting point — it is a working plugin with all four
views. Then in `src/settings.yml`: set `name`, `strategy: polling`, and a
`refresh_interval`. Leave `id`, `polling_url`, and `polling_headers` out of the file.

Wire the sample data in:

```sh
python3 automations/scripts/trmnl_push.py <plugin> --local
```

This writes the real payload into `.trmnlp.yml` below a generated marker. Never
hand-edit that block — regenerate it, or the preview drifts from what gets pushed.

### Step 4 — Write the markup, one view at a time

Load the `trmnl` skill and read its `agent_prompt.md` reference first, then jump to the
relevant section of its `template_guide.md`.

Plan the space before writing HTML — what blocks, what fractions, what gets cut at
smaller sizes. Build `full.liquid` first, then adapt (don't shrink) for the others.

**Hold every view to the design bar in `trmnl/AGENTS.md` § "The design bar"**: full
views fill the screen (no more than about a third blank), `lg:` type bumps are
mandatory, sparse content gets poster-sized centered type, no truncation while the
screen has blank space, and the screen must earn its playlist slot with data that
changes day to day.

| View | Size | Content height |
|---|---|---|
| `full` | 800x480 | ~320px |
| `half_horizontal` | 800x240 | ~144px |
| `half_vertical` | 400x480 | ~368px |
| `quadrant` | 400x240 | ~144px |

Gotchas this repo has already hit:

- Grid children need the `col` class: `<div class="col col--span-7">`, not
  `<div class="col--span-7">`. Without it the children lay out in a row.
- `layout--col` centers its direct children — wrap content in `<div class="col">` for
  left-aligned headings.
- `.meta` is required inside `.item` even when empty.
- Completion state is `[x]` / `[ ]` text, never emoji.

### Step 5 — Preview and look at it

```sh
trmnl/bin/preview <plugin>            # refresh data → lint → 4-bit PNGs in _build/
trmnl/bin/preview <plugin> --serve    # same, then live reload at http://localhost:4567
```

**Read every `_build/<view>.png` before calling a view done.** Lint checks rules, not
layout — it will happily pass a heading that centered itself or a list that overflowed.
Iterate: fix, rebuild, look again. While looking, apply the design bar
(`trmnl/AGENTS.md`): if the full view is more than about a third blank, or text is
truncated while blank space remains, the view fails — fix the layout or the builder
caps before moving on.

Renders at 4-bit to match a 16-grayscale panel. `trmnlp`'s own default is 1-bit, which
dithers every gray into dot patterns and makes a fine screen look broken — do not judge
a layout from a 1-bit render.

### Step 6 — Deploy

1. Upload the markup:

   ```sh
   cd trmnl/<plugin> && ../bin/trmnlp push
   ```

   Add the returned `id:` to `src/settings.yml` — without it every push creates a
   *new* plugin instead of updating this one.

   **Then clean the round-trip:** the push writes the server's settings back into
   `src/settings.yml`, including the live `polling_headers` bearer token and empty
   `oauth_*` keys. Keep only the `id:` line; `git restore` (or strip) the rest before
   any commit — committing the round-tripped file leaks the token into git history.
2. Restart the polling endpoint so it loads the new builder:

   ```sh
   systemctl --user restart pfc-trmnl-serve
   ```

3. In TRMNL: Plugins → Private Plugins → New, with Strategy = Polling, Polling URL
   `https://<your-endpoint>/p/<plugin>`, and Polling Headers
   `Authorization: Bearer <TRMNL_SERVE_TOKEN>`. Headers go in the UI, never in
   `settings.yml` — `trmnlp push` would round-trip the token through the repo.
4. Hit **Force Refresh** on the plugin settings page to fetch immediately instead of
   waiting for the device's next cycle.
5. Add a row to the plugin table in `docs/trmnl-plugins.md` and `trmnl/README.md`.

Endpoint setup, if it does not exist yet: `docs/install/trmnl-endpoint.md`. The webhook
fallback (`trmnl_push.py <plugin>` with `TRMNL_WEBHOOK_<PLUGIN>` in `.env`) still works
and needs no infrastructure.

## Workflow B — edit an existing plugin

1. Refresh the sample data: `trmnl_push.py <plugin> --local`.
2. Read the current markup for the views you're changing.
3. If the change needs new fields, **update the builder first** and re-run `--local`.
4. Edit → `lint` → `build --png` → read the PNGs.
5. `../bin/trmnlp push`, then restart the endpoint if the builder changed.

## Workflow C — the screen is stale

Diagnose in order:

1. `python3 automations/scripts/trmnl_push.py <plugin> --dry-run` — is the payload
   right, and is it under the limit?
2. On polling: is the endpoint up (`curl https://<endpoint>/p/<plugin>` with the bearer
   header) and is the server's clone current (`pfc-repo-sync.timer`)?
   On webhook: push it. A `429` means the hourly quota is spent; wait it out rather
   than forcing.
3. TRMNL **skips screen generation when merge variables are unchanged** — if the data
   genuinely did not change, that is correct behavior, not a bug. Force Refresh on the
   plugin settings page overrides it.
4. Check the device refreshed — `refresh_interval` in `src/settings.yml` and the
   device's own refresh-rate setting govern how often it pulls.

## Tuning the pulse screen

`pfc-pulse` holds no thresholds — it renders what
`automations/scripts/pulse.py` computes. If the user asks to change what the pulse
tracks or what "good" means, change the bands under `health.pulse` in
`config/automation_config.yaml`, or the levers in `pulse.py` — never the Liquid, and
never a second copy in the builder. Ground the change in their own data: run
`/pfc-analyze-trends` first and use what actually separates their good days from their
average ones.

The exception is the exercise row on `pfc-pulse`, which is a today-action rather than a
sleep lever: it reads `EXERCISE_HABIT_ID` / `EXERCISE_LABEL` in
`automations/scripts/pfc_writes.py`, the one setting the web page shares. Point it at
the user's own movement habit id.

## Push cadence

`trmnl_push.py` is run on demand. **Do not add either transport to the git post-commit
hook.** Trello's render is wired there because Trello has no meaningful rate limit;
polling doesn't need the hook at all, and a webhook push there would burn the 12/hour
quota in minutes during an editing session, leaving the screen stale behind a 429.

## Related

- the `trmnl` skill (plugin `trmnl@trmnl-agent-skills`) — the design system and TRMNL's own agent rules
- `docs/trmnl-plugins.md` — architecture, limits, setup, references
- `docs/install/trmnl-endpoint.md` — standing up the polling endpoint
- `trmnl/AGENTS.md` — folder-level rules
- `/pfc-render-trello` — the phone-surface counterpart
