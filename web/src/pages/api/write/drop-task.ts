/**
 * POST /api/write/drop-task with `{ "id": "task-YYYYMMDD-NNN" }`.
 *
 * Drops an open task you decided not to do: removes it from the task list, logs a
 * `deleted` event, and commits, all inside `automations/scripts/web_write.py`. The
 * writer refuses a task that is already done. The checks in front of it are in
 * `src/lib/chat/write-request.ts`.
 */
import type { APIRoute } from 'astro'
import { isTaskId } from '../../../lib/chat/ids'
import { handleWrite, own } from '../../../lib/chat/write-request'

export const prerender = false

export const POST: APIRoute = ({ request }) =>
  handleWrite(request, 'drop-task', (body) => {
    const id = own(body, 'id')
    return isTaskId(id) ? [id] : null
  })
