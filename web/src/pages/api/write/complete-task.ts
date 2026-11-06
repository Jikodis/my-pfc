/**
 * POST /api/write/complete-task with `{ "id": "task-YYYYMMDD-NNN" }`.
 *
 * Marks the task done, logs the event, ticks today's 2+1, and commits, all inside
 * `automations/scripts/web_write.py`. The checks in front of it are in
 * `src/lib/chat/write-request.ts`.
 */
import type { APIRoute } from 'astro'
import { isTaskId } from '../../../lib/chat/ids'
import { handleWrite, own } from '../../../lib/chat/write-request'

export const prerender = false

export const POST: APIRoute = ({ request }) =>
  handleWrite(request, 'complete-task', (body) => {
    const id = own(body, 'id')
    return isTaskId(id) ? [id] : null
  })
