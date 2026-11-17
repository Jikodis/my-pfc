/**
 * Messages waiting for the reply in progress to finish, the way Claude Code queues
 * what is typed while it works.
 *
 * Pressing Send while a reply is being written puts the message here instead of
 * refusing it. When the reply ends on its own the drawer sends the first one into
 * the same conversation, and the rest wait their turn. The server knows nothing of
 * this: it still refuses a second live run in one conversation with 409.
 *
 * Nothing here touches the page. Each function takes the queue as it stands and
 * gives back a new one, and the drawer keeps it in sessionStorage so moving between
 * pages keeps it too.
 */
import { MESSAGE_LIMIT } from './guard'

/** `id` names the row, so its Remove button removes that one and not its twin. */
export type Queued = { id: string; text: string }
export type Queue = Queued[]

/** Past this a message stays in the box. Twenty waiting messages is already a plan, not a queue. */
export const QUEUE_CAP = 20

/** Long enough for any id the drawer makes, short enough that storage cannot bloat it. */
const ID_LIMIT = 64

/** A message the server would refuse for its length is not worth holding for later. */
const fits = (text: string): boolean => text !== '' && [...text].length <= MESSAGE_LIMIT

export function enqueue(queue: Queue, text: string, id: string): Queue {
  const message = text.trim()
  if (!fits(message) || queue.length >= QUEUE_CAP) return queue
  return [...queue, { id, text: message }]
}

export function removeQueued(queue: Queue, id: string): Queue {
  return queue.filter((item) => item.id !== id)
}

export function takeNext(queue: Queue): { next: Queued | null; rest: Queue } {
  const [next, ...rest] = queue
  return { next: next ?? null, rest }
}

/**
 * A message that was taken to be sent and could not be, back at the front.
 *
 * Over the cap if it has to be: the person already sent it once, and losing it to a
 * limit on what may wait is the one outcome a queue exists to prevent.
 */
export function putBack(queue: Queue, item: Queued): Queue {
  return [item, ...queue.filter((q) => q.id !== item.id)]
}

export function saveQueue(queue: Queue): string {
  return JSON.stringify(queue.map(({ id, text }) => ({ id, text })))
}

/**
 * A stored queue read back, dropping any row that is not one.
 *
 * Only an id and the text are kept, and the text is only ever written into the page
 * as text. A repeated id is dropped, because two rows answering to one Remove button
 * would remove both.
 */
export function restoreQueue(raw: string | null): Queue {
  if (!raw) return []
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    return []
  }
  if (!Array.isArray(value)) return []
  const kept: Queue = []
  const seen = new Set<string>()
  for (const row of value) {
    if (kept.length >= QUEUE_CAP) break
    if (typeof row !== 'object' || row === null || Array.isArray(row)) continue
    const { id, text } = row as { id?: unknown; text?: unknown }
    if (typeof id !== 'string' || !id || id.length > ID_LIMIT || seen.has(id)) continue
    if (typeof text !== 'string' || !fits(text.trim())) continue
    seen.add(id)
    kept.push({ id, text: text.trim() })
  }
  return kept
}
