/**
 * POST /api/chat: one message, one process, one stream of events back.
 *
 * This is the endpoint that starts a program able to edit and commit in this repo,
 * so it refuses first and runs second. In order: JSON only, a body under the cap,
 * the request came from this app's own page, the conversation is one this server
 * started, no reply is already being written into it, and the server is not already
 * running as much as it will.
 *
 * The reply is server-sent events, written by `runStream` in `src/lib/chat/stream.ts`:
 * one `run` frame carrying the id the stop and attach endpoints take, then one
 * numbered frame per event from the start of the run, then the stream closes. The
 * page leaving closes the stream and not the run; `POST /api/chat/attach` picks it up.
 */
import type { APIRoute } from 'astro'
import { checkRequest } from '../../../lib/chat/guard'
import { isJsonRequest, plain, readJsonBody } from '../../../lib/chat/http'
import { serverPort } from '../../../lib/chat/port'
import { TooManyRuns, runningForSession, startRun, type Run } from '../../../lib/chat/runner'
import { ownsSession } from '../../../lib/chat/sessions'
import { runStream } from '../../../lib/chat/stream'

export const prerender = false

export const POST: APIRoute = async ({ request }) => {
  if (!isJsonRequest(request)) {
    return plain(415, 'Send this as JSON, with the header Content-Type: application/json.')
  }

  const body = await readJsonBody(request)
  if (!body.ok) return plain(body.status, body.reason)

  const asked = checkRequest(request.headers, body.value, serverPort())
  if (!asked.ok) return plain(asked.status, asked.reason)

  if (asked.sessionId) {
    // A well formed id is not enough: every Claude Code conversation on the machine
    // has one, and resuming somebody's unrelated work session inside this repo is
    // not what a page here may do.
    if (!ownsSession(asked.sessionId)) return plain(403, 'That conversation was not started here.')
    if (runningForSession(asked.sessionId)) {
      return plain(409, 'A reply is still in progress for this conversation.')
    }
  }

  // The setting wins over the request, so a machine can be pinned to one model.
  const model = process.env.PFC_CHAT_MODEL || asked.model

  let run: Run
  try {
    run = startRun({
      message: asked.message,
      ...(asked.sessionId ? { sessionId: asked.sessionId } : {}),
      ...(model ? { model } : {}),
      ...(asked.page ? { page: asked.page } : {}),
    })
  } catch (err) {
    if (err instanceof TooManyRuns) {
      return plain(429, 'Three replies are already being written. Wait for one to finish, or stop one.')
    }
    // Whatever else went wrong, its message is for the log: it can name a path or
    // something out of the environment.
    console.error(`[pfc-chat] could not start a run: ${(err as Error).message}`)
    return plain(500, 'The server could not start a run. The server log has the details.')
  }

  return runStream(run, 0)
}
