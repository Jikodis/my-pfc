import { describe, expect, it } from 'vitest'
import { readLiveRun, writeLiveRun } from '../src/lib/chat/resume'

const ID = '22222222-2222-4222-8222-222222222222'

describe('the live run a page keeps for the next page', () => {
  it('reads back what it wrote, and asks for the event after the last one applied', () => {
    expect(readLiveRun(writeLiveRun({ id: ID, seq: 41 }))).toEqual({ id: ID, seq: 41, from: 42 })
  })

  it('starts from the first event when none was applied yet', () => {
    expect(readLiveRun(writeLiveRun({ id: ID, seq: -1 }))).toEqual({ id: ID, seq: -1, from: 0 })
  })

  it('reads anything else as no live run', () => {
    for (const raw of [
      null,
      '',
      'nope',
      '[]',
      JSON.stringify({ id: ID }),
      JSON.stringify({ id: 'not-a-run-id', seq: 1 }),
      JSON.stringify({ id: ID, seq: -2 }),
      JSON.stringify({ id: ID, seq: 1.5 }),
      JSON.stringify({ id: ID, seq: '3' }),
    ]) {
      expect(readLiveRun(raw)).toBeNull()
    }
  })
})
