---
name: pfc-daily-summary
description: Show a daily dashboard — calendar, habits, projects, focus, and day trends. Use when the user says "daily summary", "show my day", "dashboard", "what's on my plate", or "summary".
---

# Daily Summary

Show a scannable snapshot of today's status. This is the ADHD-friendly "what do I need to know right now" view. Output everything in one response — no questions, no interaction. Just the data.

## Sections (in order)

### 1. 🦸 Daily Pulse

The levers that separate your best days from ordinary ones. **This is a morning-side readout and it lives here on purpose** — at night the day is already spent, so "today's lever" and "tonight's one move" arrive too late to act on. Here, the day is still ahead. Objective numbers are the trustworthy read when "I feel fine" isn't.

The thresholds, verdict, and per-lever fix all come from one place, `automations/scripts/pulse.py` (generic starting bands; override them in `config/automation_config.yaml` under `health.pulse`, grounded in your own numbers from `/pfc-analyze-trends`). The same data renders ambiently on the `🦸 Superman Pulse` Trello list and the TRMNL pulse screen — this section is the on-demand chat version, and all three must agree. Never re-derive a band in chat.

**Two zones.** 🛏️ **Last night (locked)** — the sleep + recovery readout, already fixed. ⚡ **Today's lever** — the same-day action (your exercise habit); during the day a miss is 🟡 *not yet*, not 🔴.

**Pull the values** from today's `data/day-tracking.ndjson` record: `health.{sleep_hours, awake_minutes, awakenings_count, sleep_rem_minutes, sleep_deep_minutes, sleep_bedtime, sleep_wake_time}` and `qqrt.{score, sleep_debt.avg_shortfall_min}`. If a field is null, show `—` and skip its light. If today's row has no health data yet, say so in one line and skip the section — do not fall back to yesterday's sleep.

Render as a compact table: `Lever | Last night | Target | ●`, sorted worst-first (red → yellow → green), with the levers and bands `pulse.py` defines.

**⚡ Today's lever.** Below the sleep table, one line from today's exercise habit (the one `config/habit_schema.yaml` marks as your movement habit): 🟢 **Exercise: done** when it's logged, 🟡 **Exercise: not yet** when it isn't. It doesn't feed the sleep verdict; it's the "have you pulled today's lever" check, and in the morning it's still actionable.

**Verdict line** — use the verdict `pulse.py` computes from the CRITICAL levers (🟢 **Primed** / 🟡 **Borderline** / 🔴 **Depleted**). Don't recompute it here.

**Today's one move** — name the single most-actionable out-of-range lever and its concrete fix (one line, not a lecture), taken from the same fix map the Trello verdict card uses, so chat and board never disagree. If every lever is green: "You're in range — just protect tonight."

**7-day trend.** After the one-move line, run:

```bash
python3 automations/scripts/trello_render.py --pulse-history 7
```

It prints a per-lever sparkline, a **days-on-target count** per lever (high is good — AGENTS.md § "Metrics point one direction"; never report these as miss-counts), and flags **chronic misses** (on target ≤3 of 7) with the fix. Surface **at most the top 2** in chat, so a single bad night reads differently from a two-week slide. If there are none, say "pulse is holding" and move on. Don't reprint the sparkline block unless asked.

Keep the whole section tight: the table + one-move line + ≤2 chronic-miss lines.

### 2. Today's Schedule (Google Calendar)

Fetch today's events from Google Calendar using the MCP connector:
- List events for today, sorted by time
- Show time, title, and location/link
- If no events, say "No events scheduled today."
- If calendar is unavailable, skip this section silently

### 3. Daily Focus (2+1)

```bash
grep "$(date +%Y-%m-%d)" 6-tasks/_data/daily-focus.ndjson | tail -1
```

- Show the 2 critical items and 1 bonus item
- For each, show completion status
- If no focus set today, say "No daily focus set. Set today's picks in the tour (`Walk me through` on http://127.0.0.1:4323/) or with /pfc-pick-tasks."

### 4. Daily Habits — This Week

Read habit definitions from `config/habit_schema.yaml` to get the list of active daily habits and their target frequencies.

```bash
# Get this week's habit entries (Monday through today)
WEEK_START=$(date -v-monday +%Y-%m-%d 2>/dev/null || date -d 'last monday' +%Y-%m-%d)
TODAY=$(date +%Y-%m-%d)
# Use jq or grep to filter entries between WEEK_START and TODAY
grep -E "$(date +%Y-%m)" 7-habits/_data/habits-daily.ndjson
```

For each daily habit, show:
- Habit name
- Completions this week vs. target (e.g., "3/7 this week")
- Simple progress indicator: `[===----]` style

If no habits are defined, say "No daily habits configured. See config/habit_schema.yaml."

### 5. Monthly Habits — This Month

```bash
grep "$(date +%Y-%m)" 7-habits/_data/habits-monthly.ndjson
```

For each monthly habit, show:
- Habit name
- Completions this month vs. target (e.g., "1/2 this month")

If no monthly habits are defined, skip this section.

### 6. Active Projects

```bash
grep '"active":true' 5-projects/_data/projects.ndjson
```

For each active project, show:
- Project name
- Completion: `completed_parts / total_parts` as percentage
- Simple progress bar: `[======----] 60%`
- Velocity: `X.X parts/wk → est <YYYY-MM-DD>` vs deadline; flag 🟢 / 🟡 / 🔴. Calc: `parts_per_day = completed_parts / max(1, days_elapsed_since_started)`; `est_completion = today + ceil(remaining_parts / parts_per_day)` if `parts_per_day > 0`, else `—`. 🟢 on or before deadline · 🟡 ≤7 days late · 🔴 >7 days late.

Also check for on-deck projects (wanted next, not started):
```bash
grep '"status":"on-deck"' 5-projects/_data/projects.ndjson
```

Show on-deck projects in a smaller "On deck" sub-section.

If no projects exist, say "No active projects."

### 7. Day Rating Trend — Last 7 Days

```bash
jq -c '{date, rating, energy, focus, mood}' data/day-tracking.ndjson | tail -7
```

Show a compact 7-day table: date | rating (stars) | E | F | M | supplement notes. Use `—` for null granular fields. Include a footer with 7-day averages for rating, energy, focus, and mood. Flag any granular axis whose average trails the overall rating by ≥0.5 — that's a hint worth noticing.

### 8. Open Task Count

```bash
TASKS=$(jq -c 'select(.status == "open")' 6-tasks/_data/tasks.ndjson | wc -l)
```

Show: "X open tasks" as a single line. Don't list them — that's what /pfc-status and /pfc-pick-tasks are for.

### 9. Open the web page (fail-safe)

After the last section is printed:

```bash
scripts/open-web-ui.sh --background
```

It opens `http://127.0.0.1:4323/` (Today) behind the current window, so the summary in chat stays in front, and prints one line saying so. It opens nothing, and says why, when there is no desktop to open a browser on, when the web server is not answering, or when the summary was started from the web page's own chat. It always exits 0. Print its one line as the last line of the summary and nothing more.

## Formatting Rules

- Use markdown headers (##) for each section
- Keep it scannable — no paragraphs, just structured data
- Use text-based progress bars where applicable: `[====------] 40%`
- No emojis except the Daily Pulse status circles (🟢/🟡/🔴), which are required by AGENTS.md
- No questions or prompts — this is a read-only view
- Total output should fit on one screen (aim for ~40-60 lines)
