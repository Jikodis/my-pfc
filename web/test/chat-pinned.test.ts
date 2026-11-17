import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { PINNED } from '../src/lib/chat/pinned'

describe('the pinned skills', () => {
  it('start with the daily summary and end with the review catch-up', () => {
    expect(PINNED[0]).toBe('pfc-daily-summary')
    expect(PINNED[PINNED.length - 1]).toBe('pfc-review')
  })
  it('are all installed under the real repo .agents/skills', () => {
    const skills = fileURLToPath(new URL('../../.agents/skills/', import.meta.url))
    for (const name of PINNED) expect(existsSync(`${skills}${name}/SKILL.md`), name).toBe(true)
  })
})
