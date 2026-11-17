/**
 * POST /api/write/set-area with `{ "key": "<area key>", "light": "green" | "yellow" | "red", "note"?: "<one line, 300 characters at most>" }`.
 *
 * Sets the life-wheel area's light (an empty note clears the note, no note leaves it) and commits, all inside
 * `automations/scripts/web_write.py`. The checks in front of it are in
 * `src/lib/chat/write-request.ts`.
 */
import type { APIRoute } from 'astro'
import { isLight, isNote, isRatingKey } from '../../../lib/chat/ids'
import { handleWrite, own } from '../../../lib/chat/write-request'

export const prerender = false

/** The note travels as ONE argv entry, `note:` plus the text, and is never split. */
export const POST: APIRoute = ({ request }) =>
  handleWrite(request, 'set-area', (body) => {
    const key = own(body, 'key')
    const light = own(body, 'light')
    const note = own(body, 'note')
    if (!isRatingKey(key) || !isLight(light)) return null
    if (note === undefined) return [key, light]
    return isNote(note) ? [key, light, `note:${note}`] : null
  })
