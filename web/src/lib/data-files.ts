/**
 * Where every NDJSON data file shows up. A file is either read for the home page
 * (HOME_DATA) or kept for the agent alone (AGENT_ONLY_DATA): the agent raises one
 * in chat when it applies to what you are doing. `test/data-files.test.ts` fails
 * when a data file is in neither list, so a new file has to be placed on purpose.
 */

/** Read by `automations/scripts/home_data.py` (or the task and day readers in `repo.ts`) for `/`, `/tasks` or `/review`. */
export const HOME_DATA = [
  '2-areas/_data/household-status.ndjson',
  '2-areas/_data/life-wheel.ndjson',
  '4-focus/_data/focus.ndjson',
  '5-projects/_data/projects.ndjson',
  '6-tasks/_data/daily-focus.ndjson',
  '6-tasks/_data/task_events.ndjson',
  '6-tasks/_data/tasks-archive.ndjson',
  '6-tasks/_data/tasks.ndjson',
  '7-habits/_data/habits-daily.ndjson',
  '7-habits/_data/habits-monthly.ndjson',
  'data/day-tracking.ndjson',
  'data/grounding.ndjson',
  'data/review-ledger.ndjson',
]

/** Not on any page. Findings, hypotheses and insights are agent-only. */
export const AGENT_ONLY_DATA = [
  '3-visions/_data/vision-brainstorm.ndjson',
  'data/ai-news.ndjson',
  'data/findings.ndjson',
  'data/hypotheses.ndjson',
  'data/insights.ndjson',
  'data/revive-events.ndjson',
  'data/supplements.ndjson',
]
