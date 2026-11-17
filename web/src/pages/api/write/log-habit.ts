/**
 * POST /api/write/log-habit with `{ "id": "<habit id>" }`, or with `"date":
 * "YYYY-MM-DD"` beside the id to log a day other than today.
 *
 * Logs the habit done for that day (today, local date, when none is named) in the
 * daily or monthly log its schema entry names, and commits, all inside
 * `automations/scripts/web_write.py`. The writer refuses a habit a script logs
 * (`auto_derived`), a day that has not happened, and a day more than a week back.
 * The checks in front of it are in `src/lib/chat/write-request.ts`; a date that is
 * not a real calendar date is refused here and starts nothing.
 */
import type { APIRoute } from 'astro'
import { isHabitId } from '../../../lib/chat/ids'
import { handleWrite, own } from '../../../lib/chat/write-request'
import { isIsoDate } from '../../../lib/dates'

export const prerender = false

export const POST: APIRoute = ({ request }) =>
  handleWrite(request, 'log-habit', (body) => {
    const id = own(body, 'id')
    const date = own(body, 'date')
    if (!isHabitId(id)) return null
    if (date === undefined) return [id]
    return isIsoDate(date) ? [id, date] : null
  })
