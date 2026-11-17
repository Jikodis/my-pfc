import { describe, expect, it } from 'vitest'
import { appendPicksRequest, picksRequest, rateRequest, reviewHint } from '../src/lib/day'

const d = '2025-10-31'

describe('picksRequest', () => {
  it('sends the first two taps as critical and a third as the bonus', () => {
    expect(JSON.parse(picksRequest(d, ['task-20250101-001', 'task-20250101-002', 'task-20250101-003'])))
      .toEqual({ date: d, critical: ['task-20250101-001', 'task-20250101-002'], bonus: 'task-20250101-003' })
  })
  it('sends one pick with no bonus', () => {
    expect(JSON.parse(picksRequest(d, ['task-20250101-001']))).toEqual({ date: d, critical: ['task-20250101-001'] })
  })
})

describe('appendPicksRequest', () => {
  const keep = { critical: ['task-20250101-001', 'task-20250101-002'], bonus: 'task-20250101-009' }
  it('sends the stored picks first, then the new ones, and keeps the bonus', () => {
    expect(JSON.parse(appendPicksRequest(d, keep, ['task-20250101-003']))).toEqual({
      date: d, critical: ['task-20250101-001', 'task-20250101-002', 'task-20250101-003'], bonus: 'task-20250101-009' })
  })
  it('drops the bonus when it is tapped as a pick', () => {
    expect(JSON.parse(appendPicksRequest(d, keep, ['task-20250101-009']))).toEqual({
      date: d, critical: ['task-20250101-001', 'task-20250101-002', 'task-20250101-009'] })
  })
})

describe('rateRequest', () => {
  it('leaves out the optional answer when it was not tapped', () => {
    expect(JSON.parse(rateRequest(d, { energy: 3, mood: 4, focus: 2 }))).toEqual({ date: d, energy: 3, mood: 4, focus: 2 })
  })
  it('includes hyperfocused when tapped', () => {
    expect(JSON.parse(rateRequest(d, { energy: 3, mood: 4, focus: 2, hyperfocused: false })))
      .toEqual({ date: d, energy: 3, mood: 4, focus: 2, hyperfocused: false })
  })
})

describe('reviewHint', () => {
  it('reads as plain text: no backticks, link targets, or bold markers', () => {
    expect(reviewHint("open [`state.md`](../../x/state.md) § The backlog, **never** add pressure"))
      .toBe('open state.md § The backlog, never add pressure')
    expect(reviewHint('`/pfc-insights` — triage active insights')).toBe('/pfc-insights — triage active insights')
  })
  it('is empty for a review with no skill text', () => {
    expect(reviewHint(null)).toBe('')
  })
})
