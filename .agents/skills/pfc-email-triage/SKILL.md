---
name: pfc-email-triage
description: Triage email inbox by priority. Use when the user says "triage my inbox", "check my email", "show me my emails", "unread emails", or "email".
---

# Email Triage

Use the Gmail connector to review and triage emails by priority.

## Prerequisites — 9 priority labels in Gmail

This skill expects 9 manually-applied Gmail labels (`AA`, `AB`, `AC`, `BA`, `BB`, `BC`, `CA`, `CB`, `CC`) that map to a 3×3 importance×urgency grid. Without the labels, every tier query returns zero results and the skill has nothing to surface.

If you haven't set them up, run `/pfc-onboarding integrations/email-triage` for the walkthrough (create the 9 labels + optional Gmail filter for bulk-apply). Then come back here. If you don't use Gmail or don't want this system, run `/pfc-onboarding skip integrations/email-triage`.

## Priority mapping (AA–CC label grid)

Emails are manually tagged with the 3×3 priority grid. First letter = importance, second letter = urgency; A > B > C on both axes. Labels are applied manually, so labeled emails may already be read — do NOT filter by read status.

| Label | Tier |
|---|---|
| `AA` | Top — critical and urgent |
| `AB` / `BA` | High |
| `AC` / `BB` / `CA` | Medium |
| `BC` / `CB` | Low |
| `CC` | Lowest |

## Steps

1. **Fetch by tier** using Gmail search. **Every query must include `in:inbox`** — archived emails are out of scope.
   - `in:inbox label:AA` → Top — show all: sender, subject, snippet
   - `in:inbox (label:AB OR label:BA)` → High — show all: sender, subject
   - `in:inbox (label:AC OR label:BB OR label:CA)` → Medium — show all: sender, subject (or count if many)
   - `in:inbox (label:BC OR label:CB)` → Low — count only unless asked for details
   - `in:inbox label:CC` → Lowest — count only

   If any result slips through without the `INBOX` labelId (shouldn't happen with `in:inbox`, but defense-in-depth), drop it.

2. **Fetch unprocessed emails** (in inbox, unread, and not in any priority tier):
   - Search: `in:inbox is:unread -label:AA -label:AB -label:AC -label:BA -label:BB -label:BC -label:CA -label:CB -label:CC`
   - Show as a numbered list: sender + subject

3. **Present summary** grouped as: Top → High → Medium → Low → Lowest → Unprocessed

4. **Walk through High and Medium items by default — these are task candidates.** After presenting the summary, go through each AA, AB/BA, AC/BB/CA email in order and offer to convert it into a task via `pfc-add-task`. The user's labels are applied manually, so anything at or above medium already reflects their judgment that the email matters. Low (BC/CB) / Lowest (CC) / Unprocessed do not get this treatment unless the user asks.
   - Set `source: "email-triage"` on new task records.
   - Always run the `pfc-add-task` duplicate check — many email-originated tasks already exist.
   - Honor the breakdown rule — multi-step email tasks split into `pick X + do X` (or similar) as usual.
   - Bundle multiple new tasks into one commit (`task: add [N descriptions] from email triage`).

5. **For each High/Medium, also offer:** can this be handled in under 2 minutes right now?

Do NOT auto-create tasks without asking. Always let the user decide.
