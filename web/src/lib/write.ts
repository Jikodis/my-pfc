/**
 * The web UI's one way to change the repo: start `automations/scripts/web_write.py`
 * and read the one JSON object it prints.
 *
 * Nothing here decides anything about a record. The script takes its own lock,
 * changes the files through `pfc_writes.py`, commits (the pre-commit hook runs the
 * validator), and pushes; this
 * module starts it with an argv array (no shell) in the repo, stops it after two
 * minutes, runs one at a time server-wide (a write that arrives while another runs
 * waits its turn, up to MAX_PENDING), and turns its exit code into an HTTP status.
 * The writer leads a process group of its own, and a timeout sends that
 * group SIGTERM; the writer passes it on to git and the hooks it started, which run
 * in sessions of their own, then SIGKILL follows. What the browser is told is the
 * script's own message or a fixed sentence; any other detail goes to the server log
 * on a `[pfc-write]` line.
 */
import { spawn } from 'node:child_process'
import { join } from 'node:path'
import { REPO } from './repo'

export type WriteAction =
  | 'complete-task' | 'drop-task' | 'log-habit' | 'park-focus'
  | 'rate-day' | 'set-picks' | 'stamp-review'
  | 'skip-suggestion' | 'set-area' | 'set-room' | 'retire-anchor' | 'set-project'

/** What every write route answers with, success or not. */
export type WriteBody = {
  ok: boolean
  message: string
  commit: string | null
  pushed: boolean
  push_error: string | null
  title: string
  email_linked: boolean
  changed: boolean
}
export type WriteResult = { status: number; body: WriteBody }

export const BUSY = 'Another change is still being saved.'
export const QUEUE_FULL = 'Too many changes are waiting to be saved. Try again in a minute.'

/** Writes waiting or running at once. Clicking down a list queues each one; past this many the next is refused. */
export const MAX_PENDING = 20
export const FAILED = 'The change could not be saved. The server log has the details.'

/** Above a validator run, a commit, and a push; the Trello render runs after the writer returns. */
const DEFAULT_TIMEOUT_MS = 120_000
/** Five seconds after SIGTERM, whatever is left of the writer's process group gets SIGKILL. */
const KILL_GRACE_MS = 5_000
/** After a timeout, how long the exit waits for the writer's last output. */
const EXIT_READ_MS = 500
/** More output than the script ever prints; past it the rest is dropped. */
const OUTPUT_CAP = 64 * 1024

/** Writes accepted and not finished yet, the running one included. */
let pending = 0
/** The end of the line: each write starts when the one before it has finished. */
let tail: Promise<unknown> = Promise.resolve()

/** True while a write is running or waiting its turn. Tests end on false. */
export const writeInProgress = (): boolean => pending > 0

export function failure(status: number, message: string): WriteResult {
  return {
    status,
    body: { ok: false, message, commit: null, pushed: false, push_error: null, title: '', email_linked: false, changed: false },
  }
}

/**
 * Which program to start. The real writer is a Python script run by PFC_PYTHON.
 * PFC_WEB_WRITE names another writer for tests; one that does not end in `.py` is
 * started as it is, the way PFC_CLAUDE names a fake binary.
 */
function command(action: WriteAction, args: string[]): [string, string[]] {
  const script = process.env.PFC_WEB_WRITE || join(REPO, 'automations/scripts/web_write.py')
  if (!script.endsWith('.py')) return [script, [action, ...args]]
  return [process.env.PFC_PYTHON || 'python3', [script, action, ...args]]
}

export function writeTimeoutMs(): number {
  const named = Number(process.env.PFC_WRITE_TIMEOUT_MS)
  return Number.isFinite(named) && named > 0 ? named : DEFAULT_TIMEOUT_MS
}

type Exit = { code: number | null; signal: NodeJS.Signals | null; stdout: string; stderr: string; timedOut: boolean; error?: Error }

function start(action: WriteAction, args: string[]): Promise<Exit> {
  return new Promise((resolve) => {
    const [program, argv] = command(action, args)
    let stdout = ''
    let stderr = ''
    let timedOut = false
    let settled = false
    // detached: the writer leads its own process group, and the timeout signals that group.
    // web_write.py starts git and its hooks in sessions of their own, which this signal
    // does not reach; the writer's SIGTERM handler passes it on to them and waits.
    const child = spawn(program, argv, { cwd: REPO, stdio: ['ignore', 'pipe', 'pipe'], detached: true })
    const signalGroup = (signal: NodeJS.Signals) => {
      try {
        if (child.pid) process.kill(-child.pid, signal)
      } catch {
        // The group is already gone.
      }
    }
    const keep = (text: string, chunk: Buffer) => (text.length < OUTPUT_CAP ? text + chunk.toString('utf8') : text)
    child.stdout.on('data', (chunk: Buffer) => { stdout = keep(stdout, chunk) })
    child.stderr.on('data', (chunk: Buffer) => { stderr = keep(stderr, chunk) })

    const timer = setTimeout(() => {
      timedOut = true
      signalGroup('SIGTERM')
      // Kept after the writer exits: a child that ignored SIGTERM still gets SIGKILL.
      setTimeout(() => signalGroup('SIGKILL'), KILL_GRACE_MS).unref()
    }, writeTimeoutMs())

    const finish = (exit: Omit<Exit, 'stdout' | 'stderr' | 'timedOut'>) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve({ ...exit, stdout, stderr, timedOut })
    }
    child.on('error', (error) => finish({ code: null, signal: null, error }))
    child.on('close', (code, signal) => finish({ code, signal }))
    // A stopped writer can leave a child of its own holding the output pipes open,
    // and 'close' waits for those. After a timeout the exit is enough, a moment
    // later, so the line a writer prints on its way out (a saved commit whose push
    // was cut short) is read first.
    child.on('exit', (code, signal) => {
      if (timedOut) setTimeout(() => finish({ code, signal }), EXIT_READ_MS).unref()
    })
  })
}

function parse(stdout: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(stdout.trim())
    return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null
  } catch {
    return null
  }
}

const text = (value: unknown, fallback: string): string => (typeof value === 'string' && value ? value : fallback)

function logFailure(action: WriteAction, why: string, exit: Exit): void {
  const tail = (exit.stderr || exit.stdout).trim().slice(-2_000)
  console.error(`[pfc-write] ${action} ${why}${tail ? `: ${tail}` : ''}`)
}

/** Exit 2 carries a reason: a bad request, a record that is not there, or a change the record refuses. */
function refusedStatus(reason: unknown): number {
  if (reason === 'not_found') return 404
  if (reason === 'bad_request') return 400
  return 422
}

function toResult(action: WriteAction, exit: Exit): WriteResult {
  if (exit.error) {
    logFailure(action, `could not start: ${exit.error.message}`, exit)
    return failure(500, FAILED)
  }
  const out = parse(exit.stdout)
  if (exit.timedOut) {
    logFailure(action, `timed out after ${writeTimeoutMs() / 1000} seconds and was stopped`, exit)
    // Stopped after its commit, the writer still reports the saved change (not pushed).
    if (!(exit.code === 0 && out?.ok === true)) return failure(500, FAILED)
  }
  if (exit.code === 0 && out?.ok === true) {
    return {
      status: 200,
      body: {
        ok: true,
        message: text(out.message, 'Saved.'),
        commit: typeof out.commit === 'string' ? out.commit : null,
        pushed: out.pushed === true,
        push_error: typeof out.push_error === 'string' ? out.push_error : null,
        title: typeof out.title === 'string' ? out.title : '',
        email_linked: out.email_linked === true,
        changed: out.changed === true,
      },
    }
  }
  const message = out && out.ok === false ? text(out.error, '') : ''
  if (message && exit.code === 2) return failure(refusedStatus(out?.reason), message)
  if (message && exit.code === 3) return failure(409, message)
  if (message && exit.code === 4) return failure(422, message)
  logFailure(action, `exited ${exit.code ?? exit.signal}`, exit)
  return failure(500, FAILED)
}

/**
 * Start the writer for one action and wait for it. A call that arrives while
 * another write runs waits in line and starts when that one has finished, so a
 * person can click Done down a list without waiting between clicks. Past
 * MAX_PENDING the call is answered at once with 409 and starts nothing.
 */
export async function runWrite(action: WriteAction, args: string[]): Promise<WriteResult> {
  if (pending >= MAX_PENDING) return failure(409, QUEUE_FULL)
  pending++
  const turn = tail.then(async () => toResult(action, await start(action, args)))
  tail = turn.catch(() => undefined)
  try {
    return await turn
  } finally {
    pending--
  }
}
