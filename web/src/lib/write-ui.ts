/**
 * What an edit button on a page sends, and what it says afterwards.
 *
 * Pure decisions only, so each wording can be tested without a browser:
 * `src/scripts/write-client.ts` does the clicking, the fetching, and the reloading.
 * The button always says what happened, in words, because a button that only
 * changes color leaves the person guessing whether the change was saved.
 */

export type ButtonAction =
  | 'complete-task' | 'drop-task' | 'log-habit' | 'park-focus' | 'skip-suggestion' | 'set-project' | 'retire-anchor'

/** The headers the chat drawer sends too; the write routes run the same guard. */
export const WRITE_HEADERS = { 'Content-Type': 'application/json', 'X-PFC-Chat': '1' } as const

export const PENDING = 'Saving...'
export const UNREACHABLE = 'Could not reach the local server.'
export const SERVER_FAILED = 'The change could not be saved. The server log has the details.'
export const NOT_PUSHED = 'Saved. Not pushed yet.'
export const EMAIL_NOTE = 'Its source email is still in the inbox; archive it in Gmail.'

/** How long a success stays on screen before the page reloads to show the new state. */
export const RELOAD_PUSHED_MS = 2_000
export const RELOAD_UNPUSHED_MS = 3_000

const ACTIONS: readonly ButtonAction[] = [
  'complete-task', 'drop-task', 'log-habit', 'park-focus', 'skip-suggestion', 'set-project', 'retire-anchor',
]

export const isButtonAction = (value: unknown): value is ButtonAction =>
  typeof value === 'string' && (ACTIONS as readonly string[]).includes(value)

/**
 * The route and JSON body for one click. Park takes `on` or `off` as its extra. A
 * habit log takes the day it is for, YYYY-MM-DD, and none means today. A skipped
 * suggestion takes the day it is skipped for. A project takes `active` or `parked`.
 */
export function requestFor(action: ButtonAction, id: string, extra?: string | null): { url: string; body: string } {
  const payload = action === 'park-focus' ? { id, parked: extra === 'on' }
    : action === 'log-habit' && extra ? { id, date: extra }
    : action === 'skip-suggestion' ? { date: extra, id }
    : action === 'set-project' ? { id, active: extra === 'active' }
    : { id }
  return { url: `/api/write/${action}`, body: JSON.stringify(payload) }
}

export type Tone = 'ok' | 'info' | 'error'

/** What the button area shows after a reply, and whether (and when) the page reloads. */
export type Outcome = { text: string; tone: Tone; reloadAfterMs: number | null }

const str = (value: unknown): string => (typeof value === 'string' ? value.trim() : '')

/**
 * The reply turned into words. `status` is null when the request never got an
 * answer (the server is down or the network failed).
 */
export function outcome(status: number | null, body: unknown, action?: ButtonAction): Outcome {
  if (status === null) return { text: UNREACHABLE, tone: 'error', reloadAfterMs: null }
  const b = typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : {}
  const message = str(b.message)

  if (status === 200 && b.ok === true) {
    if (b.changed !== true) return { text: message || 'Nothing to change.', tone: 'info', reloadAfterMs: null }
    const note = b.email_linked === true ? ` ${EMAIL_NOTE}` : ''
    if (b.pushed === true) {
      const commit = str(b.commit)
      const word = action === 'drop-task' ? 'Dropped.' : 'Done.'
      const text = commit ? `${word} Committed as ${commit}.` : word
      return { text: `${text}${note}`, tone: 'ok', reloadAfterMs: RELOAD_PUSHED_MS }
    }
    return { text: `${NOT_PUSHED}${note}`, tone: 'ok', reloadAfterMs: RELOAD_UNPUSHED_MS }
  }
  if (status >= 500) return { text: SERVER_FAILED, tone: 'error', reloadAfterMs: null }
  return { text: message || SERVER_FAILED, tone: 'error', reloadAfterMs: null }
}

/**
 * Save for one life-wheel area or household room: its light and its note. The note is
 * always sent, trimmed, so clearing the box clears the note.
 */
export function lightRequest(kind: 'area' | 'room', key: string, light: string, note: string): { url: string; body: string } {
  return { url: `/api/write/${kind === 'area' ? 'set-area' : 'set-room'}`, body: JSON.stringify({ key, light, note: note.trim() }) }
}

export const PICKS_FULL = 'Today already has two open picks. Finish one before pulling in another.'
export const ALREADY_PICKED = 'That task is already one of today\'s picks.'

/**
 * The set-picks body that pulls one task into today: today's critical picks as they
 * stand (done ones included, so they stay done), then this one, and the bonus kept.
 * Refused, with words, when two picks are still open or the task is already a pick;
 * the writer checks the same cap against the stored record. `today` is the stored
 * daily-focus record for today, or null when there is none.
 */
export function pullIntoToday(
  date: string, today: { critical: string[]; completed?: string[]; bonus?: string | null } | null, id: string,
): { ok: true; body: string } | { ok: false; message: string } {
  const critical = today?.critical ?? []
  const done = new Set(today?.completed ?? [])
  if (critical.includes(id)) return { ok: false, message: ALREADY_PICKED }
  if (critical.filter((t) => !done.has(t)).length >= 2) return { ok: false, message: PICKS_FULL }
  // Pulling today's bonus in makes it a critical pick, so it stops being the bonus.
  const bonus = today?.bonus && today.bonus !== id ? today.bonus : null
  const next = [...critical, id]
  return { ok: true, body: JSON.stringify(bonus ? { date, critical: next, bonus } : { date, critical: next }) }
}
