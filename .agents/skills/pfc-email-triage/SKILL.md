---
name: pfc-email-triage
description: Triage email inbox by priority. Use when the user says "triage my inbox", "check my email", "show me my emails", "unread emails", or "email".
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
       | {id, thread_id: .source_email_thread_id, description}' 6-actions/_data/tasks.ndjson
```

b. For each candidate, call the Gmail connector's get-thread tool with `threadId` = the task's `source_email_thread_id` and `messageFormat: "MINIMAL"` (label IDs only — no body-token cost).

c. Inspect labels. The thread is "still actionable in the inbox" if and only if **any** message has `INBOX` in `labelIds`. If no message has `INBOX` (archived), or any has `TRASH` and none has `INBOX` (deleted), it was handled elsewhere.

d. For each handled thread, mark its task done (date derived in `$LOCAL_TZ`):

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
jq -c --arg id "TASK_ID" --arg d "$TODAY" \
  'if .id == $id then . + {status:"done", completed:$d} else . end' \
  6-actions/_data/tasks.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp 6-actions/_data/tasks.ndjson
jq -cn --arg id "TASK_ID" --arg d "$TODAY" \
  '{task_id:$id, event:"completed", timestamp:$d, source:"email-sync"}' \
  >> 6-actions/_data/task_events.ndjson
```

If the task appears in today's `daily-focus.ndjson`, also update `completed[]` / `bonus_completed`:

```bash
jq -c --arg d "$TODAY" --arg id "TASK_ID" '
  if .date == $d then
    if (.critical // [] | index($id)) then .completed = ((.completed // []) + [$id] | unique)
    elif .bonus == $id then .bonus_completed = true
    else . end
  else . end' 6-actions/_data/daily-focus.ndjson > data/.jq_update.tmp \
  && mv data/.jq_update.tmp 6-actions/_data/daily-focus.ndjson
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
  6-actions/_data/tasks.ndjson 6-actions/_data/tasks-archive.ndjson | sort -u > /tmp/pfc-linked-threads.txt
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
N=$(cat 6-actions/_data/tasks.ndjson 6-actions/_data/tasks-archive.ndjson 2>/dev/null \
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
    >> 6-actions/_data/tasks.ndjson
  jq -cn --arg id "$ID" --arg d "$TODAY" \
    '{task_id:$id,event:"created",timestamp:$d,source:"email-triage"}' >> 6-actions/_data/task_events.ndjson
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
