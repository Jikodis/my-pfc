# TRMNL plugins — operational rules

Everything under `trmnl/` is source for TRMNL e-ink display plugins. One folder per
plugin, in the layout `trmnlp` expects. The design authority is the **`trmnl` skill**,
which ships as the Claude Code plugin `trmnl@trmnl-agent-skills` and carries TRMNL's own
production agent prompts verbatim. The PFC-side workflow is
[`/pfc-trmnl-plugin`](../.agents/skills/pfc-trmnl-plugin/SKILL.md). Architecture and the
why behind the choices: [`docs/trmnl-plugins.md`](../docs/trmnl-plugins.md).

**Do not restate TRMNL's own documentation in this repo.** The plugin carries the design
system verbatim and auto-updates; TRMNL's docs are the authority on limits, endpoints,
and framework classes. Files here should only hold what is specific to *this* system —
which repo data feeds which screen, the decisions already made, and the mistakes already
paid for. Anything copied out of TRMNL's docs becomes a second source of truth that
silently goes stale.

## Read the design system before writing markup

**Before writing or editing any `.liquid` file, load the `trmnl` skill and read its
`agent_prompt.md` reference.** Do not write TRMNL markup from memory or general HTML
instinct — the framework has hard rules that silently produce broken screens on the
device:

- No inline `style="..."`, no `<style>` blocks. Framework classes only.
- No emoji anywhere in markup — e-ink has no emoji font, they render as empty boxes.
  Use text markers (`[x]` / `[ ]`) instead.
- Content `<img>` needs `class="image image-dither"` or it renders washed out.
- A status light is a shape plus the word: square RED, triangle YELLOW, circle GREEN. Render
  it with the `status_shape` template (inline SVG) copied from `pfc-areas/src/shared.liquid`;
  the payload keeps the plain word so Liquid comparisons still work.
- Never wrap markup in `<div class="view view--*">` — the platform adds that wrapper.
- Use `trmnl.com` URLs, never `usetrmnl.com`.

## Private plugins only

Every plugin here is a **private plugin** on your own TRMNL account. Nothing in this
repo is destined for the public marketplace, so skip anything about plugin publication,
OAuth installation flows, `installation_url` / management URLs, or the marketplace
"Chef" linter — none of it applies. If a marketplace plugin ever becomes the goal, that
is a new decision, not a default.

**GitHub Sync is deliberately not used.** TRMNL can auto-commit a private plugin's
markup and settings to a GitHub repo on every save. It syncs *one plugin per repo*,
and it makes trmnl.com a second writer to files this repo already owns. Two write
paths to the same markup is how you lose edits. `trmnlp push` from this repo is the
only deploy path.

## Device profile

The plugins here are authored for a 16-grayscale panel (TRMNL X class):

| Property | Value |
|---|---|
| Logical render size | 1040x780 (the framework scales; author against the 800x480 view sizes) |
| Bit depth | **4-bit** |

`trmnlp` defaults PNG output to **1-bit**, which dithers every gray into dot patterns
and makes a fine screen look broken. Always render at 4-bit — `trmnl/bin/preview` does
this by default (`TRMNL_COLOR_DEPTH`, default 4). On a 1-bit device set
`TRMNL_COLOR_DEPTH=1` in `.env` instead.

Because a larger panel renders bigger than the 800x480 base view, the framework's `lg:`
responsive prefixes (`lg:value--giga`, `lg:title--base`) are the lever for using the
extra room. Author the base classes for 800x480 and add `lg:` variants where bigger
genuinely helps.

## The design bar — read like the web band, earn the slot

Every plugin, existing or new, is held to these:

- **Each screen reads like its web band: less, not more.** One headline first (the
  band's verdict or count, e.g. "0 of 4 daily habits logged today"), then only the
  rows that need a look, worst first, with everything green or on target folded into
  a count, the way the page folds it into a `<details>`. Cap rows in the builder
  (`*_ROWS` in `trmnl_home.py`) and count the rest ("N more"). Use the page's wording.
- **Blank space is fine; crowding is not.** Fill a sparse screen with bigger type
  (poster sizing), never with extra rows or columns of detail the band does not show.
- **`lg:` bumps are mandatory, not optional.** Every full view carries `lg:` variants
  one type tier up (`label lg:label--large`, `title--small lg:title--base`,
  `value--large lg:value--xxlarge`). Base classes alone render small type on a large
  panel.
- **Sparse-by-nature content gets the poster treatment.** When a screen's data is
  naturally 1–6 short lines (values, trends, front-of-mind), render it centered
  with large type (`title--xlarge`, `value--xxlarge`) instead of a small list in a
  corner.
- **Keep a status shape out of a `data-clamp` span.** The clamp engine hides the
  inline SVG; put the shape in its own span beside the clamped text.
- **A screen must earn its playlist slot.** It has to change day to day — a static
  screen goes invisible within a couple of days — and answer a question you actually
  ask. If the live data can't fill it usefully (one stale list, all-identical rows),
  fix the data or fold the screen into another plugin; don't keep a wall slot busy
  with noise.
- **Verify by reading the rendered PNG, per view.** The lint pass catches rule
  violations, not emptiness — the coverage judgment is made by looking.

## Folder layout

```
trmnl/
├── bin/trmnlp             # runtime-agnostic wrapper (gem → docker/podman/nerdctl)
├── bin/preview            # data → lint → 4-bit PNGs for one plugin
└── <plugin-name>/
    ├── .trmnlp.yml     # local dev config + generated sample merge variables
    └── src/
        ├── settings.yml            # uploaded to TRMNL by `trmnlp push`
        ├── shared.liquid           # captures shared by every view
        ├── full.liquid             # 800x480
        ├── half_horizontal.liquid  # 800x240
        ├── half_vertical.liquid    # 400x480
        └── quadrant.liquid         # 400x240
```

`_build/` is generated output and is gitignored. Never commit it.

## Data flows one way: repo → TRMNL, by polling

Plugins use `strategy: polling`. TRMNL GETs an HTTPS endpoint you host
(`automations/scripts/trmnl_serve.py`, behind a reverse proxy) that runs the payload
builder **per request**, so the screen is current as of the moment TRMNL asks. Setup:
[`docs/install/trmnl-endpoint.md`](../docs/install/trmnl-endpoint.md).

The webhook path (`trmnl_push.py <plugin>`) still works and needs no infrastructure —
keep it as the fallback, not the default.

**A change to repo data or its display rules must update every screen that shows it, in
the same session.** Before finishing any change to a data file, schema, or a rendering
rule (a new field, a new sort order, a merged/retired record, a changed status
vocabulary), grep `home_data.py` and `trmnl_home.py` for the data file and check
whether a builder reads it. If one does, update the builder and its views too — and read the rendered PNG.
This is the same obligation the Trello render has; the difference is that Trello
re-renders itself from a post-commit hook and TRMNL does not, so a stale screen is
silent. The screens drift first because nobody is looking at them while the change is
being made.

**Every plugin needs a payload builder (in `trmnl_home.py`) registered in `BUILDERS`
in `trmnl_push.py`.**
Both transports read that same registry, so a plugin folder with no builder is
half-built — the display will never update. After adding one, restart the endpoint
(`systemctl --user restart pfc-trmnl-serve`) so it loads the new code.

Do the shaping in Python, not in Liquid. The templates should iterate flat lists and
print pre-formatted values; if a template is growing `{% if %}` chains or nested
lookups, that logic belongs in the builder.

## Keep payloads small anyway

Polling has no size limit, but the discipline still applies: pre-digest in Python so
Liquid iterates flat lists. Clip strings, drop fields the view doesn't render, send
counts instead of the arrays they summarize. A screen is 800x480 — a payload much
bigger than what the screen can show means the builder is doing too little.

The **webhook fallback** does have hard limits: 12 requests/hour at 2 KB on a standard
account (30/hour at 5 KB on TRMNL+). `trmnl_push.py` enforces both. Do not raise
`TRMNL_PAYLOAD_LIMIT` to get around a fat payload — trim the builder.

**Do not wire either transport into the git post-commit hook** the way the Trello render
is wired. Polling does not need it — TRMNL pulls on its own — and a webhook push there
would burn the hourly quota during any editing session.

## The local loop

```sh
trmnl/bin/preview <plugin>            # data → lint → 4-bit PNGs in _build/
trmnl/bin/preview <plugin> --serve    # same, then live reload at http://localhost:4567
```

**Look at the PNGs before calling a view done.** `trmnlp lint` catches rule violations,
not layout that overflows, collapses, or centers when it should be left-aligned. Read
`_build/<view>.png` and check it.

**Most of the loop runs on a small server, but the PNG render often will not.** Data
refresh, lint, and `trmnlp push` all work on a 1 GB VPS, so plugin development can
happen from Claude Code anywhere. The `--png` step is the exception: it runs headless
Chrome in the container, and Chrome has to load the page inside a hard-coded 5-second
Selenium wait (`Selenium::WebDriver::Error::TimeoutError: timed out after 5 seconds`).
Once the box is swapping it cannot, and retrying does not change that; swap does not
make it fit.

So when the PNG step fails:

1. Check `free -m` **first**. Under about 300 MB available, the render will not
   succeed. Stop retrying: it is a resource wall, not a flake.
2. Fall back to reading `_build/<view>.html`. It is written before the screenshot step,
   so it exists even on failure, and it verifies structure, real data, and class names,
   everything except visual layout.
3. **Say plainly that layout is unverified.** `trmnlp lint` checks rules, not emptiness
   or overflow. "Lint passed" is not "I looked at it."
4. Render on a machine with real memory when layout matters, or push and look at the
   device.

The underlying commands, if you need them individually: `trmnl_push.py <plugin> --local`
writes sample data, then `bin/trmnlp lint` / `build --png --color-depth 4` / `serve`
from inside the plugin folder.

The sample merge variables in `.trmnlp.yml` sit below a generated marker — regenerate
them with `--local`, never hand-edit them, or the preview drifts from what the push
actually sends.

## Gotchas already paid for

- **A `.liquid` edit is not live until `trmnlp push` runs — push in the same session.**
  The repo is the source of truth but the device renders the *server's* copy, and a
  stale server copy fails silently: every poll still returns 200 while the screen
  renders empty loops. End any markup-editing session with a push, or say explicitly
  that the push is pending. `/pfc-repo-maintenance` diffs server vs repo as a backstop.
- **`bin/trmnlp` runs the container with `--pull always`.** On a nearly full disk the
  pull dies with `no space left on device` before anything renders. The cached image
  still works: run `podman run --rm -i --pull never` (or the docker equivalent) with
  the same volumes and arguments the wrapper uses.
- **A PNG with serif text, no title bar, or a blank page is a failed render, not bad
  markup.** Under memory pressure the screenshot fires before the framework CSS or its
  font loads. Check `_build/<view>.html`, then render again.
- **`trmnlp push` prompts for confirmation and dies on EOF in non-interactive runs.**
  Pipe the answer: `echo y | ../bin/trmnlp push`.
- **`.env` values with shell metacharacters must be single-quoted.** `bin/preview` and
  `bin/trmnlp` `source` the file, so an unquoted `&` in a value executes the rest of
  the line as a command and kills the script mid-run. The Python loaders strip
  surrounding quotes, so quoting is safe for both consumers.
- **`trmnlp push` writes the server's settings back into `src/settings.yml` — including
  the live `polling_headers` bearer token and a block of empty `oauth_*` keys.** After
  every push, `git restore trmnl/*/src/settings.yml` before committing anything; never
  commit the round-tripped file. The only server write-back worth keeping is the `id:`
  a *first* push assigns a new plugin — keep that line, strip the rest.
- **Grid children need the `col` class.** `<div class="col--span-7">` lays its children
  out in a row; `<div class="col col--span-7">` stacks them. A section heading that
  lands beside its list instead of above it is this bug.
- **`layout--col` centers direct children.** Wrap a view's content in `<div class="col">`
  to get left-aligned headings.
- **`.meta` is required inside `.item`, even when empty** — it carries the flex alignment.
- Habit display names come from the habit **id** (`morning-walk` → "Morning walk"), not
  `description`. Descriptions run a paragraph long and truncate into noise.

## Adding a plugin

1. Scaffold: `cd trmnl && bin/trmnlp init <plugin-name>` (or copy `pfc-today/`).
2. Set `strategy: polling` in `src/settings.yml`. Leave `polling_url` and
   `polling_headers` out of the file — they are set in the TRMNL UI, because the header
   carries a bearer token and `trmnlp push` would round-trip it through the repo. Leave
   `id:` out too until a first push assigns one.
3. Write the payload builder in `trmnl_home.py` and register it in `BUILDERS` in
   `trmnl_push.py` — **data first, before any markup.**
4. `trmnl/bin/preview <plugin>`, then read the PNGs.
5. `trmnlp push` the markup. Create the plugin in the TRMNL UI pointing at
   `https://<your-endpoint>/p/<plugin>` with the bearer header, then restart the
   endpoint so it picks up the new builder:
   `systemctl --user restart pfc-trmnl-serve`.
6. Add the plugin to the tables in `docs/trmnl-plugins.md` and `trmnl/README.md`.

**One screen per web band.** The screens mirror the home page's bands in its order,
built in `automations/scripts/trmnl_home.py` from `home_data.build_home`, the same
call the page makes. Do not compute a number for a screen that the page does not
show; add it to `home_data.py` so both surfaces get it.
