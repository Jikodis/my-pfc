/**
 * runWrite, the one function that starts the writer. The writer here is always the
 * fake script: a real one commits to a repo.
 */
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gone } from './helpers/processes'

const FAKE = fileURLToPath(new URL('./fixtures/fake_web_write.sh', import.meta.url))
const FAKE_PYTHON = fileURLToPath(new URL('./fixtures/fake_python.sh', import.meta.url))
const FAILED = 'The change could not be saved. The server log has the details.'

let logs: MockInstance<typeof console.error>
let dir = ''

async function load(mode: string, env: Record<string, string> = {}) {
  vi.stubEnv('PFC_WEB_WRITE', FAKE)
  vi.stubEnv('FAKE_WRITE_MODE', mode)
  for (const [name, value] of Object.entries(env)) vi.stubEnv(name, value)
  vi.resetModules()
  return import('../src/lib/write')
}

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'pfc-write-'))
  logs = vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  logs.mockRestore()
  vi.unstubAllEnvs()
  vi.resetModules()
  rmSync(dir, { recursive: true, force: true })
})

describe('runWrite', () => {
  it('passes the action and arguments as argv and returns the saved result', async () => {
    const argsFile = join(dir, 'args.txt')
    const { runWrite, writeInProgress } = await load('ok', { FAKE_WRITE_ARGS_FILE: argsFile })
    const result = await runWrite('park-focus', ['focus-20260706-001', 'on'])
    expect(readFileSync(argsFile, 'utf8')).toBe('park-focus\nfocus-20260706-001\non\n')
    expect(result).toEqual({
      status: 200,
      body: {
        ok: true, message: 'Saved.', commit: 'abc1234', pushed: true, push_error: null,
        title: 'Call the dentist', email_linked: true, changed: true,
      },
    })
    expect(writeInProgress()).toBe(false)
  })

  it('reports a commit the push did not deliver', async () => {
    const { runWrite } = await load('unpushed')
    const { status, body } = await runWrite('complete-task', ['task-20260901-001'])
    expect(status).toBe(200)
    expect(body).toMatchObject({ ok: true, pushed: false, push_error: 'fatal: No configured push destination.',
      message: 'Saved. Not pushed yet.' })
  })

  it('reports nothing to change as a success that changed nothing', async () => {
    const { runWrite } = await load('unchanged')
    const { status, body } = await runWrite('complete-task', ['task-20260901-001'])
    expect(status).toBe(200)
    expect(body).toMatchObject({ ok: true, changed: false, commit: null, message: 'Already done.' })
  })

  it.each([
    ['unknown', 404, 'No open task with that id.'],
    ['refused', 422, 'That focus is retired.'],
    ['locked', 409, 'Another change is still being saved.'],
    ['invalid', 422, 'tasks.ndjson: record task-x violates schema'],
  ])('maps %s to %i with the script\'s own message', async (mode, status, message) => {
    const { runWrite } = await load(mode)
    const result = await runWrite('complete-task', ['task-20260901-001'])
    expect(result.status).toBe(status)
    expect(result.body).toEqual({
      ok: false, message, commit: null, pushed: false, push_error: null, title: '', email_linked: false, changed: false,
    })
  })

  it.each(['crash', 'junk'])('answers %s with fixed text and logs the detail', async (mode) => {
    const { runWrite, writeInProgress } = await load(mode)
    const result = await runWrite('complete-task', ['task-20260901-001'])
    expect(result.status).toBe(500)
    expect(result.body.message).toBe(FAILED)
    expect(JSON.stringify(result.body)).not.toMatch(/secret|Traceback/)
    expect(logs).toHaveBeenCalled()
    expect(String(logs.mock.calls[0]?.[0])).toMatch(/^\[pfc-write\]/)
    expect(writeInProgress()).toBe(false)
  })

  it('queues a second write while one is running and runs it after the first', async () => {
    const argsFile = join(dir, 'args.txt')
    const { runWrite, writeInProgress } = await load('slow', { FAKE_WRITE_ARGS_FILE: argsFile })
    const first = runWrite('complete-task', ['task-20260901-001'])
    expect(writeInProgress()).toBe(true)
    const second = runWrite('drop-task', ['task-20260901-002'])
    expect((await first).status).toBe(200)
    // The first has finished and the second has not started yet or is running now.
    expect(writeInProgress()).toBe(true)
    expect((await second).status).toBe(200)
    expect(readFileSync(argsFile, 'utf8')).toBe('drop-task\ntask-20260901-002\n')
    expect(writeInProgress()).toBe(false)
  }, 15_000)

  it('refuses a write past the queue limit and starts nothing for it', async () => {
    const { runWrite, writeInProgress, MAX_PENDING, QUEUE_FULL } = await load('ok')
    const accepted = Array.from({ length: MAX_PENDING }, () => runWrite('complete-task', ['task-20260901-001']))
    const refused = await runWrite('complete-task', ['task-20260901-001'])
    expect(refused.status).toBe(409)
    expect(refused.body.message).toBe(QUEUE_FULL)
    expect((await Promise.all(accepted)).every((r) => r.status === 200)).toBe(true)
    expect(writeInProgress()).toBe(false)
  }, 30_000)

  it('stops a writer that runs past the timeout and frees the gate', async () => {
    const { runWrite, writeInProgress } = await load('slow', { PFC_WRITE_TIMEOUT_MS: '300' })
    const started = Date.now()
    const result = await runWrite('complete-task', ['task-20260901-001'])
    expect(Date.now() - started).toBeLessThan(2_500)
    expect(result.status).toBe(500)
    expect(result.body.message).toBe(FAILED)
    expect(String(logs.mock.calls[0]?.[0])).toMatch(/timed out/)
    expect(writeInProgress()).toBe(false)
  })

  it('reports a commit that outlived its push when the timeout stops the writer', async () => {
    const { runWrite, writeInProgress } = await load('late', { PFC_WRITE_TIMEOUT_MS: '300' })
    const { status, body } = await runWrite('complete-task', ['task-20260901-001'])
    expect(status).toBe(200)
    expect(body).toMatchObject({ ok: true, changed: true, commit: 'abc1234', pushed: false,
      push_error: 'The push timed out; the commit is saved and will push next time.', message: 'Saved. Not pushed yet.' })
    expect(String(logs.mock.calls[0]?.[0])).toMatch(/timed out/)
    expect(writeInProgress()).toBe(false)
  })

  it('waits two minutes for a writer by default', async () => {
    const { writeTimeoutMs } = await load('ok')
    expect(writeTimeoutMs()).toBe(120_000)
  })

  it('stops the writer and everything it started when the timeout fires', async () => {
    const pids = join(dir, 'pids.txt')
    const { runWrite, writeInProgress } = await load('stubborn', { PFC_WRITE_TIMEOUT_MS: '500', FAKE_WRITE_PIDS_FILE: pids })
    const result = await runWrite('complete-task', ['task-20260901-001'])
    expect(result.status).toBe(500)
    expect(writeInProgress()).toBe(false)
    const [leader, sleeper] = readFileSync(pids, 'utf8').trim().split(' ').map(Number)
    expect(await gone(leader)).toBe(true)
    expect(await gone(sleeper)).toBe(true)
  })

  it('answers 409 with the message when the repo is on another branch', async () => {
    const { runWrite } = await load('branch')
    const result = await runWrite('complete-task', ['task-20260901-001'])
    expect(result.status).toBe(409)
    expect(result.body.message).toBe('The repo is on branch feature, not main; nothing was changed.')
  })

  it('answers 409 with the message when the pre-commit hook is not installed', async () => {
    const { runWrite } = await load('nohook')
    const result = await runWrite('complete-task', ['task-20260901-001'])
    expect(result.status).toBe(409)
    expect(result.body.message).toBe("The repo's pre-commit hook is not installed; see docs/install/web-ui.md.")
  })

  it('runs a .py writer with PFC_PYTHON, the script first and the action after it', async () => {
    // A stand-in interpreter that reports what it was handed as the title.
    const python = join(dir, 'python.sh')
    writeFileSync(python, '#!/bin/sh\nprintf \'{"ok": true, "title": "%s", "changed": false, "message": "x"}\\n\' "$*"\n')
    chmodSync(python, 0o755)
    const script = join(dir, 'web_write.py')
    const { runWrite } = await load('ok', { PFC_WEB_WRITE: script, PFC_PYTHON: python })
    const result = await runWrite('complete-task', ['task-20260901-001'])
    expect(result.status).toBe(200)
    expect(result.body.title).toBe(`${script} complete-task task-20260901-001`)
  })

  it('treats an exit 0 without ok: true as a failure', async () => {
    const { runWrite } = await load('ok', { PFC_WEB_WRITE: join(dir, 'web_write.py'), PFC_PYTHON: FAKE_PYTHON })
    const result = await runWrite('complete-task', ['task-20260901-001'])
    expect(result.status).toBe(500)
    expect(result.body.message).toBe(FAILED)
  })

  it('answers 500 when the writer cannot be started', async () => {
    const { runWrite, writeInProgress } = await load('ok', { PFC_WEB_WRITE: join(dir, 'missing.sh') })
    const result = await runWrite('complete-task', ['task-20260901-001'])
    expect(result.status).toBe(500)
    expect(result.body.message).toBe(FAILED)
    expect(writeInProgress()).toBe(false)
  })
})
