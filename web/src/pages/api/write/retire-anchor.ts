/**
 * POST /api/write/retire-anchor with `{ "id": "ground-YYYYMMDD-NNN" }`.
 *
 * Retires the Front-of-Mind anchor and commits, all inside
 * `automations/scripts/web_write.py`. The checks in front of it are in
 * `src/lib/chat/write-request.ts`.
 */
import type { APIRoute } from 'astro'
import { isGroundId } from '../../../lib/chat/ids'
import { handleWrite, own } from '../../../lib/chat/write-request'

export const prerender = false

export const POST: APIRoute = ({ request }) =>
  handleWrite(request, 'retire-anchor', (body) => {
    const id = own(body, 'id')
    return isGroundId(id) ? [id] : null
  })
