# trmnl/

Source for the TRMNL e-ink display plugins that mirror PFC state to a screen on the
wall — the always-visible counterpart to the Trello dashboard on the phone.

| Plugin | Shows |
|---|---|
| [`pfc-today/`](pfc-today/) | Today's 2+1 and last day rating |
| [`pfc-front-of-mind/`](pfc-front-of-mind/) | Active grounding anchors, rotating on smaller views |
| [`pfc-habits/`](pfc-habits/) | Daily habits (today + 7-day counts), monthly habits vs target |
| [`pfc-pulse/`](pfc-pulse/) | Daily Pulse levers vs target, verdict, tonight's one move |
| [`pfc-focus/`](pfc-focus/) | Current Focus: pursuits with landings, foundations, consuming |
| [`pfc-projects/`](pfc-projects/) | Active projects: percent complete + next 1-2 open tasks each |
| [`pfc-trends/`](pfc-trends/) | 30-day rating chart with 7-day rolling mean + tiles (sleep, exercise, sleep debt) |
| [`pfc-week/`](pfc-week/) | Week at a Glance from the committed calendar cache |
| [`pfc-compass/`](pfc-compass/) | One value, area statement, vision, or life question per refresh |
| [`pfc-back-on-track/`](pfc-back-on-track/) | Off-track intentions (focus, projects, habits) + the smallest step back in |
| [`pfc-pulse-trend/`](pfc-pulse-trend/) | 30-day pulse: per-lever days-on-target, days primed, the standing fix |
| [`pfc-areas/`](pfc-areas/) | Life-wheel status per area: red/yellow with notes, greens holding |

You do not need all thirteen. Start with one or two that answer a question you ask
every day, and add screens as the data behind them becomes real.

## Quick start

```sh
trmnl/bin/preview pfc-today            # real repo data → lint → PNGs in _build/
trmnl/bin/preview pfc-today --serve    # same, then live reload at localhost:4567
```

`bin/trmnlp` uses the `trmnl_preview` gem if you have Ruby >= 3.4, otherwise Docker,
Podman, or nerdctl — whichever it finds. Override with `TRMNL_CONTAINER_RUNTIME`.

Previews render at 4-bit to match a 16-grayscale panel. `trmnlp`'s own default is
1-bit, which dithers grays into dot patterns and misrepresents the layout.

## Before you push

Each plugin's `src/settings.yml` ships **without an `id:`**. The first `trmnlp push`
creates the plugin on your TRMNL account and returns an id — add that one line to
`settings.yml` so later pushes update the same plugin instead of creating a new one.
Everything else the push writes back (including the live bearer token in
`polling_headers`) must be stripped before you commit.

## Where the rules live

| What | Where |
|---|---|
| How this fits the PFC system, and the webhook-vs-polling decision | [`docs/trmnl-plugins.md`](../docs/trmnl-plugins.md) |
| Operational rules for working in this folder | [`AGENTS.md`](AGENTS.md) |
| End-to-end workflow for building a plugin | `/pfc-trmnl-plugin` |
| The TRMNL design system and framework rules | the `trmnl` skill (plugin `trmnl@trmnl-agent-skills`) |
