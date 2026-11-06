import { describe, expect, it } from 'vitest'
import {
  QUEUE_CAP,
  enqueue,
  putBack,
  removeQueued,
  restoreQueue,
  saveQueue,
  takeNext,
  type Queue,
} from '../src/lib/chat/queue'
import { MESSAGE_LIMIT } from '../src/lib/chat/guard'

const three = (): Queue => enqueue(enqueue(enqueue([], 'one', 'a'), 'two', 'b'), 'three', 'c')

describe('the message queue', () => {
  it('adds at the end, trimmed, and takes from the front', () => {
    const queue = three()
    expect(queue.map((q) => q.text)).toEqual(['one', 'two', 'three'])
    const { next, rest } = takeNext(queue)
    expect(next).toEqual({ id: 'a', text: 'one' })
    expect(rest.map((q) => q.text)).toEqual(['two', 'three'])
    expect(enqueue([], '  padded \n', 'x')).toEqual([{ id: 'x', text: 'padded' }])
  })

  it('never changes the queue it was handed', () => {
    const queue = three()
    enqueue(queue, 'four', 'd')
    removeQueued(queue, 'b')
    takeNext(queue)
    expect(queue.length).toBe(3)
  })

  it('adds nothing for an empty message, a message past the limit, or a full queue', () => {
    expect(enqueue([], '   ', 'x')).toEqual([])
    expect(enqueue([], 'x'.repeat(MESSAGE_LIMIT + 1), 'x')).toEqual([])
    let full: Queue = []
    for (let n = 0; n < QUEUE_CAP; n++) full = enqueue(full, `m${n}`, `id${n}`)
    expect(full.length).toBe(QUEUE_CAP)
    expect(enqueue(full, 'one more', 'z')).toBe(full)
  })

  it('removes one message by id and leaves the order of the rest', () => {
    expect(removeQueued(three(), 'b').map((q) => q.text)).toEqual(['one', 'three'])
    expect(removeQueued(three(), 'nope').map((q) => q.text)).toEqual(['one', 'two', 'three'])
  })

  it('takes nothing from an empty queue', () => {
    expect(takeNext([])).toEqual({ next: null, rest: [] })
  })

  it('puts a message that could not be sent back at the front, under the cap', () => {
    const { next, rest } = takeNext(three())
    expect(putBack(rest, next as { id: string; text: string }).map((q) => q.text)).toEqual(['one', 'two', 'three'])
    let full: Queue = []
    for (let n = 0; n < QUEUE_CAP; n++) full = enqueue(full, `m${n}`, `id${n}`)
    // A message the person already sent once is not lost to the cap: it goes first.
    const back = putBack(full, { id: 'first', text: 'first' })
    expect(back[0]?.text).toBe('first')
    expect(back.length).toBe(QUEUE_CAP + 1)
  })

  it('reads back what it saved', () => {
    expect(restoreQueue(saveQueue(three()))).toEqual(three())
  })

  it('reads anything that is not a saved queue as an empty one, and drops rows of the wrong shape', () => {
    for (const raw of [null, '', 'not json', '{}', '"text"', '42']) expect(restoreQueue(raw)).toEqual([])
    const mixed = JSON.stringify([
      { id: 'a', text: 'kept' },
      { id: 'b' },
      { id: 3, text: 'number id' },
      { id: 'c', text: '   ' },
      { id: 'd', text: 'x'.repeat(MESSAGE_LIMIT + 1) },
      'a string',
      null,
      { id: 'a', text: 'same id twice' },
      { id: 'e', text: 'also kept', extra: '<img>' },
    ])
    expect(restoreQueue(mixed)).toEqual([{ id: 'a', text: 'kept' }, { id: 'e', text: 'also kept' }])
  })

  it('keeps no more than the cap from storage', () => {
    const rows = Array.from({ length: QUEUE_CAP + 5 }, (_, n) => ({ id: `id${n}`, text: `m${n}` }))
    expect(restoreQueue(JSON.stringify(rows)).length).toBe(QUEUE_CAP)
  })
})
