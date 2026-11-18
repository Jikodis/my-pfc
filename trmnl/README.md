# trmnl/

Source for the TRMNL e-ink display plugins that mirror PFC state to a screen on the
wall — the always-visible counterpart to the Trello dashboard on the phone.

| Plugin | Web band | Shows |
|---|---|---|
| `pfc-pulse` | Body first | The verdict and its light, tonight's move, three stats (slept, awake, the exercise habit today), then only the levers off target last night, worst first, with nights on target over 30; levers on target fold into a count |
| `pfc-today` | The 2+1 | The why line, today's picks (an overdue pick carries its date), picks done, tomorrow's picks after about 6 PM, at most three rows of what needs you, and the hand-off count |
| `pfc-habits` | Habits | "N of M daily habits logged today", the daily habits still to log, and the monthly habits on one line; logged and automatic ones fold into counts |
| `pfc-week` | Week | Seven days from today, at most three events a day with the rest counted |
| `pfc-focus` | Focuses | "N of M live focuses are red", the re-pick callout, then each tier's focuses not green, worst first; green and parked fold into counts |
| `pfc-projects` | Projects | "N active, M stalled", then at most three active projects with percent, the next task and days idle; parked and on deck as one count |
| `pfc-trends` | Trends | The last 30 days: trends not green with their reason, the green ones on one "on track" line |
| `pfc-areas` | Areas | The plate (committed of free waking hours, with a bar), the life wheel's green count and its areas not green, worst first; household as a green count plus the rooms that need a look |
| `pfc-values` | Values | The values in rank order and, large, the question of the day |
| `pfc-visions` | Visions | Today's vision and the value it serves, then the other active visions |
| `pfc-front-of-mind` | Front of mind | The active anchors, poster-sized while there are three or fewer |

To add or remove a screen, see [`docs/trmnl-plugins.md`](../docs/trmnl-plugins.md) § "Changing what the wall shows".

You do not need all eleven. Start with one or two that answer a question you ask
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
