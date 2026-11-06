# trmnl/

Source for the TRMNL e-ink display plugins that mirror PFC state to a screen on the
wall — the always-visible counterpart to the Trello dashboard on the phone.

Each screen mirrors one band of the web home page, in the page's order.

| Plugin | Web band | Shows |
|---|---|---|
| [`pfc-values/`](pfc-values/) | Values | Your values in rank order and the question of the day |
| [`pfc-areas/`](pfc-areas/) | Areas | Life wheel and household lights, worst first, with notes |
| [`pfc-visions/`](pfc-visions/) | Visions | Active visions, today's vision and the value it serves |
| [`pfc-focus/`](pfc-focus/) | Focuses | Foundations, Active Pursuits, Currently Consuming: light and progress |
| [`pfc-projects/`](pfc-projects/) | Projects | Active projects: percent done and the next task |
| [`pfc-pulse/`](pfc-pulse/) | Body first | Last night's sleep, the exercise habit today, the verdict and tonight's move, each lever with last night and nights on target over 30 |
| [`pfc-today/`](pfc-today/) | Tasks | Today's 2+1 (tomorrow's too after about 6 PM), what needs you, hand-offs |
| [`pfc-habits/`](pfc-habits/) | Habits | Daily and monthly habits: logged today, yesterday, or not |
| [`pfc-trends/`](pfc-trends/) | Trends | How the last 30 days turned out: day rating, energy, mood, focus, picks done |
| [`pfc-front-of-mind/`](pfc-front-of-mind/) | Front of mind | Active anchors, smaller views rotating by the clock |
| [`pfc-week/`](pfc-week/) | Week | The next seven days from `data/calendar-cache.json` |

You do not need all eleven. Start with one or two that answer a question you ask
every day, and add screens as the data behind them becomes real. To add or remove a
screen, see [`docs/trmnl-plugins.md`](../docs/trmnl-plugins.md) § "Changing what the wall shows".

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
