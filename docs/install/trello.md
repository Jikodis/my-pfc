# Trello dashboard install guide

The Trello dashboard renders your PFC system — the same bands as the web home page, in the same order (body first, today's 2+1, habits, the week, focuses, projects, trends, areas, values, visions, front-of-mind anchors), plus every open task — onto a single board you can glance at from your phone. Two-way completion sync lets you mark tasks and habits done directly from an Android home-screen widget. For any profile where "externalize state" matters (ADHD, autism, low story memory), this visual layer is the highest-leverage upgrade you can make after the core system is running.

**Tier:** 2 unlock. Do the [Tier 1 quickstart](../../README.md) first. This setup takes ~15–20 minutes and requires a Trello account.

---

## Prerequisites

- Trello account (free tier is sufficient — no paid subscription required).
- Tier 1 quickstart complete: `.env` exists, `python3` dependencies installed, at least one checkin has run successfully.
- Optional but recommended: the Calendar integration already set up (`docs/install/connectors.md`). The `🗓️ Week` list degrades gracefully without it, but lands much better when it's live. (Email has no dashboard list — labeled emails become tasks via `/pfc-email-triage` and show up as ordinary task cards.)

---

## Step 1 — Create the dashboard board

Create one board in Trello. It will host both the `📥 Inbox` capture list and all the read-only dashboard lists.

**Lists.** Create only `📥 Inbox` by hand. The render creates every other list and keeps them in the web home page's order, right after `📥 Inbox`:

| # | List | What it holds |
|---|------|---------------|
| 1 | `📥 Inbox` | Your captures (never touched by the render) |
| 2 | `🦸 Body first` | The `🤖 Brief`, last night's sleep against target, the day's rating card while it is unrated |
| 3 | `✅ The 2+1` | Today's picks (tick to complete, archive to drop), tomorrow's picks in the evening, then one card with what needs you, why today, and hand-offs |
| 4 | `☀️ Habits` | Daily then monthly habits (tick to log) |
| 5 | `🗓️ Week` | One card per day of the next seven |
| 6 | `🎯 Focuses` | This quarter's focuses with their lights |
| 7 | `🛠️ Projects` | Active projects with their gauges, then parked and on deck |
| 8 | `📈 Trends` | The last 30 days |
| 9 | `🧭 Areas` | The plate, each life area, then the household rooms |
| 10 | `💎 Values` | Your values and the question of the day |
| 11 | `🔭 Visions` | Today's vision, then each vision |
| 12 | `🧠 Front of mind` | Your grounding anchors |
| 13 | `✅ Tasks` | Every open task in rotation, in priority order (tick to complete) |

The render matches lists by name and moves them back into this order when they drift. A list it does not name stays where you put it. Coming from an older layout, archive the old lists once (`docs/trello-dashboard.md` names them) or run `--rebuild`.

---

## Step 2 — Mint an API key + token

Trello's API key/token pair is issued through the Power-Up admin console. This is free for personal use — you are not building a real Power-Up, just using the admin as a key-issuance page.

1. Go to [https://trello.com/power-ups/admin](https://trello.com/power-ups/admin).
2. Click **New Power-Up**.
3. Give it any name (e.g. "Personal Inbox"). Set the workspace to the one your dashboard board belongs to. Leave the iframe URL blank.
4. Click **Create**.
5. Open the new Power-Up → **API Key** tab → click **Generate** (or it may already show a key). Copy the key — this goes into `TRELLO_API_KEY`.
6. On the same page, find the **Token** hyperlink (it is separate from "API Secret"). Click it → authorize → copy the long token from the resulting page into `TRELLO_API_TOKEN`.

**Common pitfalls:**

- **Do not use the legacy `trello.com/app-key` URL.** That page is deprecated and produces keys that do not pair with new tokens. You must go through the Power-Up admin path above.
- **Ignore the API Secret.** It is only used for OAuth request signing, which this integration does not do. The secret field on the Power-Up admin page is not `TRELLO_API_TOKEN`.
- **Key and token must come from the same Power-Up admin page.** A token issued from a different app or key will fail authorization.

---

## Step 3 — Find your list and board IDs

Use single-quoted `curl` so the shell does not background on `&` or expand `$vars`:

```bash
# List all boards and find your dashboard board id
curl 'https://api.trello.com/1/members/me/boards?fields=name&key=YOUR_KEY&token=YOUR_TOKEN'
```

Find your dashboard board in the response and copy its `id`.

```bash
# List all lists on the board and find the 📥 Inbox list id
curl 'https://api.trello.com/1/boards/{boardId}/lists?fields=name&key=YOUR_KEY&token=YOUR_TOKEN'
```

Copy:
- The `📥 Inbox` list `id` → `TRELLO_INBOX_LIST_ID`
- The board `id` → `TRELLO_DASHBOARD_BOARD_ID`

> **Note:** List IDs are globally unique but board-scoped in meaning. If you recreate the board, re-fetch both IDs — the old ones will be invalid.

---

## Step 4 — Set env vars

Add to your `.env`:

```
TRELLO_API_KEY=<from Step 2>
TRELLO_API_TOKEN=<from Step 2>
TRELLO_INBOX_LIST_ID=<from Step 3>
TRELLO_DASHBOARD_BOARD_ID=<from Step 3>
```

---

## Step 5 — First render

```bash
python3 automations/scripts/trello_render.py
```

Or via skill:

```
/pfc-render-trello
```

Open the board on your phone or desktop. You should see cards populated across the system lists. The `📥 Inbox` list will be empty — that is correct.

---

## Step 6 — Mobile widget setup

This is the biggest UX win. A few home-screen widgets turn the dashboard into the external memory it was designed to be. Pick the widgets that match how you use the system; start with two or three and add more once you know what you actually want.

### Android (recommended path)

Long-press the home screen → **Widgets** → **Trello** → pick widget type → point at the relevant board or list. The Trello Android app supports two widget shapes:

- **Board widget** — single tile showing the whole board. Tap to open. Best as a one-tap launcher into the dashboard.
- **List widget** — scrollable view of one list, plus a `+` button to add a card. The cards are interactive: tap the checkbox on a card with a due date to mark it complete (the next sync pulls the completion into the repo). Best for any list you want to glance at or interact with often.

### Recommended widget set

Place these on whichever home screen you actually look at. You do not need all of them; pick by use case.

| Widget | Why you want it | Tap behavior |
|---|---|---|
| Board (whole dashboard) | One-tap launcher; full system glance | Opens the board in the Trello app |
| List: `📥 Inbox` | Voice-dictated capture from anywhere | Add a card via `+`; processed later by `/pfc-trello-inbox` |
| List: `🦸 Body first` | Last night against target, and the day's rating card | Tick one number in each of Energy, Mood and Focus; the next sync saves the rating |
| List: `✅ The 2+1` | Today's focus tasks at a glance | Tick the checkbox to complete; archive a card to drop that pick |
| List: `☀️ Habits` | Daily and monthly habits | Tick off habits; the next sync or render pulls the log in |
| List: `🛠️ Projects` | Quick project-status read-out (% complete in titles) | View only — full editing happens in repo via skills |
| List: `🗓️ Week` | The next seven days, one card per day (PFC scaffolding and known weekly patterns filtered out) | View only — adjust via your real calendar app |
| List: `🧠 Front of mind` | The handful of things you most need to keep in view | View only |
| List: `✅ Tasks` | Every open task, priority first | Tick the checkbox to complete |

### Why interactive lists matter

Marking a 2+1 task or a daily habit complete from the widget (one tap) is the difference between "I'll log it when I'm at my computer" and "I logged it the instant I did it." The two-way sync built into `pfc-evening-checkin` (and the optional morning daily sync job, [`daily-sync.md`](daily-sync.md)) pulls those completions back into the canonical NDJSON files — no manual reconciliation needed.

### iOS

Trello's iOS app does not ship a true home-screen list widget at the time of writing — the same interactive workflow Android users get is not available. Workarounds:

- **iPhone 15 Pro and later:** assign Trello to the **Action Button** (Settings → Action Button → App → Trello) for one-press board access.
- **Older iPhones:** create a **Shortcut** that opens a specific list URL (`trello.com/b/<boardId>/<listId>`) and assign it to the home screen. Repeat for each list you want one-tap access to.
- **Quick capture from any app:** use the **Share Sheet → Trello** action to dump the current URL, text, or note directly into the `📥 Inbox` list.
- **Lock-screen widget (iOS 16+):** Trello's iOS widget shows your starred boards. Star your dashboard board for it to appear there.

### Verify

After setting up a widget, mark a habit or 2+1 task complete from the home screen. Then run `/pfc-sync-trello` (or wait for the next checkin) and confirm the completion landed in `7-habits/_data/habits-daily.ndjson` or `6-tasks/_data/tasks.ndjson`. If it didn't, see the troubleshooting section below.

---

## Step 7 — Daily sync hooks (already wired)

`pfc-evening-checkin` includes Trello sync steps that fire automatically when `TRELLO_DASHBOARD_BOARD_ID` is set. Nothing further to configure.

- Start of the check-in: any `dueComplete: true` card you ticked from the widget triggers the matching task completion or habit log in the repo.
- End of the check-in: the whole board re-renders, so `✅ The 2+1` shows the picks the day's `daily-focus.ndjson` record holds (tomorrow's from 6 PM on) and an unfinished pick returns to `✅ Tasks`.
- Every sync also saves the `🦸 Body first` rating card once each list has one tick, drops a pick whose `✅ The 2+1` card you archived, and, before 6 PM on a day with no picks, sets the home page's suggestions as the 2+1. Those three commit and push their own file.
- Optional: the daily sync job runs the same sync each morning, so ticks reach the repo on days you skip the check-in ([`daily-sync.md`](daily-sync.md), `PFC_DAILY_SYNC=1`).
- Every web UI write re-renders the board afterward, so `✅ The 2+1` follows the picks set on the home page.
- A `post-commit` git hook re-renders the board whenever a mirrored file is committed outside a skill — see `.githooks/post-commit`. Install it with `cp .githooks/* .git/hooks/ && chmod +x .git/hooks/{pre,post}-commit`.
- Fail-safe: any Trello API error logs 🟡 and the check-in continues — Trello state never blocks the workflow.

---

## Step 8 — Inbox processing flow

`/pfc-trello-inbox` walks each card in `📥 Inbox` one at a time. The card title is treated as if you had typed it in chat, and the appropriate skill runs. On success, the card is deleted.

**Example loop:**

1. You voice-dictate "add task buy oat milk" from the home-screen widget. Card lands in `📥 Inbox`.
2. You run `/pfc-trello-inbox` later.
3. Claude sees the card title "add task buy oat milk", proposes running `/pfc-add-task buy oat milk`, and confirms with you.
4. You say yes (or it runs automatically in auto mode). Task is written to `tasks.ndjson`.
5. Card is deleted from Trello.

Any card that does not match a known skill pattern is surfaced for manual routing — you decide whether to treat it as a task, insight, note, or discard.

---

## Step 9 — Recovery modes

If you've moved cards around manually and want to start fresh:

```bash
# Archive all cards on all lists and re-render from scratch
# (confirmation-gated — will prompt before archiving)
python3 automations/scripts/trello_render.py --rebuild

# Reset a single list only
# (confirmation-gated)
python3 automations/scripts/trello_render.py --reset-list "🛠️ Projects"
```

The `📥 Inbox` list is hard-excluded from both operations — capture cards are never touched by the render.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `401 Unauthorized` on first render | Key/token mismatch or stale token | Re-mint the token from the same Power-Up admin page as the key; they must be a matched pair |
| "API Secret" pasted as token | Wrong field — secret is unused | Re-read Step 2; copy the value from the **Token** link, not the API Secret field |
| `List not found` error | Board was recreated or list ID is from a different board | Re-run the Step 3 curl chain and update `TRELLO_INBOX_LIST_ID` and `TRELLO_DASHBOARD_BOARD_ID` in `.env` |
| `🗓️ Week` renders empty | Calendar integration not set up | Expected graceful degradation — see `docs/install/connectors.md` to add Calendar |
| `🧠 Front of mind` renders empty | `data/grounding.ndjson` has no `active` records | Expected — add anchors, or leave the list empty until you have one |
| `🦸 Body first` shows `No sleep reading yet.` | No day-tracking record has a `health.sleep_hours` value yet | Expected until a wearable integration or a manual entry fills it in |
| A list appears twice after a rename | The render creates a list it names when no list has that name | Archive the renamed copy; the render's list is the one it fills |
| Check-in fails with a Trello error | API key expired or network issue | Error is logged 🟡 and the check-in continues; fix the key/token and re-render manually |
| `post-commit` hook never renders | Hook can't see the `TRELLO_*` vars | The hook reads them out of `.env` itself — confirm `.env` sits at the repo root and the three vars are spelled exactly as in `.env.example` |
