import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { ChatEvent } from '../src/lib/chat/events'
import type { Run } from '../src/lib/chat/runner'

/**
 * Every run here is the fake binary, never the real claude: a real run spends the
 * user's subscription and can touch the repo. The fake reads FAKE_CLAUDE_MODE and
 * prints the captured sample stream, so these tests cover the reader, the caps, the
 * stop paths, and the bookkeeping, which is everything this module decides.
 */
const FAKE = fileURLToPath(new URL('./fixtures/fake_claude.sh', import.meta.url))

type Runner = typeof import('../src/lib/chat/runner')

let dir = ''
let runner: Runner

async function load(mode: string, env: Record<string, string> = {}): Promise<Runner> {
  vi.stubEnv('PFC_CLAUDE', FAKE)
  vi.stubEnv('FAKE_CLAUDE_MODE', mode)
  // The list of conversations this server started is a real file; tests write their own.
  vi.stubEnv('PFC_CHAT_SESSIONS_FILE', join(dir, 'sessions.json'))
  for (const [name, value] of Object.entries(env)) vi.stubEnv(name, value)
  vi.resetModules()
  runner = await import('../src/lib/chat/runner')
  return runner
}

/**
 * Everything one reader gets from the start of the run's log, which is how every one
 * of these tests proves a reader's iterator ends.
 */
async function collect(run: Run, from = 0): Promise<ChatEvent[]> {
  const out: ChatEvent[] = []
  for await (const { event } of run.read(from)) out.push(event)
  return out
}

const gone = (pid: number) => {
  try {
    process.kill(pid, 0)
    return false
  } catch {
    return true
  }
}

/** The child takes a moment to leave after its signal; this waits for that and no longer. */
async function until(check: () => boolean, ms = 2_000): Promise<boolean> {
  const stop = Date.now() + ms
  while (Date.now() < stop) {
    if (check()) return true
    await new Promise((r) => setTimeout(r, 25))
  }
  return check()
}

/** What the run wrote to the server log, kept out of the test output and read back. */
let logs: MockInstance<typeof console.error>

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'pfc-runner-'))
  logs = vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(async () => {
  // No child outlives a test, whatever the test did.
  const live = runner as Runner | undefined
  if (live) {
    for (let n = 0; n < 5 && live.liveRuns() > 0; n++) {
      await new Promise((r) => setTimeout(r, 50))
    }
  }
  logs.mockRestore()
  vi.unstubAllEnvs()
  vi.resetModules()
  rmSync(dir, { recursive: true, force: true })
})

describe('a run that works', () => {
  it('yields the events the sample stream carries, ending in done, and leaves nothing running', async () => {
    const { startRun, liveRuns } = await load('ok')
    const run = startRun({ message: 'hello' })
    expect(liveRuns()).toBe(1)
    const events = await collect(run)
    expect(events[0]).toEqual({ kind: 'session', id: '00000000-0000-4000-8000-000000000000', model: 'claude-sonnet-5' })
    expect(events.map((e) => e.kind)).toEqual(['session', 'text', 'tool', 'tool_result', 'tool_result', 'done'])
    const last = events[events.length - 1]
    expect(last.kind === 'done' && last.denied.length).toBe(2)
    expect(liveRuns()).toBe(0)
  })

  it('records the conversation, so the endpoint can let that one be resumed later', async () => {
    const { startRun } = await load('ok')
    await collect(startRun({ message: 'hello' }))
    const { ownsSession } = await import('../src/lib/chat/sessions')
    expect(ownsSession('00000000-0000-4000-8000-000000000000')).toBe(true)
    expect(ownsSession('11111111-1111-4111-8111-111111111111')).toBe(false)
  })

  it('tells the program it was started from the web page, so a skill does not open that page again', async () => {
    const seen = join(dir, 'env.txt')
    const { startRun } = await load('envcheck', { FAKE_CLAUDE_ENV_FILE: seen })
    await collect(startRun({ message: 'hello' }))
    expect(readFileSync(seen, 'utf8')).toBe('1')
  })
})

describe('a run that fails', () => {
  it('ends with one error naming the exit code, and says where the rest of it is', async () => {
    const { startRun, liveRuns } = await load('crash')
    const events = await collect(startRun({ message: 'hello' }))
    const last = events[events.length - 1]
    expect(last.kind).toBe('error')
    expect(last.kind === 'error' && last.message).toBe('claude stopped without a reply (exit code 2). The server log has the details.')
    expect(liveRuns()).toBe(0)
  })

  it('sends the page the reason and the log what the program printed', async () => {
    // A real crash printed the path of node's copy of the CLI and a value out of
    // the environment. Neither is a page's to read; both belong in the log.
    const { startRun } = await load('leaky')
    const events = await collect(startRun({ message: 'hello' }))
    const said = events.map((e) => (e.kind === 'error' ? e.message : '')).join(' ')
    expect(said).toMatch(/exit code 7/)
    expect(said).not.toMatch(/cli\.js|\/opt\/homebrew|hunter2|TOKEN/)
    const logged = logs.mock.calls.map((call) => String(call[0])).join('\n')
    expect(logged).toMatch(/cli\.js/)
    expect(logged).toMatch(/TOKEN=hunter2/)
  })

  it('keeps only the tail of a program that floods its error output, in the log', async () => {
    const { startRun } = await load('stderrflood')
    const events = await collect(startRun({ message: 'hello' }))
    const last = events[events.length - 1]
    expect(last.kind === 'error' && last.message).toMatch(/exit code 3/)
    const logged = logs.mock.calls.map((call) => String(call[0])).join('\n')
    expect(logged).toMatch(/the last words/)
    // Ten thousand characters were written; a little over four thousand is kept.
    expect(logged.length).toBeLessThan(4_500)
  })

  it('ends with one error when the binary is not there, and starts nothing', async () => {
    const { startRun, liveRuns } = await load('ok', { PFC_CLAUDE: join(dir, 'no-such-binary') })
    const events = await collect(startRun({ message: 'hello' }))
    expect(events.length).toBe(1)
    expect(events[0].kind === 'error' && events[0].message).toBe('Could not start claude. The server log has the details.')
    // Neither the path of a binary outside the repo nor the name of the setting
    // that points at it is the browser's to read.
    expect(events[0].kind === 'error' && events[0].message).not.toMatch(/no-such-binary|ENOENT|PFC_CLAUDE/)
    expect(logs.mock.calls.map((call) => String(call[0])).join('\n')).toMatch(/no-such-binary/)
    expect(liveRuns()).toBe(0)
  })
})

describe('stopping', () => {
  it('ends the run and the child when the person stops it', async () => {
    const { startRun, runPid, liveRuns } = await load('hang')
    const run = startRun({ message: 'hello' })
    const pid = runPid(run.id) as number
    expect(pid).toBeGreaterThan(0)
    const events: ChatEvent[] = []
    const reading = (async () => {
      for await (const { event } of run.read(0)) events.push(event)
    })()
    await until(() => events.length > 0)
    run.stop()
    await reading
    expect(events[0].kind).toBe('session')
    expect(liveRuns()).toBe(0)
    expect(await until(() => gone(pid))).toBe(true)
  })

  it('ends the run through stopRun, which is what the stop endpoint calls', async () => {
    const { startRun, stopRun, liveRuns } = await load('hang')
    const run = startRun({ message: 'hello' })
    const reading = collect(run)
    await until(() => liveRuns() === 1)
    expect(stopRun(run.id)).toBe(true)
    await reading
    expect(stopRun(run.id)).toBe(false)
    expect(liveRuns()).toBe(0)
  })

  it('keeps the child running when a reader walks away, which is a person moving to another page', async () => {
    const { startRun, runPid, liveRuns, stopRun } = await load('hang')
    const run = startRun({ message: 'hello' })
    const pid = runPid(run.id) as number
    // One event, then the reader leaves, exactly as a page that navigates does.
    for await (const read of run.read(0)) {
      void read
      break
    }
    await new Promise((r) => setTimeout(r, 200))
    expect(liveRuns()).toBe(1)
    expect(gone(pid)).toBe(false)
    expect(stopRun(run.id)).toBe(true)
    expect(await until(() => gone(pid))).toBe(true)
  })

  it('kills a child that will not leave on its own, and still ends the run', async () => {
    const { startRun, runPid, liveRuns } = await load('stubborn', { PFC_CHAT_KILL_MS: '200' })
    const run = startRun({ message: 'hello' })
    const pid = runPid(run.id) as number
    const reading = collect(run)
    await until(() => liveRuns() === 1)
    run.stop()
    await reading
    expect(liveRuns()).toBe(0)
    expect(await until(() => gone(pid))).toBe(true)
  })

  it('ends with the timeout error when the run outlives its time, and the child is gone', async () => {
    const { startRun, runPid, liveRuns } = await load('hang', { PFC_CHAT_TIMEOUT_MS: '300' })
    const run = startRun({ message: 'hello' })
    const pid = runPid(run.id) as number
    const events = await collect(run)
    const last = events[events.length - 1]
    expect(last.kind === 'error' && last.message).toMatch(/Stopped after 0\.3 seconds\./)
    expect(liveRuns()).toBe(0)
    expect(await until(() => gone(pid))).toBe(true)
  })
})

describe('the timers a run sets', () => {
  const timers = () => process.getActiveResourcesInfo().filter((kind) => kind === 'Timeout').length

  it('leaves none behind when the run ends, so nothing holds the process open', async () => {
    // The kill timer and the timeout timer are deliberately not unref'd: they are
    // the last thing standing between a child that ignores SIGTERM and a process
    // nobody stops. That only works if every path that ends a run clears them.
    const { startRun, liveRuns } = await load('crash', { PFC_CHAT_TIMEOUT_MS: '300000', PFC_CHAT_KILL_MS: '300000' })
    const before = timers()
    await collect(startRun({ message: 'hello' }))
    expect(liveRuns()).toBe(0)
    expect(timers()).toBeLessThanOrEqual(before)
  })

  it('leaves none behind when the person stops the run', async () => {
    const { startRun, liveRuns } = await load('hang', { PFC_CHAT_TIMEOUT_MS: '300000', PFC_CHAT_KILL_MS: '300000' })
    const before = timers()
    const run = startRun({ message: 'hello' })
    const reading = collect(run)
    await until(() => liveRuns() === 1)
    run.stop()
    await reading
    expect(timers()).toBeLessThanOrEqual(before)
  })
})

describe('what one server will run at once', () => {
  it('refuses a fourth run and keeps the three it has', async () => {
    const { startRun, stopRun, liveRuns, TooManyRuns } = await load('hang')
    const live = [startRun({ message: 'a' }), startRun({ message: 'b' }), startRun({ message: 'c' })]
    const reading = live.map((run) => collect(run))
    expect(liveRuns()).toBe(3)
    expect(() => startRun({ message: 'd' })).toThrow(TooManyRuns)
    for (const run of live) stopRun(run.id)
    await Promise.all(reading)
    expect(liveRuns()).toBe(0)
  })

  it('knows which conversation a run belongs to, so a second message to it can wait', async () => {
    const session = '00000000-0000-4000-8000-000000000000'
    const { startRun, stopRun, runningForSession } = await load('hang')
    expect(runningForSession(session)).toBe(false)
    const run = startRun({ message: 'hello', sessionId: session })
    const reading = collect(run)
    expect(runningForSession(session)).toBe(true)
    expect(runningForSession('11111111-1111-4111-8111-111111111111')).toBe(false)
    stopRun(run.id)
    await reading
    expect(runningForSession(session)).toBe(false)
  })

  it('knows the conversation of a run that started a new one, once the stream names it', async () => {
    const { startRun, runningForSession } = await load('ok')
    const run = startRun({ message: 'hello' })
    const events: ChatEvent[] = []
    const reading = (async () => {
      for await (const { event } of run.read(0)) {
        events.push(event)
        if (event.kind === 'session') expect(runningForSession(event.id)).toBe(true)
      }
    })()
    await reading
    expect(events.some((e) => e.kind === 'session')).toBe(true)
  })
})

describe('reading the output', () => {
  it('keeps a character whole when the pipe splits it between two chunks', async () => {
    const { readLines } = await load('ok')
    const lines: string[] = []
    const reader = readLines((line) => lines.push(line), () => lines.push('DROPPED'))
    const bytes = Buffer.from('{"a":"em dash — here"}\n', 'utf8')
    // The em dash is three bytes; this cut lands in the middle of it.
    const cut = bytes.indexOf(0xe2) + 1
    reader.write(bytes.subarray(0, cut))
    reader.write(bytes.subarray(cut))
    reader.end()
    expect(lines).toEqual(['{"a":"em dash — here"}'])
  })

  it('holds a partial line until the rest of it arrives, and flushes a last line with no newline', async () => {
    const { readLines } = await load('ok')
    const lines: string[] = []
    const reader = readLines((line) => lines.push(line), () => lines.push('DROPPED'))
    reader.write(Buffer.from('{"one":1}\n{"two"'))
    expect(lines).toEqual(['{"one":1}'])
    reader.write(Buffer.from(':2}\n{"three":3}'))
    expect(lines).toEqual(['{"one":1}', '{"two":2}'])
    reader.end()
    expect(lines).toEqual(['{"one":1}', '{"two":2}', '{"three":3}'])
  })

  it('keeps at most five thousand events in a run, dropping only text past that, even for a reader that keeps up', async () => {
    const { startRun, liveRuns } = await load('flood')
    const run = startRun({ message: 'hello' })
    // Read as it arrives: the cap is on what the run keeps for every reader, not on
    // how far one reader has fallen behind, because a page may come back for all of it.
    const events = await collect(run)
    const text = events.filter((e) => e.kind === 'text')
    const dropped = events.filter((e) => e.kind === 'error')
    expect(text.length).toBeLessThanOrEqual(5_000)
    expect(text.length).toBeGreaterThan(4_000)
    // Said once, however many were dropped.
    expect(dropped.length).toBe(1)
    expect(dropped[0].kind === 'error' && dropped[0].message)
      .toBe('Some reply text was dropped because the reply was too long to keep.')
    // Everything that is not text still arrives, the reply included.
    expect(events[0].kind).toBe('session')
    expect(events[events.length - 1].kind).toBe('done')
    expect(liveRuns()).toBe(0)
    // A second reader from the start gets exactly the same, from the log.
    expect(await collect(run)).toEqual(events)
  })

  it('drops one runaway line and reads the stream after it', async () => {
    const { startRun, liveRuns } = await load('bigline')
    const events = await collect(startRun({ message: 'hello' }))
    const dropped = events.filter((e) => e.kind === 'error')
    expect(dropped.length).toBe(1)
    expect(dropped[0].kind === 'error' && dropped[0].message).toMatch(/too long/)
    // The stream after the runaway line still reads, ending in the result.
    expect(events[events.length - 1].kind).toBe('done')
    expect(liveRuns()).toBe(0)
  })
})

describe('a run outlives its readers', () => {
  it('numbers every event in order, starting at zero', async () => {
    const { startRun } = await load('ok')
    const run = startRun({ message: 'hello' })
    const seqs: number[] = []
    for await (const { seq } of run.read(0)) seqs.push(seq)
    expect(seqs).toEqual(seqs.map((_, i) => i))
    expect(seqs.length).toBe(6)
  })

  it('gives two readers at once the same events, and a late reader the tail from the index it names', async () => {
    const { startRun } = await load('ok')
    const run = startRun({ message: 'hello' })
    const [a, b] = await Promise.all([collect(run), collect(run)])
    expect(b).toEqual(a)
    const tail: { seq: number; event: ChatEvent }[] = []
    for await (const read of run.read(3)) tail.push(read)
    expect(tail.map((t) => t.seq)).toEqual([3, 4, 5])
    expect(tail.map((t) => t.event)).toEqual(a.slice(3))
  })

  it('lets a reader that comes back mid-run pick up where it left off, and see the end', async () => {
    const { startRun } = await load('ok')
    const run = startRun({ message: 'hello' })
    let last = -1
    for await (const { seq } of run.read(0)) {
      last = seq
      if (seq === 1) break
    }
    const rest = await collect(run, last + 1)
    expect(rest[0]?.kind).toBe('tool')
    expect(rest[rest.length - 1]?.kind).toBe('done')
  })

  it('keeps a finished run reachable by id for the grace period, counted as live by nothing', async () => {
    const session = '00000000-0000-4000-8000-000000000000'
    const { startRun, getRun, liveRuns, runningForSession, stopRun } = await load('ok', { PFC_CHAT_KEEP_MS: '300' })
    const run = startRun({ message: 'hello' })
    const events = await collect(run)
    expect(run.over()).toBe(true)
    expect(liveRuns()).toBe(0)
    expect(runningForSession(session)).toBe(false)
    // There is nothing left to stop.
    expect(stopRun(run.id)).toBe(false)
    const kept = getRun(run.id)
    expect(kept?.id).toBe(run.id)
    expect(await collect(kept as Run, 4)).toEqual(events.slice(4))
    expect(await until(() => getRun(run.id) === undefined, 2_000)).toBe(true)
  })

  it('finds a live run by id, and nothing for an id it never started', async () => {
    const { startRun, getRun, stopRun } = await load('hang')
    const run = startRun({ message: 'hello' })
    expect(getRun(run.id)).toBe(run)
    expect(getRun('no-such-run')).toBeUndefined()
    const reading = collect(run)
    stopRun(run.id)
    await reading
  })

  it('does not count a finished run against the cap of three', async () => {
    const { startRun, stopRun, liveRuns } = await load('crash', { PFC_CHAT_KEEP_MS: '60000' })
    for (let n = 0; n < 4; n++) await collect(startRun({ message: String(n) }))
    expect(liveRuns()).toBe(0)
    const more = startRun({ message: 'still room' })
    const reading = collect(more)
    stopRun(more.id)
    await reading
  })
})
