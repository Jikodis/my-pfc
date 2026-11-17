/** The wording an edit button shows for each reply, and the request it sends. */
import { describe, expect, it } from 'vitest'
import {
  ALREADY_PICKED, EMAIL_NOTE, NOT_PUSHED, PICKS_FULL, SERVER_FAILED, UNREACHABLE, WRITE_HEADERS, isButtonAction, lightRequest,
  outcome, pullIntoToday, requestFor,
} from '../src/lib/write-ui'

const saved = (over: Record<string, unknown> = {}) => ({
  ok: true, changed: true, pushed: true, commit: 'abc1234', push_error: null,
  message: 'Saved.', title: 'Call the dentist', email_linked: false, ...over,
})

describe('requestFor', () => {
  it('sends the id for complete and log', () => {
    expect(requestFor('complete-task', 'task-20250901-001')).toEqual({
      url: '/api/write/complete-task', body: '{"id":"task-20250901-001"}' })
    expect(requestFor('log-habit', 'morning-walk')).toEqual({
      url: '/api/write/log-habit', body: '{"id":"morning-walk"}' })
  })

  it('sends the day with a habit log made for a day other than today', () => {
    expect(JSON.parse(requestFor('log-habit', 'morning-walk', '2025-10-12').body))
      .toEqual({ id: 'morning-walk', date: '2025-10-12' })
  })

  it('sends parked true for on and false for off', () => {
    expect(JSON.parse(requestFor('park-focus', 'focus-20250706-001', 'on').body)).toEqual({ id: 'focus-20250706-001', parked: true })
    expect(JSON.parse(requestFor('park-focus', 'focus-20250706-001', 'off').body)).toEqual({ id: 'focus-20250706-001', parked: false })
  })

  it('sends the day with a skipped suggestion', () => {
    expect(JSON.parse(requestFor('skip-suggestion', 'task-20250901-001', '2025-11-02').body))
      .toEqual({ date: '2025-11-02', id: 'task-20250901-001' })
  })

  it('sends active true or false for a project', () => {
    expect(JSON.parse(requestFor('set-project', 'proj-20250412-001', 'active').body)).toEqual({ id: 'proj-20250412-001', active: true })
    expect(JSON.parse(requestFor('set-project', 'proj-20250412-001', 'parked').body)).toEqual({ id: 'proj-20250412-001', active: false })
  })

  it('sends the id to retire an anchor', () => {
    expect(requestFor('retire-anchor', 'ground-20250627-001')).toEqual({
      url: '/api/write/retire-anchor', body: '{"id":"ground-20250627-001"}' })
  })

  it('knows the seven actions and nothing else', () => {
    expect(['complete-task', 'drop-task', 'log-habit', 'park-focus', 'skip-suggestion', 'set-project', 'retire-anchor']
      .every(isButtonAction)).toBe(true)
    expect(isButtonAction('delete-task')).toBe(false)
    expect(isButtonAction(undefined)).toBe(false)
  })

  it('uses the chat guard headers', () => {
    expect(WRITE_HEADERS).toEqual({ 'Content-Type': 'application/json', 'X-PFC-Chat': '1' })
  })
})

describe('lightRequest', () => {
  it('posts an area light with its note to set-area', () => {
    expect(lightRequest('area', 'health', 'yellow', ' Not enough sleep. ')).toEqual({
      url: '/api/write/set-area', body: '{"key":"health","light":"yellow","note":"Not enough sleep."}' })
  })
  it('posts a room to set-room, and an empty note clears the note', () => {
    expect(JSON.parse(lightRequest('room', 'car', 'green', '').body)).toEqual({ key: 'car', light: 'green', note: '' })
    expect(lightRequest('room', 'car', 'green', '').url).toBe('/api/write/set-room')
  })
})

describe('pullIntoToday', () => {
  const d = '2025-11-01'
  it('adds the task after the picks already set, keeping the bonus', () => {
    expect(pullIntoToday(d, { critical: ['task-20250101-001'], bonus: 'task-20250101-009' }, 'task-20250101-002')).toEqual({
      ok: true, body: JSON.stringify({ date: d, critical: ['task-20250101-001', 'task-20250101-002'], bonus: 'task-20250101-009' }) })
  })
  it('makes it the first pick on a day with none', () => {
    expect(pullIntoToday(d, null, 'task-20250101-002')).toEqual({
      ok: true, body: JSON.stringify({ date: d, critical: ['task-20250101-002'] }) })
  })
  it('moves today\'s bonus up to a critical pick instead of listing it twice', () => {
    expect(pullIntoToday(d, { critical: ['task-20250101-001'], bonus: 'task-20250101-002' }, 'task-20250101-002')).toEqual({
      ok: true, body: JSON.stringify({ date: d, critical: ['task-20250101-001', 'task-20250101-002'] }) })
  })
  it('refuses when two open picks are already set', () => {
    expect(pullIntoToday(d, { critical: ['task-20250101-001', 'task-20250101-003'], bonus: null }, 'task-20250101-002'))
      .toEqual({ ok: false, message: PICKS_FULL })
    expect(pullIntoToday(d, { critical: ['task-20250101-001', 'task-20250101-003', 'task-20250101-004'],
      completed: ['task-20250101-001'], bonus: null }, 'task-20250101-002')).toEqual({ ok: false, message: PICKS_FULL })
  })
  it('sends the done picks along and counts only the open ones toward two', () => {
    expect(pullIntoToday(d, { critical: ['task-20250101-001', 'task-20250101-003'], completed: ['task-20250101-001'],
      bonus: null }, 'task-20250101-002')).toEqual({
      ok: true, body: JSON.stringify({ date: d, critical: ['task-20250101-001', 'task-20250101-003', 'task-20250101-002'] }) })
    expect(pullIntoToday(d, { critical: ['task-20250101-001', 'task-20250101-003'],
      completed: ['task-20250101-001', 'task-20250101-003'], bonus: null }, 'task-20250101-002')).toEqual({
      ok: true, body: JSON.stringify({ date: d, critical: ['task-20250101-001', 'task-20250101-003', 'task-20250101-002'] }) })
  })
  it('the refusal points at finishing a pick, not at a control elsewhere', () => {
    expect(PICKS_FULL).not.toMatch(/Now page|Change them/)
  })
  it('refuses a task that is already one of today\'s picks', () => {
    expect(pullIntoToday(d, { critical: ['task-20250101-002'], bonus: null }, 'task-20250101-002'))
      .toEqual({ ok: false, message: ALREADY_PICKED })
  })
})

describe('outcome', () => {
  it('committed and pushed: names the commit, reloads after two seconds', () => {
    expect(outcome(200, saved())).toEqual({ text: 'Done. Committed as abc1234.', tone: 'ok', reloadAfterMs: 2000 })
  })

  it('a dropped task says Dropped, not Done', () => {
    expect(outcome(200, saved(), 'drop-task').text).toBe('Dropped. Committed as abc1234.')
  })

  it('committed, not pushed: says so, reloads after three seconds', () => {
    const o = outcome(200, saved({ pushed: false, push_error: 'fatal: no remote', message: 'Saved. Not pushed yet.' }))
    expect(o).toEqual({ text: NOT_PUSHED, tone: 'ok', reloadAfterMs: 3000 })
  })

  it('nothing changed: shows the server message and keeps the page', () => {
    expect(outcome(200, saved({ changed: false, commit: null, pushed: false, message: 'Already logged today.' })))
      .toEqual({ text: 'Already logged today.', tone: 'info', reloadAfterMs: null })
  })

  it('adds the email note when the task came from an email', () => {
    expect(outcome(200, saved({ email_linked: true })).text).toBe(`Done. Committed as abc1234. ${EMAIL_NOTE}`)
    expect(outcome(200, saved({ email_linked: true, pushed: false })).text).toBe(`${NOT_PUSHED} ${EMAIL_NOTE}`)
    expect(EMAIL_NOTE).toBe('Its source email is still in the inbox; archive it in Gmail.')
  })

  it.each([404, 409, 422, 400, 403])('%i shows the server message and keeps the page', (status) => {
    expect(outcome(status, { ok: false, message: 'Another change is still being saved.' }))
      .toEqual({ text: 'Another change is still being saved.', tone: 'error', reloadAfterMs: null })
  })

  it('500 shows fixed text whatever the body says', () => {
    expect(outcome(500, { ok: false, message: '/Users/someone/secret' }))
      .toEqual({ text: SERVER_FAILED, tone: 'error', reloadAfterMs: null })
  })

  it('an error with no readable body falls back to fixed text', () => {
    expect(outcome(409, 'not json').text).toBe(SERVER_FAILED)
  })

  it('no answer at all: the local server could not be reached', () => {
    expect(outcome(null, null)).toEqual({ text: UNREACHABLE, tone: 'error', reloadAfterMs: null })
    expect(UNREACHABLE).toBe('Could not reach the local server.')
  })
})
