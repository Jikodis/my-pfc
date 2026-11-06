/**
 * POST /api/write/rate-day with
 * `{ "date": "YYYY-MM-DD", "energy": 1-5, "mood": 1-5, "focus": 1-5, "hyperfocused"?: boolean }`.
 *
 * Rates the day and commits, all inside `automations/scripts/web_write.py`, which
 * decides which days may be rated. The checks in front of it are in
 * `src/lib/chat/write-request.ts`; the shapes are checked here, so nothing but
 * integers 1 to 5 and a real date ever reaches the writer.
 */
import type { APIRoute } from 'astro'
import { handleWrite, own } from '../../../lib/chat/write-request'
import { isIsoDate } from '../../../lib/dates'

export const prerender = false

const isRating = (value: unknown): value is number => Number.isInteger(value) && (value as number) >= 1 && (value as number) <= 5

export const POST: APIRoute = ({ request }) =>
  handleWrite(request, 'rate-day', (body) => {
    const date = own(body, 'date')
    const [energy, mood, focus] = ['energy', 'mood', 'focus'].map((key) => own(body, key))
    const hyper = own(body, 'hyperfocused')
    if (!isIsoDate(date) || !isRating(energy) || !isRating(mood) || !isRating(focus)) return null
    if (hyper !== undefined && typeof hyper !== 'boolean') return null
    const args = [date, String(energy), String(mood), String(focus)]
    if (hyper !== undefined) args.push(hyper ? 'hyper:yes' : 'hyper:no')
    return args
  })
