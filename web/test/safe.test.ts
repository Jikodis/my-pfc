import { expect, it } from 'vitest'
import { safe } from '../src/lib/safe'

it('returns the value when the call succeeds', () => {
  expect(safe(() => 41 + 1)).toEqual({ ok: true, value: 42 })
})

it('returns the message when the call throws an Error', () => {
  expect(safe(() => { throw new Error('web_data.py failed: no module named yaml') }))
    .toEqual({ ok: false, error: 'web_data.py failed: no module named yaml' })
})

it('returns text when something other than an Error is thrown', () => {
  expect(safe(() => { throw 'plain string' })).toEqual({ ok: false, error: 'plain string' })
})
