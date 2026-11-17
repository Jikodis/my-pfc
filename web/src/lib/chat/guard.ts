/**
 * The one check standing in front of the chat endpoint.
 *
 * That endpoint starts a process that can edit and commit in this repo, so it
 * serves this app's own pages and nothing else. Three things must all hold, and a
 * failure starts nothing:
 *
 * 1. `Host` is this server, by either of its two names, on this port.
 * 2. `Origin`, when the browser sent one, is this server over plain http.
 * 3. `Sec-Fetch-Site`, when the browser sent one, says the request came from this
 *    same site. Browsers set it themselves and a page cannot, so it costs nothing
 *    and catches a request a browser already knows is foreign.
 * 4. `X-PFC-Chat: 1` is present. A custom header is not a simple request, so a page
 *    on another origin has to ask permission first, and this server never answers
 *    a preflight.
 *
 * The port is handed in rather than read here, because the server knows which port
 * it was started on and this module must not guess.
 */

/** The shape Claude Code writes a session id in. Anchored, so nothing rides beside one. */
export const SESSION_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

/** Characters per message. Long enough for a pasted note, short of a pasted file. */
export const MESSAGE_LIMIT = 20_000

/**
 * Characters that take up no room and show nothing: the three zero-width joiners
 * and splitters, and the byte order mark. A message made only of these looks empty
 * on screen and would otherwise start a run, so emptiness is judged without them.
 * They stay in the message that is sent.
 */
const INVISIBLE = /[​‌‍﻿]/g

/** The models a person may pick. Anything else is dropped and the run uses the default. */
export const MODELS = ['fable', 'opus', 'sonnet', 'haiku'] as const
export type Model = (typeof MODELS)[number]

export type GuardResult =
  | { ok: true; message: string; sessionId?: string; model?: Model; page?: string }
  | { ok: false; status: 400 | 403; reason: string }

const HOST_NAMES = ['127.0.0.1', 'localhost']

const refuse = (status: 400 | 403, reason: string): GuardResult => ({ ok: false, status, reason })

const isObj = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v)

const isModel = (v: unknown): v is Model => MODELS.includes(v as Model)

/**
 * Which server the request believes it reached.
 *
 * Whole-string comparison against the two names, never `startsWith`: a host of
 * `127.0.0.1.evil.example:4323` begins with the loopback address and is a name
 * somebody else controls. The value is lower cased first, because a host name is
 * not case sensitive and `LOCALHOST:4323` is this server. An origin is not lowered:
 * there the whole string, scheme included, is compared as the browser sent it.
 */
export function checkHost(headers: Headers, port: string): string | null {
  const host = (headers.get('host') ?? '').toLowerCase()
  return HOST_NAMES.some((name) => host === `${name}:${port}`)
    ? null
    : `Host ${host || '(missing)'} is not this server.`
}

/**
 * Where the request came from, for the endpoints that start or stop a process.
 *
 * Returns the reason it is not this app's own page, or null when it is.
 */
export function checkHeaders(headers: Headers, port: string): string | null {
  const wrongHost = checkHost(headers, port)
  if (wrongHost) return wrongHost

  // A same-origin fetch often sends no Origin at all, which is why a missing one
  // passes. The custom header below is what a cross-origin page cannot forge.
  const origin = headers.get('origin')
  if (origin !== null && !HOST_NAMES.some((name) => origin === `http://${name}:${port}`)) {
    return `Origin ${origin} is not this server.`
  }
  // The browser writes this one itself and a page cannot set it, so when it is here
  // it is worth reading. `none` is a request the person typed or bookmarked.
  const site = headers.get('sec-fetch-site')
  if (site !== null && site !== 'same-origin' && site !== 'none') {
    return `The browser says this request came from ${site}.`
  }
  if (headers.get('x-pfc-chat') !== '1') {
    return 'The request is missing the X-PFC-Chat header.'
  }
  return null
}

/**
 * The three fields, read as the body's own properties.
 *
 * `body.message` on an object somebody built rather than parsed can be inherited or
 * can be a getter that throws, and a throw here would reach the endpoint as a
 * server error instead of a refusal. Own properties only, and one try around all
 * three reads.
 */
function fields(body: Record<string, unknown>): { message: unknown; sessionId: unknown; model: unknown; page: unknown } | null {
  const own = (key: string) => (Object.prototype.hasOwnProperty.call(body, key) ? body[key] : undefined)
  try {
    return { message: own('message'), sessionId: own('sessionId'), model: own('model'), page: own('page') }
  } catch {
    return null
  }
}

export function checkRequest(headers: Headers, body: unknown, port: string): GuardResult {
  // Where it came from is settled before a single field of the body is read, so
  // nothing in it can reach a decision. The endpoint has already parsed the body by
  // now, under its own size cap, because a body has to be read before it can be
  // handed here at all.
  const wrongPlace = checkHeaders(headers, port)
  if (wrongPlace) return refuse(403, wrongPlace)

  if (!isObj(body)) return refuse(400, 'The request body is not an object.')

  const read = fields(body)
  if (!read) return refuse(400, 'The request body could not be read.')
  const { message, sessionId, model, page } = read
  if (typeof message !== 'string') return refuse(400, 'The message is missing, or is not text.')

  // A message made only of invisible characters is empty rather than a run nobody
  // asked for, so emptiness is judged without them. The message itself keeps them:
  // a joiner is part of an emoji such as a family, and taking it out splits that
  // emoji into four people.
  const trimmed = message.trim()
  if (!trimmed.replace(INVISIBLE, '').trim()) return refuse(400, 'The message is empty.')
  // Counted in characters a person would count: an emoji is one, not two, and the
  // count is of the message as it will be sent, after the spaces are trimmed.
  if ([...trimmed].length > MESSAGE_LIMIT) {
    return refuse(400, `The message is longer than ${MESSAGE_LIMIT.toLocaleString('en-US')} characters, counted after trimming spaces.`)
  }

  if (sessionId !== undefined && (typeof sessionId !== 'string' || !SESSION_ID.test(sessionId))) {
    return refuse(400, 'That is not a session id.')
  }

  return {
    ok: true,
    message: trimmed,
    ...(sessionId === undefined ? {} : { sessionId: sessionId as string }),
    // A model this app does not offer is dropped rather than refused: the person
    // gets their answer from the default model instead of an error they cannot act on.
    ...(isModel(model) ? { model } : {}),
    // The page the message came from, for the system prompt. Like the model, a page
    // name that is not short plain text is dropped rather than refused.
    ...(isPageName(page) ? { page: page.trim() } : {}),
  }
}

/** The longest page name passed on: a title and a path fit easily. */
export const PAGE_LIMIT = 200

/** Text with no control characters, so a page name can never add a line to the prompt. */
function isPageName(page: unknown): page is string {
  // eslint-disable-next-line no-control-regex
  return typeof page === 'string' && page.trim() !== '' && page.length <= PAGE_LIMIT && !/[\u0000-\u001f\u007f]/.test(page)
}
