/**
 * The endpoints themselves, called as Astro calls them.
 *
 * The modules under test are the ones the server loads, so a refusal that is
 * deleted or reordered fails here: the guard, who owns a conversation, one reply at
 * a time per conversation, three runs at once, the size cap, and the shape of the
 * stream. The binary is always the fake one.
 */
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { APIContext } from 'astro'

const FAKE = fileURLToPath(new URL('./fixtures/fake_claude.sh', import.meta.url))

/** The port the server is started on, which is the only port its Host may name. */
const PORT = '4399'
const SESSION = '00000000-0000-4000-8000-000000000000'
const OTHER = '11111111-1111-4111-8111-111111111111'

type Routes = {
  chat: typeof import('../src/pages/api/chat/index')
  stop: typeof import('../src/pages/api/chat/stop')
  attach: typeof import('../src/pages/api/chat/attach')
  skills: typeof import('../src/pages/api/chat/skills')
  runner: typeof import('../src/lib/chat/runner')
}

let dir = ''
let sessionsFile = ''
let routes: Routes
let logs: MockInstance<typeof console.error>

async function load(mode = 'ok', env: Record<string, string> = {}): Promise<Routes> {
  vi.stubEnv('PFC_CLAUDE', FAKE)
  vi.stubEnv('FAKE_CLAUDE_MODE', mode)
  vi.stubEnv('PFC_CHAT_SESSIONS_FILE', sessionsFile)
  vi.stubEnv('PORT', PORT)
  for (const [name, value] of Object.entries(env)) vi.stubEnv(name, value)
  vi.resetModules()
  routes = {
    chat: await import('../src/pages/api/chat/index'),
    stop: await import('../src/pages/api/chat/stop'),
    attach: await import('../src/pages/api/chat/attach'),
    skills: await import('../src/pages/api/chat/skills'),
    runner: await import('../src/lib/chat/runner'),
  }
  return routes
}

/**
 * Astro hands a route a context. The url in it is built from the request's own Host
 * header, which is the whole reason a route may not read its port from there, so
 * this helper builds it the same way.
 */
const call = async (
  route: (context: APIContext) => Response | Promise<Response>,
  request: Request,
): Promise<Response> => {
  const host = request.headers.get('host') ?? '127.0.0.1'
  const { pathname, search } = new URL(request.url)
  return route({ request, url: new URL(`http://${host}${pathname}${search}`) } as unknown as APIContext)
}

type Extra = { headers?: Record<string, string>; host?: string; path?: string }

function post(body: unknown, extra: Extra = {}): Request {
  const headers: Record<string, string> = {
    host: extra.host ?? `127.0.0.1:${PORT}`,
    'content-type': 'application/json',
    'x-pfc-chat': '1',
    ...extra.headers,
  }
  for (const [name, value] of Object.entries(headers)) {
    if (value === '') delete headers[name]
  }
  return new Request(`http://127.0.0.1:${PORT}${extra.path ?? '/api/chat'}`, {
    method: 'POST',
    headers,
    body: typeof body === 'string' ? body : JSON.stringify(body),
  })
}

/** Everything the stream carried, read to its end. */
async function readStream(response: Response): Promise<string> {
  const reader = (response.body as ReadableStream<Uint8Array>).getReader()
  const decoder = new TextDecoder()
  let text = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    text += decoder.decode(value, { stream: true })
  }
  return text + decoder.decode()
}

const until = async (check: () => boolean, ms = 2_000): Promise<boolean> => {
  const stop = Date.now() + ms
  while (Date.now() < stop) {
    if (check()) return true
    await new Promise((r) => setTimeout(r, 20))
  }
  return check()
}

/** The run id out of the first frame of a stream, read off a reader the caller keeps. */
async function runIdOf(reader: ReadableStreamDefaultReader<Uint8Array>): Promise<string> {
  const first = await reader.read()
  return /"id":"([^"]+)"/.exec(new TextDecoder().decode(first.value))?.[1] as string
}

/** Every test ends with nothing running, whatever it started. */
async function stopEverything(): Promise<void> {
  if (!routes) return
  // A reader walking away no longer stops a run, so a test's leftovers are stopped here.
  for (const id of routes.runner.liveRunIds()) routes.runner.stopRun(id)
  for (let n = 0; n < 40 && routes.runner.liveRuns() > 0; n++) {
    await new Promise((r) => setTimeout(r, 50))
  }
}

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'pfc-route-'))
  sessionsFile = join(dir, 'sessions.json')
  logs = vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(async () => {
  await stopEverything()
  logs.mockRestore()
  vi.unstubAllEnvs()
  vi.resetModules()
  rmSync(dir, { recursive: true, force: true })
})

describe('POST /api/chat refuses before it runs anything', () => {
  it('refuses a body that is not sent as JSON', async () => {
    const { chat, runner } = await load()
    const response = await call(chat.POST, post('hello', { headers: { 'content-type': 'application/xml' } }))
    expect(response.status).toBe(415)
    expect(runner.liveRuns()).toBe(0)
  })

  it('refuses a body whose declared length is past the cap, without reading it', async () => {
    const { chat, runner } = await load()
    const response = await call(chat.POST, post({ message: 'hello' }, { headers: { 'content-length': '999999' } }))
    expect(response.status).toBe(413)
    expect(runner.liveRuns()).toBe(0)
  })

  it('refuses a body that is not JSON, and an empty message', async () => {
    const { chat, runner } = await load()
    expect((await call(chat.POST, post('{ not json'))).status).toBe(400)
    expect((await call(chat.POST, post({ message: '   ' }))).status).toBe(400)
    expect(runner.liveRuns()).toBe(0)
  })

  it('refuses a request without the custom header', async () => {
    const { chat, runner } = await load()
    const response = await call(chat.POST, post({ message: 'hello' }, { headers: { 'x-pfc-chat': '' } }))
    expect(response.status).toBe(403)
    expect(runner.liveRuns()).toBe(0)
  })

  it('refuses a conversation this server did not start', async () => {
    const { chat, runner } = await load()
    const response = await call(chat.POST, post({ message: 'hello', sessionId: OTHER }))
    expect(response.status).toBe(403)
    expect(await response.text()).toMatch(/not started here/)
    expect(runner.liveRuns()).toBe(0)
  })
})

describe('the port a Host is checked against', () => {
  it('is the port the server was started on, not the one the request names', async () => {
    // Astro builds the request URL out of the request's own Host header, so reading
    // the port from there compared a claim with itself and let any Host through.
    const { chat, runner } = await load()
    const response = await call(chat.POST, post({ message: 'hello' }, { host: '127.0.0.1:1' }))
    expect(response.status).toBe(403)
    expect(await response.text()).toMatch(/is not this server/)
    expect(runner.liveRuns()).toBe(0)
  })

  it('accepts a Host that names the port the server was started on', async () => {
    const { chat } = await load()
    const response = await call(chat.POST, post({ message: 'hello' }, { host: `127.0.0.1:${PORT}` }))
    expect(response.status).toBe(200)
    await readStream(response)
  })
})

describe('serverPort', () => {
  const port = async (value: string | undefined) => {
    if (value === undefined) vi.stubEnv('PORT', '')
    else vi.stubEnv('PORT', value)
    vi.resetModules()
    return (await import('../src/lib/chat/port')).serverPort()
  }

  it('is the port the server was told to serve', async () => {
    expect(await port('4324')).toBe('4324')
    expect(await port(' 4399 ')).toBe('4399')
  })

  it('falls back to the port in the Astro config when nothing names one', async () => {
    // `astro dev` sets no PORT, and its default is the one in astro.config.mjs.
    expect(await port(undefined)).toBe('4323')
    for (const bad of ['no', '0', '70000', '-1', '80.5', '4323 or so']) {
      expect(await port(bad)).toBe('4323')
    }
  })
})

describe('POST /api/chat when it runs', () => {
  it('streams the run id first, then every event, to the reply', async () => {
    const { chat, runner } = await load('ok')
    const response = await call(chat.POST, post({ message: 'hello' }))
    expect(response.status).toBe(200)
    expect(response.headers.get('content-type')).toMatch(/text\/event-stream/)
    expect(response.headers.get('cache-control')).toBe('no-store')
    expect(response.headers.get('x-accel-buffering')).toBe('no')

    const body = await readStream(response)
    expect(body.startsWith('event: run\ndata: {"id":"')).toBe(true)
    expect(body).toMatch(/data: \{"kind":"session"/)
    expect(body).toMatch(/data: \{"kind":"done"/)
    expect(runner.liveRuns()).toBe(0)
  })

  it('numbers each event frame, so a page knows how far it got', async () => {
    const { chat } = await load('ok')
    const body = await readStream(await call(chat.POST, post({ message: 'hello' })))
    const ids = [...body.matchAll(/^id: (\d+)\ndata: /gm)].map((m) => Number(m[1]))
    expect(ids).toEqual([0, 1, 2, 3, 4, 5])
  })

  it('keeps the run going when the page that started it goes away', async () => {
    const { chat, runner } = await load('hang')
    const response = await call(chat.POST, post({ message: 'hello' }))
    const reader = (response.body as ReadableStream<Uint8Array>).getReader()
    const id = await runIdOf(reader)
    await reader.cancel()
    await new Promise((r) => setTimeout(r, 200))
    expect(runner.liveRuns()).toBe(1)
    expect(runner.stopRun(id)).toBe(true)
    expect(await until(() => runner.liveRuns() === 0)).toBe(true)
  })

  it('refuses a second message to a conversation that is still being answered', async () => {
    const { chat, runner } = await load('hang')
    // Owned, because a run of this server's recorded it.
    writeFileSync(sessionsFile, JSON.stringify([SESSION]))

    const first = await call(chat.POST, post({ message: 'hello', sessionId: SESSION }))
    expect(first.status).toBe(200)
    expect(await until(() => runner.liveRuns() === 1)).toBe(true)

    const second = await call(chat.POST, post({ message: 'again', sessionId: SESSION }))
    expect(second.status).toBe(409)
    expect(await second.text()).toMatch(/still in progress/)

    const reader = (first.body as ReadableStream<Uint8Array>).getReader()
    runner.stopRun(await runIdOf(reader))
    await reader.cancel()
    expect(await until(() => runner.liveRuns() === 0)).toBe(true)
  })

  it('refuses a fourth run while three are live', async () => {
    const { chat, runner } = await load('hang')
    const live = [
      await call(chat.POST, post({ message: 'a' })),
      await call(chat.POST, post({ message: 'b' })),
      await call(chat.POST, post({ message: 'c' })),
    ]
    expect(await until(() => runner.liveRuns() === 3)).toBe(true)

    const fourth = await call(chat.POST, post({ message: 'd' }))
    expect(fourth.status).toBe(429)
    expect(await fourth.text()).toMatch(/already being written/)

    for (const id of runner.liveRunIds()) runner.stopRun(id)
    for (const response of live) await response.body?.cancel()
    expect(await until(() => runner.liveRuns() === 0)).toBe(true)
  })

  it('sends a comment frame while the run is quiet, well before the connection could time out', async () => {
    // The interval used to tick once per quiet period, so the first check always
    // landed a millisecond short and the first frame went out at twice the wait.
    // Measured from the last frame that arrived before the comment, not from the
    // request: the quiet starts when the fake prints its first line, and a slow
    // start used to eat into the margin and fail the test on a busy machine.
    const { chat, runner } = await load('hang', { PFC_CHAT_KEEPALIVE_MS: '1000' })
    const response = await call(chat.POST, post({ message: 'hello' }))
    const reader = (response.body as ReadableStream<Uint8Array>).getReader()
    const decoder = new TextDecoder()
    const started = Date.now()
    let lastFrame = started
    let waited = Infinity
    let text = ''
    while (Date.now() - started < 4_000) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      text += chunk
      if (chunk.includes(': keep-alive')) {
        waited = Date.now() - lastFrame
        break
      }
      lastFrame = Date.now()
    }
    expect(text).toMatch(/: keep-alive/)
    // Half again the quiet period. A timer ticking once per period first fires at
    // twice it, which is what this catches.
    expect(waited).toBeLessThan(1_500)

    await reader.cancel()
    for (const id of runner.liveRunIds()) runner.stopRun(id)
    expect(await until(() => runner.liveRuns() === 0)).toBe(true)
  })

  it('never waits less than a second between comment frames, whatever the setting says', async () => {
    const { chat } = await load('hang', { PFC_CHAT_KEEPALIVE_MS: '5' })
    const response = await call(chat.POST, post({ message: 'hello' }))
    const reader = (response.body as ReadableStream<Uint8Array>).getReader()
    const decoder = new TextDecoder()
    let text = ''
    const stopAt = Date.now() + 600
    while (Date.now() < stopAt) {
      const next = await Promise.race([
        reader.read(),
        new Promise<null>((r) => setTimeout(() => r(null), stopAt - Date.now())),
      ])
      if (!next || next.done) break
      text += decoder.decode(next.value, { stream: true })
    }
    expect(text).toMatch(/event: run/)
    expect(text).not.toMatch(/: keep-alive/)
    await reader.cancel()
  })

  it('stops waiting for a reader that never reads once the run is over', async () => {
    // Nobody reads this stream. Once the run has ended, the loop that waits for room
    // must end with it, rather than hold the stream and its timer open for good.
    const cleared = vi.spyOn(globalThis, 'clearInterval')
    const { chat, runner } = await load('ok')
    const response = await call(chat.POST, post({ message: 'hello' }))
    expect(response.status).toBe(200)
    expect(await until(() => runner.liveRuns() === 0, 5_000)).toBe(true)
    expect(await until(() => cleared.mock.calls.length > 0)).toBe(true)
    cleared.mockRestore()
    // And what it held is all still there for a reader that comes back.
    expect(await readStream(response)).toMatch(/"kind":"done"/)
  })
})

describe('POST /api/chat/stop', () => {
  it('stops a live run and says so', async () => {
    const { chat, stop, runner } = await load('hang')
    const response = await call(chat.POST, post({ message: 'hello' }))
    const first = await (response.body as ReadableStream<Uint8Array>).getReader().read()
    const id = /"id":"([^"]+)"/.exec(new TextDecoder().decode(first.value))?.[1] as string
    expect(id).toBeTruthy()

    const stopped = await call(stop.POST, post({ id }, { path: '/api/chat/stop' }))
    expect(stopped.status).toBe(200)
    expect(await stopped.json()).toEqual({ stopped: true })
    expect(await until(() => runner.liveRuns() === 0)).toBe(true)

    const again = await call(stop.POST, post({ id }, { path: '/api/chat/stop' }))
    expect(await again.json()).toEqual({ stopped: false })
  })

  it('refuses a Host that is not this server', async () => {
    const { stop } = await load()
    const wrong = await call(stop.POST, post({ id: 'x' }, { path: '/api/chat/stop', host: 'evil.example:4399' }))
    expect(wrong.status).toBe(403)
    const otherPort = await call(stop.POST, post({ id: 'x' }, { path: '/api/chat/stop', host: '127.0.0.1:4323' }))
    expect(otherPort.status).toBe(403)
  })

  it('refuses a request from somewhere else, and one that names no run', async () => {
    const { stop, runner } = await load()
    const foreign = await call(stop.POST, post({ id: 'x' }, { path: '/api/chat/stop', headers: { origin: 'https://evil.example' } }))
    expect(foreign.status).toBe(403)
    const nameless = await call(stop.POST, post({}, { path: '/api/chat/stop' }))
    expect(nameless.status).toBe(400)
    expect(runner.liveRuns()).toBe(0)
  })
})

describe('POST /api/chat/attach', () => {
  const attachPost = (body: unknown, extra: Extra = {}) => post(body, { path: '/api/chat/attach', ...extra })

  it('streams a live run from the index it is given, then the rest of it as it arrives, then closes', async () => {
    const { chat, attach } = await load('ok')
    const first = await call(chat.POST, post({ message: 'hello' }))
    const reader = (first.body as ReadableStream<Uint8Array>).getReader()
    const id = await runIdOf(reader)
    // The page that started it leaves at once.
    await reader.cancel()

    const again = await call(attach.POST, attachPost({ id, from: 2 }))
    expect(again.status).toBe(200)
    expect(again.headers.get('content-type')).toMatch(/text\/event-stream/)
    const body = await readStream(again)
    expect(body.startsWith(`event: run\ndata: {"id":"${id}"}`)).toBe(true)
    const ids = [...body.matchAll(/^id: (\d+)\ndata: /gm)].map((m) => Number(m[1]))
    expect(ids).toEqual([2, 3, 4, 5])
    expect(body).toMatch(/data: \{"kind":"done"/)
    expect(body).not.toMatch(/"kind":"session"/)
  })

  it('still hands over the tail of a run that ended while nobody was reading', async () => {
    const { chat, attach, runner } = await load('ok')
    const first = await call(chat.POST, post({ message: 'hello' }))
    const reader = (first.body as ReadableStream<Uint8Array>).getReader()
    const id = await runIdOf(reader)
    await reader.cancel()
    expect(await until(() => runner.getRun(id)?.over() === true, 5_000)).toBe(true)

    const body = await readStream(await call(attach.POST, attachPost({ id, from: 5 })))
    const ids = [...body.matchAll(/^id: (\d+)\ndata: /gm)].map((m) => Number(m[1]))
    expect(ids).toEqual([5])
    expect(body).toMatch(/"kind":"done"/)
  })

  it('answers 404 in fixed words for a run it does not know or no longer keeps', async () => {
    const { chat, attach, runner } = await load('ok', { PFC_CHAT_KEEP_MS: '200' })
    const unknown = await call(attach.POST, attachPost({ id: '22222222-2222-4222-8222-222222222222', from: 0 }))
    expect(unknown.status).toBe(404)
    expect(await unknown.text()).toBe('That reply is no longer available.\n')

    const response = await call(chat.POST, post({ message: 'hello' }))
    const id = await runIdOf((response.body as ReadableStream<Uint8Array>).getReader())
    expect(await until(() => runner.getRun(id) === undefined, 5_000)).toBe(true)
    expect((await call(attach.POST, attachPost({ id, from: 0 }))).status).toBe(404)
  })

  it('refuses a malformed id or index with 400', async () => {
    const { attach } = await load()
    const good = '22222222-2222-4222-8222-222222222222'
    for (const body of [
      {},
      { id: good },
      { id: '', from: 0 },
      { id: 7, from: 0 },
      { id: '--help', from: 0 },
      { id: good, from: -1 },
      { id: good, from: 1.5 },
      { id: good, from: '3' },
      [good, 0],
    ]) {
      expect((await call(attach.POST, attachPost(body))).status).toBe(400)
    }
    expect((await call(attach.POST, attachPost('{ not json'))).status).toBe(400)
  })

  it('runs the same header checks as the stop route', async () => {
    const { attach } = await load()
    const body = { id: '22222222-2222-4222-8222-222222222222', from: 0 }
    expect((await call(attach.POST, attachPost(body, { host: 'evil.example:4399' }))).status).toBe(403)
    expect((await call(attach.POST, attachPost(body, { headers: { origin: 'https://evil.example' } }))).status).toBe(403)
    expect((await call(attach.POST, attachPost(body, { headers: { 'x-pfc-chat': '' } }))).status).toBe(403)
  })
})

describe('GET /api/chat/skills', () => {
  const get = (host: string) =>
    new Request(`http://127.0.0.1:${PORT}/api/chat/skills`, { headers: { host } })

  it('lists the skills for a request to this server', async () => {
    const { skills } = await load()
    const response = await call(skills.GET, get(`127.0.0.1:${PORT}`))
    expect(response.status).toBe(200)
    const listed = (await response.json()) as { name: string; takesArgs: boolean }[]
    expect(listed.map((s) => s.name)).toContain('pfc-add-task')
  })

  it('refuses a Host that is not this server', async () => {
    const { skills } = await load()
    expect((await call(skills.GET, get('127.0.0.1:1'))).status).toBe(403)
    expect((await call(skills.GET, get('evil.example'))).status).toBe(403)
  })
})
