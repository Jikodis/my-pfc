import { describe, expect, it } from 'vitest'
import { parseFrames } from '../src/lib/chat/frames'

describe('parseFrames', () => {
  it('reads one data frame and keeps nothing back', () => {
    expect(parseFrames('data: {"kind":"text"}\n\n')).toEqual({
      frames: [{ event: null, data: '{"kind":"text"}' }],
      rest: '',
    })
  })

  it('reads the named run frame', () => {
    expect(parseFrames('event: run\ndata: {"id":"abc"}\n\n')).toEqual({
      frames: [{ event: 'run', data: '{"id":"abc"}' }],
      rest: '',
    })
  })

  it('reads the sequence number a frame carries in its id field', () => {
    expect(parseFrames('id: 12\ndata: {"kind":"text"}\n\n')).toEqual({
      frames: [{ event: null, id: '12', data: '{"kind":"text"}' }],
      rest: '',
    })
    // A frame with no id says nothing about one.
    expect(parseFrames('data: x\n\n').frames[0]).not.toHaveProperty('id')
  })

  it('returns a frame split across chunks only once the blank line arrives', () => {
    const first = parseFrames('data: {"kind":"te')
    expect(first).toEqual({ frames: [], rest: 'data: {"kind":"te' })
    const second = parseFrames(`${first.rest}xt","delta":"hi"}\n\n`)
    expect(second).toEqual({
      frames: [{ event: null, data: '{"kind":"text","delta":"hi"}' }],
      rest: '',
    })
  })

  it('drops comment lines and keeps the frame beside them', () => {
    expect(parseFrames(': keep-alive\n\ndata: one\n\n')).toEqual({
      frames: [{ event: null, data: 'one' }],
      rest: '',
    })
  })

  it('reads carriage return line endings, including one split across chunks', () => {
    const first = parseFrames('event: run\r\ndata: {"id":"a"}\r')
    expect(first.frames).toEqual([])
    const second = parseFrames(`${first.rest}\n\r\ndata: two\r\n\r\n`)
    expect(second).toEqual({
      frames: [
        { event: 'run', data: '{"id":"a"}' },
        { event: null, data: 'two' },
      ],
      rest: '',
    })
  })

  it('joins two data lines in one frame with a newline', () => {
    expect(parseFrames('data: one\ndata: two\n\n').frames).toEqual([{ event: null, data: 'one\ntwo' }])
  })

  it('accepts a data line with no space after the colon', () => {
    expect(parseFrames('data:one\n\n').frames).toEqual([{ event: null, data: 'one' }])
  })

  it('leaves out a frame that carries no data line', () => {
    expect(parseFrames('event: run\n\n')).toEqual({ frames: [], rest: '' })
  })

  it('returns several frames from one chunk and keeps the unfinished tail', () => {
    expect(parseFrames('data: a\n\ndata: b\n\ndata: c')).toEqual({
      frames: [
        { event: null, data: 'a' },
        { event: null, data: 'b' },
      ],
      rest: 'data: c',
    })
  })

  it('reads an empty buffer as nothing at all', () => {
    expect(parseFrames('')).toEqual({ frames: [], rest: '' })
  })
})
