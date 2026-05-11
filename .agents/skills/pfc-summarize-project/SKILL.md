---
name: pfc-summarize-project
description: Summarize the current status of a project. Use when the user asks for a "project summary", "project status", or "what's happening with [project]".
---

# Summarize Project

When summarizing a project:

1. Identify the project from the user's input
2. Check the project registry:
   ```bash
   grep '"[project-name]"' 4-projects/_data/projects.ndjson
   ```
3. Read the project files in `4-projects/[project-name]/`:
   - `overview.md` for definition and scope
   - `notes.md` for running context
4. Find related tasks:
   ```bash
   grep '"project":"[project-name]"' 5-actions/_data/tasks.ndjson | grep '"status":"open"'
   grep '"project":"[project-name]"' 5-actions/_data/tasks.ndjson | grep '"status":"done"'
   ```
5. Present a concise summary:
   - Project purpose and which life area it relates to
   - Active status, excitement, impact, urgency
   - **Completion percentage** (completed_parts / total_parts)
   - **Velocity** (parts/week and estimated completion date based on observed pace; flag 🟢 / 🟡 / 🔴 vs deadline — see below)
   - Open tasks count
   - Completed tasks count
   - Recent activity
   - Any blockers or next steps

**Velocity calc:**
- `days_elapsed = today - started`
- `parts_per_day = completed_parts / max(1, days_elapsed)`; show as `parts/week = parts_per_day * 7`
- `est_completion = today + ceil((total_parts - completed_parts) / parts_per_day)` if `parts_per_day > 0`; else `est_completion = "—"` (no progress yet)
- Compare to project `deadline`: 🟢 on or before · 🟡 ≤7 days late · 🔴 >7 days late
- Use velocity to surface drift early. If 🔴, the user uses this to decide between resetting the deadline, reducing scope, or speeding up — do NOT pre-schedule extra calendar events to "catch up"; that's churn.
6. **If the project feels stalled or overwhelming, offer to break it down:**
   - Each part should be completable in 1–3 sessions
   - Create parts as tasks in `5-actions/_data/tasks.ndjson` linked via the `project` field
   - Completing tasks drives the completion percentage (completed_parts / total_parts)
   - ADHD context: overwhelm usually means the task definition is too big, not that motivation is lacking — break it down into 15-minute chunks
7. Ask if the user wants to update any project files or adjust the project metadata
