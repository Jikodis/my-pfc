# Calendar + Gmail integration guide

This doc covers how to connect the PFC system to Google Calendar and Gmail. These two integrations unlock calendar-aware morning planning, schedule conflict checking, and email triage from inside Claude Code. Trello has its own install doc (`docs/install/trello.md`).

Pick one path — A, B, or C. They are mutually exclusive. If you switch paths later, just update your MCP config and restart Claude Code.

---

## Path A — Anthropic Claude Connectors (paid Pro/Max subscription)

**What it is.** Anthropic runs first-party Calendar and Gmail connectors hosted in their infrastructure. Setup takes about two clicks from the Claude.ai Connectors marketplace — no Google Cloud Console, no OAuth tokens to manage yourself.

**How to set it up.**

1. Open [claude.ai](https://claude.ai) → click your avatar → **Settings** → **Connectors**.
2. Find **Google Calendar** and **Gmail** in the marketplace and click **Connect** on each. Authorize the Google account you want to use.
3. Claude Code picks up the connectors automatically at next launch — no changes to `.mcp.json` or `.env` needed.

**Caveats.**

- Requires an active Claude Pro or Max subscription. Does not work with the free tier or bare API keys.
- Connectors are available inside Claude.ai and Claude Code only. If you call the Anthropic API directly from another tool, the connectors are not in scope.
- Connectors are managed by Anthropic and update automatically. You are trusting Anthropic with read (and in some cases write) access to your calendar and inbox.

**When to pick this path.** You already have a Pro/Max subscription. Lowest friction.

---

## Path B — Google's official first-party MCP servers (recommended free path)

**What it is.** Google publishes official MCP server install guides for Calendar and Gmail. These run locally (or on your VPS) using a standard Google Cloud Console + OAuth flow — the same pattern as `docs/install/google-health.md`. No subscription required; no third-party code in the trust chain.

**How to set it up.** Follow Google's docs directly — they are the source of truth and track API changes more reliably than a copy here would:

- **Google Calendar MCP server:** <https://developers.google.com/workspace/calendar/api/guides/configure-mcp-server>
- **Gmail MCP server:** <https://developers.google.com/workspace/gmail/api/guides/configure-mcp-server>

Both guides walk through creating a Cloud Console project, enabling the relevant API, configuring the OAuth consent screen, generating credentials, and adding the server to your MCP config. The shape is very similar to `docs/install/google-health.md` §§1–5 if you want a preview of what to expect.

Once both servers are running, add their entries to `.mcp.json` (or `~/.claude/mcp.json` for global config) per the instructions in each guide.

**When to pick this path.** You want Calendar + Gmail integration but don't have a Pro/Max subscription, or you prefer not to route your data through Anthropic's hosted infrastructure.

---

## Path C — Skip the integration entirely

The PFC system works without Calendar and Gmail. Skills that would have used them degrade gracefully: they skip the calendar/email block rather than erroring out.

If you skip and later decide you want the integration, come back and follow Path A or B — no other changes needed.

**When to pick this path.** You don't use Google Calendar, you don't want to manage OAuth tokens, or you want to evaluate the core system before adding integrations.

---

## Recommendation order

| Order | Path | Best for |
|---|---|---|
| 1st | **A — Anthropic Connectors** | Pro/Max subscribers, lowest friction |
| 2nd | **B — Google official MCP** | Everyone else who wants the integration |
| 3rd | **C — Skip** | Users who don't need or want it |

---

## Why no community MCP servers?

Calendar and email are high-trust, high-blast-radius surfaces. A malicious or abandoned community MCP server has read (and write) access to every calendar event you own and every message in your inbox. That is not a reasonable risk-to-convenience trade.

The bar is first-party: Anthropic (Path A) or Google (Path B). If neither fits your environment, skip (Path C) is the right call — not "find a third-party server."

---

## Affected skills if you skip (Path C)

Skills that call into Calendar or Gmail will silently skip those blocks. Nothing breaks; you just won't get the integrations listed below.

**Calendar-dependent skills** (skip calendar block when integration is absent):

| Skill | What you lose |
|---|---|
| `pfc-morning-checkin` | Today's schedule block; conflict detection for focus-task scheduling |
| `pfc-schedule-focus` | Entire skill is calendar-only — schedules 2+1 onto primary calendar |
| `pfc-evening-checkin` | Tomorrow's schedule preview block |

**Email-dependent skills** (skip email block when integration is absent):

| Skill | What you lose |
|---|---|
| `pfc-email-triage` | Entire skill is email-only — triage inbox by priority label |
| `pfc-morning-checkin` | Top-priority email summary block |

**Skills unaffected.** Everything in `pfc-*` that does not touch Calendar or Gmail — task management, habit tracking, daily focus, project summaries, day ratings, weekly/monthly/yearly check-ins, insights, hypotheses, supplement tracking, Trello sync — continues to work exactly as documented.
