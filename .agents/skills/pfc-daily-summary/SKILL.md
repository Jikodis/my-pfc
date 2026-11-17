---
name: pfc-daily-summary
description: Show a daily dashboard — sleep pulse, calendar, habits, projects, focus, and day trends. Use when the user says "daily summary", "show my day", "dashboard", "what's on my plate", or "summary".
---

# Daily Summary

Show a scannable snapshot of today's status. This is the ADHD-friendly "what do I need to know right now" view. Output everything in one response — no questions, no interaction. Just the data.

## Sections (in order)

### 1. Daily Pulse

The sleep and recovery levers that set up a good day, read from last night. **This readout lives in the morning view on purpose:** at night the day is already spent, so "today's one move" arrives too late to act on. In the morning the day is still ahead.

Every threshold, the verdict, and the per-lever fix come from `automations/scripts/pulse.py`, the single source of truth that the Trello and TRMNL pulse surfaces also read. Never restate a band here; tune it in `config/automation_config.yaml` → `health.pulse`.

```bash
python3 - <<'PY'
import json, os, subprocess, sys
from pathlib import Path
sys.path.insert(0, "automations/scripts")
from pulse import pulse_snapshot
tz = os.environ.get("LOCAL_TZ", "America/Denver")
today = subprocess.run(["date", "+%Y-%m-%d"], env={**os.environ, "TZ": tz},
                       capture_output=True, text=True).stdout.strip()
rows = [json.loads(l) for l in Path("data/day-tracking.ndjson").read_text().splitlines() if l.strip()]
snap = pulse_snapshot(rows)
if not snap or snap["date"] != today:
    print("no-health-today"); sys.exit()
for lid, tier, _rank, label, disp, target, status in snap["levers"]:
    print(f"{status} | {label} | {disp} | {target} | {tier}")
print("VERDICT", snap["verdict"]["status"], snap["verdict"]["text"])
print("MOVE", snap["move"] or "")
PY
```

- If it prints `no-health-today`, say so in one line and skip the section. Do not fall back to an older night's sleep.
- Render a compact table `Lever | Last night | Target | ●`, sorted worst-first (🔴, then 🟡, then 🟢). A ⚪ lever has no data: show `—`.
- Then the verdict line, then **Today's one move** (the `MOVE` line) as one sentence, not a lecture.

**7-day trend.** After the one-move line:

```bash
python3 automations/scripts/trello_render.py --pulse-history 7
```

It prints a per-lever sparkline, a **days-on-target count** per lever (high is good: AGENTS.md § "Metrics point one direction"; never report these as miss-counts), and flags **chronic misses** (on target ≤3 of 7) with the fix. Surface **at most the top 2**, so a single bad night reads differently from a two-week slide. If there are none, say "pulse is holding" and move on. Don't reprint the sparkline block unless asked.

Keep the whole section tight: the table, the verdict, the one-move line, and at most two chronic-miss lines.

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
- If no focus set today, say "No daily focus set — tomorrow's 2+1 gets picked at the evening check-in (or on the web home page, if you run it). Run /pfc-pick-tasks if you want something to work on now."

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

### 9. Open the web UI (optional, last line)

If the optional web UI is installed ([`docs/install/web-ui.md`](../../../docs/install/web-ui.md)), open its home page behind the current window:

```bash
scripts/open-web-ui.sh --background
```

It opens `http://127.0.0.1:4323/` and prints one line saying so. It opens nothing, and says why, when this is not a Mac, when the web server is not answering, or when the summary was started from the web page's own chat; it always exits 0. Print its one line as the last line of the summary.

## Formatting Rules

- Use markdown headers (##) for each section
- Keep it scannable — no paragraphs, just structured data
- Use text-based progress bars where applicable: `[====------] 40%`
- No emojis except the pulse status circles (🟢/🟡/🔴/⚪), which AGENTS.md requires
- No questions or prompts — this is a read-only view
- Total output should fit on one screen (aim for ~40-60 lines)
