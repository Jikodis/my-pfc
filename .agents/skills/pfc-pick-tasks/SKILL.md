---
name: pfc-pick-tasks
description: Suggest tasks to work on, prioritized by impact, urgency, and size. Use when the user says "pick tasks", "what should I work on", "suggest tasks", "next task", "what's important", or "prioritize".
---

# Pick Tasks

Help the user select tasks to work on right now. Optimized for ADHD: surface the highest-value, lowest-friction work first. Quick wins build momentum.

## Step 1: Gather open tasks

```bash
jq -c 'select(.status == "open" and (.deferred // false) == false)' 6-actions/_data/tasks.ndjson
```

**`deferred: true` means the user parked it — never suggest it.** A deferred task is still open work; the user has just said "not now, and stop offering it." It stays out of every pick pool, off the Trello `✅ Actions` list, and out of `pfc-revive`'s slippage signals until they ask for it back. Do NOT surface it as a candidate, do NOT nudge about it, and do NOT count it as slipping. To un-park one, set `deferred` to `false`. `/pfc-list-tasks` is where parked tasks stay visible.

### Step 1a: Exclude blocked tasks (depends_on not yet done)

A task with a non-empty `depends_on` array is only ready when **every** referenced task has `status == "done"`. Never suggest a blocked task.

```bash
jq -cs '
  (map(select(.status == "open") | .id)) as $open_ids |
  .[] | select(.status == "open" and (.deferred // false) == false) |
  select((.depends_on // []) | all(. as $d | $open_ids | index($d) | not))
' 6-actions/_data/tasks.ndjson
```

This returns only open tasks whose dependencies are all completed (or never existed in the first place — deleted/archived dependencies are treated as resolved, same as done).

### Step 1b: Exclude tasks already scheduled on the calendar today or later

A task that has a calendar event today or any future day is already committed to a time — don't surface it as a candidate. But DO surface tasks whose calendar event was yesterday or earlier and never completed (overdue carry-forwards).

Pull primary-calendar events from today through the next ~60 days via MCP `list_events`, extract embedded task IDs from titles (they follow the `[task-YYYYMMDD-NNN]` pattern), and filter them out of the candidate pool:

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
# After fetching events, extract task IDs with a grep:
#   echo "$EVENT_TITLES" | grep -oE 'task-[0-9]{8}-[0-9]{3}' | sort -u > /tmp/scheduled-ids
# Then filter:
jq -c --slurpfile scheduled /tmp/scheduled-ids.json \
  'select(.status == "open" and (.id as $id | $scheduled | any(. == $id) | not))' \
  6-actions/_data/tasks.ndjson
```

Only exclude events whose `start.dateTime` (or `start.date` for all-day) is `>= TODAY`. An event dated `< TODAY` that references a still-open task is a carry-forward and SHOULD remain a candidate.

### Step 1c: For project tasks, surface only the next sequenced task per project

A project task with a higher `sequence` than another open task in the same project is blocked behind it (course curricula, ordered method books). Surface only the lowest-sequence open task per project. Standalone tasks (`project == "none"`) are unaffected — let them all through.

After the dep + scheduled filters above, run:

```bash
jq -cs '
  (map(select((.project // "none") != "none"))
   | group_by(.project)
   | map(sort_by(.sequence // 999999) | .[0]))
  +
  (map(select((.project // "none") == "none")))
  | .[]
'
```

This keeps every standalone task and exactly one project task per project (the next-up one). Project tasks with `sequence: null` sort last — they only surface if no sequenced sibling is open.

## Step 2: Score and rank tasks

**Impact score:** high = 3, medium = 2, low = 1
**Urgency score:** high = 3, medium = 2, low = 1
**Size bonus (smaller = better for getting started):** XS = 3, S = 2, M = 1, L = 0, XL = -1
**Deadline bonus:** If deadline exists and is within 7 days, add +2. If overdue, add +4.
**Stale penalty:** If created 2+ weeks ago and still open, add +1 (these need to move or die).

**Total score = impact + urgency + size_bonus + deadline_bonus + stale_bonus**

Sort descending by total score.

**Never suggest calendar events as tasks.** Calendar events are already built into the day — they don't belong in the 2+1 focus or task recommendations. Only pull from `6-actions/_data/tasks.ndjson`.

**Top-priority tasks surface every day — never filter them out by day of week.** Rank the pool by `priority` when it's set (AA > AB/BA > AC/BB/CA > BC/CB > CC; fall back to impact + urgency when it isn't). **Always surface the top AA (high-impact + high-urgency) items regardless of what day it is** — including a rest day, a holiday, an observance, or any day you've marked off. Do NOT suppress, hide, or skip an AA task because the day "isn't for that kind of work." Top-priority items surface every day; the *user* decides whether to act on them. Day-appropriateness may only shape which *lower-priority* task rounds out the bonus slot (e.g. prefer a restful or family task over an errand on a rest day) — it must never keep an AA task off the list or leave the user without their most-important items in view. The failure this rule kills: a check-in that quietly drops needed top-priority tasks in favor of "appropriate for today" picks.

## Step 3: Check today's focus

```bash
grep "$(date +%Y-%m-%d)" 6-actions/_data/daily-focus.ndjson | tail -1
```

If a daily focus is already set, show it and note which items are already completed. Suggest replacements only for completed items.

If no focus is set, proceed to suggest a 2+1 set.

## Step 4: Present recommendations

### Format

Show the top 5-8 tasks as a ranked table:

| # | Score | Description | Size | Impact | Urgency | Location |
|---|-------|-------------|------|--------|---------|----------|

Flag any with deadlines: `[DUE: Apr 15]` or `[OVERDUE]`
Flag any that are stale: `[STALE: 3 weeks]`

### Suggested 2+1 Focus

After the ranked table, suggest a 2+1 daily focus:
- **Critical 1:** Highest-scored task
- **Critical 2:** Second-highest, ideally from a different project/area for variety
- **Bonus:** A quick win (XS or S size) that would feel good to knock out

### Location filter (optional)

If the user specifies a location (e.g., "what should I work on at home?" or "phone tasks"), filter the list to only show tasks matching that location.

## Step 5: Ask to commit

After presenting recommendations, ask:
- "Want me to set this as today's focus?" (the evening check-in stages the *next* day's 2+1; `/pfc-schedule-focus` places today's on the calendar on demand)
- "Want to break any of these down into smaller pieces?"

## ADHD Momentum Notes

Include one of these contextual nudges at the bottom (pick the most relevant):
- If there are XS/S tasks available: "You have N quick wins available. Starting with a small task builds momentum."
- If all remaining tasks are L/XL: "All open tasks are large. Consider breaking one down into 15-minute chunks."
- If there are stale tasks: "N tasks have been open 2+ weeks. During your next review, consider: eliminate, break down, or re-prioritize."
- If task list is empty or very short: "Task list is light. Good time to capture anything floating in your head."

## Engagement overlays (apply when relevant)

These four overlays exist because *what* to work on and *whether the pick will actually launch* are different questions. Keep them to one line each — a picker that lectures stops getting used. If any of them don't describe your brain, delete them; if your profile (`0-me/profile.md` § Brain, § How to work with this brain) names other launch failures, add your own.

- **Music-on default for low-interest picks.** Whenever the top pick is something you have no natural pull toward — chores, admin, paperwork, anything outside whatever you're currently absorbed in — append one line under the 2+1: **"Music on before you start — the cheapest reliable lever for low-reward chunks."** Before, not after stalling. Do not lecture; one line. Worth tracking as a hypothesis in `data/hypotheses.ndjson` so you find out whether it holds for you.

- **Flag the open-ended-creation tax.** Flag a task 🟡 when it requires generating from nothing AND holding a sequence in your head at the same time — composing music from scratch, cooking from an unfamiliar recipe, drafting from a blank document with no template. Those two demands land on the weakest faculties in this profile simultaneously. Format: `🟡 Open-ended + sequence — externalize one fixed method before starting, or expect a stall.` Don't auto-deprioritize it; just surface the cost so the choice is made with eyes open.

- **Flag tasks that won't finish in one sitting.** When a task is L/XL and can't be broken into a single-session chunk, flag it 🟡: `Won't finish in one session — being interrupted near the end is expensive, because a task forced out of focus tends to go invisible rather than resume. Prefer to break it down before starting.`

- **Surface the trigger plan on stalled re-entries.** If the top pick's `notes` already contains a `trigger:` plan (anchor-to-running-state, person-at-start, scheduled live event, action-alarm), print it inline so it actually gets used: `Trigger plan on file: <text from notes>.` If a stalled task has no trigger plan and has carried forward repeatedly, prompt once: `This has carried 3+ times — want a trigger plan? (anchor-to-running-state is the default; person-at-start only if someone's genuinely available.)` See `/pfc-revive` for the full palette.
