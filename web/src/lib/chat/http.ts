/**
 * The small pieces the three chat endpoints share.
 *
 * A refusal is plain text a page can show as it stands. It never names a path
 * outside the repo and never carries the value of a setting: the browser gets the
 * reason, and the log gets the detail.
 */

/** Bytes of request body read before the request is refused. A message is capped far below this. */
export const BODY_LIMIT = 64 * 1024

export function plain(status: number, reason: string): Response {
  return new Response(`${reason}\n`, {
    status,
    headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' },
  })
}

export function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
  })
}

/** JSON only, so a form on another page cannot post here without asking permission first. */
export function isJsonRequest(request: Request): boolean {
  const type = (request.headers.get('content-type') ?? '').split(';')[0]?.trim().toLowerCase()
  return type === 'application/json'
}

export type BodyRead =
  | { ok: true; value: unknown }
  | { ok: false; status: 400 | 413; reason: string }

const TOO_BIG: BodyRead = { ok: false, status: 413, reason: 'That request is too large for this endpoint.' }

/**
 * The body, as JSON, up to the cap.
 *
 * The declared length is checked first and then the bytes are counted as they
 * arrive, because a declared length is a claim: a request can say 10 and send
 * megabytes. Reading stops the moment the cap is passed, so nothing larger is ever
 * held in memory. The cap is the chat's unless a caller names a smaller one.
 */
export async function readJsonBody(request: Request, limit = BODY_LIMIT): Promise<BodyRead> {
  const declared = Number(request.headers.get('content-length'))
  if (Number.isFinite(declared) && declared > limit) return TOO_BIG

  let text = ''
  const body = request.body
  if (body) {
    const reader = body.getReader()
    const decoder = new TextDecoder()
    let size = 0
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > limit) {
        await reader.cancel()
        return TOO_BIG
      }
      text += decoder.decode(value, { stream: true })
    }
    text += decoder.decode()
  } else {
    text = await request.text()
    if (text.length > limit) return TOO_BIG
  }

  try {
    return { ok: true, value: JSON.parse(text) }
  } catch {
    return { ok: false, status: 400, reason: 'The request body is not JSON.' }
  }
}
