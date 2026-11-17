/**
 * POST /api/write/skip-suggestion with `{ "date": "YYYY-MM-DD", "id": "task-YYYYMMDD-NNN" }`.
 *
 * Skips the suggested task for that day (the writer takes today or tomorrow and an open task) and commits, all inside
 * `automations/scripts/web_write.py`. The checks in front of it are in
 * `src/lib/chat/write-request.ts`.
 */
import type { APIRoute } from 'astro'
import { isTaskId } from '../../../lib/chat/ids'
import { handleWrite, own } from '../../../lib/chat/write-request'
import { isIsoDate } from '../../../lib/dates'

export const prerender = false

export const POST: APIRoute = ({ request }) =>
  handleWrite(request, 'skip-suggestion', (body) => {
    const date = own(body, 'date')
    const id = own(body, 'id')
    return isIsoDate(date) && isTaskId(id) ? [date, id] : null
  })
