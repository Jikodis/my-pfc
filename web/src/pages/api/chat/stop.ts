/**
 * POST /api/chat/stop: end a run the person started.
 *
 * The same check on where the request came from as the endpoint that starts one,
 * because stopping somebody else's run mid-edit is its own kind of damage.
 *
 * This route does not check the content type of its own. That is not a way in:
 * Astro refuses a cross-site POST carrying a form's content type, or none at all,
 * before this route runs, and the drawer sends `application/json` like every other
 * request it makes. The body is read as JSON whatever the header says.
 */
import type { APIRoute } from 'astro'
import { checkHeaders } from '../../../lib/chat/guard'
import { json, plain, readJsonBody } from '../../../lib/chat/http'
import { serverPort } from '../../../lib/chat/port'
import { stopRun } from '../../../lib/chat/runner'

export const prerender = false

export const POST: APIRoute = async ({ request }) => {
  const wrongPlace = checkHeaders(request.headers, serverPort())
  if (wrongPlace) return plain(403, wrongPlace)

  const body = await readJsonBody(request)
  if (!body.ok) return plain(body.status, body.reason)

  const value = body.value
  const id = typeof value === 'object' && value !== null && !Array.isArray(value)
    && Object.prototype.hasOwnProperty.call(value, 'id')
    ? (value as Record<string, unknown>).id
    : undefined
  if (typeof id !== 'string' || !id) return plain(400, 'Name the run to stop.')

  // False means there was nothing to stop, which is what a second press says.
  return json({ stopped: stopRun(id) })
}
