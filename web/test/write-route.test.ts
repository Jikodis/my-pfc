/**
 * The write routes, called as Astro calls them, with the fake writer. Every
 * refusal is checked to start nothing (the fake records its argv when it runs),
 * and every test ends with the one-at-a-time gate free.
 */
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { APIContext } from 'astro'

import { gone } from './helpers/processes'

const FAKE = fileURLToPath(new URL('./fixtures/fake_web_write.sh', import.meta.url))
const PORT = '4399'
const TASK = 'task-20260901-001'

type Routes = {
  complete: typeof import('../src/pages/api/write/complete-task')
  drop: typeof import('../src/pages/api/write/drop-task')
  habit: typeof import('../src/pages/api/write/log-habit')
  park: typeof import('../src/pages/api/write/park-focus')
  rate: typeof import('../src/pages/api/write/rate-day')
  picks: typeof import('../src/pages/api/write/set-picks')
  stamp: typeof import('../src/pages/api/write/stamp-review')
  skip: typeof import('../src/pages/api/write/skip-suggestion')
  area: typeof import('../src/pages/api/write/set-area')
  room: typeof import('../src/pages/api/write/set-room')
  retire: typeof import('../src/pages/api/write/retire-anchor')
  project: typeof import('../src/pages/api/write/set-project')
  write: typeof import('../src/lib/write')
}

let dir = ''
let argsFile = ''
let logs: MockInstance<typeof console.error>
let routes: Routes | undefined

async function load(mode = 'ok', env: Record<string, string> = {}): Promise<Routes> {
  vi.stubEnv('PFC_WEB_WRITE', FAKE)
  vi.stubEnv('FAKE_WRITE_MODE', mode)
  vi.stubEnv('FAKE_WRITE_ARGS_FILE', argsFile)
  vi.stubEnv('PORT', PORT)
  for (const [name, value] of Object.entries(env)) vi.stubEnv(name, value)
  vi.resetModules()
  routes = {
    complete: await import('../src/pages/api/write/complete-task'),
    drop: await import('../src/pages/api/write/drop-task'),
    habit: await import('../src/pages/api/write/log-habit'),
    park: await import('../src/pages/api/write/park-focus'),
    rate: await import('../src/pages/api/write/rate-day'),
    picks: await import('../src/pages/api/write/set-picks'),
    stamp: await import('../src/pages/api/write/stamp-review'),
    skip: await import('../src/pages/api/write/skip-suggestion'),
    area: await import('../src/pages/api/write/set-area'),
    room: await import('../src/pages/api/write/set-room'),
    retire: await import('../src/pages/api/write/retire-anchor'),
    project: await import('../src/pages/api/write/set-project'),
    write: await import('../src/lib/write'),
  }
  return routes
}

const call = async (route: (context: APIContext) => Response | Promise<Response>, request: Request) => {
  const host = request.headers.get('host') ?? '127.0.0.1'
  const { pathname } = new URL(request.url)
  return route({ request, url: new URL(`http://${host}${pathname}`) } as unknown as APIContext)
}

function post(body: unknown, headers: Record<string, string> = {}, path = '/api/write/complete-task'): Request {
  const all: Record<string, string> = {
    host: `127.0.0.1:${PORT}`,
    'content-type': 'application/json',
    'x-pfc-chat': '1',
    ...headers,
  }
  for (const [name, value] of Object.entries(all)) if (value === '') delete all[name]
  return new Request(`http://127.0.0.1:${PORT}${path}`, {
    method: 'POST',
    headers: all,
    body: typeof body === 'string' ? body : JSON.stringify(body),
  })
}

const ran = () => existsSync(argsFile)
const argv = () => readFileSync(argsFile, 'utf8').trim().split('\n')

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'pfc-write-route-'))
  argsFile = join(dir, 'args.txt')
  logs = vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  expect(routes?.write.writeInProgress() ?? false).toBe(false)
  routes = undefined
  logs.mockRestore()
  vi.unstubAllEnvs()
  vi.resetModules()
  rmSync(dir, { recursive: true, force: true })
})

describe('the write routes refuse before they run anything', () => {
  it('415 for a body not sent as JSON', async () => {
    const { complete } = await load()
    const response = await call(complete.POST, post({ id: TASK }, { 'content-type': 'application/xml' }))
    expect(response.status).toBe(415)
    expect((await response.json()).ok).toBe(false)
    expect(ran()).toBe(false)
  })

  it('413 for a declared length past 4 KB, and for a body past 4 KB', async () => {
    const { complete } = await load()
    expect((await call(complete.POST, post({ id: TASK }, { 'content-length': '5000' }))).status).toBe(413)
    expect((await call(complete.POST, post({ id: TASK, pad: 'x'.repeat(4_200) }))).status).toBe(413)
    expect(ran()).toBe(false)
  })

  it('403 without the custom header, from another origin, or for another Host', async () => {
    const { complete } = await load()
    const refused: Record<string, string>[] = [{ 'x-pfc-chat': '' }, { origin: 'https://evil.example' },
      { host: '127.0.0.1:1' }, { 'sec-fetch-site': 'cross-site' }]
    for (const headers of refused) {
      const response = await call(complete.POST, post({ id: TASK }, headers))
      expect(response.status, JSON.stringify(headers)).toBe(403)
    }
    expect(ran()).toBe(false)
  })

  it('400 for a body that is not JSON, not an object, or has a bad id', async () => {
    const { complete, habit, park } = await load()
    const cases: [typeof complete.POST, unknown, string][] = [
      [complete.POST, '{ not json', '/api/write/complete-task'],
      [complete.POST, [TASK], '/api/write/complete-task'],
      [complete.POST, {}, '/api/write/complete-task'],
      [complete.POST, { id: 'task-1; rm -rf /' }, '/api/write/complete-task'],
      [complete.POST, { id: 42 }, '/api/write/complete-task'],
      [habit.POST, { id: 'Morning_Row' }, '/api/write/log-habit'],
      [habit.POST, { id: 'x'.repeat(65) }, '/api/write/log-habit'],
      [habit.POST, { id: '--dry-run' }, '/api/write/log-habit'],
      [habit.POST, { id: 'morning-walk', date: 'yesterday' }, '/api/write/log-habit'],
      [habit.POST, { id: 'morning-walk', date: '2026-02-30' }, '/api/write/log-habit'],
      [habit.POST, { id: 'morning-walk', date: '--dry-run' }, '/api/write/log-habit'],
      [habit.POST, { id: 'morning-walk', date: 20261012 }, '/api/write/log-habit'],
      [park.POST, { id: 'focus-20260706-001' }, '/api/write/park-focus'],
      [park.POST, { id: 'focus-20260706-001', parked: 'on' }, '/api/write/park-focus'],
      [park.POST, { id: 'focus-1', parked: true }, '/api/write/park-focus'],
    ]
    for (const [route, body, path] of cases) {
      const response = await call(route, post(body, {}, path))
      expect(response.status, JSON.stringify(body)).toBe(400)
    }
    expect(ran()).toBe(false)
  })

  it('reads the id as an own property, not an inherited one', async () => {
    const { complete } = await load()
    const response = await call(complete.POST, post('{"__proto__": {"id": "task-20260901-001"}}'))
    expect(response.status).toBe(400)
    expect(ran()).toBe(false)
  })
})

describe('the write routes pass the writer\'s answer on', () => {
  it('200 with the full result for each action, and the argv each one sends', async () => {
    const { complete, habit, park } = await load('ok')
    const response = await call(complete.POST, post({ id: TASK }))
    expect(response.status).toBe(200)
    expect(await response.json()).toEqual({
      ok: true, message: 'Saved.', commit: 'abc1234', pushed: true, push_error: null,
      title: 'Call the dentist', email_linked: true, changed: true,
    })
    expect(argv()).toEqual(['complete-task', TASK])

    expect((await call(habit.POST, post({ id: 'morning-walk' }, {}, '/api/write/log-habit'))).status).toBe(200)
    expect(argv()).toEqual(['log-habit', 'morning-walk'])

    const dated = post({ id: 'morning-walk', date: '2026-10-12' }, {}, '/api/write/log-habit')
    expect((await call(habit.POST, dated)).status).toBe(200)
    expect(argv()).toEqual(['log-habit', 'morning-walk', '2026-10-12'])

    expect((await call(park.POST, post({ id: 'focus-20260706-001', parked: true }, {}, '/api/write/park-focus'))).status).toBe(200)
    expect(argv()).toEqual(['park-focus', 'focus-20260706-001', 'on'])
    expect((await call(park.POST, post({ id: 'focus-20260706-001', parked: false }, {}, '/api/write/park-focus'))).status).toBe(200)
    expect(argv()).toEqual(['park-focus', 'focus-20260706-001', 'off'])
  })

  it('answers as JSON with no-store', async () => {
    const { complete } = await load('ok')
    const response = await call(complete.POST, post({ id: TASK }))
    expect(response.headers.get('content-type')).toMatch(/^application\/json/)
    expect(response.headers.get('cache-control')).toBe('no-store')
  })

  it.each([
    ['unknown', 404, 'No open task with that id.'],
    ['refused', 422, 'That focus is retired.'],
    ['locked', 409, 'Another change is still being saved.'],
    ['invalid', 422, 'tasks.ndjson: record task-x violates schema'],
    ['crash', 500, 'The change could not be saved. The server log has the details.'],
  ])('%s is %i with its message', async (mode, status, message) => {
    const { complete } = await load(mode)
    const response = await call(complete.POST, post({ id: TASK }))
    expect(response.status).toBe(status)
    const body = await response.json()
    expect(body.ok).toBe(false)
    expect(body.message).toBe(message)
    expect(JSON.stringify(body)).not.toMatch(/Traceback|secret/)
  })

  it('a second write while the first is still running waits its turn, then both are saved', async () => {
    const { complete, drop, write } = await load('slow')
    const first = call(complete.POST, post({ id: TASK }))
    // The first request reads its body before it spawns; wait until it has.
    for (let n = 0; n < 100 && !write.writeInProgress(); n++) await new Promise((r) => setTimeout(r, 10))
    expect(write.writeInProgress()).toBe(true)
    const second = call(drop.POST, post({ id: 'task-20260901-002' }, {}, '/api/write/drop-task'))
    expect((await first).status).toBe(200)
    expect((await second).status).toBe(200)
    expect(argv()).toEqual(['drop-task', 'task-20260901-002'])
  }, 15_000)

  it('drop-task passes the id and refuses one that is not a task id', async () => {
    const { drop } = await load('ok')
    expect((await call(drop.POST, post({ id: TASK }, {}, '/api/write/drop-task'))).status).toBe(200)
    expect(argv()).toEqual(['drop-task', TASK])
    expect((await call(drop.POST, post({ id: '--help' }, {}, '/api/write/drop-task'))).status).toBe(400)
  })

  it('500 with fixed text when the writer runs past the timeout', async () => {
    const { complete } = await load('slow', { PFC_WRITE_TIMEOUT_MS: '300' })
    const response = await call(complete.POST, post({ id: TASK }))
    expect(response.status).toBe(500)
    expect((await response.json()).message).toBe('The change could not be saved. The server log has the details.')
  })

  it('a timed-out write leaves no process behind and frees the gate', async () => {
    const pids = join(dir, 'pids.txt')
    const { complete, write } = await load('stubborn', { PFC_WRITE_TIMEOUT_MS: '500', FAKE_WRITE_PIDS_FILE: pids })
    const response = await call(complete.POST, post({ id: TASK }))
    expect(response.status).toBe(500)
    expect(write.writeInProgress()).toBe(false)
    const [leader, sleeper] = readFileSync(pids, 'utf8').trim().split(' ').map(Number)
    expect(await gone(leader)).toBe(true)
    expect(await gone(sleeper)).toBe(true)
  })
})

describe('the tour write routes', () => {
  const RATE = '/api/write/rate-day'
  const PICKS = '/api/write/set-picks'
  const STAMP = '/api/write/stamp-review'
  const day = { date: '2026-11-01', energy: 4, mood: 3, focus: 5 }

  it('rate-day refuses a rating of 6 before starting the writer', async () => {
    const { rate } = await load()
    expect((await call(rate.POST, post({ ...day, energy: 6 }, {}, RATE))).status).toBe(400)
    expect(ran()).toBe(false)
  })

  it('rate-day refuses non-integer ratings, a bad date, and bad optional fields', async () => {
    const { rate } = await load()
    const bad: unknown[] = [
      { ...day, mood: 0 }, { ...day, focus: 2.5 }, { ...day, energy: '4' }, { ...day, date: '--dry-run' },
      { ...day, date: '2026-02-30' }, { ...day, hyperfocused: 'yes' }, { ...day, hyperfocused: 1 },
      { energy: 4, mood: 3, focus: 5 },
    ]
    for (const body of bad) expect((await call(rate.POST, post(body, {}, RATE))).status, JSON.stringify(body)).toBe(400)
    expect(ran()).toBe(false)
  })

  it('rate-day maps the body to the writer\'s argv', async () => {
    const { rate } = await load()
    expect((await call(rate.POST, post(day, {}, RATE))).status).toBe(200)
    expect(argv()).toEqual(['rate-day', '2026-11-01', '4', '3', '5'])
    expect((await call(rate.POST, post({ ...day, hyperfocused: true }, {}, RATE))).status).toBe(200)
    expect(argv()).toEqual(['rate-day', '2026-11-01', '4', '3', '5', 'hyper:yes'])
    // A field the route does not know is never passed on.
    expect((await call(rate.POST, post({ ...day, extra: 2 }, {}, RATE))).status).toBe(200)
    expect(argv()).toEqual(['rate-day', '2026-11-01', '4', '3', '5'])
    expect((await call(rate.POST, post({ ...day, hyperfocused: false }, {}, RATE))).status).toBe(200)
    expect(argv()).toEqual(['rate-day', '2026-11-01', '4', '3', '5', 'hyper:no'])
  })

  it('set-picks refuses more than eight critical ids, none, bad ids, and a bad bonus', async () => {
    const { picks } = await load()
    const a = 'task-20260901-001'
    const bad: unknown[] = [
      { date: '2026-11-01', critical: Array.from({ length: 9 }, (_, i) => `task-20260901-${String(i + 1).padStart(3, '0')}`) },
      { date: '2026-11-01', critical: [] },
      { date: '2026-11-01', critical: ['--dry-run'] },
      { date: '2026-11-01', critical: a },
      { date: '2026-11-01', critical: [a], bonus: 'bonus:x' },
      { date: 'tomorrow', critical: [a] },
    ]
    for (const body of bad) expect((await call(picks.POST, post(body, {}, PICKS))).status, JSON.stringify(body)).toBe(400)
    expect(ran()).toBe(false)
  })

  it('set-picks passes ids as separate argv entries', async () => {
    const { picks } = await load()
    const a = 'task-20260901-001'
    const b = 'task-20260901-002'
    const c = 'task-20260901-003'
    expect((await call(picks.POST, post({ date: '2026-11-01', critical: [a, b] }, {}, PICKS))).status).toBe(200)
    expect(argv()).toEqual(['set-picks', '2026-11-01', a, b])
    expect((await call(picks.POST, post({ date: '2026-11-01', critical: [a], bonus: c }, {}, PICKS))).status).toBe(200)
    expect(argv()).toEqual(['set-picks', '2026-11-01', a, `bonus:${c}`])
    // A done pick travels with the open ones when more work is pulled in.
    expect((await call(picks.POST, post({ date: '2026-11-01', critical: [a, b, c] }, {}, PICKS))).status).toBe(200)
    expect(argv()).toEqual(['set-picks', '2026-11-01', a, b, c])
  })

  it('stamp-review refuses an id with a leading hyphen', async () => {
    const { stamp } = await load()
    for (const id of ['-rf', '--dry-run', 'Upper', 'x'.repeat(65), 7, undefined]) {
      expect((await call(stamp.POST, post({ id }, {}, STAMP))).status, String(id)).toBe(400)
    }
    expect(ran()).toBe(false)
  })

  it('stamp-review passes the id', async () => {
    const { stamp } = await load()
    expect((await call(stamp.POST, post({ id: 'rev-life-wheel' }, {}, STAMP))).status).toBe(200)
    expect(argv()).toEqual(['stamp-review', 'rev-life-wheel'])
  })
})

describe('the one-tap write routes', () => {
  const path = (name: string) => `/api/write/${name}`
  const GROUND = 'ground-20260812-001'
  const PROJ = 'proj-20260801-001'

  it('skip-suggestion refuses bad shapes before starting the writer', async () => {
    const { skip } = await load()
    const bad: unknown[] = [
      { date: '2026-11-01' }, { id: TASK }, { date: 'today', id: TASK }, { date: '2026-02-30', id: TASK },
      { date: '2026-11-01', id: '--dry-run' }, { date: '2026-11-01', id: [TASK] }, { date: '2026-11-01', id: GROUND },
    ]
    for (const body of bad) expect((await call(skip.POST, post(body, {}, path('skip-suggestion')))).status, JSON.stringify(body)).toBe(400)
    expect(ran()).toBe(false)
  })

  it('skip-suggestion passes the day and the id', async () => {
    const { skip } = await load()
    expect((await call(skip.POST, post({ date: '2026-11-01', id: TASK }, {}, path('skip-suggestion')))).status).toBe(200)
    expect(argv()).toEqual(['skip-suggestion', '2026-11-01', TASK])
  })

  for (const name of ['set-area', 'set-room'] as const) {
    const route = (r: Routes) => (name === 'set-area' ? r.area : r.room)

    it(`${name} refuses bad keys, lights, and notes before starting the writer`, async () => {
      const r = await load()
      const bad: unknown[] = [
        { light: 'red' }, { key: 'career' }, { key: 'Career', light: 'red' }, { key: '-x', light: 'red' },
        { key: '--dry-run', light: 'red' }, { key: 'x'.repeat(33), light: 'red' }, { key: 'career', light: 'purple' },
        { key: 'career', light: 1 }, { key: 'career', light: 'red', note: 5 },
        { key: 'career', light: 'red', note: 'two\nlines' }, { key: 'career', light: 'red', note: 'tab\there' },
        { key: 'career', light: 'red', note: 'a\u0085b' }, { key: 'career', light: 'red', note: 'a\u2028b' },
        { key: 'career', light: 'red', note: 'a\u2029b' },
        { key: 'career', light: 'red', note: 'x'.repeat(301) },
      ]
      for (const body of bad) expect((await call(route(r).POST, post(body, {}, path(name)))).status, JSON.stringify(body)).toBe(400)
      expect(ran()).toBe(false)
    })

    it(`${name} passes the note as one argv entry, never split`, async () => {
      const r = await load()
      expect((await call(route(r).POST, post({ key: 'career', light: 'yellow' }, {}, path(name)))).status).toBe(200)
      expect(argv()).toEqual([name, 'career', 'yellow'])
      const text = 'Sleeping better --dry-run; two words  and "quotes"'
      expect((await call(route(r).POST, post({ key: 'career', light: 'green', note: text }, {}, path(name)))).status).toBe(200)
      expect(argv()).toEqual([name, 'career', 'green', `note:${text}`])
      expect((await call(route(r).POST, post({ key: 'career', light: 'green', note: '' }, {}, path(name)))).status).toBe(200)
      expect(argv()).toEqual([name, 'career', 'green', 'note:'])
      expect((await call(route(r).POST, post({ key: 'career', light: 'green', note: 'x'.repeat(300) }, {}, path(name)))).status).toBe(200)
    })
  }

  it('retire-anchor refuses other id shapes and passes the id', async () => {
    const { retire } = await load()
    for (const id of ['--dry-run', PROJ, TASK, 'ground-1', 7, undefined]) {
      expect((await call(retire.POST, post({ id }, {}, path('retire-anchor')))).status, String(id)).toBe(400)
    }
    expect(ran()).toBe(false)
    expect((await call(retire.POST, post({ id: GROUND }, {}, path('retire-anchor')))).status).toBe(200)
    expect(argv()).toEqual(['retire-anchor', GROUND])
  })

  it('set-project refuses bad ids and a non-boolean, and maps active to the argv word', async () => {
    const { project } = await load()
    const bad: unknown[] = [
      { id: PROJ }, { id: PROJ, active: 'true' }, { id: GROUND, active: true }, { id: '--dry-run', active: true },
      { active: true },
    ]
    for (const body of bad) expect((await call(project.POST, post(body, {}, path('set-project')))).status, JSON.stringify(body)).toBe(400)
    expect(ran()).toBe(false)
    expect((await call(project.POST, post({ id: PROJ, active: true }, {}, path('set-project')))).status).toBe(200)
    expect(argv()).toEqual(['set-project', PROJ, 'active'])
    expect((await call(project.POST, post({ id: PROJ, active: false }, {}, path('set-project')))).status).toBe(200)
    expect(argv()).toEqual(['set-project', PROJ, 'parked'])
  })
})
