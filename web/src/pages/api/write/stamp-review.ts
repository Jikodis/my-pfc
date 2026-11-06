/**
 * POST /api/write/stamp-review with `{ "id": "<review id>" }`.
 *
 * Stamps the review as done today and commits, all inside
 * `automations/scripts/web_write.py`. The checks in front of it are in
 * `src/lib/chat/write-request.ts`.
 */
import type { APIRoute } from 'astro'
import { isReviewId } from '../../../lib/chat/ids'
import { handleWrite, own } from '../../../lib/chat/write-request'

export const prerender = false

export const POST: APIRoute = ({ request }) =>
  handleWrite(request, 'stamp-review', (body) => {
    const id = own(body, 'id')
    return isReviewId(id) ? [id] : null
  })
