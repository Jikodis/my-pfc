/**
 * The event stream turned into the lines a person reads.
 *
 * Nothing here touches the page. It takes the transcript as it stands and one
 * event, and gives back the transcript as it now stands, so the hard parts (a
 * delta that arrives before the session line, two tools in flight, a refusal that
 * has to be joined to the tool line it belongs to) are testable without a browser.
 *
 * Every function returns a new object. The drawer keeps one of these, hands it to
 * the renderer, and writes it to sessionStorage so moving between pages keeps it.
 */
import type { ChatEvent } from './events'

/**
 * `refused` is not a kind of failure. The run asked for something the settings do
 * not allow, the answer was no, and nothing ran, which is a different thing to
 * report than a command that ran and returned an error.
 */
export type ToolStatus = 'running' | 'ok' | 'failed' | 'refused'

export type Denial = { id: string; tool: string; summary: string }

export type Item =
  | { kind: 'user'; text: string }
  /** `text` is markdown, kept as it arrived. The renderer is the one that turns it into HTML. */
  | { kind: 'assistant'; text: string }
  /** `writes` is the tool event's own flag, kept so the end of the turn can read it. */
  | { kind: 'tool'; id: string; name: string; summary: string; status: ToolStatus; result: string; writes: boolean }
  | { kind: 'refusals'; denied: Denial[] }
  | { kind: 'error'; text: string }
  /** `changed` says the turn ran a tool that can write, so the page may be out of date. */
  | { kind: 'done'; ok: boolean; turns: number; ms: number; changed: boolean }
  /** A line about the conversation rather than in it, such as a stop or a reply that ended while you were away. */
  | { kind: 'note'; text: string; stopped: boolean }

export type Transcript = {
  items: Item[]
  sessionId: string | null
  model: string | null
  /**
   * Results whose tool line has not arrived yet, kept by id. The order of the two
   * is the model's to decide, and a result shown with no line above it says nothing
   * until the turn ends, at which point one is better than losing it.
   */
  waiting: Record<string, { ok: boolean; text: string }>
  /**
   * How many items the cap has dropped from the front. An item's key is `base` plus
   * its index (`keyOf`), and it keeps that key while older items go, so the drawer can
   * hold on to the node it drew for it instead of shifting every node down one.
   */
  base: number
}

/** Why a turn ended, which is the difference between a fault and a choice. */
export type TurnEnd = 'ended' | 'stopped'

/**
 * Lines kept. Past this the oldest go, in the transcript itself and not only in
 * storage, so a reload shows what the page showed.
 */
export const ITEM_CAP = 200

/**
 * Whether one finished tool call can have changed a file. The flag was set in
 * `events.ts` from the call's whole input (`writesFiles`); the summary on the line
 * is cut short and is never read for this.
 */
const wrote = (item: Extract<Item, { kind: 'tool' }>): boolean => item.status === 'ok' && item.writes

const cap = (items: Item[]): Item[] => (items.length > ITEM_CAP ? items.slice(items.length - ITEM_CAP) : items)

/** How many items `cap` drops from the front of this list. */
const over = (items: Item[]): number => Math.max(0, items.length - ITEM_CAP)

export function newTranscript(items: Item[] = [], sessionId: string | null = null): Transcript {
  return { items: cap(items), sessionId, model: null, waiting: {}, base: 0 }
}

const next = (state: Transcript, items: Item[], waiting = state.waiting): Transcript =>
  ({ items: cap(items), sessionId: state.sessionId, model: state.model, waiting, base: state.base + over(items) })

/** The stable key of the item at `index`: it does not change when the cap drops older items. */
export const keyOf = (state: Transcript, index: number): number => state.base + index

/** One line added at the end, under the same cap as every other change. */
export function addItem(state: Transcript, item: Item): Transcript {
  return next(state, [...state.items, item])
}

export function addUser(state: Transcript, text: string): Transcript {
  return next(state, [...state.items, { kind: 'user', text }])
}

/**
 * Take back the person's message when the server never accepted it.
 *
 * The drawer shows a message as soon as it is sent, so leaving the page before the
 * run answers still has a message to offer again. A refusal means it never became a
 * turn, so it leaves the transcript and stays in the box. Only the last line, and
 * only when it is that same message: anything after it means the turn did start.
 */
export function dropUser(state: Transcript, text: string): Transcript {
  const last = state.items[state.items.length - 1]
  if (!last || last.kind !== 'user' || last.text !== text) return state
  return next(state, state.items.slice(0, -1))
}

/**
 * The tool line a result or a refusal belongs to, or nothing when it has none.
 *
 * Searched from the end. An id is meant to be unique, but a transcript holds several
 * turns and the same id turning up twice must land on the call that is running now,
 * not on one that finished three questions ago.
 */
function withTool(items: Item[], id: string, change: (item: Extract<Item, { kind: 'tool' }>) => Item): Item[] | null {
  let at = -1
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i]
    if (item && item.kind === 'tool' && item.id === id) {
      at = i
      break
    }
  }
  if (at === -1) return null
  const copy = [...items]
  copy[at] = change(items[at] as Extract<Item, { kind: 'tool' }>)
  return copy
}

/**
 * Each refused call marked on the tool line it belongs to.
 *
 * The join is by id, and an id that matches nothing is normal: a refusal can arrive
 * with no tool line of its own. Those still reach the person, once, in the box the
 * caller adds beside this.
 */
export function joinDenials(items: Item[], denied: Denial[]): Item[] {
  let out = items
  for (const one of denied) {
    if (!one.id) continue
    const marked = withTool(out, one.id, (tool) => ({ ...tool, status: 'refused' }))
    if (marked) out = marked
  }
  return out
}

/**
 * Results that never found their call, written out as lines of their own.
 *
 * A result held forever is a result nobody sees, and one of them in the captured
 * stream is a failure. So when a turn ends, whatever is still parked is shown,
 * saying plainly that the call it belongs to never arrived.
 */
function flushWaiting(state: Transcript, items: Item[]): { items: Item[]; waiting: Record<string, never> } {
  const ids = Object.keys(state.waiting)
  if (!ids.length) return { items, waiting: {} }
  const flushed: Item[] = ids.map((id) => {
    const held = state.waiting[id] as { ok: boolean; text: string }
    return {
      kind: 'tool',
      id,
      name: '',
      summary: 'Result with no matching call',
      status: held.ok ? 'ok' : 'failed',
      result: held.text,
      writes: false,
    }
  })
  return { items: [...items, ...flushed], waiting: {} }
}

/** A line written for a result that arrived with no call, found by id from the end. */
function withOrphan(items: Item[], id: string, change: (item: Extract<Item, { kind: 'tool' }>) => Item): Item[] | null {
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i]
    if (item && item.kind === 'tool' && item.id === id) {
      if (item.name !== '') return null
      const copy = [...items]
      copy[i] = change(item)
      return copy
    }
  }
  return null
}

/** Where the server writes what it did not put in a reply. */
export const SERVER_LOG = '/tmp/pfc-web.log'

const POINTS_AT_LOG = 'The server log has the details.'

/**
 * An error as the person reads it.
 *
 * The server keeps paths and environment values out of what it sends, and says the
 * details are in its log instead. A pointer to a log with no name is a dead end, so
 * the name is added here, on the side that knows where the launch agent writes it.
 */
export function errorText(text: string): string {
  if (!text.endsWith(POINTS_AT_LOG)) return text
  return `${text.slice(0, -1)}: ${SERVER_LOG}`
}

/**
 * Whether the turn that just ended ran a tool that can write.
 *
 * Read back only as far as the person's own last message, because the offer to
 * reload is about what this reply did, not about the conversation.
 */
function turnChangedAnything(items: Item[]): boolean {
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i]
    if (!item || item.kind === 'user') break
    if (item.kind === 'tool' && wrote(item)) return true
  }
  return false
}

export function applyEvent(state: Transcript, event: ChatEvent): Transcript {
  switch (event.kind) {
    case 'session':
      return { ...state, sessionId: event.id, model: event.model }

    case 'text': {
      const last = state.items[state.items.length - 1]
      if (last && last.kind === 'assistant') {
        const items = [...state.items]
        items[items.length - 1] = { kind: 'assistant', text: last.text + event.delta }
        return next(state, items)
      }
      return next(state, [...state.items, { kind: 'assistant', text: event.delta }])
    }

    case 'tool': {
      const held = state.waiting[event.id]
      if (!held) {
        // Its result may already be on screen as a line of its own, flushed by an
        // error the rest of the run followed. That line gets its name, rather than a
        // second line appearing that waits for a result which has already come.
        const named = withOrphan(state.items, event.id, (line) => ({ ...line, name: event.name, summary: event.summary, writes: event.writes }))
        if (named) return next(state, named)
      }
      const item: Item = {
        kind: 'tool',
        id: event.id,
        name: event.name,
        summary: event.summary,
        status: held ? (held.ok ? 'ok' : 'failed') : 'running',
        result: held ? held.text : '',
        writes: event.writes,
      }
      const waiting = { ...state.waiting }
      delete waiting[event.id]
      return next(state, [...state.items, item], waiting)
    }

    case 'tool_result': {
      const items = withTool(state.items, event.id, (tool) => ({
        ...tool,
        status: event.ok ? 'ok' : 'failed',
        result: event.text,
      }))
      if (items) return next(state, items)
      return next(state, state.items, { ...state.waiting, [event.id]: { ok: event.ok, text: event.text } })
    }

    case 'done': {
      // Flushed before the join, so a parked result that was a refusal reads as
      // refused like every other refused call, not as a failure.
      const flushed = flushWaiting(state, state.items)
      let items = joinDenials(flushed.items, event.denied)
      if (event.denied.length) items = [...items, { kind: 'refusals', denied: event.denied }]
      const done: Item = {
        kind: 'done',
        ok: event.ok,
        turns: event.turns,
        ms: event.ms,
        changed: turnChangedAnything(items),
      }
      return next(state, [...items, done], flushed.waiting)
    }

    case 'error': {
      const flushed = flushWaiting(state, state.items)
      return next(state, [...flushed.items, { kind: 'error', text: errorText(event.message) }], flushed.waiting)
    }
  }
}

/**
 * The line that closes a turn, when the stream stopped for a reason of its own.
 *
 * A stream that simply ran out says so: the alternative is a reply that looks
 * finished and is not, which is the one thing a transcript must never do. A turn
 * that already ended in a done or an error keeps that ending.
 */
export function finishTurn(state: Transcript, reason: TurnEnd): Transcript {
  // How the turn ended is read before anything parked is added below it.
  const last = state.items[state.items.length - 1]
  const flushed = flushWaiting(state, state.items)
  const items = flushed.items
  if (reason === 'ended') {
    if (last && (last.kind === 'done' || last.kind === 'error')) return next(state, items, flushed.waiting)
    return next(state, [...items, { kind: 'error', text: 'The reply ended unexpectedly.' }], flushed.waiting)
  }
  return next(state, [...items, { kind: 'note', text: 'You stopped this reply.', stopped: true }], flushed.waiting)
}

/** How the status line reads, so the color and the words are decided in one place. */
export type Tone = 'ready' | 'thinking' | 'running' | 'refused' | 'error' | 'stopped' | 'not-sent'
export type Status = { text: string; tone: Tone }

/**
 * One line saying where the conversation stands, shown at all times.
 *
 * It is read off the transcript rather than remembered, so it cannot drift from what
 * is on screen. When nothing is running it describes the turn that just ended, back
 * as far as the person's own last message and no further. `notSent` is the one thing
 * it cannot read there: a message the server refused never became a turn at all.
 */
export function statusOf(state: Transcript, opts: { live: boolean; notSent?: boolean }): Status {
  const items = state.items
  if (opts.live) {
    for (let i = items.length - 1; i >= 0; i -= 1) {
      const item = items[i]
      if (item && item.kind === 'tool' && item.status === 'running') {
        return { text: `Running: ${item.name}`, tone: 'running' }
      }
    }
    return { text: 'Thinking...', tone: 'thinking' }
  }
  if (opts.notSent) return { text: 'Not sent', tone: 'not-sent' }

  let refused = 0
  let stopped = false
  let failed = false
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i]
    if (!item || item.kind === 'user') break
    // An error after the end of a turn is a message the server refused, which never
    // became a turn of its own. Read this way it survives a reload, where `notSent`
    // does not, and the last turn's refusals no longer speak for it.
    const ended = item.kind === 'done' || (item.kind === 'note' && item.stopped)
    if (ended && failed) return { text: 'Not sent', tone: 'not-sent' }
    if (item.kind === 'refusals') refused += item.denied.length
    if (item.kind === 'note' && item.stopped) stopped = true
    if (item.kind === 'error') failed = true
  }
  if (refused) return { text: `Refused ${refused} action${refused === 1 ? '' : 's'}`, tone: 'refused' }
  if (stopped) return { text: 'Stopped', tone: 'stopped' }
  if (failed) return { text: 'Something went wrong', tone: 'error' }
  return { text: 'Ready', tone: 'ready' }
}

/**
 * The message to offer sending again, or nothing.
 *
 * Offered only for a turn that never finished, and only when the stored message is
 * that turn's own message. Without both tests a message from an hour ago is offered
 * on every page load for the rest of the day, which is how a real prompt becomes
 * something to click past.
 */
export function resendOffer(state: Transcript, stored: string | null): string | null {
  if (!stored) return null
  const items = state.items
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i]
    if (!item) continue
    if (item.kind === 'done') return null
    if (item.kind === 'user') return item.text === stored ? stored : null
  }
  return null
}

type Obj = Record<string, unknown>
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v)
const isStr = (v: unknown): v is string => typeof v === 'string'
const isBool = (v: unknown): v is boolean => typeof v === 'boolean'
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)

const STATUSES = new Set<string>(['running', 'ok', 'failed', 'refused'])

const isDenial = (v: unknown): boolean => isObj(v) && isStr(v.id) && isStr(v.tool) && isStr(v.summary)

/**
 * A stored transcript read back as items, dropping anything that is not one.
 *
 * What comes out of sessionStorage was written by this app, but it is text a person
 * or another page can edit, and the renderer reads these fields straight into the
 * document. A line that is not of a known shape is dropped without a word: there is
 * nothing a person could do about it and the rest of the conversation still reads.
 */
export function validItems(value: unknown): Item[] {
  if (!Array.isArray(value)) return []
  const kept: Item[] = []
  for (const row of value) {
    if (!isObj(row)) continue
    switch (row.kind) {
      case 'user':
      case 'assistant':
      case 'error':
        if (isStr(row.text)) kept.push({ kind: row.kind, text: row.text })
        break
      case 'note':
        if (isStr(row.text) && isBool(row.stopped)) kept.push({ kind: 'note', text: row.text, stopped: row.stopped })
        break
      case 'tool':
        if (isStr(row.id) && isStr(row.name) && isStr(row.summary) && isStr(row.result)
          && isStr(row.status) && STATUSES.has(row.status)) {
          kept.push({
            kind: 'tool',
            id: row.id,
            name: row.name,
            summary: row.summary,
            status: row.status as ToolStatus,
            result: row.result,
            // A line stored before the flag existed reads as one that did not write.
            writes: row.writes === true,
          })
        }
        break
      case 'refusals':
        if (Array.isArray(row.denied) && row.denied.every(isDenial)) {
          kept.push({ kind: 'refusals', denied: row.denied as Denial[] })
        }
        break
      case 'done':
        if (isBool(row.ok) && isNum(row.turns) && isNum(row.ms) && isBool(row.changed)) {
          kept.push({ kind: 'done', ok: row.ok, turns: row.turns, ms: row.ms, changed: row.changed })
        }
        break
      default:
        break
    }
  }
  return cap(kept)
}
