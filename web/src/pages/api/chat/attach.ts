/**
 * POST /api/chat/attach: read a run that is already going, from a given event on.
 *
 * Moving to another page closes the stream a run was being read through, and the
 * run carries on. The next page sends the run's id and the index of the first event
 * it does not have yet, and gets the same stream `POST /api/chat` sends: a `run`
 * frame, then each event from that index, then the end. A run that ended a little
 * while ago is still here, so a page that comes back late gets the tail and the
 * final event; one that ended longer ago than the grace period is gone, and that is
 * a 404.
 *
 * The same check on where the request came from as the stop route. Reading a run is
 * reading what the program printed about this repo, which is not another site's to read.
 * Like the stop route it does not check the content type itself: Astro refuses a
 * cross-site POST carrying a form's content type before this runs, and the custom
 * header the guard requires forces a preflight this server never approves.
 */
import type { APIRoute } from 'astro'
import { checkHeaders } from '../../../lib/chat/guard'
import { plain, readJsonBody } from '../../../lib/chat/http'
import { serverPort } from '../../../lib/chat/port'
import { RUN_ID } from '../../../lib/chat/resume'
import { getRun } from '../../../lib/chat/runner'
import { runStream } from '../../../lib/chat/stream'

export const prerender = false

export const POST: APIRoute = async ({ request }) => {
  const wrongPlace = checkHeaders(request.headers, serverPort())
  if (wrongPlace) return plain(403, wrongPlace)

  const body = await readJsonBody(request)
  if (!body.ok) return plain(body.status, body.reason)

  const value = body.value
  const own = (key: string): unknown =>
    typeof value === 'object' && value !== null && !Array.isArray(value) && Object.prototype.hasOwnProperty.call(value, key)
      ? (value as Record<string, unknown>)[key]
      : undefined
  const id = own('id')
  const from = own('from')
  if (typeof id !== 'string' || !RUN_ID.test(id)) return plain(400, 'Name the run to read.')
  if (typeof from !== 'number' || !Number.isSafeInteger(from) || from < 0) {
    return plain(400, 'Say which event to start from, as a whole number of zero or more.')
  }

  const run = getRun(id)
  if (!run) return plain(404, 'That reply is no longer available.')
  return runStream(run, from)
}
