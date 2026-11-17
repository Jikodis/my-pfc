/**
 * POST /api/write/park-focus with `{ "id": "focus-YYYYMMDD-NNN", "parked": true | false }`.
 *
 * Parks or unparks the focus and commits, all inside
 * `automations/scripts/web_write.py`. The writer refuses a retired focus. The
 * checks in front of it are in `src/lib/chat/write-request.ts`.
 */
import type { APIRoute } from 'astro'
import { isFocusId } from '../../../lib/chat/ids'
import { handleWrite, own } from '../../../lib/chat/write-request'

export const prerender = false

export const POST: APIRoute = ({ request }) =>
  handleWrite(request, 'park-focus', (body) => {
    const id = own(body, 'id')
    const parked = own(body, 'parked')
    return isFocusId(id) && typeof parked === 'boolean' ? [id, parked ? 'on' : 'off'] : null
  })
