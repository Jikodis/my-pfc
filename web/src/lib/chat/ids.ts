/**
 * The shapes a record id may take before it is handed to the writer.
 *
 * Anchored and whole-string, so nothing rides beside an id. `automations/scripts/
 * web_write.py` checks the same shapes again, and the id travels as one argv
 * element, never through a shell. A well formed id that names no record is the
 * writer's to refuse (404); a malformed one never reaches it (400).
 */
export const TASK_ID = /^task-\d{8}-\d{3}$/
export const HABIT_ID = /^[A-Za-z0-9][A-Za-z0-9-]{0,63}$/
export const FOCUS_ID = /^focus-\d{8}-\d{3}$/

const matches = (pattern: RegExp) => (value: unknown): value is string =>
  typeof value === 'string' && pattern.test(value)

export const isTaskId = matches(TASK_ID)
export const isHabitId = matches(HABIT_ID)
export const isFocusId = matches(FOCUS_ID)

/** A review ledger id: the same shape as a habit id, so it can never read as a flag. */
export const REVIEW_ID = /^[a-z0-9][a-z0-9-]{0,63}$/
export const isReviewId = matches(REVIEW_ID)

/** A Front-of-Mind anchor id. */
export const GROUND_ID = /^ground-\d{8}-\d{3}$/
export const isGroundId = matches(GROUND_ID)

/** A project id. */
export const PROJECT_ID = /^proj-\d{8}-\d{3}$/
export const isProjectId = matches(PROJECT_ID)

/** A life-wheel area key or a household room key. It starts with a letter, so it can never read as a flag. */
export const RATING_KEY = /^[a-z][a-z_]{0,31}$/
export const isRatingKey = matches(RATING_KEY)

export const LIGHTS = ['green', 'yellow', 'red'] as const
export const isLight = (value: unknown): value is (typeof LIGHTS)[number] =>
  typeof value === 'string' && (LIGHTS as readonly string[]).includes(value)

/** A rating note: one line of text, at most this many characters. Empty clears the note. */
export const NOTE_LIMIT = 300
export const isNote = (value: unknown): value is string =>
  typeof value === 'string' && [...value].length <= NOTE_LIMIT && !/[\u0000-\u001f\u007f-\u009f\u2028\u2029]/.test(value)
