import { expect, it } from 'vitest'
import { areaLabel, plainText, readableValue } from '../src/lib/text'

it('drops the asterisks and underscores that mark emphasis', () => {
  expect(plainText('the two together *and* tied tightly')).toBe('the two together and tied tightly')
  expect(plainText('**Really** __sure__ about _this_')).toBe('Really sure about this')
})

it('leaves the rest of the words alone', () => {
  const s = 'I cook at a beginner level - well-rested, "on a plan" (mostly), 8+ hours.'
  expect(plainText(s)).toBe(s)
})

it('keeps an underscore that is part of a name', () => {
  expect(plainText('read sleep_hours and awake_minutes')).toBe('read sleep_hours and awake_minutes')
})

it('keeps a lone asterisk that is not wrapping anything', () => {
  expect(plainText('2 * 3 * 4 is 24')).toBe('2 * 3 * 4 is 24')
})

it('handles an empty or missing statement', () => {
  expect(plainText('')).toBe('')
})

it('reads a slug as a name', () => {
  expect(areaLabel('health')).toBe('Health')
  expect(areaLabel('master_bathroom')).toBe('Master bathroom')
  expect(areaLabel('living-room')).toBe('Living room')
  expect(areaLabel('')).toBe('')
})

it('leaves a leading bullet asterisk alone', () => {
  expect(plainText('* Item')).toBe('* Item')
  expect(plainText('* Item one\n* Item two')).toBe('* Item one\n* Item two')
})

it('reads a stored value as words, and leaves everything else alone', () => {
  expect(readableValue('with_fat')).toBe('With fat')
  expect(readableValue('with_food')).toBe('With food')
  expect(readableValue('active')).toBe('active')
  expect(readableValue('hyp-20260412-001')).toBe('hyp-20260412-001')
  expect(readableValue('data/insights.ndjson')).toBe('data/insights.ndjson')
  expect(readableValue('read sleep_hours and awake_minutes')).toBe('read sleep_hours and awake_minutes')
})
