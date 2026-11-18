# TRMNL plugins

TRMNL is an e-ink display that pulls its screens from trmnl.com. A **plugin** is a
data source plus Liquid markup for four screen sizes. This doc covers how TRMNL fits
the PFC system and the decisions already made; the per-task workflow is the
[`/pfc-trmnl-plugin`](../.agents/skills/pfc-trmnl-plugin/SKILL.md) skill, and the
design system is the `trmnl` skill (Claude Code plugin `trmnl@trmnl-agent-skills`).

This is an **optional** part of the system — nothing else depends on it. Skip the
whole folder if you don't own the hardware.

## Why TRMNL is here

Trello is the phone surface — interactive, checkable, always a tap away. TRMNL is the
**ambient** surface: a screen that sits in the room and shows the thing without being
opened. That distinction matters. A screen you stop noticing is worse than no screen,
so a TRMNL plugin is not a reminder system and should not be sold as one. It earns its
place when the content changes on its own — today's 2+1, today's habit row, the current
focus — so the screen is different every time you glance at it.

**Do not port the whole Trello board to e-ink.** Trello has ~20 lists because tapping
into one is cheap. A screen shows one thing. When picking what a plugin displays,
pick the smallest set that answers a question worth asking every day.

## Architecture

```
repo (canonical)
   │
   │  home_data.build_home → trmnl_home.py builders (BUILDERS in trmnl_push.py)
   │
   ├── polling  (chosen)   an HTTPS endpoint TRMNL GETs, just before showing the screen
   └── webhook  (fallback) POST https://trmnl.com/api/custom_plugins/<uuid>
                              │
                              ▼
            TRMNL renders src/*.liquid against the merge variables → device
```

Same shape as the Trello render: the repo is canonical, the external surface is a
rendered cache, and the write path is one-directional. Unlike Trello there is **no
write-back** — a TRMNL screen is read-only, so nothing to reconcile.

The builders are pure functions of repo state, so they serve either transport unchanged:
`--out <path>` writes the payload as bare JSON for polling, and a bare invocation POSTs
it as a webhook body.

### Webhook vs polling — the tradeoff

Both strategies are supported by TRMNL, and the choice determines how fresh the screen
can be.

| | Webhook (push) | Polling (pull) |
|---|---|---|
| Direction | Repo POSTs to TRMNL | TRMNL GETs a URL you host |
| Freshness ceiling | Whenever a push runs | **Just-in-time — TRMNL refreshes plugin data right before the screen is shown** |
| Rate limit | 12 pushes/hour, 2 KB (30/hour, 5 KB on TRMNL+) | None on your side; capped by the device's refresh rate |
| Cost of adding a 5th plugin | Competes for the same push quota | Free — each plugin polls independently |
| Infrastructure | None | An internet-reachable HTTPS endpoint |
| Credentials | None leave the machine | A bearer token you issue, sent by TRMNL in polling headers |
| Failure mode | Quota exhausted → 429 → screen stale | Endpoint down → TRMNL serves the last good screen |

**Polling is the better fit for a multi-screen dashboard**, for one reason that
outweighs the rest: TRMNL refreshes a plugin's data *just before displaying it*, so a
polled screen is current as of the moment you look at it. A pushed screen is only as
current as the last push. With five plugins on a rotating playlist, push also has to
divide a 12/hour budget five ways while poll does not.

The webhook's advantage is that it needs no infrastructure. That makes it the right
first move: one plugin proves the whole pipeline end to end today, with no server to
stand up. It is the wrong long-term answer for "I want fresher data."

Migrating later is small because the payload builders (`trmnl_home.py`) are pure
functions of repo state: polling reuses them behind an HTTP handler instead of a POST.
Only `strategy:` in each `settings.yml` and the delivery mechanism change; no markup
moves.

**Whether the 12/hour webhook limit is per plugin or per account is not stated in
TRMNL's docs** — the wording is "you may send data to TRMNL's server up to 12x per
hour." Treat it as per-account until confirmed; that is the assumption that fails safe.

### The polling endpoint

TRMNL fetches from an HTTPS endpoint you host:

```
TRMNL ──HTTPS──► Caddy :443 ──► trmnl_serve.py :8765 (loopback) ──► repo clone
```

`automations/scripts/trmnl_serve.py` runs the payload builder **per request** — no cache
— which is what makes the wall current at a glance. It binds loopback only, so the
reverse proxy is the sole public listener, and it refuses to start without
`TRMNL_SERVE_TOKEN`. TRMNL sends that token as `Authorization: Bearer …` in the plugin's
polling headers.

Routes: `GET /p/<plugin>` (authenticated) and `GET /healthz` (loopback only, liveness).

Two systemd user units support it: `pfc-trmnl-serve.service` runs the endpoint, and
`pfc-repo-sync.timer` fast-forwards the server's clone every 5 minutes so served data
tracks the remote — comfortably under the device's 15-minute refresh, so the sync is
invisible.

Full setup, including Caddy and the firewall: [`docs/install/trmnl-endpoint.md`](install/trmnl-endpoint.md).

**Headers live in the TRMNL UI, never in `src/settings.yml`.** The header carries a
secret, and `trmnlp push` would round-trip it through the repo. TRMNL treats
`polling_headers` as a protected field for the same reason.

### Rate and size limits (webhook)

| Account | Requests | Payload |
|---|---|---|
| Standard | 12 / hour | 2 KB |
| TRMNL+ | 30 / hour | 5 KB |

Verify against [the webhook docs](https://docs.trmnl.com/go/private-plugins/webhooks)
before relying on these — they are TRMNL's numbers, restated here only because they
shape the design.

`trmnl_push.py` enforces both: it refuses an oversized payload outright and refuses to
push more than once per 5 minutes (`--force` overrides). Raising `TRMNL_PAYLOAD_LIMIT`
is only correct on a TRMNL+ account — otherwise trim the builder.

The limits are why **the git post-commit hook does not push to TRMNL** even though it
does render Trello. A working session commits many times an hour and would exhaust the
quota, leaving the screen stale behind HTTP 429. Push on demand instead.

2 KB also forces the right habit: shape the data in Python and let Liquid iterate flat
lists. That matches TRMNL's own "data first" rule — the design system's hard gate is
that markup is never written against data you haven't confirmed.

### What actually limits freshness

Three stages sit between something changing and the wall showing it. Which stage is the
bottleneck depends entirely on *how* the change was made — this is the part that is easy
to get wrong.

**Stage 1 — repo freshness.** Not one number. It splits by write path:

| How the change happens | When the repo knows |
|---|---|
| Agent or page action: the home page, "change my 2+1", complete a task in chat or on the page | **Immediately.** The skill or `web_write.py` writes NDJSON and commits in the same step. |
| Checking a card off in the Trello widget | Only when `trello_writeback.py` runs: the daily sync job ([`install/daily-sync.md`](install/daily-sync.md)), or on demand |
| Marks on the reMarkable pages | Within about 15 minutes (`pfc-remarkable-sync`, every 10 minutes; [`remarkable.md`](remarkable.md)) |
| Auto-fetched data (sleep, activity → Body first) | Only when the scheduled fetch runs |

So agent-driven state is already as fresh as it gets. The lag is confined to changes
that originate *outside* the repo: phone checkoffs and scheduled fetches. Body first
showing 10 AM data at 4 PM is a stage-1 problem in the third row — no delivery change
fixes it, only a more frequent fetch.

**Stage 2 — delivery.** Push cadence (webhook) or just-in-time fetch (polling). Polling
removes this stage as a bottleneck entirely.

**Stage 3 — device refresh.** The device pulls the next playlist item on its own
refresh-rate setting (Device Settings → Battery & Sleep). More frequent costs battery,
and TRMNL is explicit that the timing is fuzzy and
[not a clock](https://help.trmnl.com/en/articles/12746770-trmnl-is-not-a-clock).

**Net:** with polling, an agent-made change to the 2+1 reaches the screen on the next
device refresh, with nothing in between. That is the ceiling, and it is a good one.

### Private plugins only

Everything here is a private plugin on a personal account. Marketplace publication,
OAuth install flows, and the "Chef" submission linter are out of scope. **GitHub Sync
is deliberately not used** — it syncs one plugin per repo and makes trmnl.com a second
writer to markup this repo already owns; two write paths is how edits get lost.
`trmnlp push` from this repo is the only deploy path.

### Device profile

These plugins are authored for a 16-grayscale panel (TRMNL X class) that renders
logically at 1040x780, versus 800x480 on the original device. Author markup against
the 800x480 view sizes — the framework scales — and use the `lg:` responsive prefixes
where the extra room genuinely helps.

**Preview at 4-bit.** `trmnlp` defaults PNG output to 1-bit, which dithers every gray
into dot patterns; `trmnl/bin/preview` renders at `TRMNL_COLOR_DEPTH` (default 4) so
what you see matches what the panel shows. On a 1-bit device set `TRMNL_COLOR_DEPTH=1`
in `.env`.

## Setup

### 1. TRMNL account access

Private plugins need the **Developer add-on** or a BYOD license on the TRMNL account.
Without it there is no "Private Plugins → New" and no webhook UUID.

### 1b. The `trmnl` skill

The design system arrives as a **Claude Code plugin**, `trmnl@trmnl-agent-skills`, which
carries TRMNL's production agent prompts and the full framework v3 guide. It is declared
in the project's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "trmnl-agent-skills": {
      "source": { "source": "github", "repo": "usetrmnl/trmnl-agent-skills" },
      "autoUpdate": true
    }
  },
  "enabledPlugins": { "trmnl@trmnl-agent-skills": true }
}
```

Declaring it in project settings means a fresh clone is prompted to install it and it
auto-updates from upstream, so the design system never goes stale — which is the whole
reason for using a plugin over a checked-in copy.

The one thing settings cannot do is install it for you. On a new machine, or on the
server, run it once:

```sh
claude plugin install trmnl@trmnl-agent-skills
```

Until then Claude Code reports the plugin as not installed. Nothing else in this repo
depends on it — the push script, `trmnlp`, and the plugin sources all work without it;
only markup *authoring* needs the design system.

Because the skill lives in the plugin cache rather than the repo, **never reference its
files by path** — say "load the `trmnl` skill" instead. Paths into
`~/.claude/plugins/cache/` break on every other machine.

### 2. Local dev server

`trmnlp` renders Liquid against the TRMNL design system on localhost, watching files
and reloading. `trmnl/bin/trmnlp` resolves a runtime in this order:

1. A native `trmnlp` on `$PATH` — the `trmnl_preview` gem, needs Ruby >= 3.4
   (macOS ships 2.6, so `brew install ruby` first)
2. `$TRMNL_CONTAINER_RUNTIME` if set — takes arguments, e.g. `"lima nerdctl"`
3. The first of `docker`, `podman`, `nerdctl` found on `$PATH`

PNG rendering works out of the box in the container image; with the gem it needs
Firefox and ImageMagick installed.

### 3. Environment variables

| Variable | Purpose |
|---|---|
| `TRMNL_API_KEY` | `trmnlp push` / `pull` / `clone` auth. From TRMNL account settings. Workstation only — not needed to serve data. |
| `TRMNL_SERVE_TOKEN` | **Server.** Bearer token for the polling endpoint; the same value goes in the plugin's polling headers. Generate with `trmnl_serve.py --gen-token`. The server refuses to start without it. |
| `TRMNL_SERVE_PORT` | Optional, server. Loopback port for the endpoint (default 8765). |
| `TRMNL_WEBHOOK_<PLUGIN>` | Fallback transport only. The plugin's webhook UUID, e.g. `TRMNL_WEBHOOK_PFC_TODAY`. |
| `TRMNL_PAYLOAD_LIMIT` | Optional, webhook only. Raise to `5120` only on TRMNL+. |
| `TRMNL_CONTAINER_RUNTIME` | Optional. Force a container runtime for `bin/trmnlp`. |
| `TRMNL_COLOR_DEPTH` | Optional. Preview bit depth (default 4). |

The workstation and the server need different halves of this: author markup locally
with `TRMNL_API_KEY`; serve data from the server with `TRMNL_SERVE_TOKEN`. Neither
needs the other's.

### 4. TRMNL MCP server — not used here

TRMNL hosts an MCP server that lets an agent read/write markup on live plugins,
screenshot them, and inspect merge variables.

**It is deliberately not set up.** Everything it offers for building a plugin, `trmnlp`
already does locally and better: `build --png` gives the same screenshot feedback loop
offline, at the correct bit depth, with no key management, and `push` writes markup to
the live plugin. The MCP key is also **scoped to a single plugin**, so a multi-plugin
repo would mean rotating keys to point the agent at whichever screen is under work —
real friction for no gain.

The one thing it adds that `trmnlp` cannot is searching TRMNL's published recipe catalog
for markup to crib from. Worth adding if that becomes a bottleneck:

```sh
claude mcp add --transport http trmnl "https://trmnl.com/mcp?api_key=<key>"
```

The key comes from a plugin's settings → MCP tab; treat it as a password, which is why
it is not committed to a `.mcp.json`. Rate limit: 60 requests / 60 seconds.

TRMNL also has an **in-app AI agent** (Plugins → Private Plugins → Edit Markup →
Agent tab) that builds plugins from a natural-language prompt using your own
OpenRouter or Anthropic key. It is a separate path from this repo: plugins it generates
live only on trmnl.com until you `trmnlp clone` them down. Prefer building here — the
repo is canonical.

## Current plugins

All eleven use the polling strategy.

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

Eleven screens is the full set the repo ships, not a target. A playlist of two or
three you actually read beats eleven you scroll past.

`pfc-today` follows the home page's 2+1 band: today's picks all day, and from about
6 PM tomorrow's picks under them once they are set.

## Changing what the wall shows

Each screen mirrors one band of the web home page (`/`), in the page's order, and is
built from the same `home_data.build_home` call (`automations/scripts/trmnl_home.py`),
so the wall and the page never disagree. A band added to or removed from the page gets
the same change here. Each screen also reads like its band: one headline first, then only
the rows that need a look, worst first, with what is green or on target folded into a
count (row caps are the `*_ROWS` constants in `trmnl_home.py`; the design bar is in
[`trmnl/AGENTS.md`](../trmnl/AGENTS.md)).

**Add a screen** (repo side, then trmnl.com):

1. Add a builder to `trmnl_home.py` and register it in `BUILDERS` (`trmnl_push.py`).
2. Copy a plugin folder, drop the `id:` line from its `src/settings.yml`, write the markup,
   `trmnl/bin/preview <plugin>` and read the PNGs.
3. `cd trmnl/<plugin> && echo y | ../bin/trmnlp push` creates the private plugin on
   trmnl.com; keep the `id:` line the push writes back, `git restore` the rest.
4. On trmnl.com, open the new plugin: polling URL `https://<endpoint>/p/<plugin>`,
   polling header `Authorization: Bearer <TRMNL_SERVE_TOKEN>`, then Save.
5. Add it to the device's playlist (Playlists, Add item), in the page's order.
6. On the server: `systemctl --user restart pfc-trmnl-serve` so the endpoint loads the
   new builder (the repo-sync timer pulls the code; the restart is still needed).

**Remove a screen:** delete its folder and builder, then on trmnl.com remove it from the
playlist and delete the private plugin. A plugin left on the playlist after its builder
is gone shows an error screen.

### Data each screen needs before it is worth a slot

A plugin whose source file is empty renders an honest but useless screen. Before adding
one to the playlist, check its source has real content:

| Plugin | Needs |
|---|---|
| `pfc-today` | `6-tasks/_data/daily-focus.ndjson` (set a 2+1) and open tasks |
| `pfc-habits` | habits defined in `config/habit_schema.yaml`, plus a few days of logs |
| `pfc-pulse` | `data/day-tracking.ndjson` with `health` populated (a wearable connector, or manual entry) |
| `pfc-trends` | `data/day-tracking.ndjson` ratings and a few weeks of 2+1 picks |
| `pfc-focus` | `4-focus/_data/focus.ndjson` |
| `pfc-projects` | active projects and open tasks |
| `pfc-areas` | `2-areas/_data/life-wheel.ndjson` (items in `2-areas/_data/area-items.ndjson` add the plate) |
| `pfc-values` | ranked values (numbered) in `1-values/values.md`; questions in `0-me/questions.md` |
| `pfc-visions` | active visions in `3-visions/` |
| `pfc-front-of-mind` | `data/grounding.ndjson` |
| `pfc-week` | `data/calendar-cache.json`, written by the calendar fetch |

### Tuning the pulse to your own data

`pfc-pulse` renders whatever `automations/scripts/pulse.py`
computes — they hold no thresholds of their own. That module ships generic
sleep-guidance bands, which are a starting point, **not findings about you**.

Retune without touching code by overriding the bands under `health.pulse` in
`config/automation_config.yaml`. Ground the new numbers in your own data: once you have
a couple of months of day ratings, run `/pfc-analyze-trends` and keep only the levers
that actually separate your best days from your average ones. A metric that does not
separate a good day from a mediocre one does not earn a status light. `PULSE_FIX` in
the same module holds the concrete "when this is off, do THIS" line each lever shows —
rewrite those in your own words; a fix you would not actually do is dead text on a wall.

The one thing the TRMNL side owns is the exercise stat on `pfc-pulse`: the exercise habit,
set by `EXERCISE_HABIT_ID` / `EXERCISE_LABEL` at the top of `trmnl_push.py`. Point it at
your own movement habit id from `config/habit_schema.yaml`.

## References

Ordered by how often they are actually the right thing to open.

| Source | What it covers |
|---|---|
| the `trmnl` skill (plugin `trmnl@trmnl-agent-skills`) | TRMNL's agent prompts + full design system, framework **v3**. The authority on markup — start here, not on the web. |
| [`trmnl/AGENTS.md`](../trmnl/AGENTS.md) | Rules for working inside the plugin folders |
| [usetrmnl/trmnlp](https://github.com/usetrmnl/trmnlp) | Local dev server. `examples/hn-stories` is a complete working plugin with a serverless transform. |
| [docs.trmnl.com/go](https://docs.trmnl.com/go) | Official API docs. Append `.md` to any page URL for Markdown; [`llms.txt`](https://docs.trmnl.com/go/llms.txt) is the machine-readable index and [`llms-full.txt`](https://docs.trmnl.com/go/llms-full.txt) the full corpus. |
| [help.trmnl.com — private plugins](https://help.trmnl.com/en/articles/9510536-private-plugins) | Strategies, merge variables, Liquid, force refresh |
| [help.trmnl.com — on-demand refresh](https://help.trmnl.com/en/articles/15123293-on-demand-plugin-refresh) | Why polled data is current at display time |
| [help.trmnl.com — refresh rates](https://help.trmnl.com/en/articles/10113695-how-refresh-rates-work) | Device refresh interval vs battery |
| [help.trmnl.com — LLM-ready docs](https://help.trmnl.com/en/articles/11157496-llm-ready-docs) | TRMNL's own index of agent-consumable sources |
| [usetrmnl/trmnl-agent-skills](https://github.com/usetrmnl/trmnl-agent-skills) | Source of the `trmnl` plugin |
| [help.trmnl.com — GitHub Sync](https://help.trmnl.com/en/articles/15977899-github-sync) | Deliberately unused here — see "Private plugins only" above |

**Two sources that look more useful than they are:**

- [usetrmnl/plugins](https://github.com/usetrmnl/plugins) holds TRMNL's *native* plugins,
  written in Ruby with **ERB** views — not the Liquid that private plugins use. Read them
  for how a third-party API gets reduced to a screen's worth of values; do not copy the
  markup. For Liquid markup patterns, the skill's template-guide examples and TRMNL's
  published Recipes are the better reference.
- TRMNL's Context7 entry is listed alongside framework **v1 and v2**. The `trmnl` skill
  carries v3, so Context7 would be a step backward here — one of the few cases where the
  usual "prefer Context7 for library docs" rule loses.
