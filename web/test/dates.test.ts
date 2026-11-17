import { describe, expect, it } from 'vitest'
import {
  addDays, daysBetween, deadlineCell, deadlineLabel, formatDate, formatDateLong, formatTime12, formatWhen, isIsoDate, lastNDays, todayLocal,
} from '../src/lib/dates'

describe('dates', () => {
  it('words a local timestamp as weekday and 12-hour time', () => {
    expect(formatWhen('2025-11-02T05:00:09')).toBe('Sun 5:00 AM')
    expect(formatWhen('2025-11-01T17:30:00')).toBe('Sat 5:30 PM')
  })
  it('derives today in Denver, not UTC', () => {
    // 2025-09-22 02:00 UTC is still 2025-09-21 8:00 PM in Denver.
    expect(todayLocal(new Date('2025-09-22T02:00:00Z'))).toBe('2025-09-21')
  })
  it('formats a date without shifting the day', () => {
    expect(formatDate('2025-09-21')).toBe('Sun, Sep 21')
  })
  it('formats 24-hour clock strings as 12-hour', () => {
    expect(formatTime12('16:45')).toBe('4:45 PM')
    expect(formatTime12('00:05:00')).toBe('12:05 AM')
    expect(formatTime12('12:00')).toBe('12:00 PM')
  })
  it('formats an ISO timestamp in local time', () => {
    expect(formatTime12('2025-09-20T22:31:00-06:00')).toBe('10:31 PM')
  })
  it('counts whole days between dates', () => {
    expect(daysBetween('2025-09-04', '2025-09-20')).toBe(16)
  })
  it('lists the last n days oldest first', () => {
    expect(lastNDays(3, '2025-09-20')).toEqual(['2025-09-18', '2025-09-19', '2025-09-20'])
  })
  it('labels a deadline ahead, today, and behind', () => {
    expect(deadlineLabel('2025-09-20', '2025-09-30')).toBe('due in 10 days')
    expect(deadlineLabel('2025-09-20', '2025-09-20')).toBe('due today')
    expect(deadlineLabel('2025-09-20', '2025-09-13')).toBe('7 days overdue')
  })
  it('says day, not days, when the deadline is one day out', () => {
    expect(deadlineLabel('2025-09-20', '2025-09-21')).toBe('due in 1 day')
    expect(deadlineLabel('2025-09-20', '2025-09-19')).toBe('1 day overdue')
  })
})

describe('formatDateLong', () => {
  it('keeps the year, so records that span years read correctly', () => {
    expect(formatDateLong('2025-09-14')).toBe('Sep 14, 2025')
    expect(formatDateLong('2025-01-01')).toBe('Jan 1, 2025')
  })
  it('shows the time as well for a full timestamp, in local time', () => {
    expect(formatDateLong('2025-09-14T22:45:00Z')).toBe('Sep 14, 2025, 4:45 PM')
  })
  it('hands back anything that is not a date', () => {
    expect(formatDateLong('active')).toBe('active')
  })
  it('steps a plain date forward and back across a month and a year', () => {
    expect(addDays('2025-10-13', 1)).toBe('2025-10-14')
    expect(addDays('2025-10-01', -1)).toBe('2025-09-30')
    expect(addDays('2025-12-31', 1)).toBe('2026-01-01')
    expect(addDays('2025-10-13', 0)).toBe('2025-10-13')
  })
  it('accepts only a real calendar date as a date', () => {
    expect(isIsoDate('2025-10-13')).toBe(true)
    expect(isIsoDate('2025-02-30')).toBe(false)
    expect(isIsoDate('2025-13-01')).toBe(false)
    expect(isIsoDate('13 Oct')).toBe(false)
    expect(isIsoDate('')).toBe(false)
  })
})

describe('deadlineCell', () => {
  it('reads an open deadline the way deadlineLabel does and marks a missed one', () => {
    expect(deadlineCell('2025-10-13', { deadline: '2025-10-20' }, false)).toEqual({ text: 'due in 7 days', overdue: false })
    expect(deadlineCell('2025-10-13', { deadline: '2025-10-10' }, false)).toEqual({ text: '3 days overdue', overdue: true })
  })
  it('says when finished work was finished and never calls it overdue', () => {
    expect(deadlineCell('2025-10-13', { deadline: '2025-04-15', completed: '2025-04-15' }, true))
      .toEqual({ text: 'Finished Apr 15, 2025', overdue: false })
    expect(deadlineCell('2025-10-13', { deadline: '2025-04-15' }, true)).toEqual({ text: 'Finished', overdue: false })
  })
  it('is empty for open work with no deadline', () => {
    expect(deadlineCell('2025-10-13', {}, false)).toEqual({ text: '', overdue: false })
  })
})
