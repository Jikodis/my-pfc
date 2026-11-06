import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

/**
 * The file is named by an environment variable so these tests never touch the list
 * the running server reads, and each test gets a fresh folder of its own.
 */
let dir = ''
let file = ''

async function load() {
  vi.resetModules()
  return import('../src/lib/chat/sessions')
}

beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), 'pfc-sessions-'))
  file = join(dir, 'sessions.json')
  vi.stubEnv('PFC_CHAT_SESSIONS_FILE', file)
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.resetModules()
  rmSync(dir, { recursive: true, force: true })
})

const id = (n: number) => `0000000${n % 10}-0000-4000-8000-${String(n).padStart(12, '0')}`

describe('a conversation this server started', () => {
  it('is not owned before a run records it', async () => {
    const { ownsSession } = await load()
    expect(ownsSession(id(1))).toBe(false)
  })

  it('is owned once a run records it', async () => {
    const { ownsSession, rememberSession } = await load()
    rememberSession(id(1))
    expect(ownsSession(id(1))).toBe(true)
    expect(ownsSession(id(2))).toBe(false)
  })

  it('stays owned after the module is loaded again, which is what a server restart does', async () => {
    const first = await load()
    first.rememberSession(id(3))
    const second = await load()
    expect(second.ownsSession(id(3))).toBe(true)
  })

  it('is recorded once, however many times a run reports it', async () => {
    const { rememberSession } = await load()
    rememberSession(id(4))
    rememberSession(id(4))
    expect(JSON.parse(readFileSync(file, 'utf8'))).toEqual([id(4)])
  })
})

describe('the file itself', () => {
  it('keeps the newest ids and drops the oldest past the cap', async () => {
    const { ownsSession, rememberSession } = await load()
    for (let n = 1; n <= 205; n++) rememberSession(id(n))
    const kept: string[] = JSON.parse(readFileSync(file, 'utf8'))
    expect(kept.length).toBe(200)
    expect(ownsSession(id(205))).toBe(true)
    expect(ownsSession(id(6))).toBe(true)
    // The first five fell off the front.
    expect(ownsSession(id(5))).toBe(false)
    expect(ownsSession(id(1))).toBe(false)
  })

  it('reads as empty when it holds something that is not a list of ids, and still records the next one', async () => {
    writeFileSync(file, '{ this is not json')
    const { ownsSession, rememberSession } = await load()
    expect(ownsSession(id(7))).toBe(false)
    rememberSession(id(7))
    expect(ownsSession(id(7))).toBe(true)
  })

  it('ignores entries in it that are not ids', async () => {
    writeFileSync(file, JSON.stringify([id(8), 42, null, { id: id(9) }]))
    const { ownsSession } = await load()
    expect(ownsSession(id(8))).toBe(true)
    expect(ownsSession(id(9))).toBe(false)
  })

  it('never throws when it cannot be written, so a run is not lost to a full disk', async () => {
    vi.stubEnv('PFC_CHAT_SESSIONS_FILE', join(dir, 'no-such-folder', 'sessions.json'))
    const { ownsSession, rememberSession } = await load()
    expect(() => rememberSession(id(10))).not.toThrow()
    expect(ownsSession(id(10))).toBe(false)
  })
})
