import { describe, expect, it } from 'vitest'
import { escapeHtml, idTooltip, percentComplete, round1 } from '../src/lib/format'

describe('round1', () => {
  it('keeps one decimal place and rounds half up', () => {
    expect(round1(91.75)).toBe(91.8)
    expect(round1(3)).toBe(3)
    expect(round1(0.04)).toBe(0)
  })
})

describe('escapeHtml', () => {
  it('escapes both brackets, both quote characters, and the ampersand', () => {
    expect(escapeHtml(`<b> & "x" 'y'`)).toBe('&lt;b&gt; &amp; &quot;x&quot; &#39;y&#39;')
  })
  it('escapes the ampersand first, so an escape is never escaped twice', () => {
    expect(escapeHtml('&lt;')).toBe('&amp;lt;')
  })
  it('leaves ordinary words alone', () => {
    expect(escapeHtml('Sun, Sep 20: done')).toBe('Sun, Sep 20: done')
  })
})

describe('percentComplete', () => {
  it('rounds to a whole percent', () => {
    expect(percentComplete(1, 3)).toBe(33)
    expect(percentComplete(5, 10)).toBe(50)
  })
  it('reads zero rather than dividing by zero', () => {
    expect(percentComplete(0, 0)).toBe(0)
  })
})

describe('idTooltip', () => {
  it('puts the id first and the notes under it', () => {
    expect(idTooltip('task-1', 'check the cord')).toBe('task-1\ncheck the cord')
  })
  it('drops whichever side is missing', () => {
    expect(idTooltip('task-1', null)).toBe('task-1')
    expect(idTooltip('', 'just a note')).toBe('just a note')
  })
  it('takes a wider separator where the notes of a record run to paragraphs', () => {
    expect(idTooltip('insight-1', 'a', '\n\n')).toBe('insight-1\n\na')
  })
})
