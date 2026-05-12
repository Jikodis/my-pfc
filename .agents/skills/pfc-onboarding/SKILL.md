---
name: pfc-onboarding
description: Introduce PFC system features one at a time. Use when the user says "onboarding", "/pfc-onboarding", "show me the system", "what features are there", "introduce me to a feature", "skip a feature", "onboarding status", or names a specific feature to learn about.
---

# PFC Onboarding

Walk new users through the system one feature at a time. This skill covers the full feature catalog (33 features across 9 categories). State persists across sessions in `config/onboarding.ndjson`.

---

## Step 1: Resolve invocation pattern

Check what the user typed and branch:

| Input | Action |
|---|---|
| `/pfc-onboarding` (bare) | Go to Step 4 — suggest next feature |
| `/pfc-onboarding status` | Go to Step 6 — render full status table |
| `/pfc-onboarding <feature-key>` | Go to Step 5 — run that lesson directly |
| `/pfc-onboarding skip <feature-key>` | Append `dismissed` event, confirm, stop |
| `/pfc-onboarding reset <feature-key>` | Append `introduced` event, confirm, stop |

For skip/reset, run the state write then confirm in one line: "Marked `<feature-key>` as dismissed." or "Reset `<feature-key>` to introduced."

---

## Step 2: State helpers

All state lives in `config/onboarding.ndjson` (append-only event log). Most-recent event per feature wins.

```bash
# Ensure file exists
touch config/onboarding.ndjson

# Get most-recent status for a feature
FEATURE="daily-loop/add-task"
jq -c --arg f "$FEATURE" 'select(.feature == $f)' config/onboarding.ndjson | tail -1

# List all features with their latest status
jq -s 'group_by(.feature) | map({feature: .[0].feature, status: .[-1].status})' config/onboarding.ndjson

# Append a new event (TODAY must be derived via TZ="${LOCAL_TZ:-America/Denver}" date)
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
jq -cn --arg f "$FEATURE" --arg s "tried" --arg d "$TODAY" \
  '{feature:$f, status:$s, date:$d}' >> config/onboarding.ndjson
```

Status enum: `introduced` | `tried` | `dismissed` | `not_introduced` (default when no event exists)

When appending a `tried` event, always append it immediately after the user completes the "Try it now" action in that lesson.

---

## Step 3: Feature catalog

39 features across 9 categories. Auth-gated features require external service setup before the lesson can proceed.

| Category | Feature key | Description | Auth-gated? |
|---|---|---|---|
| meta | meta/set-local-timezone | Set `LOCAL_TZ` for date derivation | No |
| meta | meta/auto-mode | Enable Claude Code auto mode (fewer enter presses) | No |
| areas | areas/define-rooms | Define rooms for the weekly tidiness check | No |
| areas | areas/define-household-areas | Define household areas for the monthly status check | No |
| daily-loop | daily-loop/add-task | Capture a task | No |
| daily-loop | daily-loop/list-tasks | See your open tasks | No |
| daily-loop | daily-loop/complete-task | Mark a task done | No |
| daily-loop | daily-loop/focus-2plus1 | Pick 2 critical + 1 bonus for the day | No |
| daily-loop | daily-loop/morning-checkin | Start-of-day routine | No |
| daily-loop | daily-loop/evening-checkin | End-of-day reflection | No |
| daily-loop | daily-loop/log-day | Rate the day (1–5) | No |
| daily-loop | daily-loop/add-hypothesis | Capture a testable claim | No |
| daily-loop | daily-loop/add-project | Register a new short-term project | No |
| tracking | tracking/habits | Daily + monthly habit logging | No |
| tracking | tracking/day-rating | Emotional/energy/focus tracking | No |
| tracking | tracking/trend-analysis | Find what predicts good vs bad days | No |
| knowledge | knowledge/insights | Capture noticings | No |
| knowledge | knowledge/hypotheses | Frame patterns as testable claims | No |
| knowledge | knowledge/findings | Promote validated hypotheses | No |
| health | health/supplements | Supplement registry | No |
| health | health/google-health | Auto-fetch sleep + AZM | Yes |
| reviews | reviews/weekly-checkin | Sunday 30-min retro | No |
| reviews | reviews/monthly-checkin | First-of-month deeper review | No |
| reviews | reviews/yearly-checkin | Annual reflection | No |
| areas | areas/areas | Life-area folder structure | No |
| areas | areas/area-statements | Write what each area means to you | No |
| areas | areas/second-brain | Drop docs into 2-areas/<area>/ | No |
| visions | visions/visions | Long-term direction (no deadlines) | No |
| integrations | integrations/calendar | Google Calendar event scheduling | Yes |
| integrations | integrations/email-triage | Gmail inbox prioritization | Yes |
| integrations | integrations/google-health | Auto-fetch sleep + AZM | Yes |
| integrations | integrations/trello-inbox | Phone widget for fast voice capture | Yes |
| integrations | integrations/trello-dashboard | Full PFC board + mark-complete sync from phone | Yes |
| meta | meta/personas | Voice/character overlays for the assistant | No |
| meta | meta/profile | Personality/brain context (interview + optional assessments) | No |
| meta | meta/personality | Deep personality reference file (`0-me/personality.md`) | No |
| meta | meta/core-psychology | Deep neuropsych / EF / alexithymia reference (`0-me/core-psychology.md`) | No |
| meta | meta/working-with-me | Collaboration profile (interview) | No |
| meta | meta/system-is-editable | How to ask the system to change itself | No |

---

## Step 4: Suggestion logic (bare `/pfc-onboarding`)

Read current state, then apply this logic:

1. **Zero events in `config/onboarding.ndjson`** (brand new user): suggest the early-foundation sequence. Frame it as: "Let's start with the most basic move — capturing a task. Run `/pfc-onboarding daily-loop/add-task` when ready. After that, the four foundation lessons that shape every future session are: `meta/set-local-timezone` (so dates are right), `meta/profile` (so the agent knows who it's working with — loaded every request), `areas/areas` (so the life domains in your weekly check-in and Trello board reflect *your* life — fresh installs can prune freely), and `meta/system-is-editable` (so you know the system itself is editable). After those, the suggestions get specific to features you'd actually use."

2. **Only `daily-loop/add-task` has been tried**: suggest `meta/set-local-timezone` (30-second fix; dates will be wrong otherwise).

3. **`daily-loop/add-task` and `meta/set-local-timezone` tried, `meta/profile` not yet**: suggest `meta/profile`. Make the always-loaded framing explicit: "This file is read on every agent request — even a 5-minute pass at the Who section sharply improves suggestions across every future session."

4. **First three foundations done (`daily-loop/add-task`, `meta/set-local-timezone`, `meta/profile`), `areas/areas` not yet**: suggest `areas/areas`. Frame it as: "Right now you have 12 shipped life areas — career, family, finances, health, household, learning, legal, personal, recreation, relationship, social, spiritual. Most users delete 2–4 of these (e.g. `legal` if you don't track regulatory work, `spiritual` if it doesn't fit, `relationship` if you're single) and maybe add 1–2 specific ones. Right now nothing references these areas yet, so pruning is free."

5. **First four foundations done but `meta/system-is-editable` not yet**: suggest `meta/system-is-editable`. Knowing the system is editable retains users.

6. **Otherwise**: scan categories in this order — daily-loop, meta, tracking, knowledge, health, reviews, areas, visions, integrations. For each category, if at least one feature in that category has status `tried`, find the first feature in that category with status `not_introduced` and suggest it. Cap at 1 suggestion. If all features in all tried-categories are exhausted, suggest the first `not_introduced` feature in the next untouched category.

7. **All features tried or dismissed**: congratulate briefly. Offer to revisit any dismissed feature or show status.

Show at most 1-2 suggestions per bare invocation. Do not dump the full catalog.

---

## Step 5: Lesson sections

Run the matching lesson below. After the user completes "Try it now," append a `tried` event (Step 2 state helpers). If the user says skip or dismiss at any point, append a `dismissed` event and stop.

---

### Lesson: daily-loop/add-task

**What it is**
Tasks live in `5-actions/_data/tasks.ndjson`. Every task has a size (XS–XL), location (Home/PC/Errand/Phone/Anywhere), impact (high/medium/low), and urgency (high/medium/low). The system picks tasks for you based on these fields — you don't have to re-prioritize by hand each morning.

**Why use it**
Use this whenever something occurs to you that you don't want to lose. The external capture is the whole point — your brain doesn't have to hold it. Skip if you already have a capture system you trust.

**Try it now**
Type something you want to remember to do. It can be as small as "buy milk" or as large as "research new laptop." The skill will walk you through any missing fields.

```
/pfc-add-task <describe the thing>
```

After you run it and the task is saved, come back here and I'll mark this lesson complete.

*(After user completes the action, append `tried` event for `daily-loop/add-task`.)*

**Skip / dismiss**
Not ready? `/pfc-onboarding skip daily-loop/add-task`

---

### Lesson: daily-loop/list-tasks

**What it is**
Shows all open tasks in a readable list, sorted by urgency and impact. Pulls directly from `5-actions/_data/tasks.ndjson` using `jq`.

**Why use it**
Your task file is the canonical backlog. This is the fast way to see what's there without opening the file. Use it any time you want to know what you have in flight.

**Try it now**
```
/pfc-list-tasks
```

*(After user runs it, append `tried` event for `daily-loop/list-tasks`.)*

**Skip / dismiss**
`/pfc-onboarding skip daily-loop/list-tasks`

---

### Lesson: daily-loop/complete-task

**What it is**
Marks a task done, sets the `completed` date, and logs a lifecycle event to `5-actions/_data/task_events.ndjson`. Completed tasks stay in `tasks.ndjson` until the next weekly check-in archives them.

**Why use it**
Closing the loop matters. Completed tasks get archived weekly, which keeps the active file clean. The event log builds a history of what you actually shipped.

**Try it now**
Pick a task you've already finished (or add a throwaway one first). Run:
```
/pfc-complete-task
```
The skill will ask which task to close if you don't specify one.

*(After user completes the action, append `tried` event for `daily-loop/complete-task`.)*

**Skip / dismiss**
`/pfc-onboarding skip daily-loop/complete-task`

---

### Lesson: daily-loop/focus-2plus1

**What it is**
Each morning you pick 3 deliberate items: 2 critical tasks + 1 bonus stretch task. Optionally a 4th slot for an active project task. Logged in `5-actions/_data/daily-focus.ndjson`. The morning check-in runs this automatically, but you can run it standalone too.

**Why use it**
The 2+1 structure prevents the "I'll just pick the easy things" trap. Two critical items forces prioritization. The bonus slot gives you a safe stretch without guilt if it doesn't land. If you're doing the morning check-in daily, you get this automatically — no need to run it separately.

**Try it now**
```
/pfc-morning-checkin
```
Or if you want focus only:
```
/pfc-schedule-focus
```

*(After user completes the action, append `tried` event for `daily-loop/focus-2plus1`.)*

**Skip / dismiss**
`/pfc-onboarding skip daily-loop/focus-2plus1`

---

### Lesson: daily-loop/morning-checkin

**What it is**
A structured start-of-day routine: pulls your schedule, surfaces active projects, picks your 2+1 focus, schedules focus blocks on your calendar (if configured), and shows habit reminders. Takes 5-10 minutes. The highest-leverage daily ritual in the system.

**Why use it**
The morning check-in externalizes what your prefrontal cortex is supposed to do natively — prioritize, plan, sequence. If you do one thing in the system daily, make it this. Skip it if your mornings are already structured and you don't want a routine.

**Try it now**
```
/pfc-morning-checkin
```

*(After user completes the action, append `tried` event for `daily-loop/morning-checkin`.)*

**Skip / dismiss**
`/pfc-onboarding skip daily-loop/morning-checkin`

---

### Lesson: daily-loop/evening-checkin

**What it is**
An end-of-day reflection: logs which focus tasks were completed, surfaces active project status, prompts for manual habits, and captures anything that surfaced during the day. Takes 5-7 minutes.

**Why use it**
The evening check-in closes the loop on the day. It catches drift — tasks that didn't happen, habits that were missed, project velocity that slipped. If you're only doing one check-in, morning is higher leverage, but evening gives you the retrospective data.

**Try it now**
```
/pfc-evening-checkin
```

*(After user completes the action, append `tried` event for `daily-loop/evening-checkin`.)*

**Skip / dismiss**
`/pfc-onboarding skip daily-loop/evening-checkin`

---

### Lesson: daily-loop/log-day

**What it is**
Logs a 1–5 day rating plus optional tags (energy, focus, mood, what went well, what didn't). Stored in `data/day-tracking.ndjson`. The trend-analysis skill later mines this data to find what predicts your best days.

**Why use it**
The rating is low-friction — takes 30 seconds. Over weeks, it becomes your most actionable dataset: which inputs (sleep, exercise, meds, social load) actually move your day quality. Skip it if you're not interested in trend data.

**Try it now**
```
/pfc-log-day
```
The skill will ask for a rating and a few optional tags.

*(After user completes the action, append `tried` event for `daily-loop/log-day`.)*

**Skip / dismiss**
`/pfc-onboarding skip daily-loop/log-day`

---

### Lesson: daily-loop/add-hypothesis

<!-- TODO: full lesson content -->

**Try it now:** `/pfc-add-hypothesis` | **Skip:** `/pfc-onboarding skip daily-loop/add-hypothesis`

---

### Lesson: daily-loop/add-project

<!-- TODO: full lesson content -->

**Try it now:** `/pfc-add-project` | **Skip:** `/pfc-onboarding skip daily-loop/add-project`

---

### Lesson: tracking/habits

**What it is**
Daily and monthly habit tracking. Up to 5 daily habits (logged each day, frequency 1–7/week) and 5 monthly habits (frequency 1–4/month). Defined in `config/habit_schema.yaml`. Logged to `6-habits/_data/habits-daily.ndjson` and `habits-monthly.ndjson`. Some habits can be auto-fetched from Google Health (sleep, active zone minutes) — the automation handles those without prompting.

**Why use it**
Habits are the repeating behaviors that compound. The system tracks streaks, surfaces missed habits in check-ins, and feeds the trend-analysis skill so you can see which habits actually move your day rating. Skip if you're already using a separate habit tracker you trust — don't double-log.

**Try it now**
Think of one behavior you want to build or track. Run:
```
/pfc-log-habit
```
The skill will show your configured habits and let you log today's completion.

*(After user completes the action, append `tried` event for `tracking/habits`.)*

**Skip / dismiss**
`/pfc-onboarding skip tracking/habits`

---

### Lesson: tracking/day-rating

**What it is**
The numeric backbone of day tracking: a 1–5 daily rating stored alongside energy level, focus level, mood tags, and free-text notes in `data/day-tracking.ndjson`. Run via `/pfc-log-day`. This is the same as the `daily-loop/log-day` feature — the `tracking/day-rating` entry is the data-side view of the same action.

**Why use it**
The rating alone is worth logging even if you skip all other tags. It's the Y-axis for trend analysis — without it, you can't find correlations. If you logged a day already in `daily-loop/log-day`, this lesson is already tried.

**Try it now**
If you haven't logged today's rating yet:
```
/pfc-log-day
```

*(After user completes the action, append `tried` event for `tracking/day-rating`.)*

**Skip / dismiss**
`/pfc-onboarding skip tracking/day-rating`

---

### Lesson: tracking/trend-analysis

<!-- TODO: full lesson content -->

**Try it now:** `/pfc-analyze-trends` | **Skip:** `/pfc-onboarding skip tracking/trend-analysis`

---

### Lesson: knowledge/insights

<!-- TODO: full lesson content -->

**Try it now:** `/pfc-add-insight` | **Skip:** `/pfc-onboarding skip knowledge/insights`

---

### Lesson: knowledge/hypotheses

<!-- TODO: full lesson content -->

**Try it now:** `/pfc-add-hypothesis` | **Skip:** `/pfc-onboarding skip knowledge/hypotheses`

---

### Lesson: knowledge/findings

<!-- TODO: full lesson content -->

**Try it now:** View `data/findings.ndjson` | **Skip:** `/pfc-onboarding skip knowledge/findings`

---

### Lesson: health/supplements

<!-- TODO: full lesson content -->

**Try it now:** `/pfc-supplement` | **Skip:** `/pfc-onboarding skip health/supplements`

---

### Lesson: health/google-health

<!-- TODO: full lesson content -->

Auth-gated — requires Google Health setup. See `docs/install/connectors.md`. **Skip:** `/pfc-onboarding skip health/google-health`

---

### Lesson: reviews/weekly-checkin

<!-- TODO: full lesson content -->

**Try it now:** `/pfc-weekly-checkin` | **Skip:** `/pfc-onboarding skip reviews/weekly-checkin`

---

### Lesson: reviews/monthly-checkin

<!-- TODO: full lesson content -->

**Try it now:** `/pfc-monthly-checkin` | **Skip:** `/pfc-onboarding skip reviews/monthly-checkin`

---

### Lesson: reviews/yearly-checkin

<!-- TODO: full lesson content -->

**Try it now:** `/pfc-yearly-checkin` | **Skip:** `/pfc-onboarding skip reviews/yearly-checkin`

---

### Lesson: areas/areas

**What it is.** Areas are the life domains the system tracks against. Every project, habit, and strategic task declares an `area:` field that must match one of the folder names under `2-areas/`. That linkage powers the weekly Values Alignment Check, the monthly Life Wheel, and the Trello area-color labels.

**Why this is one of the earliest customizations.** The template ships with 12 starter areas (`career`, `family`, `finances`, `health`, `household`, `learning`, `legal`, `personal`, `recreation`, `relationship`, `social`, `spiritual`) — a reasonable menu, not a prescription. **On a fresh install no tasks/habits/projects reference any area, so you can delete, rename, and add areas freely.** Once you start logging real data, deletions require cleaning up the references first.

Pruning is healthier than aspiration. The right number is whatever you'll actually engage with.

**Try it now**

1. List what's there:
   ```bash
   ls 2-areas/
   ```

2. Read `2-areas/README.md` for the customization recipes (delete, rename, add) and common patterns (single → drop `relationship`; non-religious → drop or rename `spiritual`; small-footprint life → cut down to 5–6).

3. Delete what doesn't apply. Examples:
   ```bash
   rm -rf 2-areas/legal       # if you don't have regulatory/wills/contracts work to track
   rm -rf 2-areas/spiritual   # if it doesn't fit your worldview
   rm -rf 2-areas/relationship  # if you're single and don't want a hopeful-future placeholder
   ```

4. Rename anything that's close-but-not-right. Example:
   ```bash
   mv 2-areas/spiritual 2-areas/meaning
   ```

5. Add anything you need that isn't there. Example:
   ```bash
   mkdir 2-areas/parenting
   cp 2-areas/career/statement.md 2-areas/parenting/statement.md
   ```

6. Run the validator to confirm everything still parses:
   ```bash
   scripts/validate.sh
   ```

*(After user has at least listed or edited the area set, append `tried` event for `areas/areas`.)*

**Common pitfalls**

- **Deleting an area after you've logged tasks against it.** The validator will fail with broken references. Fix by editing the affected NDJSON records to point at a different area, then delete.
- **Aspirational areas you'll never touch.** If `spiritual` has been an empty statement for three months, that's not a moral failure — it's a signal the area doesn't fit your life. Delete it.
- **Too many overlapping areas.** If `personal` and `recreation` blur, merge them. The system tolerates whatever cardinality you choose.

**Skip / dismiss**
`/pfc-onboarding skip areas/areas`

---

### Lesson: areas/define-rooms

<!-- TODO: full lesson content -->

Define the rooms in your home for the weekly tidiness check. Edit the room list in `pfc-weekly-checkin` (search for `room_a, room_b`), or skip if you don't want this part of the system.

**Try it now:** open `.agents/skills/pfc-weekly-checkin/SKILL.md`, find `room_a, room_b`, replace with your room list | **Skip:** `/pfc-onboarding skip areas/define-rooms`

---

### Lesson: areas/define-household-areas

<!-- TODO: full lesson content -->

Define your household areas (kitchen, garage, etc.) for the monthly household-status check. These get tracked in `2-areas/_data/household-status.ndjson` — add them as you set up the system.

**Try it now:** open `2-areas/_data/household-status.ndjson` and add an initial entry with your household areas | **Skip:** `/pfc-onboarding skip areas/define-household-areas`

---

### Lesson: areas/area-statements

<!-- TODO: full lesson content -->

**Try it now:** Open `2-areas/<your-area>/statement.md` and write one sentence | **Skip:** `/pfc-onboarding skip areas/area-statements`

---

### Lesson: areas/second-brain

<!-- TODO: full lesson content -->

**Try it now:** Drop any document into `2-areas/<area>/` | **Skip:** `/pfc-onboarding skip areas/second-brain`

---

### Lesson: visions/visions

<!-- TODO: full lesson content -->

**Try it now:** `/pfc-add-vision` | **Skip:** `/pfc-onboarding skip visions/visions`

---

### Lesson: integrations/calendar

<!-- TODO: full lesson content -->

Auth-gated — requires Google Calendar MCP setup. See `docs/install/connectors.md`. **Skip:** `/pfc-onboarding skip integrations/calendar`

---

### Lesson: integrations/email-triage

**What it is.** `/pfc-email-triage` walks your Gmail inbox by priority and offers to convert each high-or-medium-priority email into a task. The skill requires 9 manually-applied labels — without them, the queries return zero results and the skill has nothing to show.

**The label scheme.** A 3×3 grid: first letter = **importance** (A high · B medium · C low), second letter = **urgency** (same axes). 9 labels total, plus an implicit "unprocessed" bucket for inbox emails that haven't been labeled yet.

| Importance ↓ / Urgency → | A (urgent) | B (medium) | C (low) |
|---|---|---|---|
| **A (high)** | `AA` Top | `AB` High | `AC` Medium |
| **B (medium)** | `BA` High | `BB` Medium | `BC` Low |
| **C (low)** | `CA` Medium | `CB` Low | `CC` Lowest |

Why two axes: a 1-D priority scheme collapses "really matters but not on fire" (e.g. quarterly tax planning) with "not important but yelling for response" (e.g. a vendor's follow-up email). Two axes keeps them distinct, and the diagonal becomes the natural sort order.

**Setup — create the 9 labels:**

1. Open Gmail in a browser.
2. Left sidebar → scroll down → **Create new label** → enter `AA` → Create. Repeat for `AB`, `AC`, `BA`, `BB`, `BC`, `CA`, `CB`, `CC`. (Yes, 9 clicks. One-time.)
3. Optional: assign colors. A common pattern is reds for AA-AB-BA (top + high), oranges for AC-BB-CA (medium), yellows for BC-CB (low), green for CC (lowest). Color is cosmetic — the skill reads label names only.

**Bulk-apply via Gmail filters (optional but recommended):**

Gmail can auto-apply labels by sender pattern. Settings → Filters and Blocked Addresses → Create a new filter:

- `from:(boss@example.com OR cofounder@example.com)` → Apply label `AB`
- `from:(*@bank.example.com OR *@irs.gov)` → Apply label `AC`
- `from:(notifications@*.com OR newsletters@*.com)` → Apply label `BC`

After creating each filter, check "Apply to existing conversations" to backfill.

**Daily workflow:**

- Anything that lands unlabeled in inbox is "unprocessed." During the day, swipe-label or click-label important threads as `AA`/`AB`/`BA`/`AC`/`BB`/`CA`.
- Run `/pfc-email-triage` once or twice a day. It shows everything labeled, walks you through high/medium items, offers to convert each into a task.

**MCP gate:** also requires the Gmail MCP connector. See `docs/install/connectors.md` for the auth flow.

**Skip:** `/pfc-onboarding skip integrations/email-triage` if you don't use Gmail or don't want labeled triage.

---

### Lesson: integrations/google-health

<!-- TODO: full lesson content -->

Auth-gated — requires Google Health API setup. See `docs/install/connectors.md`. **Skip:** `/pfc-onboarding skip integrations/google-health`

---

### Lesson: integrations/trello-inbox

**What it is**
A Trello board configured as a phone-accessible inbox. You add cards from your phone (voice dictation, Android widget, or iOS Shortcuts) and then process them in Claude Code via `/pfc-trello-inbox`. Each card becomes a task, insight, or note. This is the recommended fast-capture path when you're away from your desk.

**Auth check — run this before proceeding**

```bash
# Check if Trello MCP is configured
# Look for trello-related MCP tool availability
jq -r '.mcpServers | keys[]' .claude/settings.json 2>/dev/null | grep -i trello || echo "not configured"
```

If not configured: Trello integration is optional but recommended. It's free (Power-Ups don't require a paid Trello plan). Setup takes ~20 minutes. See `docs/install/trello.md` for the full walkthrough. Run `/pfc-onboarding reset integrations/trello-inbox` when you've set it up.

Mark `introduced` now and stop if Trello isn't configured.

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
jq -cn --arg f "integrations/trello-inbox" --arg s "introduced" --arg d "$TODAY" \
  '{feature:$f, status:$s, date:$d}' >> config/onboarding.ndjson
```

**If configured, continue:**

**Trello framing — important before you set this up**
- Recommended, not required. The system works fully without it. The benefit is phone-accessible capture when you're not at your keyboard.
- Power-Ups are FREE. You do not need a paid Trello plan for the integrations this system uses.
- Android: add the Trello board widget to your home screen for one-tap board view. Use the Trello dictation shortcut for inbox cards.
- iOS: set up Trello in Shortcuts or use the Action Button for quick board access.
- The inbox board is a single list. Everything you add there gets processed the next time you run `/pfc-trello-inbox`.

**Why use it**
Fast capture away from keyboard is where most ideas and to-dos get lost. If you rely on your phone throughout the day, this closes the gap. Skip if you're always near a keyboard or have a different phone-capture habit that works.

**Try it now**
1. Add one card to your Trello inbox board (any title).
2. Then run:
```
/pfc-trello-inbox
```
The skill will walk through each card, propose what to do with it, and delete it on success.

*(After user completes the action, append `tried` event for `integrations/trello-inbox`.)*

**Skip / dismiss**
`/pfc-onboarding skip integrations/trello-inbox`

---

### Lesson: integrations/trello-dashboard

**What it is.** A read-only mirror of your entire PFC system rendered onto a Trello board: values, areas, visions, projects, today's 2+1, all open actions, daily/monthly habits, recent day ratings, calendar week, top-priority email, insights, findings, hypotheses, supplements. Combined with the `📥 Inbox` list from the previous lesson, this is the single most useful thing you can do for phone-accessible system visibility. Two-way sync lets you tick off tasks and habits from a home-screen widget and have them flow back into the repo.

**Why this matters specifically for the kinds of brains this template targets.** Story memory loss, low working-memory carry between contexts, ADHD's "out of sight, out of mind" tax — the dashboard is the externalized prefrontal cortex layer. If you have any version of "I forget what I was tracking once I close the laptop," this fixes it.

**Auth check — run this before proceeding**

```bash
# Check whether the Trello env vars are set (the render does not use MCP — it uses the helper script directly)
[ -n "$TRELLO_API_KEY" ] && [ -n "$TRELLO_API_TOKEN" ] && [ -n "$TRELLO_DASHBOARD_BOARD_ID" ] && echo "configured" || echo "not configured"
```

If `not configured`: this lesson requires the full Trello board setup. See `docs/install/trello.md`. Mark `introduced` and come back after setup:

```bash
TODAY=$(TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d')
jq -cn --arg f "integrations/trello-dashboard" --arg s "introduced" --arg d "$TODAY" \
  '{feature:$f, status:$s, date:$d}' >> config/onboarding.ndjson
```

Then run `/pfc-onboarding reset integrations/trello-dashboard` once you've worked through `docs/install/trello.md` Steps 1–5 (board created, API key/token minted, env vars set, first `python3 automations/scripts/trello_render.py` succeeded).

**If configured, continue:**

**This is a multi-session lesson.** Plan 30+ minutes total, but split it across 2–3 sittings:

1. **Setup walkthrough** (~15–20 min) — covered by `docs/install/trello.md`. By the time you start this lesson the board should already exist, the API key/token should be in `.env`, and `/pfc-render-trello` should produce cards. If it doesn't, fix that first.
2. **Widget setup** (~5–10 min) — `docs/install/trello.md` Step 6. Decide which lists you want as home-screen widgets. Most-recommended starter set:
   - `📥 Inbox` (capture; Android list widget with `+` button)
   - `✅ 2+1` (tap-to-complete today's focus)
   - `☀️ Daily Habits` (tap-to-check off habits)
   - One board widget as a one-tap launcher into the full dashboard.
   Add the others (`📧 Email Priorities`, `🗓️ Week at a Glance`, `🛠️ Projects`, `⬅ Last 7 Days`) once you know which surfaces you reach for most.
3. **Sync verification** (~5 min) — mark a habit complete from the widget, run `/pfc-sync-trello` or wait for the next checkin, and confirm the entry landed in `6-habits/_data/habits-daily.ndjson`. Do the same for a 2+1 task. If the round-trip works, the system is live.

**Try it now**

1. Run a render: `/pfc-render-trello`.
2. Open the board on your phone. Confirm cards have populated across `✅ 2+1`, `☀️ Daily Habits`, `🛠️ Projects`, etc.
3. Set up at least the `📥 Inbox` + `✅ 2+1` + Board widgets on your home screen.
4. From the widget, tick off one daily habit you actually did today (or add a test card to Inbox).
5. Run `/pfc-sync-trello` — counters should show what landed.

*(After the round-trip works, append `tried` event for `integrations/trello-dashboard`.)*

**What this gets you in daily use**

- Morning: glance at the widget instead of opening the laptop to see today's focus.
- Throughout the day: tick off habits and 2+1 tasks the moment you finish them. No "I'll log it later" debt.
- Anytime: voice-dictate captures into `📥 Inbox`. Process when convenient via `/pfc-trello-inbox`.
- The repo is still canonical. The dashboard is a rendered cache. If they ever drift, `/pfc-render-trello` re-establishes the dashboard from repo state — no manual reconciliation.

**Skip / dismiss**
`/pfc-onboarding skip integrations/trello-dashboard`

---

### Lesson: meta/set-local-timezone

**What it is**
Set `LOCAL_TZ` in `.env` to your IANA timezone (e.g. `America/New_York`, `Europe/London`). Defaults to `America/Denver` if unset. This drives every date-derivation step — get it right before you start logging.

**Why use it**
Every date the system stamps (task ids, focus picks, habit logs, day-tracking entries) is derived in your local timezone. If `LOCAL_TZ` is wrong, late-evening entries land on the wrong day.

**Try it now**
```
cp .env.example .env   # if you haven't already
# Edit .env and set LOCAL_TZ to your IANA timezone, e.g.
# LOCAL_TZ=America/New_York
```

Confirm with:
```
TZ="${LOCAL_TZ:-America/Denver}" date '+%Y-%m-%d %H:%M %Z'
```

*(After user completes the action, append `tried` event for `meta/set-local-timezone`.)*

**Skip / dismiss**
`/pfc-onboarding skip meta/set-local-timezone`

---

### Lesson: meta/auto-mode

**What it is.** Claude Code's "auto mode" lets the assistant execute multi-step work without pausing to ask permission after every tool call. With auto mode off, you tap enter dozens of times per session to approve each Bash / Edit / Read. With it on, low-risk operations run autonomously and you're only interrupted for destructive or shared-system actions (force-pushes, deletions, etc.).

**Why this is worth doing.** The PFC system runs *lots* of small operations per skill — a single morning-checkin can fire 30+ tool calls. Auto mode keeps you out of the loop for the safe ones while still asking before anything you'd actually want to think about.

**Safety note.** Auto mode does NOT mean "no guardrails." Anything that deletes data, force-pushes, or modifies shared systems still requires explicit confirmation. The harness classifier blocks destructive actions even in auto mode unless you've explicitly authorized them.

**How to enable it.** In a Claude Code session, type the `/` command listed in Claude Code's docs for auto / accept-edits mode (the exact name varies by version — current versions surface a toggle in the slash-command menu). You can also set per-project `defaultMode` in `.claude/settings.json` to `acceptEdits` if you want the harness to default to accepting tool-use edits — but **auto mode itself is a runtime toggle, not a settings.json field.**

**Where to use it.** Auto mode works in a normal terminal session (e.g. SSH from Termius into a tmux'd Claude Code instance — see `docs/install/remote-access.md`). It may or may not be exposed in Claude Code Remote Control depending on your version. If you rely on auto mode and Remote Control's toggle doesn't behave, fall back to attaching via Termius and toggling there.

```bash
# To check what's available in your version of Claude Code:
claude --help | grep -iE "auto|accept|mode" || true
# Or in an active session: type "/" and look for a mode-toggle entry.
```

**Try it now**
1. Start a session, type `/`, look for an auto-mode or accept-edits entry, enable it.
2. Run `/pfc-morning-checkin` and notice how few times you're asked to approve a tool call.
3. If you don't like the lower friction, switch it back off — it's a session-level toggle.

*(After user has tried it once, append `tried` event for `meta/auto-mode`.)*

**Skip / dismiss**
`/pfc-onboarding skip meta/auto-mode`

---

### Lesson: meta/personas

**What it is**
Optional voice/character overlays for the assistant. Personas change tone, diction, and style — not the underlying system rules. The active persona is stored in `config/persona.yaml`. Switch with `/pfc-persona`. Examples include a calm coach, a direct operator, or a game-UI framing (the Solo Leveling System persona renders output as bracketed game windows).

**Why use it**
If you find the default assistant voice flat or uninspiring, a persona can make daily interactions more engaging without sacrificing accuracy. Skip entirely if you don't care about tone customization.

**Try it now**
```
/pfc-persona
```
The skill will list available personas and let you activate one. You can always switch back with `/pfc-persona off`.

*(After user completes the action, append `tried` event for `meta/personas`.)*

**Skip / dismiss**
`/pfc-onboarding skip meta/personas`

---

### Lesson: meta/profile

**What it is.** `0-me/profile.md` is the always-loaded ground-truth file about who you are and how your brain operates. It is `@`-imported by `AGENTS.md`, which means **every agent request loads its contents** — so whatever's in this file shapes every suggestion, every check-in, every prioritization the system makes.

**Why this is one of the earliest things to do.** The file ships with conservative defaults for the **Brain** section (works for the target ADHD/autism profile out of the box), but the **Who** section is mostly empty placeholders. Until you fill in Who, the agent has no real handle on your motivators, anti-motivators, top values, or connection style — so its suggestions stay generic. Five minutes of editing here pays back across every future session.

**How to do it — minimum viable fill-in (~5 min).**

Open `0-me/profile.md` and fill in just these four lines under "Who" with a short phrase each. Don't overthink it; you can always come back and refine.

1. **Top motivators (3–5 of them).** What actually drives you to do work? Examples: problem-solving, family, impact, learning, mastery, autonomy, contribution. Skip the corporate-poster list — name what's true for you.
2. **Anti-motivators (top 2–3).** What's *supposed* to motivate but doesn't? Common ones that fall flat for many people in the target audience: recognition, money, prestige, pressure, fun-as-a-goal. If any of these feel like noise rather than fuel, name them — the system will stop trying to use them as carrots.
3. **Top values — link to `1-values/values.md`.** You'll be doing the values exercise via `/pfc-add-vision` or similar later; for now, name 3–5 values that feel non-negotiable.
4. **Love languages or connection currencies (optional but high-leverage).** If quality time, physical touch, words, acts, or gifts have noticeably different weights for you, name your top one. The system uses this for the "personal time vs deep work" calibration.

**How to do it — deeper fill-in (~30 min, optional).**

If you want a more grounded profile, take a few free assessments first. The "Who" section has a slot for personality framework results — fill in whatever framework's vocabulary helps you think:

- [openpsychometrics.org](https://openpsychometrics.org) — Big Five, Enneagram, MBTI, Working Genius, DISC. Free, no signup, takes 10–15 min each.
- For Working Genius specifically (E+W / T+G framing is referenced in the shipped Brain section), the official assessment is paid — the openpsychometrics version is a reasonable free proxy.

Drop your results into the relevant lines. Don't feel obligated to fill every framework — pick 1–2 that resonate.

**About the Brain section.** It ships with target-audience defaults (ADHD attention paradox, story-memory weakness, masking load, hyperfocus-as-problem-state, "I'm fine" calibration). If you're not in that audience, edit aggressively — remove lines that don't apply, soften ones that are partially true. If you *are* in that audience, the defaults likely fit better than you'd guess; leave them and tune later if specific lines feel wrong.

**Try it now**

1. Open `0-me/profile.md` in your editor.
2. Fill in the four "Who" lines above with short phrases.
3. Save. The next agent response will pick up the new context automatically.

*(After user has edited the file at all, append `tried` event for `meta/profile`.)*

**Going deeper (later, optional)**

- `meta/personality` lesson — create `0-me/personality.md` as a deeper assessment archive (multiple frameworks). Loaded on demand, not on every request.
- `meta/core-psychology` lesson — create `0-me/core-psychology.md` for neuropsych eval / EF / alexithymia instrument results, if you have them.

**Skip / dismiss**
`/pfc-onboarding skip meta/profile`

---

### Lesson: meta/personality

**What it is**
A deep-reference file at `0-me/personality.md` capturing your personality across multiple assessment frameworks (Big Five, Enneagram, MBTI, DISC, Working Genius, Kolbe, etc.). The system reads this on demand when a decision needs deeper context than `profile.md` provides.

**Why use it**
`profile.md` is the always-loaded summary — kept short for performance. `personality.md` is the deep archive, only loaded when explicitly asked. Skip if you don't want a detailed personality reference.

**Try it now**
1. Take free assessments at [openpsychometrics.org](https://openpsychometrics.org) (Big Five, Enneagram, others).
2. Optionally do Working Genius, Kolbe, MBTI variants elsewhere.
3. Create `0-me/personality.md` with your results as plain markdown — copy raw scores and one-line interpretations per framework.

**Skip / dismiss**
`/pfc-onboarding skip meta/personality`

---

### Lesson: meta/core-psychology

**What it is**
A deep-reference file at `0-me/core-psychology.md` capturing neuropsych evaluation results, executive function profile, ADHD / autism / alexithymia instrument scores, and any clinical findings. Only relevant if you have such results or want to do deep self-assessment.

**Why use it**
The system reads this when working with neurodivergent context — initiation / execution patterns, sensory needs, masking load, alexithymia signals. Skip if you don't have or don't want clinical-depth self-data.

**Try it now**
1. If you have a neuropsych evaluation, transcribe key findings into `0-me/core-psychology.md`.
2. Optionally take instruments: AQ-10 (autism), ASRS (ADHD), TAS-20 (alexithymia), BRIEF-A (executive function), SQ-R (systemizing), EQ (empathy).
3. Format as plain markdown with framework name + score + one-line interpretation.

**Skip / dismiss**
`/pfc-onboarding skip meta/core-psychology`

---

### Lesson: meta/working-with-me

**What it is.** `0-me/working-with-me.md` is the long-form companion to the hot-path rules in `AGENTS.md`. It documents *why* the agent should behave a certain way — the texture, examples, and reasoning behind each rule. Unlike `0-me/profile.md`, this file is **read on demand**, not `@`-imported every request — the agent reaches for it when it needs grounding for a judgment call.

**Why this matters.** When the agent has to make a call (push back? clarify? just do it?) without a covering rule in `AGENTS.md`, it falls back to whatever's in this file. The shipped defaults work for the target audience, but tailoring even a few sections sharpens the agent's read of borderline cases.

**Why this is *not* in the foundation sequence.** Loaded on demand, not every request — so a generic-but-correct shipped version still works fine while you focus on getting `meta/profile` and `meta/set-local-timezone` done first. Come back to this once the daily loop feels familiar.

**The shipped defaults — what's already there.** The file has 8 sections:

1. Three frustration patterns to avoid (confident wrongness, abstract jargon, repetition)
2. Working memory accommodations (recap at top, restate prior answers, pin open questions)
3. Trust, confidence, and pushback (cite sources; defend claims with evidence; where to push back)
4. Decision authority — act vs. ask
5. State adaptation — tired / stuck / hyperfocused
6. Long-term vision — no SMART goals
7. Role and tone (be proactive; soft framing + low-friction next step)
8. System diagnosis — inputs vs. broken-system branching

All eight are framed in generic voice. Out of the box they're conservative defaults that fit most users in the target audience.

**Highest-leverage sections to tailor first.**

If you only have 10 minutes, edit these three:

- **§3 Pushback.** When should the agent push back, and where should it never? Defaults welcome pushback everywhere as long as it's grounded — if you want narrower scope, narrow it here.
- **§4 Decision authority.** Default is "act first, show diff, give a short prose explanation." If you'd rather the agent always ask before editing, change it here.
- **§7 Role and tone.** Defaults toward proactive flagging ("you've skipped X four days in a row"). If you find that intrusive rather than helpful, soften it here.

The other five sections are reasonable to leave for later — they're either accommodations that work for most target-audience users (§1, §2, §5) or scaffolding that rarely needs personalization (§6, §8).

**Try it now**

1. Open `0-me/working-with-me.md` in your editor.
2. Skim the eight sections. Find anything that doesn't match how you actually want to be worked with.
3. Edit those lines. Save.
4. Optional: add a new section if you have a clear collaboration preference the shipped defaults don't cover.

*(After user has edited the file at all, append `tried` event for `meta/working-with-me`.)*

**Skip / dismiss**
`/pfc-onboarding skip meta/working-with-me`

---

### Lesson: meta/system-is-editable

**What it is**
The PFC system is not fixed software. Every skill, rule, schema, and behavior lives in plain text files in this repo — and you can ask Claude to change any of it. You can say "from now on, when I add a task, also ask me for a due date" and it will update the skill file to make that permanent. You can edit `CLAUDE.md` (or `AGENTS.md`) to change cross-cutting rules. You can update `config/habit_schema.yaml` to add a new habit. The whole system is yours.

**Why use it**
Most productivity apps are closed boxes — you get the behavior they ship. This system is a living repo. The skills that run today were written to fit one person's brain; yours is different. The fastest path to a system that actually works for you is to start editing it early, before you build habits around behavior that doesn't fit.

High-leverage edits to consider early:
- Change the default task fields in `pfc-add-task` (e.g., add "energy required" as a field)
- Edit `0-me/profile.md` to match your actual brain and working style
- Update `config/habit_schema.yaml` with habits you actually want to track
- Adjust the 2+1 logic in `pfc-morning-checkin` if 2 critical + 1 bonus doesn't fit your flow

**Try it now**
Pick one thing that already feels off about the system. Tell Claude what you want changed and say "update the skill" or "add this rule to CLAUDE.md." Watch what it does. If you don't like the result, revert with `git checkout <file>`.

Example: "When I add a task, also ask me what time of day is best for it. Add that as a field."

*(After user attempts an edit or says they understand how it works, append `tried` event for `meta/system-is-editable`.)*

**Skip / dismiss**
`/pfc-onboarding skip meta/system-is-editable`

---

## Step 6: Status command (`/pfc-onboarding status`)

Render the full feature table. For each feature, get the most-recent event status from `config/onboarding.ndjson`. Default to `not_introduced` if no event exists.

```bash
# Build status map from onboarding log
jq -s 'group_by(.feature) | map({key: .[0].feature, value: .[-1].status}) | from_entries' \
  config/onboarding.ndjson 2>/dev/null || echo "{}"
```

Then render as a table using circle emojis:

| Symbol | Meaning |
|---|---|
| ✅ | tried |
| 🟡 | introduced |
| ⚫ | dismissed |
| ⬜ | not introduced |

Example output format:

```
Category        Feature                          Status
──────────────────────────────────────────────────────
daily-loop      add-task                         ✅ tried
daily-loop      list-tasks                       🟡 introduced
daily-loop      complete-task                    ⬜ not introduced
tracking        habits                           ⚫ dismissed
...
```

At the bottom, show a one-line summary: "X of 33 features tried · Y dismissed · Z not introduced"

---

## Step 7: Trello-specific framing

Apply this framing at the top of any `integrations/trello-*` lesson — not just trello-inbox:

> **About Trello integration**
> - Recommended, not required. Full PFC works without it.
> - Power-Ups are FREE — no paid Trello plan needed.
> - Android: board widget for home screen, dictation widget for inbox captures.
> - iOS: Action Button or Shortcuts for quick board access.
> - `integrations/trello-dashboard` is a multi-session lesson (3-5 chunks, plan 30+ minutes total).
> - Trello lessons come late in the onboarding arc — complete calendar and email integrations first, or skip them if you're not using those.

---

## Auth-gated lesson pattern ("check before teach")

For every auth-gated feature (marked Yes in Step 3 catalog), apply this pattern before delivering the lesson content:

1. **Detect** — check for the relevant env var or MCP tool availability.
2. **If unconfigured** — show a one-line note with the install path, mark `introduced`, stop. Do NOT teach the lesson content yet.
3. **If configured** — proceed with the full lesson.

```bash
# Calendar detection example
jq -r '.mcpServers | keys[]' .claude/settings.json 2>/dev/null | grep -i calendar || echo "not configured"

# Gmail detection example
jq -r '.mcpServers | keys[]' .claude/settings.json 2>/dev/null | grep -i gmail || echo "not configured"

# Google Health detection example
grep -q "GOOGLE_HEALTH_CLIENT_ID" .env 2>/dev/null && echo "configured" || echo "not configured"
```

If not configured, say:

> "`<feature>` requires `<service>` to be set up. See `docs/install/connectors.md`. Run `/pfc-onboarding reset <feature>` once you've configured it.

Then append `introduced` and stop.
