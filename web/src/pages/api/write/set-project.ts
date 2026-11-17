/**
 * POST /api/write/set-project with `{ "id": "proj-YYYYMMDD-NNN", "active": true | false }`.
 *
 * Switches the project between active and parked (the writer refuses a done or dropped project) and commits, all inside
 * `automations/scripts/web_write.py`. The checks in front of it are in
 * `src/lib/chat/write-request.ts`.
 */
import type { APIRoute } from 'astro'
import { isProjectId } from '../../../lib/chat/ids'
import { handleWrite, own } from '../../../lib/chat/write-request'

export const prerender = false

export const POST: APIRoute = ({ request }) =>
  handleWrite(request, 'set-project', (body) => {
    const id = own(body, 'id')
    const active = own(body, 'active')
    return isProjectId(id) && typeof active === 'boolean' ? [id, active ? 'active' : 'parked'] : null
  })
