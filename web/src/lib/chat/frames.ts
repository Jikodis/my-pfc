/**
 * Server-sent events, read out of whatever the network handed over.
 *
 * A `fetch` reader gives back bytes, not messages: one read can carry three frames
 * and half of a fourth, and the half has to wait for the rest rather than be parsed
 * into a broken event. So this takes the whole unread buffer and gives back the
 * frames that are complete plus the tail that is not, and the caller keeps the tail
 * for the next read.
 *
 * It decides nothing about the chat. It splits text.
 */

export type Frame = {
  /** The `event:` name when the frame carried one, such as `run`. */
  event: string | null
  /** The `id:` field when the frame carried one: the event's place in the run's log. */
  id?: string
  /** Every `data:` line of the frame, joined with newlines, as the protocol says. */
  data: string
}

export type ParsedFrames = { frames: Frame[]; rest: string }

/** One `data: x`, `event: x`, or `id: x` line, with the single optional space after the colon removed. */
function value(line: string, at: number): string {
  const text = line.slice(at + 1)
  return text.startsWith(' ') ? text.slice(1) : text
}

function frame(block: string): Frame | null {
  let event: string | null = null
  let id: string | null = null
  const data: string[] = []
  for (const line of block.split('\n')) {
    // A line that opens with a colon is a comment. The keep-alive frame is one, and
    // it exists to hold the connection open, not to say anything.
    if (!line || line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    const text = colon === -1 ? '' : value(line, colon)
    if (field === 'data') data.push(text)
    else if (field === 'event') event = text
    else if (field === 'id') id = text
  }
  // A frame with no data says nothing a page can act on, so it is not one.
  if (!data.length) return null
  return id === null ? { event, data: data.join('\n') } : { event, id, data: data.join('\n') }
}

/**
 * The complete frames in `buffer`, and the part of it that is still unfinished.
 *
 * Carriage returns are folded first, so a stream written with `\r\n` reads the same
 * as one written with `\n`. A lone `\r` at the very end stays in the tail: it may be
 * the first half of a line ending whose `\n` is in the next read.
 */
export function parseFrames(buffer: string): ParsedFrames {
  const text = buffer.replace(/\r\n/g, '\n')
  const blocks = text.split('\n\n')
  const rest = blocks.pop() ?? ''
  const frames: Frame[] = []
  for (const block of blocks) {
    const one = frame(block)
    if (one) frames.push(one)
  }
  return { frames, rest }
}
