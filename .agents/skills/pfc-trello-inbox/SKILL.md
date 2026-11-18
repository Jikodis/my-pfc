---
name: pfc-trello-inbox
description: Process all Trello inbox cards — batch-propose simple actions for bulk approval, then walk complex cards one at a time. Use when the user says "process inbox", "trello inbox", "process trello", "clear inbox", "/pfc-trello-inbox", or "walk my inbox".
---

# Process Trello Inbox

Process the user's Trello inbox in two phases: batch-propose all SIMPLE cards in a single table for bulk approval, then walk the COMPLEX cards one-at-a-time using the original card-by-card prompt flow. Goal: minimize confirmation prompts when titles are unambiguous, while preserving careful per-card review for cards that need real judgment.

> **Note:** "Inbox" here means a **regular Trello board with a list** that the user dictates into from their phone (typically via a pinned widget or Shortcuts action). It is **not** Trello's built-in personal Inbox feature — that feature is gated to first-party clients and has no public REST API. The list ID lives in `TRELLO_INBOX_LIST_ID` (see `.env.example`).

## When this skill triggers

- Explicit: "process inbox", "trello inbox", "clear inbox", "walk my inbox"
- "/pfc-trello-inbox"
- `/pfc-trello-inbox unattended` from the timer (see Unattended mode)

## Unattended mode (the 10-minute timer)

`scripts/trello-inbox-auto.sh` (timer `pfc-trello-inbox`, every 10 minutes, opt-in with `PFC_TRELLO_INBOX=1` in `.env`, [`docs/install/vps.md`](../../../docs/install/vps.md)) runs this skill headless with the argument `unattended` whenever the 📥 Inbox list has cards. Cards come from the phone (dictated, so expect misheard words) and, when the tablet pages are on, from the reMarkable `0 - Inbox` page (handwriting read by Claude, so expect misread words and `[?]` where a word could not be read). Nobody is there to answer, so:

- **Never ask.** Do not print proposals or wait for approval.
- **Act on every card whose meaning is clear, whatever the action.** Adding, logging, renaming, completing, removing, cancelling, archiving, scheduling, creating a project, sending a message and spending are all allowed once you turn this mode on; that is the point of it. Follow the rules of the skill or doc that owns the action (a calendar event follows `docs/calendar-scheduling.md`; a project gets `/pfc-add-project` with every field inferred; an area note is captured in the user's words, `2-areas/AGENTS.md` § Capture). Pass every argument up front; if a skill would still need to ask, treat the card as unclear. Delete the card after the action succeeds, as in step 11.
- **What waits is only what is unclear,** because a misread note acted on is a wrong record: a card that reads oddly, contains `[?]`, names something that does not exist or matches more than one record, or could mean two things. For anything that removes, sends or spends, the bar for "clear" is higher: the record or recipient must match exactly one thing and the words must leave no doubt. Rename it to `❓ <original title>` and put the question in its description, one line (`python3 automations/scripts/trello_helper.py card-update <id> --name "❓ …" --desc "…"`). Never guess past a misread: a wrong record is worse than a card that waits.
- **Skip cards whose title already starts with `❓`.** They wait for the user; the interactive run walks them as COMPLEX.
- **Commits** follow the repo policy (each capture skill auto-commits and pushes).
- **A reMarkable note may answer the agent.** Its description then lists the agent's recent replies on that page (a question a review asked, a card left ❓). Read the note as the answer to the question it fits: apply it (change the record the question was about) and say so in the action.
- **End** with one line per card: `🟢 <title> → <action>` or `🟡 <title> → left (❓ <question>)`, keeping the card's title exactly as written (its `From the <page> page:` prefix included). `scripts/trello-inbox-auto.sh` turns these lines into the agent's replies at the bottom of that reMarkable page, so write the action in a few plain words the user can read there ("added the task 'Fix the Week band'").

## Pre-flight

1. Verify env vars by running list. If creds are missing, the helper prints to stderr and exits 1 — surface it and stop.

## Workflow

1. Fetch cards:
   ```bash
   python3 automations/scripts/trello_helper.py list
   ```
   - On exit 1: print "🔴 Trello fetch failed: <stderr message>." and exit. Do not retry — the helper already retries internally.
   - On exit 0: parse JSONL output (one `{id, name}` per line) into the working list.

2. If empty: print "🟢 Inbox empty." and exit.

3. **Classify every card** as SIMPLE or COMPLEX (see "Classification heuristics" below). For SIMPLE cards, determine the action + arguments WITHOUT prompting the user — use sensible defaults where a field is ambiguous.

4. Print the inbox header:
   ```
   📥 Inbox: <total> cards. <S> simple, <C> complex.
   ```

### Phase 1 — Batch propose simple cards

5. If there are zero SIMPLE cards, skip to Phase 2.

6. If any SIMPLE task is missing an inferable `area`, ask **once** at the top of the table (not per card): `"Default area for new tasks in this batch? (e.g. work, health, family — or 'skip' to leave area unset)"`. Use the answer as the default for every SIMPLE task that didn't have a clear area.

7. Print the proposals table:
   ```
   Simple proposals (will batch-execute after approval):
   | # | Card title | Proposed action |
   |---|---|---|
   | 1 | "<title>" | /pfc-add-task description="...", size=15min, area=<...>, impact=medium, urgency=low |
   | 2 | "<title>" | /pfc-add-hypothesis statement="..." |
   | 3 | "<title>" | /pfc-log-habit habit_id=<id> completed=true |
   ...
   ```

8. Print the COMPLEX list **before** asking for approval, so the user sees the full landscape:
   ```
   Complex (deferred — will walk one-by-one after batch):
   - "<title>" — <one-line reason: needs project area/values/total_parts decision / long-form / ambiguous>
   - ...
   ```

9. Ask: `Approve all? (Reply 'yes', 'no', or list exceptions like 'skip 2', 'skip 2,5', 'change 5 to task', 'approve except 3')`

10. **Parse the response:**
    - `yes` / `approve all` / `go` / `do it` → batch-execute every SIMPLE proposal
    - `no` / `stop` / `cancel` → exit cleanly. Print `🟡 Cancelled. No cards processed.` Skip Phase 2 too.
    - Selective edits, applied in order:
      - `skip N` / `skip N,M,...` → drop those rows from the batch (cards stay in inbox)
      - `approve except N` (or `N,M,...`) → same as skip
      - `change N to <other action>` → swap that row's action. Re-confirm only that one row if the new action needs an arg you can't infer.
    - Anything ambiguous → restate what you understood and ask once more before proceeding.

11. **Execute approved SIMPLE proposals in order.** For each:
    - Run the action. This may invoke another skill which has its own multi-step prompt flow — but for batch mode, **pass all inferred args up front so the inner skill runs without prompting**. If the inner skill still prompts (because an arg couldn't be inferred), fall back to per-card interaction for that one card and continue.
    - On action SUCCESS:
      ```bash
      python3 automations/scripts/trello_helper.py delete <card_id>
      ```
      - On delete exit 0: print `🟢 #N → <one-line action summary>. Card deleted.`
      - On delete exit 1: print `🟡 #N routed but card delete failed: <stderr>. Card still in Trello.` Continue.
    - On action FAILURE / ABORT: print `🟡 #N action failed: <reason>. Card left in inbox.` Continue. Never delete a card on failure.

### Phase 2 — Walk complex cards one-at-a-time

12. If there are zero COMPLEX cards, skip to step 14.

13. Print: `📥 <C> complex cards to walk. Reply 'stop' to halt, 'skip' to leave a card.`

14. **For each COMPLEX card** (in original order), do the following:

    a. Print: `📥 Card N/<C>: <title>`

    b. Read the title as if the user just typed those exact words in chat. Decide what skill (if any) you'd invoke, OR what direct action you'd take. Propose in **one** sentence:
       - "Looks like a new project — I'd run /pfc-add-project (needs area, values, total_parts, deadline)."
       - "Reads as a long-form insight — I'd run /pfc-add-insight; want to review the content together first?"
       - "Sounds like a task but the area is ambiguous — I'd run /pfc-add-task; what area?"
       - "I'm not sure — best guess is X. Want X, something else, skip, or stop?"

    c. Wait for user response. Interpret naturally:
       - confirm-shaped (`yes`, `y`, `go`, `do it`, `sure`) → run the proposed action
       - alternative ("actually make it an insight", "no, task instead") → run that instead
       - `skip` / `s` → leave the card in Trello, advance to next card, no delete
       - `stop` / `halt` / `q` → end loop, jump to summary

    d. **Run the action.** This may invoke another skill which has its own multi-step prompt flow (e.g. /pfc-add-project asks area/values/total_parts/deadline). Let it run to completion. Treat the inner skill's success as your action's success.

    e. **On action SUCCESS:**
       ```bash
       python3 automations/scripts/trello_helper.py delete <card_id>
       ```
       - On exit 0: print `🟢 Routed → <one-line action summary>. Card deleted.`
       - On exit 1: print `🟡 Routed but card delete failed: <stderr>. Card still in Trello — resolve manually.` Continue.

    f. **On action ABORT** (the inner skill was cancelled mid-flow by user, or surfaced an error):
       Print `🟡 Action cancelled. Card left in inbox.`
       Continue to the next card.

15. End summary:
    ```
    Done. Simple processed: X · Simple skipped: Y · Complex processed: Z · Complex skipped: W · Remaining in inbox: R
    ```

## Classification heuristics

These define the line between SIMPLE (batch-eligible) and COMPLEX (defer to one-at-a-time). Use them when classifying in step 3.

**SIMPLE** (batch-eligible — action + arguments inferable from title alone with sensible defaults):
- **Task** with obvious description. Defaults: `size=15min`, `impact=medium`, `urgency=low`, `area`=inferred from keywords if possible, else use the one-time-asked batch default. Example titles: "Buy birthday gift", "Email teammate back", "Renew driver's license".
- **Hypothesis** — just needs the statement; whole title becomes `statement`. Common shapes: "X causes Y", "Caffeine after 2pm tanks sleep", "Less sugar → better sleep".
- **Insight** — short noticing, fits in one card title. The title becomes the insight content. Optional `domain` inferable from keywords (e.g. "sleep" → sleep, "work" → work).
- **Habit log** — `habit_id` pattern-matchable from title (verify against `config/habit_schema.yaml`), `completed=true`. Examples: "Did 20 min exercise", "Asleep by 10:30", "Walked 30 min".
- **Day log** — explicit rating extractable from title. Examples: "Rated my day 4/5", "Day rating: 3".
- **Supplement add/stop** — recognizable from "started X" / "stopped X" / "discontinued X" with a clear name. Dose changes that pattern-match cleanly (stop+add of same supplement) also qualify.

**COMPLEX** (defer to one-at-a-time):
- **Project** — needs area, values, total_parts, deadline. Multi-field judgment can't be inferred from a title.
- **Long-form insight** — multi-sentence card, or content that needs review with the user before captured verbatim.
- **Ambiguous classification** — you can't pattern-match the title cleanly (could be a task or an insight or a hypothesis).
- **Anything with multi-field judgment beyond defaults** — e.g. a task that clearly needs a deadline, dependency, or non-default impact/urgency that you can't safely infer.

When in doubt between SIMPLE and COMPLEX, classify as COMPLEX — the cost of a one-card walk is small; the cost of misrouting in a batch is silent data drift.

## Cards from the reMarkable

With the optional reMarkable pages ([`docs/remarkable.md`](../../../docs/remarkable.md)), handwritten notes arrive here too, read by Claude from the tablet, so expect misread words and `[?]` where a word could not be read. Their shapes:

- `From the <page> page: <note>` (a page's note box or free writing on it): read the note in that page's context. On the Today page "make reading 20 minutes" means the habit; on This quarter a line naming a project is a progress update for it.
- `Note on task "<title>" (<task id>): <note>`: a change to that task (a new deadline, a correction, "call first"). Apply it to the named task.
- `Also written on the <page> page: …`: stray handwriting; usually COMPLEX.
- The card's description starts `From the reMarkable` and may list the agent's recent replies on that page. A note that answers one of them (a question a review asked) is the answer: apply it to the record the question was about.

A misread note is COMPLEX: ask, never guess.

## Behavioral rules

- **No hardcoded routing taxonomy.** Your normal skill-detection handles each title. The lists in classification heuristics are illustrative, not exhaustive — pattern-match by intent, not by exact wording.
- **Batch first, walk second.** Phase 1 covers the easy bulk; Phase 2 covers the judgment calls. Never collapse both into a single per-card loop.
- **Card deletion is gated on action success.** A mid-flow abort or skill failure leaves the card in Trello. No card is ever deleted on failure.
- **No state files.** Failures are surfaced immediately. No retry queue.
- **Display.** Use 🟢 / 🟡 / 🔴 status circles per AGENTS.md.
- **Cancellation in Phase 1 halts Phase 2 too.** If the user says `no` / `cancel` / `stop` to the batch approval, do not proceed to walk the COMPLEX cards in the same invocation — they re-run on the next `/pfc-trello-inbox`.

## Out of scope

Card descriptions (except a reMarkable card's, above), attachments, audio, labels, multiple boards, archive (cards are deleted, not archived).
