# Trello dashboard install guide

The Trello dashboard renders your entire PFC system — values, areas, visions, projects, today's 2+1, all open actions, daily/monthly habits, recent day ratings, calendar week, top-priority email, insights, findings, hypotheses, and supplements — onto a single board you can glance at from your phone. Two-way completion sync lets you mark tasks and habits done directly from an Android home-screen widget. For any profile where "externalize state" matters (ADHD, autism, low story memory), this visual layer is the highest-leverage upgrade you can make after the core system is running.

**Tier:** 2 unlock. Do the [Tier 1 quickstart](../../README.md) first. This setup takes ~15–20 minutes and requires a Trello account.

---

## Prerequisites

- Trello account (free tier is sufficient — no paid subscription required).
- Tier 1 quickstart complete: `.env` exists, `python3` dependencies installed, at least one checkin has run successfully.
- Optional but recommended: Calendar and Gmail integrations already set up (`docs/install/connectors.md`). The `🗓️ Week at a Glance` and `📧 Email Priorities` lists degrade gracefully without them, but land much better when those integrations are live.

---

## Step 1 — Create the dashboard board

Create one board in Trello. It will host both the `📥 Inbox` capture list and all the read-only dashboard lists.

**Recommended initial list set** (create these in order — the render skill creates any missing lists at the bottom, but starting with the right names saves a rename pass):

| # | List name |
|---|-----------|
| 1 | `📥 Inbox` |
| 2 | `✅ 2+1` |
| 3 | `⬅ Last 7 Days` |
| 4 | `🗓️ Week at a Glance` |
| 5 | `📧 Email Priorities` |
| 6 | `💎 Values` |
| 7 | `🧭 Areas` |
| 8 | `🔭 Visions` |
| 9 | `🛠️ Projects` |
| 10 | `✅ Actions` |
| 11 | `☀️ Daily Habits` |
| 12 | `🌙 Monthly Habits` |
| 13 | `🎡 Life Wheel` |
| 14 | `💡 Insights` |
| 15 | `📜 Findings` |
| 16 | `🧪 Hypothesis` |
| 17 | `💊 Supplements` |

The emoji prefix convention is recommended for visual disambiguation — you can rename or reorder lists freely after creation. The render skill matches by name, so if you rename a list it will create a new one at the bottom on the next render; just delete the old one.

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
| List: `✅ 2+1` | Today's focus tasks at a glance | Tick the checkbox to complete; next checkin pulls it into the repo |
| List: `☀️ Daily Habits` | Daily habit-tracker view | Tick off habits; next checkin or render syncs the log |
| List: `🌙 Monthly Habits` | Monthly habit view | Tick off habits the same way |
| List: `🛠️ Projects` | Quick project-status read-out (% complete in titles) | View only — full editing happens in repo via skills |
| List: `🗓️ Week at a Glance` | Upcoming calendar week — **recurring events auto-filtered** so the list shows only one-off appointments | View only — adjust via your real calendar app |
| List: `📧 Email Priorities` | Top-priority unread emails | Tap a card to jump to the linked Gmail thread |
| List: `⬅ Last 7 Days` | Recent day ratings — quick "how has the week felt?" | View only |

### Why interactive lists matter

Marking a 2+1 task or a daily habit complete from the widget (one tap) is the difference between "I'll log it when I'm at my computer" and "I logged it the instant I did it." The two-way sync built into `pfc-evening-checkin` and `pfc-morning-checkin` pulls those completions back into the canonical NDJSON files — no manual reconciliation needed.

### iOS

Trello's iOS app does not ship a true home-screen list widget at the time of writing — the same interactive workflow Android users get is not available. Workarounds:

- **iPhone 15 Pro and later:** assign Trello to the **Action Button** (Settings → Action Button → App → Trello) for one-press board access.
- **Older iPhones:** create a **Shortcut** that opens a specific list URL (`trello.com/b/<boardId>/<listId>`) and assign it to the home screen. Repeat for each list you want one-tap access to.
- **Quick capture from any app:** use the **Share Sheet → Trello** action to dump the current URL, text, or note directly into the `📥 Inbox` list.
- **Lock-screen widget (iOS 16+):** Trello's iOS widget shows your starred boards. Star your dashboard board for it to appear there.

### Verify

After setting up a widget, mark a habit or 2+1 task complete from the home screen. Then run `/pfc-sync-trello` (or wait for the next checkin) and confirm the completion landed in `6-habits/_data/habits-daily.ndjson` or `5-actions/_data/tasks.ndjson`. If it didn't, see the troubleshooting section below.

---

## Step 7 — Daily sync hooks (already wired)

Both `pfc-morning-checkin` and `pfc-evening-checkin` include Trello sync steps that fire automatically when `TRELLO_DASHBOARD_BOARD_ID` is set. Nothing further to configure.

- Morning: after 2+1 picks are committed, the 2+1 task cards move from `✅ Actions` to `✅ 2+1`.
- Evening: uncompleted 2+1 cards move back to `✅ Actions` for the next morning; any `dueComplete: true` cards trigger task completion in the repo.
- Fail-safe: any Trello API error logs 🟡 and the checkin continues — Trello state never blocks the checkin workflow.

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
| `🗓️ Week at a Glance` renders empty | Calendar integration not set up | Expected graceful degradation — see `docs/install/connectors.md` to add Calendar |
| `📧 Email Priorities` renders empty | Gmail integration not set up | Expected graceful degradation — see `docs/install/connectors.md` to add Gmail |
| Cards appear on wrong list after rename | Render creates a new list on name mismatch | Delete the mismatched old list; the new one is correct |
| Morning checkin fails with Trello error | API key expired or network issue | Error is logged 🟡 and checkin continues; fix the key/token and re-render manually |
