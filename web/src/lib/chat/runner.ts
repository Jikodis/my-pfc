/**
 * One `claude -p` process, read as a stream of events.
 *
 * This is the module that starts a program able to edit and commit in this repo, so
 * the shape of it matters more than its length:
 *
 * - The command is an argv array handed to `spawn`. No shell, ever, so a message is
 *   a message and never a command. `buildArgs` puts it last, after `--`.
 * - stdin is closed. The child cannot ask this server anything, which is the same
 *   reason `--permission-prompts none` is always passed.
 * - Every run is registered while it is live and removed when it ends, so the server
 *   knows what it is running, can stop any of it, and can refuse a fourth.
 * - A run outlives any one reader. Every event goes into the run's own log, in
 *   order, and any number of readers read that log from the index they name, so a
 *   page that moves to another page and comes back picks the reply up where it left
 *   it. A reader walking away stops nothing: only the stop route, the timeout, and
 *   this server exiting end the child.
 * - A finished run is kept, log and all, for a grace period after it ends, so a
 *   page that comes back late still gets the tail and the final event. Then it is
 *   forgotten. A kept run counts toward nothing: not the cap, not "a reply is still
 *   in progress".
 * - Every path ends every reader: a clean exit, a crash, a stop, the timeout, and a
 *   binary that is not there. A run that ends without ending its readers is a
 *   browser tab that waits forever.
 * - When this server exits, its children go with it. An orphaned `claude` keeps
 *   working in the repo with nobody watching it.
 * - What the child printed goes to the server log, never to the browser. Its output
 *   holds absolute paths and whatever the environment gave it, and a crash once
 *   delivered a node path and a token from the environment straight into a page.
 */
import { spawn, type ChildProcess } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { StringDecoder } from 'node:string_decoder'
import { REPO } from '../repo'
import { buildArgs, type ArgOptions } from './args'
import { parseLine, type ChatEvent } from './events'
import { rememberSession } from './sessions'

/** Set PFC_CLAUDE when the claude command is not on the server's PATH. */
const BIN = process.env.PFC_CLAUDE || 'claude'

/** Long enough for a real piece of work, short of a process nobody remembers starting. */
const TIMEOUT_MS = Number(process.env.PFC_CHAT_TIMEOUT_MS) || 30 * 60 * 1000

/** How long a stopped process gets to leave on its own before it is killed. */
const KILL_AFTER_MS = Number(process.env.PFC_CHAT_KILL_MS) || 5_000

/**
 * How long the output is drained after the process is gone.
 *
 * Normally the pipe ends in the same breath as the process. It does not when the
 * child left a program of its own holding that pipe, and a run whose end waits on
 * a pipe nobody will close is a browser tab that waits forever.
 */
const DRAIN_MS = 500

/** Live runs across the whole server. */
const MAX_RUNS = 3

/** One line of stream JSON. Past this the line is dropped rather than held in memory. */
const LINE_LIMIT = 1_000_000

/** How much stderr is kept for a run that fails. It goes to the log, never to a page. */
const STDERR_KEEP = 4_096

/**
 * Events kept in one run's log.
 *
 * Past this only the text is dropped, because text arrives a few characters at a
 * time and is the only kind that can pile up in the thousands. Every tool call, its
 * result, the session line, the reply, and every error still arrive. The cap is on
 * the log rather than on how far one reader has fallen behind, because the log is
 * kept whole for any page that comes back for it.
 */
const BUFFER_LIMIT = 5_000

/**
 * How long a finished run stays reachable by id. Long enough for a person to click
 * through a page or two and come back; overridable so a test does not wait ten minutes.
 */
const KEEP_MS = Number(process.env.PFC_CHAT_KEEP_MS) || 10 * 60 * 1000

export class TooManyRuns extends Error {}

/** What a page is told when the command will not start. The why is in the log. */
const CANNOT_START = 'Could not start claude. The server log has the details.'

/** One event out of a run's log, with its place in that log. The first event is 0. */
export type Logged = { seq: number; event: ChatEvent }

export type Run = {
  id: string
  /**
   * The run's events from index `from` on: what is already in the log at once, then
   * each new one as it arrives, ending when the run is over and the log is read out.
   * Any number of readers may read at once, and one that stops reading stops nothing.
   */
  read(from: number): AsyncIterable<Logged>
  stop(): void
  /**
   * Whether the run is over: the process has gone and nothing more will be added.
   * What is already in the log can still be read.
   */
  over(): boolean
}

type LiveRun = {
  id: string
  /** The conversation this run belongs to, known at the start of a resume and at `init` otherwise. */
  sessionId?: string
  /** Set once the child exists, so a caller can see whether it is really gone. */
  pid?: number
  handle: Run
  stop(): void
  kill(): void
}

/** Runs whose process is still going. Only these count toward the cap and the 409. */
const runs = new Map<string, LiveRun>()

/** Runs that have ended, kept for `KEEP_MS` so a page that comes back gets the end. */
const finished = new Map<string, Run>()

export const liveRuns = (): number => runs.size

/** The ids of the live runs, so a test can stop what it started. */
export const liveRunIds = (): string[] => [...runs.keys()]

/** A run by id, live or finished within the grace period, or nothing. */
export function getRun(id: string): Run | undefined {
  return runs.get(id)?.handle ?? finished.get(id)
}

/** Whether a reply is already being written into that conversation. */
export function runningForSession(sessionId: string): boolean {
  for (const run of runs.values()) {
    if (run.sessionId === sessionId) return true
  }
  return false
}

/** The process id of a live run. A run that has ended has none, because it is gone. */
export function runPid(id: string): number | undefined {
  return runs.get(id)?.pid
}

export function stopRun(id: string): boolean {
  const run = runs.get(id)
  if (!run) return false
  run.stop()
  return true
}

/**
 * What a failure really was, for the server log.
 *
 * Under the launch agent this lands in /tmp/pfc-web.log. The browser gets the
 * reason and a pointer to here, because the child's own output carries absolute
 * paths and values out of the environment.
 */
function logDetail(runId: string, detail: string): void {
  console.error(`[pfc-chat] run ${runId}: ${detail}`)
}

type LineReader = {
  write(chunk: Buffer): void
  /** Flush what is left, which is the last line when the program wrote no final newline. */
  end(): void
}

/**
 * Bytes to whole lines.
 *
 * The decoder is kept across chunks on purpose: a chunk boundary falls wherever the
 * pipe decides, including the middle of a character, and decoding each chunk on its
 * own turns one em dash into two replacement characters. An overlong line is dropped
 * to its end rather than buffered, so one runaway line cannot take the server's memory.
 */
export function readLines(onLine: (line: string) => void, onTooLong: () => void): LineReader {
  const decoder = new StringDecoder('utf8')
  let pending = ''
  let dropping = false

  const take = (text: string) => {
    let start = 0
    for (;;) {
      const nl = text.indexOf('\n', start)
      if (nl === -1) break
      const line = pending + text.slice(start, nl)
      pending = ''
      start = nl + 1
      if (dropping) dropping = false
      else onLine(line)
    }
    pending += text.slice(start)
    if (pending.length > LINE_LIMIT) {
      pending = ''
      if (!dropping) {
        dropping = true
        onTooLong()
      }
    }
  }

  return {
    write: (chunk) => take(decoder.write(chunk)),
    end: () => {
      take(decoder.end())
      if (pending && !dropping) onLine(pending)
      pending = ''
      dropping = false
    },
  }
}

/** `30 minutes` for the real timeout, `0.3 seconds` for the short one a test sets. */
function spell(ms: number): string {
  return ms >= 60_000 ? `${Math.round(ms / 60_000)} minutes` : `${ms / 1000} seconds`
}

export function startRun(o: ArgOptions): Run {
  if (runs.size >= MAX_RUNS) {
    throw new TooManyRuns(`${MAX_RUNS} replies are already being written.`)
  }

  const id = randomUUID()
  const log: ChatEvent[] = []
  let ended = false
  /** Every reader waiting for the next event. Each is woken once and then forgotten. */
  const waiting = new Set<() => void>()
  let saidDropped = false

  const wakeUp = () => {
    const all = [...waiting]
    waiting.clear()
    for (const w of all) w()
  }

  const emit = (event: ChatEvent) => {
    if (log.length >= BUFFER_LIMIT && event.kind === 'text') {
      // Said once per run, and it is the last thing added rather than the first, so
      // it sits in the transcript where the missing words would have been.
      if (saidDropped) return
      saidDropped = true
      log.push({ kind: 'error', message: 'Some reply text was dropped because the reply was too long to keep.' })
      wakeUp()
      return
    }
    log.push(event)
    wakeUp()
  }

  const read = (from: number): AsyncIterable<Logged> => ({
    async *[Symbol.asyncIterator]() {
      let at = Math.max(0, Math.floor(from) || 0)
      for (;;) {
        while (at < log.length) {
          const seq = at
          at += 1
          yield { seq, event: log[seq] as ChatEvent }
        }
        if (ended) return
        await new Promise<void>((resolve) => {
          waiting.add(resolve)
        })
      }
    },
  })

  const handle: Run = { id, read, stop: () => stop('person'), over: () => ended }

  /** The run is over: off the live list, kept for the grace period, then forgotten. */
  const keep = () => {
    runs.delete(id)
    finished.set(id, handle)
    // Unref'd: forgetting a finished run is housekeeping, and must never be what
    // holds the server or a test process open.
    setTimeout(() => {
      if (finished.get(id) === handle) finished.delete(id)
    }, KEEP_MS).unref()
  }

  const finish = () => {
    if (ended) return
    ended = true
    keep()
    wakeUp()
  }

  let child: ChildProcess | null = null
  let closed = false
  let sawResult = false
  let failedToStart = false
  let stopped: 'person' | 'timeout' | null = null
  let stderrTail = ''
  let killTimer: NodeJS.Timeout | null = null
  let timeoutTimer: NodeJS.Timeout | null = null

  let drainTimer: NodeJS.Timeout | null = null

  const clearTimers = () => {
    if (killTimer) clearTimeout(killTimer)
    if (timeoutTimer) clearTimeout(timeoutTimer)
    if (drainTimer) clearTimeout(drainTimer)
    killTimer = null
    timeoutTimer = null
    drainTimer = null
  }

  const alive = () => child !== null && child.exitCode === null && child.signalCode === null

  const kill = () => {
    if (alive()) child?.kill('SIGKILL')
  }

  const stop = (why: 'person' | 'timeout') => {
    stopped ??= why
    if (!alive() || killTimer) return
    child?.kill('SIGTERM')
    // Not unref'd: this timer is the last thing standing between a child that
    // ignores SIGTERM and a process nobody stops. Every path that ends a run clears it.
    killTimer = setTimeout(kill, KILL_AFTER_MS)
  }

  const entry: LiveRun = { id, sessionId: o.sessionId, handle, stop: () => stop('person'), kill }
  runs.set(id, entry)

  const out = readLines(
    (line) => {
      for (const event of parseLine(line)) {
        if (event.kind === 'session' && event.id) {
          entry.sessionId = event.id
          rememberSession(event.id)
        }
        if (event.kind === 'done') sawResult = true
        emit(event)
      }
    },
    () => emit({ kind: 'error', message: 'A line of output was too long to read, so it was dropped.' }),
  )

  const close = (code: number | null, signal: NodeJS.Signals | null) => {
    if (closed) return
    closed = true
    clearTimers()
    out.end()
    if (!sawResult && !stopped && !failedToStart) {
      const how = code === null ? `signal ${signal}` : `exit code ${code}`
      logDetail(id, `claude stopped without a reply (${how}). Its error output was: ${stderrTail.trim() || '(nothing)'}`)
      emit({ kind: 'error', message: `claude stopped without a reply (${how}). The server log has the details.` })
    }
    finish()
  }

  try {
    child = spawn(BIN, buildArgs(o), {
      cwd: REPO,
      // Nothing to read: the child never asks this server a question, and a prompt
      // it cannot ask is a prompt nobody has to answer.
      stdio: ['ignore', 'pipe', 'pipe'],
      // PFC_WEB_CHAT tells a skill it was started from this page, so one that ends
      // by opening the web UI does not open a second copy.
      env: { ...process.env, PFC_WEB_CHAT: '1' },
      // Part of this server's process group, so it cannot outlive it unnoticed.
      detached: false,
    })
  } catch (err) {
    // The real message names the binary's path, which is not the browser's to see.
    logDetail(id, `could not start claude: ${(err as Error).message}`)
    emit({ kind: 'error', message: CANNOT_START })
    finish()
    return handle
  }

  entry.pid = child.pid

  child.on('error', (err) => {
    failedToStart = true
    logDetail(id, `could not start claude: ${err.message}`)
    emit({ kind: 'error', message: CANNOT_START })
    close(null, null)
  })
  let outEnded = false
  child.stdout?.on('data', (chunk: Buffer) => out.write(chunk))
  child.stdout?.on('end', () => {
    outEnded = true
  })

  const errDecoder = new StringDecoder('utf8')
  child.stderr?.on('data', (chunk: Buffer) => {
    stderrTail = (stderrTail + errDecoder.write(chunk)).slice(-STDERR_KEEP)
  })

  // The process leaving is what ends the run. The last of its output is normally
  // already read by then; when it is not, the output gets a short moment and the run
  // ends either way, because a pipe a leftover program holds open would never close.
  child.on('exit', (code, signal) => {
    if (outEnded) close(code, signal)
    else drainTimer = setTimeout(() => close(code, signal), DRAIN_MS)
  })
  child.on('close', (code, signal) => close(code, signal))

  // Not unref'd, for the same reason as the kill timer: it is what ends a run that
  // would otherwise sit there. `close` clears it on every path that ends a run.
  timeoutTimer = setTimeout(() => {
    emit({ kind: 'error', message: `Stopped after ${spell(TIMEOUT_MS)}.` })
    stop('timeout')
  }, TIMEOUT_MS)

  return handle
}

/**
 * Children never outlive the server.
 *
 * Registered once for the process, with each loaded copy of this module adding its
 * own runs to the list, because a test suite loads this module many times and a
 * listener for each load would pass Node's warning threshold.
 */
const KILLERS = Symbol.for('pfc.chat.runner.killers')
type WithKillers = typeof globalThis & { [KILLERS]?: (() => void)[] }
const root = globalThis as WithKillers

if (!root[KILLERS]) {
  const killers: (() => void)[] = []
  root[KILLERS] = killers
  const killEverything = () => {
    for (const killer of killers) killer()
  }
  process.on('exit', killEverything)
  for (const signal of ['SIGINT', 'SIGTERM'] as const) {
    const onSignal = () => {
      killEverything()
      // Hand the signal back to whatever would have happened without this listener.
      process.removeListener(signal, onSignal)
      process.kill(process.pid, signal)
    }
    process.on(signal, onSignal)
  }
}

root[KILLERS].push(() => {
  for (const run of runs.values()) run.kill()
})
