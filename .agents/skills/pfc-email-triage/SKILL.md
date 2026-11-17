---
name: pfc-email-triage
description: Triage email inbox by priority, and clear the inbox in approved batches (archive, trash, unsubscribe, draft replies, make tasks). Use when the user says "triage my inbox", "check my email", "show me my emails", "unread emails", "email", "clear my inbox", "clean up my email", or "inbox zero".
---

# Email Triage

Use the Gmail connector to review and triage emails by priority. Labeled emails flow **into the task system automatically** — the label grid is an inbox-to-task pipeline, not a separate dashboard.

## Operating principle — labeled = a task

A priority label (AA–CC) on an inbox email means the email contains **at least one actionable item**, so **every labeled inbox email becomes a task** (auto-created, linked by `source_email_thread_id`). If an email isn't actionable, it shouldn't carry a label — remove the label or move it out of the inbox. The link runs both ways:

- **Forward** (Step 0B): a labeled inbox email with no linked task → **auto-create a task**, priority = the label.
- **Reverse** (Step 0A): a linked task whose email left the inbox (archived or deleted anywhere — phone, web, another client) → **auto-complete the task**.

Dedup is by `source_email_thread_id` across `tasks.ndjson` + `tasks-archive.ndjson`, so a thread never produces two tasks and a handled email never respawns one.

**If you'd rather approve each conversion:** skip Step 0B and use Step 3's per-email offer instead. Auto-creation is the shipped default because a labeled email that never becomes a task is an item you've decided matters and then lost.

## Prerequisites — 9 priority labels in Gmail

This skill expects 9 manually-applied Gmail labels (`AA`, `AB`, `AC`, `BA`, `BB`, `BC`, `CA`, `CB`, `CC`) mapping to a 3×3 importance×urgency grid. Without the labels, every tier query returns zero results and the skill has nothing to surface.

If you haven't set them up, run `/pfc-onboarding integrations/email-triage` for the walkthrough (create the 9 labels + an optional Gmail filter for bulk-apply). If you don't use Gmail or don't want this system, run `/pfc-onboarding skip integrations/email-triage`.

## Priority mapping (AA–CC label grid)

First letter = importance, second letter = urgency; A > B > C on both axes. Labels are applied manually, so labeled emails may already be read — do NOT filter by read status. The label maps straight onto task fields:

| Label | Tier | Task `impact` / `urgency` |
|---|---|---|
| `AA` | Top — critical and urgent | high / high |
| `AB` | High | high / medium |
| `BA` | High | medium / high |
| `AC` | Medium | high / low |
| `BB` | Medium | medium / medium |
| `CA` | Medium | low / high |
| `BC` | Low | medium / low |
| `CB` | Low | low / medium |
| `CC` | Lowest | low / low |

Task `priority` = the raw 2-letter tier. `impact` = first letter (A=high, B=medium, C=low); `urgency` = second letter (same map).

## Steps

### Step 0 — Reconcile the inbox ↔ task system (bidirectional, canonical, fail-safe)

Runs both directions every time. Invoked here and by `pfc-evening-checkin`. **Fail-safe:** any connector error in this step prints `🟡 email reconciliation skipped: <error>` and continues — never block on it.

#### 0A — Reverse: auto-complete tasks whose email was handled elsewhere

Catches emails archived or deleted outside this system (phone, web Gmail, another client).

a. Enumerate candidates — open tasks carrying `source_email_thread_id`:

```bash
jq -c 'select(.status == "open" and (.source_email_thread_id // null) != null)
       | {id, thread_id: .source_email_thread_id, description}' 6-tasks/_data/tasks.ndjson
```

b. For each candidate, call the Gmail connector's get-thread tool with `threadId` = the task's `source_email_thread_id` and `messageFormat: "MINIMAL"` (label IDs only — no body-token cost).

c. Inspect labels. The thread is "still actionable in the inbox" if and only if **any** message has `INBOX` in `labelIds`. If no message has `INBOX` (archived), or any has `TRASH` and none has `INBOX` (deleted), it was handled elsewhere.

d. For each handled thread, mark its task done (date derived in `$LOCAL_TZ`):

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
jq -c --arg id "TASK_ID" --arg d "$TODAY" \
  'if .id == $id then . + {status:"done", completed:$d} else . end' \
  6-tasks/_data/tasks.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 6-tasks/_data/tasks.ndjson
jq -cn --arg id "TASK_ID" --arg d "$TODAY" \
  '{task_id:$id, event:"completed", timestamp:$d, source:"email-sync"}' \
  >> 6-tasks/_data/task_events.ndjson
```

If the task appears in today's `daily-focus.ndjson`, also update `completed[]` / `bonus_completed`:

```bash
jq -c --arg d "$TODAY" --arg id "TASK_ID" '
  if .date == $d then
    if (.critical // [] | index($id)) then .completed = ((.completed // []) + [$id] | unique)
    elif .bonus == $id then .bonus_completed = true
    else . end
  else . end' 6-tasks/_data/daily-focus.ndjson > data/.jq_update.tmp \
  && mv data/.jq_update.tmp 6-tasks/_data/daily-focus.ndjson
```

e. Print `📧 reconciled N task(s) from externally-archived emails: <task-ids>`, or `email reconcile: nothing to complete`. Do NOT re-archive these threads — they're already out of the inbox.

#### 0B — Forward: auto-create a task for every labeled inbox email with no linked task

a. Fetch every labeled inbox thread, per tier, capturing `threadId` + `subject` + which tier it carries. **Every query includes `in:inbox`** — archived emails are out of scope:

```
search_threads   "in:inbox label:AA"
                 "in:inbox label:AB"   … through …   "in:inbox label:CC"
```

Run all nine separately so you know each thread's tier. Collect one record per thread: `{thread_id, subject, tier}`. If a thread carries two labels, keep the higher tier (AA > AB/BA > AC/BB/CA > BC/CB > CC).

b. Build the set of thread IDs already linked to a task (live + archive):

```bash
jq -s -r '[.[] | .source_email_thread_id // empty] | .[]' \
  6-tasks/_data/tasks.ndjson 6-tasks/_data/tasks-archive.ndjson | sort -u > /tmp/pfc-linked-threads.txt
```

c. **Orphans** = labeled threads whose `thread_id` is NOT in that file. For each orphan, **infer `area`** from the subject and sender — pick the single best-fit folder name from `2-areas/` (list them with `ls -d 2-areas/*/ | xargs -n1 basename`; never invent one that doesn't exist, or the validator will reject the write). When genuinely ambiguous, default to whichever catch-all area you keep. Write the orphans with their inferred area to a JSON array:

```
/tmp/pfc-email-orphans.json  →  [{"thread_id":"…","subject":"…","tier":"AA","area":"health"}, …]
```

If there are no orphans, write `[]` and skip the create block.

d. Auto-create tasks + log events (deterministic — dedup is already guaranteed by the orphan filter):

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
DSTAMP=$(echo "$TODAY" | tr -d '-')
# highest existing sequence for today's date, across live + archive
N=$(cat 6-tasks/_data/tasks.ndjson 6-tasks/_data/tasks-archive.ndjson 2>/dev/null \
    | jq -r --arg p "task-$DSTAMP-" 'select((.id // "")|startswith($p)) | .id' \
    | sed "s/^task-$DSTAMP-//" | sort -n | tail -1)
N=${N:-0}
imp_of(){ case "${1:0:1}" in A) echo high;; B) echo medium;; C) echo low;; esac; }
urg_of(){ case "${1:1:1}" in A) echo high;; B) echo medium;; C) echo low;; esac; }
jq -c '.[]' /tmp/pfc-email-orphans.json | while read -r o; do
  N=$((N+1)); ID="task-$DSTAMP-$(printf '%03d' "$N")"
  TID=$(jq -r '.thread_id' <<<"$o"); SUBJ=$(jq -r '.subject' <<<"$o")
  TIER=$(jq -r '.tier' <<<"$o"); AREA=$(jq -r '.area' <<<"$o")
  jq -cn --arg id "$ID" --arg desc "$SUBJ" --arg tier "$TIER" \
     --arg imp "$(imp_of "$TIER")" --arg urg "$(urg_of "$TIER")" \
     --arg area "$AREA" --arg tid "$TID" --arg subj "$SUBJ" --arg d "$TODAY" \
    '{id:$id,status:"open",description:$desc,notes:null,size:"M",location:"Anywhere",impact:$imp,urgency:$urg,priority:$tier,project:"none",depends_on:null,area:$area,deadline:null,created:$d,completed:null,source:"email-triage",source_email_thread_id:$tid,source_email_subject:$subj}' \
    >> 6-tasks/_data/tasks.ndjson
  jq -cn --arg id "$ID" --arg d "$TODAY" \
    '{task_id:$id,event:"created",timestamp:$d,source:"email-triage"}' >> 6-tasks/_data/task_events.ndjson
  echo "  ➕ $ID [$TIER] $AREA — $SUBJ"
done
rm -f /tmp/pfc-email-orphans.json /tmp/pfc-linked-threads.txt
```

e. Print `📧 auto-created N task(s) from labeled emails`, or `email reconcile: no new labeled emails`. Run `scripts/validate.sh` before committing; commit as `task: add N task(s) from email triage`.

### Step 1 — Interactive view (only when the user asked to *see* their inbox)

Steps 0A/0B have already moved every labeled email into the task system. Steps 1–3 are a **read-only summary** for when the user says "show me my inbox" — skip them when this skill runs as a background reconcile (e.g. from the evening check-in).

**Fetch by tier. Every query must include `in:inbox`.**

- `in:inbox label:AA` → Top — show all: sender, subject, snippet
- `in:inbox (label:AB OR label:BA)` → High — sender, subject
- `in:inbox (label:AC OR label:BB OR label:CA)` → Medium — sender, subject (or a count if there are many)
- `in:inbox (label:BC OR label:CB)` → Low — count only unless asked
- `in:inbox label:CC` → Lowest — count only

If any result slips through without the `INBOX` labelId (shouldn't happen with `in:inbox`, but defense-in-depth), drop it.

### Step 2 — Fetch unprocessed emails (in inbox, unread, no priority tier)

- Search: `in:inbox is:unread -label:AA -label:AB -label:AC -label:BA -label:BB -label:BC -label:CA -label:CB -label:CC`
- Show as a numbered list: sender + subject. These carry no label, so they did NOT auto-create a task — surface them so the user can label them (→ becomes a task on the next reconcile) or ignore them.

### Step 3 — Present summary

Group as: Top → High → Medium → Low → Lowest → Unprocessed. For each labeled tier, note that the emails already have linked tasks from Step 0B.

For each labeled email, offer the two-minute test: **can this be handled right now in under two minutes?** If yes and they handle it → archive it and remove the label; the reverse reconcile completes its task on the next run.

If you disabled auto-creation (Step 0B), this is where conversion happens instead: walk the AA / AB / BA / AC / BB / CA emails in order and offer to convert each into a task via `pfc-add-task`, setting `source: "email-triage"`, `source_email_thread_id`, and `source_email_subject`. Always run `pfc-add-task`'s duplicate check first, honor its breakdown rule, and bundle the new tasks into one commit.

### Step 4 — Clear My Inbox (only when the user says "clear my inbox" / "clean up my email")

Batch cleanup of the **unlabeled** inbox (labeled threads are already tasks, so leave them alone). The agent proposes one action per row, the user approves by number, the agent executes. **Nothing changes in Gmail before approval, and nothing is ever sent**: replies are drafts only. Manual trigger only; this step never runs as part of a background reconcile.

Why batches with one table: every row is one yes/no, so the user never has to hold a sequence in their head, and a 25-thread batch is done before it starts to feel like a chore.

**Permission prerequisite.** The Gmail connector must be authorized with modify access (Google scope `gmail.modify`). A read-only grant lets Step 0 and the proposal table work but fails every write with `Insufficient scope`. On the first `Insufficient scope` error, stop the batch (don't retry each row), print `🔴 Gmail connector is read-only — reconnect it in claude.ai → Settings → Connectors → Gmail and accept all permissions`, and still create any approved Task rows in the repo directly (Step 0B record shape, with `source_email_thread_id`).

a. **Look up label IDs once** with `mcp__claude_ai_Gmail__list_labels`: `Unsubscribe These` and the nine tiers (`AA`…`CC`). If `Unsubscribe These` is missing, create it with `mcp__claude_ai_Gmail__create_label`.

b. **Fetch a batch of 25**, newest first:
```
mcp__claude_ai_Gmail__search_threads  query: "in:inbox -label:AA -label:AB -label:AC -label:BA -label:BB -label:BC -label:CA -label:CB -label:CC"
                                      pageSize: 25   view: THREAD_VIEW_MINIMAL
```
Keep the `nextPageToken` for the next batch. Open a thread with `get_thread` only when the snippet can't decide the action (a real person, or a bill or notice that may need doing).

c. **Pick one action per thread:**

| Action | When | Gmail effect |
|---|---|---|
| Trash | **The default for anything that needs nothing from the user**: marketing, receipts, order and shipping confirmations, autopay reminders, account notices, past or no-action notices | `trash_thread` |
| Unsubscribe | A bulk sender the user never reads: the fix is stopping it, not deleting one copy | add `Unsubscribe These` + remove `INBOX` |
| Archive | **Rare**: only a true record needed later, such as tickets or passes to show at the door, tax documents, contracts, legal or medical records | remove `INBOX` |
| Draft reply | A real person asked the user something | `create_draft` with `replyToMessageId` = latest message; add a tier label (default `BB`) so it becomes a "reply" task; stays in inbox |
| Task | Needs the user to do something | add a tier label (pick from the grid) → Step 0B makes the task |
| Keep | Genuinely unsure | no change |

Default to Trash and propose Archive only for the record types listed; most people keep far less email than they think they need. If the user prefers to archive more, follow their preference for the rest of the session. **Never propose Trash for** a message from a real person asking something, an unpaid bill, or anything still needing action (a form, a sign-up, a deadline): those are Draft or Task. Trash is recoverable for 30 days.

d. **Collapse by sender.** Several threads from one sender with the same action → one row (`example-newsletter.com ×4`). Sort rows by action in the table order above, so the trash, unsubscribe and archive rows sit together for a bulk yes.

e. **Split the proposal into two tables.**

**Table 1 — Worth knowing (then trashed).** Emails that carry a fact the user needs (a date, time, place, amount, deadline, or something they are asked to do) even though the email itself can go: school or club notices, event schedules, bills (amount, due date, and whether autopay covers it), deadlines on money owed to them. **Open each with `get_thread` (`PLAIN_TEXT`)** and pull the facts out; a snippet is not enough, and a guessed date is worse than none. Columns: `# | From | The facts | Task?`. "The facts" is one line, dates as `Sun 1/5`, times 12-hour. "Task?" proposes a task when the email asks the user to do something (sign up, pay, register, bring something), else `—`. If the facts are in an image that can't be read, say so and make the row Keep instead of Trash. Approving a row trashes the email and creates any proposed task (with `source_email_thread_id` left null, since the email is gone; see step f).

**Table 2 — Everything else.** Columns `# | From | Subject / gist | Action`, numbered on from Table 1 so one reply covers both. For Draft rows, the gist includes a one-line summary of the proposed reply. End with the approval line: *Reply `all`, a range (`1-12 yes`), or overrides (`4: archive`, `7: keep`). Anything not approved is left alone.*

f. **Execute approved rows** with the tools in the table. **A Task row's email is never trashed in the same pass**: the task is linked by thread id, and Step 0A auto-completes any task whose email left the inbox. If the user wants the email gone anyway, clear the task's `source_email_thread_id` first. On any connector error for a row: print `🟡 <row>: <error>` and continue.

g. **If any Task or Draft rows ran**, run Step 0B right away so the tasks exist now, not at the next reconcile; commit per Step 0B.

h. **Unsubscribe hand-off task.** If the `Unsubscribe These` label has threads and no open task with description `Unsubscribe from senders in Gmail "Unsubscribe These" label` exists, create one (via `pfc-add-task` conventions, area = your catch-all area, `agent_doable: "yes"`, since an agent with a browser can follow each unsubscribe link). A label folder alone is an out-of-sight reminder that gets forgotten; a task shows up when picking work.

i. **Report** one line: `🧹 Batch done — trashed N · unsubscribe-queued N · archived N · drafted N · tasks N · kept N. Inbox: <before> → <after> threads.` Then offer the next batch as an open question (default: stop).
