import { describe, expect, it } from 'vitest'
import type { Home } from '../src/lib/computed'
import { STEP_LABELS, TOUR_BANDS, appendPicksRequest, picksRequest, rateRequest, resumeIndex, reviewHint, tourSteps } from '../src/lib/tour'

const d = '2026-10-31'

/** The fields `tourSteps` reads, set so that every step has something to show. */
const home: Pick<Home, 'welcome_back' | 'rate_target' | 'needs_you' | 'due_review' | 'habits' | 'tour_look'> = {
  welcome_back: true,
  habits: [{ id: 'practice-guitar', title: 'Practice guitar', description: 'Practice guitar', auto_derived: false, cadence: 'daily', logged_today: false, logged_yesterday: false }],
  tour_look: { kind: 'stale_areas', title: 'Life wheel', detail: 'last rated', date: '2026-06-03' },
  rate_target: { date: d, unrated: true },
  needs_you: [{ kind: 'deadline', id: 'task-20260719-001', title: 'Check the probe', why: 'overdue since', date: '2026-07-22' }],
  due_review: null,
}

describe('tourSteps', () => {
  it('drops welcome and rate when not needed', () => {
    expect(tourSteps({ ...home, welcome_back: false, rate_target: { date: d, unrated: false } }).map((s) => s.id))
      .toEqual(['body', 'music', 'needs', 'picks', 'habits', 'look', 'why'])
  })

  it('keeps every step for a returning, unrated day, in the order of the page', () => {
    expect(tourSteps(home).map((s) => s.id)).toEqual(['welcome', 'rate', 'body', 'music', 'needs', 'picks', 'habits', 'look', 'why'])
  })

  it('drops the look-at step when Python names nothing to look at', () => {
    expect(tourSteps({ ...home, tour_look: null }).map((s) => s.id)).not.toContain('look')
  })

  it('drops the habits step when there are no habits', () => {
    expect(tourSteps({ ...home, habits: [] }).map((s) => s.id)).not.toContain('habits')
  })

  it('drops the needs step only when nothing needs you and no review is due', () => {
    expect(tourSteps({ ...home, needs_you: [] }).map((s) => s.id)).not.toContain('needs')
    expect(tourSteps({ ...home, needs_you: [], due_review: { id: 'life-wheel', label: 'Life wheel', skill: null } }).map((s) => s.id))
      .toContain('needs')
  })

  it('names the band each step shows, and every step has a label', () => {
    for (const step of tourSteps(home)) {
      expect(step.band).toBe(TOUR_BANDS[step.id])
      expect(STEP_LABELS[step.id]).toBeTruthy()
    }
    expect(tourSteps(home).find((s) => s.id === 'picks')?.band).toBe('tasks')
    expect(tourSteps(home).find((s) => s.id === 'habits')?.band).toBe('habits')
    expect(tourSteps(home).find((s) => s.id === 'look')?.band).toBe('tour-look')
    expect(tourSteps(home).find((s) => s.id === 'body')?.band).toBe('body')
  })
})

describe('picksRequest', () => {
  it('sends the first two taps as critical and a third as the bonus', () => {
    expect(JSON.parse(picksRequest(d, ['task-20260101-001', 'task-20260101-002', 'task-20260101-003'])))
      .toEqual({ date: d, critical: ['task-20260101-001', 'task-20260101-002'], bonus: 'task-20260101-003' })
  })
  it('sends one pick with no bonus', () => {
    expect(JSON.parse(picksRequest(d, ['task-20260101-001']))).toEqual({ date: d, critical: ['task-20260101-001'] })
  })
})

describe('appendPicksRequest', () => {
  const keep = { critical: ['task-20260101-001', 'task-20260101-002'], bonus: 'task-20260101-009' }
  it('sends the stored picks first, then the new ones, and keeps the bonus', () => {
    expect(JSON.parse(appendPicksRequest(d, keep, ['task-20260101-003']))).toEqual({
      date: d, critical: ['task-20260101-001', 'task-20260101-002', 'task-20260101-003'], bonus: 'task-20260101-009' })
  })
  it('drops the bonus when it is tapped as a pick', () => {
    expect(JSON.parse(appendPicksRequest(d, keep, ['task-20260101-009']))).toEqual({
      date: d, critical: ['task-20260101-001', 'task-20260101-002', 'task-20260101-009'] })
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

describe('resumeIndex', () => {
  const steps = tourSteps({ ...home, welcome_back: false, rate_target: { date: d, unrated: false } })
  it('finds the stored step', () => {
    expect(steps[resumeIndex(steps, 'needs')].id).toBe('needs')
  })
  it('moves on to the next step that is still there when the stored one is gone', () => {
    // Rating the day removes the rate step; the reload continues at the step after it.
    expect(steps[resumeIndex(steps, 'rate')].id).toBe('body')
  })
  it('starts at the beginning for a missing or unknown value', () => {
    expect(resumeIndex(steps, null)).toBe(0)
    expect(resumeIndex(steps, 'nope')).toBe(0)
  })
  it('stops at the last step when everything after the stored one is gone', () => {
    expect(resumeIndex(steps.slice(0, 2), 'why')).toBe(1)
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
