/**
 * GET /api/chat/skills: the skill buttons the drawer shows.
 *
 * This one reads and starts nothing, so only the Host check applies: it keeps a
 * page on another name from reaching this server through the browser, and there is
 * nothing here worth a stricter gate.
 */
import type { APIRoute } from 'astro'
import { checkHost } from '../../../lib/chat/guard'
import { json, plain } from '../../../lib/chat/http'
import { serverPort } from '../../../lib/chat/port'
import { listSkills } from '../../../lib/chat/skills'

export const prerender = false

export const GET: APIRoute = ({ request }) => {
  const wrongHost = checkHost(request.headers, serverPort())
  if (wrongHost) return plain(403, wrongHost)
  return json(listSkills())
}
