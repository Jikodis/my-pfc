/**
 * Runs the real scripts against a real PFC repo, so the types in computed.ts
 * are checked against what the scripts actually print. Off by default because it
 * needs a repo with data in it: set PFC_REAL_REPO to that repo's path to turn it on.
 */
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'

const REAL_REPO = process.env.PFC_REAL_REPO

describe.skipIf(!REAL_REPO)('the real scripts', () => {
  let lib: typeof import('../src/lib/computed')

  beforeAll(async () => {
    vi.stubEnv('PFC_REPO_ROOT', REAL_REPO as string)
    vi.resetModules()
    lib = await import('../src/lib/computed')
  })

  afterAll(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })

  it('revive_watchlist.py returns items shaped like SlipItem', () => {
    const items = lib.getSlipping()
    expect(Array.isArray(items)).toBe(true)
    for (const item of items) {
      expect(typeof item.detail).toBe('string')
      expect(['project', 'task']).toContain(item.item_type)
    }
  })

  it('web_data.py --review returns null or a form shaped like Review', () => {
    const review = lib.getReview()
    if (review === null) return
    expect(typeof review.label).toBe('string')
    expect(typeof review.due_count).toBe('number')
    for (const section of review.sections) {
      expect(['choices', 'prompt']).toContain(section.kind)
      if (section.kind === 'choices') for (const row of section.rows) expect(typeof row.id).toBe('string')
      else expect(typeof section.lines).toBe('number')
    }
  })
})
