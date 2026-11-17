/**
 * Shapes of the repo's own records, as the NDJSON files actually hold them.
 *
 * The fields a page reads, as `docs/data-model.md` and the schemas in `config/`
 * describe them. A field is required only when every record carries it. Add a field
 * here when a page needs one the data model documents.
 */

export type Level = 'high' | 'medium' | 'low'

export type Task = {
  id: string; status: string; description: string; notes?: string | null; size?: string; location?: string
  impact: Level; urgency: Level; agent_doable?: 'yes' | 'partly' | 'no'; area?: string; project?: string
  depends_on?: string[] | null; deadline?: string | null; created: string; completed?: string | null; dropped?: string | null
  /** The impact x urgency code shown in list titles: AA down to CC. */
  priority?: string | null
  values?: string[] | null
  /** Order within a project's backlog. */
  sequence?: number | null
  /** Where the task came from: chat, email-triage, trello-inbox, and so on. */
  source?: string
  deferred?: boolean
  deferred_reason?: string | null
  source_email_subject?: string | null
  source_email_thread_id?: string | null
}

export type Project = {
  id: string; name: string; active: boolean; excitement?: Level; impact?: Level; urgency?: Level; area: string
  values: string[]; total_parts: number; completed_parts: number; estimated_months?: number | null; vision?: string | null
  created: string; deadline?: string | null
  status?: 'active' | 'on-deck' | 'parked' | 'done' | 'dropped'
  description?: string
  goal?: string
  notes?: string
  /** What has to finish before this project may start. */
  gate?: string
  priority?: string
  priority_order?: string[]
  started?: string
  completed?: string | null
  /** The date the project was paused, not a flag. */
  paused?: string
}

export type FocusItem = {
  id: string; tier: 'foundation' | 'pursuit' | 'consuming'; area: string; title: string; status: 'green' | 'yellow' | 'red'
  quarter: string; landing?: string | null; habits?: string[]; impact: Level; urgency: Level; parked?: boolean; retired_date?: string | null
  created?: string
  /** The one parent this focus links to, one hop up: a vision or a habit. */
  link?: { type: string; ref: string } | null
  /** Set on a 'consuming' focus: the book, course, or podcast being worked through. */
  medium?: string | null
  notes?: string | null
}

export type DailyFocus = {
  date: string; critical: string[]; bonus?: string | null; completed: string[]; bonus_completed?: boolean
  project?: string
  project_completed?: boolean
  /** Calendar slots that an older per-task scheduling run wrote, keyed by task id. */
  calendar_events?: Record<string, { event_id: string; start: string; end: string }>
}

export type HabitLog = {
  habit_id: string; date: string; completed: boolean; skipped?: boolean | null; source?: string
  skip_reason?: string | null
  note?: string
  notes?: string
  /** A measured habit's reading: a count, or a duration written as HH:MM. */
  value?: number | string
  logged_at?: string
  /** Monthly logs only. */
  month?: string
}

/**
 * One session the watch recorded, as the Python health fetch writes it. `type` is the only
 * key present on every one of them (`ROWING_MACHINE`, `RUNNING`, and so on).
 */
export type Workout = {
  type: string
  name?: string
  start?: string
  minutes?: number
  real_minutes?: number
  hard_minutes?: number
  vigorous_minutes?: number
  azm?: number
  calories?: number
  avg_hr_bpm?: number
}

export type DayRecord = {
  date: string; sick?: boolean | null; rating?: number | null; energy?: number | null; focus?: number | null; mood?: number | null
  /** Whether the anchor exercise habit happened that day, mirrored from its habit log. */
  exercised?: boolean | null
  evening_notes?: string | null
  notes?: string | null
  hyperfocused?: boolean | null
  logged_at?: string
  health?: {
    sleep_hours?: number | null; awake_minutes?: number | null; sleep_bedtime?: string | null; workout_vigorous_minutes?: number | null
    sleep_wake_time?: string | null; sleep_continuity?: string | null; sleep_minutes?: number | null
    resting_hr_bpm?: number | null; active_zone_minutes?: number | null
    /** Present on every health record in the file, empty on a day with no session. */
    workouts?: Workout[]
    [k: string]: unknown
  }
  qqrt?: {
    score?: number | null
    quantity?: boolean; quality?: boolean; regularity?: boolean; timing?: boolean
    sleep_debt?: { need_hours?: number; nights?: number; avg_shortfall_min?: number; cumulative_hours?: number }
    [k: string]: unknown
  }
}

export type ReviewItem = {
  id: string; label: string; tier: string; cadence_days: number; last_done: string | null
  /** The weekday this review prefers, when it has one. */
  weekday_hint?: string | null
}

export type Grounding = {
  id: string; title: string; body: string; area?: string; status: string
  created?: string
  notes?: string | null
  retired_date?: string | null
}

export type LifeWheel = {
  date: string; ratings: Record<string, 'green' | 'yellow' | 'red'>; notes?: Record<string, string>
  logged_at?: string
}

export type Area = { slug: string; statement: string }

export type Vision = { slug: string; area: string; status: string; title: string; statement: string }
