/**
 * Numbers with rules behind them come from the Python scripts, which already hold
 * the tested logic. This module runs a script and parses its JSON. Nothing here computes.
 */
import { execFileSync } from 'node:child_process'
import { join } from 'node:path'
import { REPO } from './repo'

/** Set PFC_PYTHON when the default python3 is not the interpreter that has the script dependencies. */
const PYTHON = process.env.PFC_PYTHON || 'python3'

export type Light = 'green' | 'yellow' | 'red'
export type HabitRow = {
  /** `title` is the short display name; `description` runs a paragraph and belongs in a tooltip. */
  id: string; cadence: 'daily' | 'monthly'; title: string; description: string; area: string | null
  frequency: number; started: string | null; completed: number; target: number; rate_pct: number; light: Light
  /** The streak the habit is on right now, counted in `run_unit`. Computed in web_data.py. */
  current_run: number
  run_unit: 'days' | 'months'
  /** The same run written out: `1 day`, `3 days`, `2 months`, or `none yet`. Print this. */
  run_label: string
  /** True when a script logs this habit, so nothing offers to log it by hand. */
  auto_derived: boolean
  /** True when today's latest log row for this habit says done. Computed in web_data.py. */
  logged_today: boolean
  /** The same for yesterday, and true for a habit that had not started by then, so nothing offers to log it. */
  logged_yesterday: boolean
}
/** The e-ink words trmnl_push.py writes. 'NO DATA' is what a lever with no reading gets. */
export type Mark = 'RED' | 'YELLOW' | 'GREEN' | 'NO DATA'

export type SlipItem = {
  item_type: 'project' | 'task'
  item_id: string
  signals: string[]
  detail: string
}

/** One habit's completion over the focus window, as focus_status.py reports it. */
export type FocusHabitRate = {
  habit_id: string
  completed: number
  target: number
  skipped: number
  rate: number
  cadence: 'daily' | 'monthly'
  light: Light
}
export type FocusStatus = {
  focus_id: string
  title: string
  tier: 'foundation' | 'pursuit' | 'consuming'
  code: string
  impact: 'high' | 'medium' | 'low'
  urgency: 'high' | 'medium' | 'low'
  parked: boolean
  /** 'parked' when the focus is parked, 'unknown' when it has no habit to read. */
  status: Light | 'parked' | 'unknown'
  primary: FocusHabitRate | null
  supporting: FocusHabitRate[]
  weeks_red: number
}

/** One task the home page offers, with the areas or values that make it worth doing. */
export type HomeTask = { id: string; title: string; why: string[] }
/** A set pick: a task plus whether the day's daily-focus record marks it done. */
export type HomePick = HomeTask & { done: boolean }
/** A habit as home_data.py lists it: every daily and monthly habit, with its log state. */
export type HomeHabit = Pick<HabitRow, 'id' | 'title' | 'description' | 'auto_derived' | 'cadence' | 'logged_today' | 'logged_yesterday'>
/** A focus row: focus_status.py's status plus the active projects that name its vision. */
export type HomeFocus = FocusStatus & { projects: { id: string; name: string }[] }
/** One life-wheel area or household room in its latest snapshot. */
export type LightRow = { key: string; label: string; light: Light; note: string | null }
/** The latest snapshot of the life wheel or the household; `stale` is Python's call. */
export type LightSnapshot = { date: string | null; stale: boolean; rows: LightRow[] }
/** `status` is the registry word (`config/project_schema.yaml`): `active`, `on-deck`, `parked`, `done`, `dropped`. */
export type HomeProject = {
  id: string; name: string; area: string | null; status: string; pct: number
  next_task: { id: string; title: string } | null
}
/** `critical_ids` and `bonus_id` are the record's ids as stored, for a write that keeps them. */
export type HomePicks = { critical: HomePick[]; bonus: HomePick | null; critical_ids: string[]; bonus_id: string | null }
export type Home = {
  date: string
  evening: boolean
  values: string[]
  questions: { n: number; text: string }[]
  /** One of the life questions, rotating daily. */
  question_of_day: { n: number; text: string } | null
  areas: LightSnapshot
  household: LightSnapshot
  visions: { id: string; title: string; area: string }[]
  vision_of_day: { id: string; title: string; value: string | null } | null
  /** Every focus, red first. */
  focus: HomeFocus[]
  /** The same focuses by tier, each with its `light` (or `unknown`, `parked`). */
  focuses: Record<'foundation' | 'pursuit' | 'consuming', (HomeFocus & { light: string })[]>
  /** All six pursuit slots are full and one has been red four weeks or more. */
  repick_nudge: boolean
  focus_of_day: { id: string; title: string; vision: string | null; value: string | null } | null
  projects: { active: HomeProject[]; other: HomeProject[] }
  habits: HomeHabit[]
  body: {
    sleep_hours: number | null; awake_minutes: number | null; broken_night: boolean
    /** The exercise habit (`EXERCISE_HABIT_ID` in `pfc_writes.py`): done today, and its label. */
    exercised: boolean; exercise_label: string
    /** Days it was done in the last `window` days, and its light against the habit's weekly pace. */
    exercised_days: number; exercise_light: Light; window: number
  }
  /** The pfc-pulse screen: last night's levers and tonight's one move. `mark` is the e-ink word. */
  pulse: {
    date: string
    /** `on` of `n`: nights on target over the last 30, null when the lever has no 30-day count. */
    levers: { label: string; value: string; target: string; tier: string; mark: Mark; on: number | null; n: number | null }[]
    verdict_mark: Mark; verdict: string; move: string
    /** Today's exercise habit, from `EXERCISE_HABIT_ID` in `pfc_writes.py`. */
    exercise_label: string; exercise_done: boolean; exercise_text: string
  } | null
  /** How the last 30 days turned out (rating, energy, mood, focus, picks done), red first. Sleep and exercise live in `body`/`pulse`. */
  trends: { name: string; light: Light; why: string }[]
  rate_target: { date: string; unrated: boolean }
  welcome_back: boolean
  /** Every active Front-of-Mind anchor. */
  anchors: { id: string; title: string }[]
  /** The next seven days from the calendar cache. `start` is an ISO time, or null for an all-day event. */
  week: { date: string; events: { start: string | null; title: string }[] }[]
  /** `date` is the deadline (ISO) on a deadline row, for the page to format; null otherwise. */
  needs_you: { kind: string; id: string; title: string; why: string; date: string | null }[]
  due_review: { id: string; label: string; skill: string | null } | null
  /** The day the picks step sets: tomorrow from about 6 PM, else today. */
  pick_date: string
  /** Today's picks, all day. */
  picks: HomePicks | null
  /** Tomorrow's picks, from about 6 PM only (null before then or when none are set). */
  tomorrow_picks: HomePicks | null
  /** Suggestions for `pick_date`, kept filled once today's picks are all done. */
  suggested: HomeTask[]
  /** Today has at least one critical pick and every one is done, so more work can be pulled in. */
  all_picks_done: boolean
  handoffs: HomeTask[]
  single_pick: boolean
  offer_open_day: boolean
  /** The tour's one look-at step, Python's pick, or null to drop the step. */
  tour_look: { kind: 'stale_areas' | 'red_focus' | 'stalled_project'; title: string; detail: string; date: string | null } | null
  /** Last finished run of the 5:00 AM sync, from the last DONE line of its log. `last_run` is local ISO time. */
  daily_sync: { last_run: string | null; ok: boolean | null; stale: boolean }
}

/** How long a script gets before it is killed. Overridable so a test can use a short one. */
const TIMEOUT_MS = 20_000

/**
 * The sentence a panel shows when a script does not deliver.
 *
 * A killed process leaves stderr as the empty string, so `??` never fell back and the
 * panel read `... failed:` with nothing after it. `||` falls back on an empty string
 * too, and a timeout says so in words, because that is the one failure whose cause is
 * not in the output.
 */
function failed(scriptRelPath: string, err: unknown, timeoutMs: number): Error {
  const detail = err as { stderr?: unknown; code?: string }
  const reason = detail.code === 'ETIMEDOUT'
    ? `timed out after ${timeoutMs / 1000} seconds`
    : String(detail.stderr || (err as Error).message).slice(0, 300)
  return new Error(`${scriptRelPath} failed: ${reason}`)
}

function run(scriptRelPath: string, args: string[], timeoutMs: number): string {
  return execFileSync(PYTHON, [join(REPO, scriptRelPath), ...args], {
    cwd: REPO, encoding: 'utf8', timeout: timeoutMs, stdio: ['ignore', 'pipe', 'pipe'],
  })
}

/** The parse sits inside the try, so a script that exits 0 with junk names itself too. */
export function runPythonJson<T>(scriptRelPath: string, args: string[] = [], timeoutMs = TIMEOUT_MS): T {
  try {
    return JSON.parse(run(scriptRelPath, args, timeoutMs)) as T
  } catch (err) {
    throw failed(scriptRelPath, err, timeoutMs)
  }
}

export const getSlipping = () => runPythonJson<SlipItem[]>('automations/scripts/revive_watchlist.py')
export const getHome = () => runPythonJson<Home>('automations/scripts/web_data.py', ['--home'])
