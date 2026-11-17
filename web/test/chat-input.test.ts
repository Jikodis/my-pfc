import { describe, expect, it } from 'vitest'
import { shouldSend, skillAction } from '../src/lib/chat/input'

describe('shouldSend', () => {
  it('sends on Enter', () => {
    expect(shouldSend({ key: 'Enter', shiftKey: false })).toBe(true)
  })

  it('does not send on Shift and Enter, which is a new line', () => {
    expect(shouldSend({ key: 'Enter', shiftKey: true })).toBe(false)
  })

  it('does not send while text is being composed', () => {
    // Dictation and every non-Latin keyboard end a composition with Enter. Sending
    // there cuts the sentence off mid word.
    expect(shouldSend({ key: 'Enter', shiftKey: false, isComposing: true })).toBe(false)
  })

  it('does not send on the key code browsers use for a composition', () => {
    expect(shouldSend({ key: 'Enter', shiftKey: false, keyCode: 229 })).toBe(false)
  })

  it('ignores every other key', () => {
    expect(shouldSend({ key: 'a', shiftKey: false })).toBe(false)
    expect(shouldSend({ key: 'Escape', shiftKey: false })).toBe(false)
  })
})

describe('skillAction', () => {
  it('sends a skill that needs nothing more and changes nothing it cannot take back', () => {
    expect(skillAction({ name: 'pfc-stuck', takesArgs: false, prefill: false }))
      .toEqual({ text: '/pfc-stuck', send: true })
  })
  it('fills the box for a skill that needs more words', () => {
    expect(skillAction({ name: 'pfc-add-task', takesArgs: true, prefill: false }))
      .toEqual({ text: '/pfc-add-task ', send: false })
  })
  it('fills the box, and never sends, for a skill marked prefill even with no words to add', () => {
    expect(skillAction({ name: 'pfc-commit-and-push', takesArgs: false, prefill: true }))
      .toEqual({ text: '/pfc-commit-and-push ', send: false })
  })
  it('treats a missing prefill field, from an older server, as prefill false', () => {
    expect(skillAction({ name: 'pfc-stuck', takesArgs: false })).toEqual({ text: '/pfc-stuck', send: true })
  })
})
