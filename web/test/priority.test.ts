import { describe, expect, it } from 'vitest'
import type { Priced } from '../src/lib/priority'
import { byPriority, code } from '../src/lib/priority'

describe('priority', () => {
  it('builds the two-letter code with impact first', () => {
    expect(code({ impact: 'high', urgency: 'low' })).toBe('AC')
    expect(code({ impact: 'medium', urgency: 'medium' })).toBe('BB')
  })

  it('sorts AA before CC', () => {
    const rows = [
      { n: 1, impact: 'low', urgency: 'low' },
      { n: 2, impact: 'high', urgency: 'high' },
    ] as const
    expect(byPriority([...rows]).map((r) => r.n)).toEqual([2, 1])
  })

  // One real project carries neither field, so both halves are optional.
  it('reads none when either half is missing', () => {
    expect(code({ impact: 'high' })).toBe('none')
    expect(code({ urgency: 'high' })).toBe('none')
    expect(code({ impact: null, urgency: null })).toBe('none')
    expect(code({})).toBe('none')
  })

  it('sorts rows with no priority last, keeping their own order', () => {
    const rows: (Priced & { n: number })[] = [
      { n: 1, impact: null, urgency: null },
      { n: 2, impact: 'low', urgency: 'low' },
      { n: 3 },
      { n: 4, impact: 'high', urgency: 'high' },
    ]
    expect(byPriority([...rows]).map((r) => r.n)).toEqual([4, 2, 1, 3])
  })

  it('keeps equal codes in the order they arrived', () => {
    const rows = [
      { n: 1, impact: 'high', urgency: 'high' },
      { n: 2, impact: 'high', urgency: 'high' },
      { n: 3, impact: 'high', urgency: 'high' },
    ] as const
    expect(byPriority([...rows]).map((r) => r.n)).toEqual([1, 2, 3])
  })
})
