---
name: pfc-daily-summary
description: Show a daily dashboard — calendar, habits, projects, focus, and day trends. Use when the user says "daily summary", "show my day", "dashboard", "what's on my plate", or "summary".
---

# Daily Summary

Show a scannable snapshot of today's status. This is the ADHD-friendly "what do I need to know right now" view. Output everything in one response — no questions, no interaction. Just the data.

## Sections (in order)

### 1. Today's Schedule (Google Calendar)

Fetch today's events from Google Calendar using the MCP connector:
- List events for today, sorted by time
- Show time, title, and location/link
- If no events, say "No events scheduled today."
- If calendar is unavailable, skip this section silently

### 2. Daily Focus (2+1)

```bash
grep "$(date +%Y-%m-%d)" 5-actions/_data/daily-focus.ndjson | tail -1
```

- Show the 2 critical items and 1 bonus item
- For each, show completion status
- If no focus set today, say "No daily focus set. Run /pfc-morning-checkin to pick your 2+1."

### 3. Daily Habits — This Week

Read habit definitions from `config/habit_schema.yaml` to get the list of active daily habits and their target frequencies.

```bash
# Get this week's habit entries (Monday through today)
WEEK_START=$(date -v-monday +%Y-%m-%d 2>/dev/null || date -d 'last monday' +%Y-%m-%d)
TODAY=$(date +%Y-%m-%d)
# Use jq or grep to filter entries between WEEK_START and TODAY
grep -E "$(date +%Y-%m)" 6-habits/_data/habits-daily.ndjson
```

For each daily habit, show:
- Habit name
- Completions this week vs. target (e.g., "3/7 this week")
- Simple progress indicator: `[===----]` style

If no habits are defined, say "No daily habits configured. See config/habit_schema.yaml."

### 4. Monthly Habits — This Month

```bash
grep "$(date +%Y-%m)" 6-habits/_data/habits-monthly.ndjson
```

For each monthly habit, show:
- Habit name
- Completions this month vs. target (e.g., "1/2 this month")

If no monthly habits are defined, skip this section.

### 5. Active Projects

```bash
grep '"active":true' 4-projects/_data/projects.ndjson
```

For each active project, show:
- Project name
- Completion: `completed_parts / total_parts` as percentage
- Simple progress bar: `[======----] 60%`
- Velocity: `X.X parts/wk → est <YYYY-MM-DD>` vs deadline; flag 🟢 / 🟡 / 🔴. Calc: `parts_per_day = completed_parts / max(1, days_elapsed_since_started)`; `est_completion = today + ceil(remaining_parts / parts_per_day)` if `parts_per_day > 0`, else `—`. 🟢 on or before deadline · 🟡 ≤7 days late · 🔴 >7 days late.

Also check for planned projects:
```bash
grep '"status":"planned"' 4-projects/_data/projects.ndjson
```

Show planned projects in a smaller "Up Next" sub-section.

If no projects exist, say "No active projects."

### 6. Day Rating Trend — Last 7 Days

```bash
jq -c '{date, rating, energy, focus, mood}' data/day-tracking.ndjson | tail -7
```

Show a compact 7-day table: date | rating (stars) | E | F | M | supplement notes. Use `—` for null granular fields. Include a footer with 7-day averages for rating, energy, focus, and mood. Flag any granular axis whose average trails the overall rating by ≥0.5 — that's a hint worth noticing.

### 7. Open Task Count

```bash
TASKS=$(jq -c 'select(.status == "open")' 5-actions/_data/tasks.ndjson | wc -l)
```

Show: "X open tasks" as a single line. Don't list them — that's what /pfc-status and /pfc-pick-tasks are for.

## Formatting Rules

- Use markdown headers (##) for each section
- Keep it scannable — no paragraphs, just structured data
- Use text-based progress bars where applicable: `[====------] 40%`
- No emojis unless the user has requested them
- No questions or prompts — this is a read-only view
- Total output should fit on one screen (aim for ~40-60 lines)
