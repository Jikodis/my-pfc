---
name: pfc-status
description: Full system status — life wheel, household, hypotheses, all tasks, projects, and habits. Use when the user says "status", "full status", "big picture", "how's everything", "system status", or "overview".
---

# Full System Status

Show the complete big-picture view of the entire productivity system. This is the "how's my life going" view — everything at a glance. Output everything in one response — no questions, no interaction.

This includes everything from /pfc-daily-summary PLUS the broader system state.

## Sections (in order)

### 1. Life Wheel

Read the most recent record from `2-areas/_data/life-wheel.ndjson`:
```bash
jq -c '.' 2-areas/_data/life-wheel.ndjson | tail -1
```

Display as a table (area | rating | notes). If the file is empty, say:

"Life wheel has no ratings yet. Run a monthly check-in to rate your life areas (red/yellow/green)."

Count the reds, yellows, and greens: "Life Wheel: X green, Y yellow, Z red — last updated YYYY-MM-DD"

### 2. Active Projects

```bash
grep '"active":true' 4-projects/_data/projects.ndjson
```

For each active project:
- Name, area, excitement level
- Completion: `[======----] 60%` (completed_parts / total_parts)
- Velocity: `X.X parts/wk → est <YYYY-MM-DD>` vs deadline; flag 🟢 (on or before deadline) · 🟡 (≤7 days late) · 🔴 (>7 days late). Calc: `parts_per_day = completed_parts / max(1, days_elapsed_since_started)`; `est_completion = today + ceil(remaining_parts / parts_per_day)` if `parts_per_day > 0`, else `—`.
- Open task count: `grep -c '"project":"PROJECT_ID".*"status":"open"' 5-actions/_data/tasks.ndjson`

Also show planned projects under "Pipeline":
```bash
grep '"status":"planned"' 4-projects/_data/projects.ndjson
```

### 3. Active Hypotheses

```bash
grep '"status":"active"' data/hypotheses.ndjson
```

For each active hypothesis, show:
- Domain and one-line summary of the hypothesis
- Current protocol (brief)
- Latest findings
- Status (calibrating, confirmed, testing, etc.)

### 4. Daily Habits — This Week

Same as /pfc-daily-summary section 3. Show each habit with weekly progress bar.

### 5. Monthly Habits — This Month

Same as /pfc-daily-summary section 4.

### 6. All Open Tasks

```bash
jq -c 'select(.status == "open")' 5-actions/_data/tasks.ndjson
```

**Two subsections. Never repeat a task across them.**

#### 6a. Standalone tasks (`project == "none"`)

Single flat list, sorted by (in order):
1. impact: high → medium → low
2. urgency: high → medium → low
3. size: XS → S → M → L → XL
4. deadline: earliest first (null deadlines last)

One compact line per task, no blank lines between rows:
```
task-YYYYMMDD-NNN  [impact/urgency size]  description  (due YYYY-MM-DD)
```
Omit the `(due …)` parenthetical if deadline is null. Flag overdue with `[OVERDUE]` prefix; flag stale (created 2+ weeks ago and no deadline) with `[STALE]` prefix.

#### 6b. Project tasks — one subsection per active project

For each project with open tasks, render a heading `**<project name>** (<N> open)` then:
- Today's task for this project (deadline == today), if any
- The next 1–2 near-term tasks (deadline > today, soonest first)
- If more remain: a single summary line `+N more through YYYY-MM-DD` (latest deadline across that project's remaining open tasks)
- Any overdue tasks for this project ALWAYS shown individually, above today's — do not collapse overdue

Do NOT enumerate 20–30 course-series tasks. Collapsing is mandatory once a project has >3 future-dated open tasks.

**Rules for both subsections:**
- Never emit a group header more than once
- Never list the same task in both 6a and 6b
- Keep single-line rows; no extra whitespace between rows

### 7. Household Status

Read the most recent record from `2-areas/_data/household-status.ndjson`:
```bash
jq -c '.' 2-areas/_data/household-status.ndjson | tail -1
```

Display as a table (area | rating | notes). If the file is empty, say:

"Household status not yet rated. Run a monthly check-in to rate each area (red/yellow/green)."

Count reds, yellows, greens: "Household: X green, Y yellow, Z red — last updated YYYY-MM-DD"

### 8. Day Rating Trend — Last 14 Days

```bash
jq -c '{date, rating, energy, focus, mood}' data/day-tracking.ndjson | tail -14
```

Show a table with columns: date | overall rating (as stars) | energy | focus | mood | notable supplements. Use `—` for any null granular field. Include 14-day averages for rating, energy, focus, and mood on a footer row. Note if a granular axis is trending visibly lower than overall rating (possible signal worth surfacing).

### 9. Daily Focus — Today

```bash
grep "$(date +%Y-%m-%d)" 5-actions/_data/daily-focus.ndjson | tail -1
```

Show today's focus items if set, otherwise note it's not set.

### 10. System Health

Quick counts:
```bash
TASKS=$(jq -c 'select(.status == "open")' 5-actions/_data/tasks.ndjson | wc -l)
DONE_TASKS=$(jq -c 'select(.status == "done")' 5-actions/_data/tasks.ndjson | wc -l)
PROJECTS_ACTIVE=$(jq -c 'select(.active == true)' 4-projects/_data/projects.ndjson | wc -l)
HYPS_ACTIVE=$(jq -c 'select(.status == "active")' data/hypotheses.ndjson | wc -l)
```

Display:
- Open tasks / Done tasks
- Active projects (max 3)
- Active hypotheses
- Done tasks needing archive (if any still in main file)
- Last check-in date
- Last weekly review date

## Formatting Rules

- Use markdown headers (##) for each section
- Keep it scannable — tables and bullets, no paragraphs
- Use text-based progress bars: `[====------] 40%`
- No emojis unless the user has requested them
- No questions or prompts — this is a read-only view
- Flag anything that needs attention (stale tasks, empty trackers, missing ratings)
- This will be longer than /pfc-daily-summary — aim for completeness over brevity
