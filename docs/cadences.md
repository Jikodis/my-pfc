# System Cadences

How and when the productivity system is used. These cadences keep you grounded, focused, and moving forward.

## Daily

| Activity | When | What happens |
|---|---|---|
| Morning check-in | First thing | Run `/pfc-morning-checkin`: rate sleep/energy/focus, review email priorities, set daily focus (2 critical + 1 bonus) |
| Day tracking | End of day | Rate the day 1-5, log supplements/variables, note observations |
| Habit logging | Throughout day | Log daily habit completions as they happen |
| Insight capture | Throughout day | Capture observations / noticings via `/pfc-add-insight`. Lower bar than findings. |
| Revive watchlist | Surfaced in morning check-in Step 5b2 | `pfc-revive` lists slipped tasks/projects (velocity 🔴, 0 parts ≥14d, open task ≥30d, high-impact ≥7d, 2+1 carry ≥3d, no activity ≥10d). Optional inline walk. |

## Weekly

| Activity | When | What happens |
|---|---|---|
| Weekly check-in | End of week | Run `/pfc-weekly-checkin`: summarize tasks completed, habit rates, energy trends, project progress. Archive completed tasks. Ask: what went well, what didn't, what to adjust. |
| Stale task triage | During weekly check-in | Identify tasks that have been open for 2+ weeks. For each: eliminate it (was it ever important?), break it down smaller (overwhelm barrier?), or re-prioritize it. ADHD-aware — if a task keeps getting skipped, the problem is usually the task definition, not motivation. |
| Insights triage | During weekly check-in | Surface this week's active insights (`data/insights.ndjson`). For each: keep / archive / graduate to a task, project, or habit. |
| Findings Alignment Check | During weekly check-in | Cross-reference active findings (`data/findings.ndjson`) against values, projects, habits, and last week's day-tracking for conflicts. Consider superseding any finding that life has moved past. |
| Revive walk | During weekly check-in, after stale-task triage | Run `/pfc-revive` and walk the full watchlist one-by-one — multi-select diagnostic + tailored intervention for each slipped item. |

## Monthly

| Activity | When | What happens |
|---|---|---|
| Monthly check-in | First week of month | Run `/pfc-monthly-checkin`: orchestrates all monthly items below. |
| Life wheel check-in | → part of monthly check-in | Rate each life area red/yellow/green. For anything not green, identify what would move it up and create a habit, action, or project. |
| Household status check-in | → part of monthly check-in | Rate each house area red/yellow/green. Create tasks for anything that needs attention. |
| Project progress review | → part of monthly check-in | Review active projects: percentage complete, blockers, excitement level still accurate? Should a project be paused or swapped? |
| Monthly habit review | → part of monthly check-in | Check monthly habit completion rates vs. target frequency. Adjust habits if needed. |
| Monthly insights review | → part of monthly check-in | Review last 30 days of active insights via `/pfc-insights` (Monthly mode). Triage each: keep / archive / graduate. Look for patterns across captures. |
| Trend analysis | → part of monthly check-in | Analyze day tracking data for patterns. What correlates with 5-star days? What predicts 1-2 star days? Cross-reference with your wearable, habits, and check-in data. Also runs as part of the yearly check-in. |
| Revive outcome review | → part of monthly check-in | Run `/pfc-revive --review-outcomes` to update outcomes on revive rows ≥30 days old (revived / still stuck / exited). |

## Yearly

| Activity | When | What happens |
|---|---|---|
| Yearly check-in | Once a year | Run `/pfc-yearly-checkin`: orchestrates all yearly items below. |
| Values review | → part of yearly check-in | Re-read values list. Still accurate? Reorder if priorities have shifted. |
| Area statements review | → part of yearly check-in | Re-read each area statement. Revise any that no longer resonate. Update the year tag. |
| Questions review | → part of yearly check-in | Revisit the questions list. Remove answered ones, add new ones. |
| Passion brainstorm refresh | → part of yearly check-in | 5-minute brainstorm session. Add new items. Move accomplished items to Done. |
| Personality & psychology review | → part of yearly check-in | Re-read `0-me/personality.md` + `0-me/core-psychology.md`. Update anything that no longer reflects current self-understanding. |
| Trend analysis | → part of yearly check-in | Analyze day tracking data for patterns over the past year. Cross-reference with your wearable, habits, and check-in data. Also runs monthly as part of `/pfc-monthly-checkin`. |

## ADHD-Aware Design

- **Stale task triage prevents guilt spirals.** Tasks that sit too long become anxiety triggers. Better to eliminate or re-scope them.
- **Project breakdown reduces overwhelm.** When a project feels too big, break it into the smallest possible next actions.
- **Task breakdown on request.** Any time a task feels daunting, ask Claude to break it into 15-minute chunks.
- **Daily focus limits scope.** Only 3 tasks per day keeps the system from becoming a source of stress.
- **Flexible cadences.** These are guidelines, not obligations. Skipping a weekly check-in is fine — the system is here to help, not to judge.
