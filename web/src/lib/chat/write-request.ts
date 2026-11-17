/**
 * The checks every write route makes before it starts the writer, in order: JSON
 * only (415), a body under 4 KB (413), this app's own page (403, the chat's
 * `checkHeaders`), a body that is an object with a well formed id (400). Only then
 * is `runWrite` called. Each refusal is the same JSON shape a write answers with,
 * so the page reads one kind of reply.
 */
import { checkHeaders } from './guard'
import { isJsonRequest, json, readJsonBody } from './http'
import { serverPort } from './port'
import { failure, runWrite, type WriteAction, type WriteResult } from '../write'

/** Bytes. A write request carries an id and at most one flag. */
export const WRITE_BODY_LIMIT = 4 * 1024

/** Turns the parsed body into the writer's arguments, or null when it is not one this route takes. */
export type ArgsFrom = (body: Record<string, unknown>) => string[] | null

const reply = ({ status, body }: WriteResult): Response => json(body, status)

/** The body's own property, never an inherited one or a getter's surprise. */
export function own(body: Record<string, unknown>, key: string): unknown {
  try {
    return Object.prototype.hasOwnProperty.call(body, key) ? body[key] : undefined
  } catch {
    return undefined
  }
}

export async function handleWrite(request: Request, action: WriteAction, argsFrom: ArgsFrom): Promise<Response> {
  if (!isJsonRequest(request)) {
    return reply(failure(415, 'Send this as JSON, with the header Content-Type: application/json.'))
  }
  const read = await readJsonBody(request, WRITE_BODY_LIMIT)
  if (!read.ok) return reply(failure(read.status, read.reason))

  // Where it came from is settled before a field of the body is read.
  const wrongPlace = checkHeaders(request.headers, serverPort())
  if (wrongPlace) return reply(failure(403, wrongPlace))

  const body = read.value
  if (typeof body !== 'object' || body === null || Array.isArray(body)) {
    return reply(failure(400, 'The request body is not an object.'))
  }
  const args = argsFrom(body as Record<string, unknown>)
  if (!args) return reply(failure(400, 'That is not a valid request for this change.'))

  return reply(await runWrite(action, args))
}
