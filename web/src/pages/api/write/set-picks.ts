/**
 * POST /api/write/set-picks with
 * `{ "date": "YYYY-MM-DD", "critical": ["task-YYYYMMDD-NNN", ...one to eight], "bonus"?: "task-YYYYMMDD-NNN" }`.
 * The critical list carries the day's picks already done as well as the open ones, so
 * eight bounds the argument list only; the writer refuses more than two open picks.
 *
 * Sets the day's picks and commits, all inside `automations/scripts/web_write.py`,
 * which decides which days may be set and refuses a task that is not open (or done
 * as one of that day's picks) or that an agent can finish. The checks in front of it are in
 * `src/lib/chat/write-request.ts`; each id travels as its own argv entry.
 */
import type { APIRoute } from 'astro'
import { isTaskId } from '../../../lib/chat/ids'
import { handleWrite, own } from '../../../lib/chat/write-request'
import { isIsoDate } from '../../../lib/dates'

export const prerender = false

/** Same bound as MAX_PICK_IDS in automations/scripts/web_write.py. */
const MAX_PICK_IDS = 8

export const POST: APIRoute = ({ request }) =>
  handleWrite(request, 'set-picks', (body) => {
    const date = own(body, 'date')
    const critical = own(body, 'critical')
    const bonus = own(body, 'bonus')
    if (!isIsoDate(date) || !Array.isArray(critical) || critical.length < 1 || critical.length > MAX_PICK_IDS) return null
    if (!critical.every(isTaskId)) return null
    if (bonus !== undefined && !isTaskId(bonus)) return null
    return [date, ...critical, ...(bonus === undefined ? [] : [`bonus:${bonus}`])]
  })
