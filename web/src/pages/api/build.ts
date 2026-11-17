/**
 * GET /api/build: `{ "build": "<id>", "busy": true|false }`.
 *
 * `build` is the id of the build this server runs (`src/lib/build.ts`); an open page
 * reloads when it changes. `busy` is true while a chat reply is running or a change is
 * being saved; `automations/scripts/run-web.sh` waits for false before it restarts the
 * server on a new build. It reads and starts nothing, so only the Host check applies.
 */
import type { APIRoute } from 'astro'
import { buildStatus } from '../../lib/build'
import { checkHost } from '../../lib/chat/guard'
import { json, plain } from '../../lib/chat/http'
import { serverPort } from '../../lib/chat/port'

export const prerender = false

export const GET: APIRoute = ({ request }) => {
  const wrongHost = checkHost(request.headers, serverPort())
  if (wrongHost) return plain(403, wrongHost)
  return json(buildStatus())
}
