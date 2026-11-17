import { describe, expect, it } from 'vitest'
import { answersPrompt, buildAnswers, dueCountLine, isEmpty, reviewDue } from '../src/lib/review'

describe('reviewDue', () => {
  it('says a review never done is never done', () => {
    expect(reviewDue(null)).toBe('Never done yet.')
  })
  it('says due today at zero days late', () => {
    expect(reviewDue(0)).toBe('Due today.')
  })
  it('counts the days overdue, singular for one', () => {
    expect(reviewDue(1)).toBe('1 day overdue.')
    expect(reviewDue(128)).toBe('128 days overdue.')
  })
})

describe('dueCountLine', () => {
  it('says how many wait and that only one is shown', () => {
    expect(dueCountLine(1)).toBe('1 review due; one at a time.')
    expect(dueCountLine(20)).toBe('20 reviews due; one at a time.')
  })
})

describe('buildAnswers', () => {
  it('leaves out blank rows and prompts and trims the rest', () => {
    const answers = buildAnswers('focus-accuracy', {
      choices: { 'focus-1': 'Keep', 'focus-2': '' },
      notes: { 'focus-1': '  ', 'focus-3': ' smaller target ' },
      prompts: { why: '\n', 'new-focuses': 'Reading, Growth' },
    })
    expect(answers).toEqual({
      review: 'focus-accuracy',
      choices: { 'focus-1': 'Keep' },
      notes: { 'focus-3': 'smaller target' },
      prompts: { 'new-focuses': 'Reading, Growth' },
    })
    expect(isEmpty(answers)).toBe(false)
  })

  it('carries the rows the form showed', () => {
    expect(buildAnswers('hypotheses-review', { choices: {}, notes: {}, prompts: {} }, ['h1', 'h2']).shown)
      .toEqual(['h1', 'h2'])
  })

  it('is empty when nothing was answered', () => {
    expect(isEmpty(buildAnswers('life-wheel', { choices: { a: '' }, notes: {}, prompts: { b: ' ' } }))).toBe(true)
  })
})

describe('answersPrompt', () => {
  it('is the review command with the answers as one line of JSON', () => {
    const answers = buildAnswers('vision-relevance', {
      choices: { 'tidy-home': 'Still fits' }, notes: {}, prompts: { why: 'Walking\nwith friends' },
    })
    expect(answersPrompt(answers)).toBe(
      '/pfc-review vision-relevance answers {"review":"vision-relevance","choices":{"tidy-home":"Still fits"},"notes":{},"prompts":{"why":"Walking\\nwith friends"}}',
    )
  })

  it('keeps a typed brace placeholder as typed', () => {
    const answers = buildAnswers('life-wheel', { choices: {}, notes: { health: '{id}' }, prompts: {} })
    expect(answersPrompt(answers)).toContain('"health":"{id}"')
  })
})
