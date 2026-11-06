import { describe, expect, it } from 'vitest'
import { type ChatEvent, writesFiles } from '../src/lib/chat/events'
import {
  ITEM_CAP,
  addItem,
  addUser,
  applyEvent,
  dropUser,
  finishTurn,
  joinDenials,
  keyOf,
  newTranscript,
  errorText,
  resendOffer,
  statusOf,
  validItems,
  type Item,
} from '../src/lib/chat/transcript'

/** Every event in order, from a fresh transcript. */
const run = (events: ChatEvent[]) => events.reduce(applyEvent, newTranscript())

/**
 * A tool call event. `writes` is what `events.ts` would have computed from the full
 * input; here it is worked out from the summary standing in for that input.
 */
const tool = (id: string, name: string, summary: string, writes = writesFiles(name, { command: summary })): ChatEvent =>
  ({ kind: 'tool', id, name, summary, writes })
const result = (id: string, ok: boolean, text: string): ChatEvent => ({ kind: 'tool_result', id, ok, text })
const done = (ok: boolean, denied: { id: string; tool: string; summary: string }[] = []): ChatEvent =>
  ({ kind: 'done', ok, text: '', turns: 1, ms: 10, denied })

describe('applyEvent', () => {
  it('keeps the session id and adds no item for it', () => {
    const state = run([{ kind: 'session', id: 'abc', model: 'claude-sonnet-5' }])
    expect(state.sessionId).toBe('abc')
    expect(state.model).toBe('claude-sonnet-5')
    expect(state.items).toEqual([])
  })

  it('gathers text deltas into one assistant block', () => {
    const state = run([
      { kind: 'session', id: 'abc', model: 'm' },
      { kind: 'text', delta: 'one ' },
      { kind: 'text', delta: 'two' },
    ])
    expect(state.items).toEqual([{ kind: 'assistant', text: 'one two' }])
  })

  it('shows text that arrives before the session event', () => {
    const state = run([
      { kind: 'text', delta: 'early' },
      { kind: 'session', id: 'abc', model: 'm' },
      { kind: 'text', delta: ' words' },
    ])
    expect(state.items).toEqual([{ kind: 'assistant', text: 'early words' }])
    expect(state.sessionId).toBe('abc')
  })

  it('starts a second assistant block after a tool line', () => {
    const state = run([
      { kind: 'text', delta: 'before' },
      tool('t1', 'Bash', 'git log'),
      { kind: 'text', delta: 'after' },
    ])
    expect(state.items.map((i) => i.kind)).toEqual(['assistant', 'tool', 'assistant'])
    expect(state.items[2]).toEqual({ kind: 'assistant', text: 'after' })
  })

  it('leaves the earlier state untouched', () => {
    const first = addUser(newTranscript(), 'hello')
    const second = applyEvent(first, { kind: 'text', delta: 'hi' })
    expect(first.items).toEqual([{ kind: 'user', text: 'hello' }])
    expect(second.items).toHaveLength(2)
  })

  it('marks a tool line ok or failed when its result arrives', () => {
    const state = run([tool('t1', 'Bash', 'git log'), result('t1', true, 'on main')])
    expect(state.items).toEqual([
      { kind: 'tool', id: 't1', name: 'Bash', summary: 'git log', status: 'ok', result: 'on main', writes: false },
    ])
  })

  it('keeps two tool calls in flight apart and finishes each on its own result', () => {
    const state = run([
      tool('t1', 'Bash', 'git log'),
      tool('t2', 'Read', 'AGENTS.md'),
      result('t2', false, 'no such file'),
      result('t1', true, 'on main'),
    ])
    expect(state.items).toEqual([
      { kind: 'tool', id: 't1', name: 'Bash', summary: 'git log', status: 'ok', result: 'on main', writes: false },
      { kind: 'tool', id: 't2', name: 'Read', summary: 'AGENTS.md', status: 'failed', result: 'no such file', writes: false },
    ])
  })

  it('gives a result to the newest tool line when an id comes round twice', () => {
    const first = run([tool('t1', 'Bash', 'git log'), result('t1', true, 'on main'), done(true)])
    const second: ChatEvent[] = [tool('t1', 'Bash', 'git log'), result('t1', false, 'no repo here')]
    const state = second.reduce(applyEvent, addUser(first, 'again'))
    const tools = state.items.filter((i) => i.kind === 'tool')
    expect(tools.map((i) => (i.kind === 'tool' ? [i.status, i.result] : []))).toEqual([
      ['ok', 'on main'],
      ['failed', 'no repo here'],
    ])
  })

  it('holds a result that arrives before its tool line and attaches it after', () => {
    const early = run([result('t1', true, 'on main')])
    expect(early.items).toEqual([])
    const state = applyEvent(early, tool('t1', 'Bash', 'git log'))
    expect(state.items).toEqual([
      { kind: 'tool', id: 't1', name: 'Bash', summary: 'git log', status: 'ok', result: 'on main', writes: false },
    ])
    expect(state.waiting).toEqual({})
  })

  it('marks a refused call as refused rather than failed and lists it once', () => {
    const state = run([
      tool('t1', 'Bash', 'brew list --versions jq'),
      result('t1', false, 'Permission to use Bash has been denied.'),
      done(true, [{ id: 't1', tool: 'Bash', summary: 'brew list --versions jq' }]),
    ])
    expect(state.items[0]).toEqual({
      kind: 'tool',
      id: 't1',
      name: 'Bash',
      summary: 'brew list --versions jq',
      status: 'refused',
      result: 'Permission to use Bash has been denied.',
      writes: false,
    })
    expect(state.items[1]).toEqual({
      kind: 'refusals',
      denied: [{ id: 't1', tool: 'Bash', summary: 'brew list --versions jq' }],
    })
    expect(state.items.filter((i) => i.kind === 'refusals')).toHaveLength(1)
  })

  it('lists a refusal that never had a tool line of its own', () => {
    const state = run([done(true, [{ id: 'gone', tool: 'Bash', summary: 'brew list' }])])
    expect(state.items[0]).toEqual({ kind: 'refusals', denied: [{ id: 'gone', tool: 'Bash', summary: 'brew list' }] })
    expect(state.items[1]).toEqual({ kind: 'done', ok: true, turns: 1, ms: 10, changed: false })
  })

  it('adds no refusal box when nothing was refused', () => {
    const state = run([done(true)])
    expect(state.items).toEqual([{ kind: 'done', ok: true, turns: 1, ms: 10, changed: false }])
  })

  it('records a done that did not work', () => {
    const state = run([done(false)])
    expect(state.items).toEqual([{ kind: 'done', ok: false, turns: 1, ms: 10, changed: false }])
  })

  it('adds an error box for an error event', () => {
    const state = run([{ kind: 'error', message: 'Could not start the claude command (ENOENT).' }])
    expect(state.items).toEqual([{ kind: 'error', text: 'Could not start the claude command (ENOENT).' }])
  })
})

describe('joinDenials', () => {
  const items: Item[] = [
    { kind: 'tool', id: 't1', name: 'Bash', summary: 'git log', status: 'ok', result: 'on main', writes: false },
    { kind: 'tool', id: 't2', name: 'Bash', summary: 'brew list', status: 'failed', result: 'denied', writes: false },
  ]

  it('marks only the tool line whose id matches', () => {
    const joined = joinDenials(items, [{ id: 't2', tool: 'Bash', summary: 'brew list' }])
    expect(joined.map((i) => (i.kind === 'tool' ? i.status : i.kind))).toEqual(['ok', 'refused'])
  })

  it('leaves every line alone when no id matches', () => {
    expect(joinDenials(items, [{ id: 'nope', tool: 'Bash', summary: 'x' }])).toEqual(items)
  })

  it('leaves every line alone when a denial carries no id', () => {
    expect(joinDenials(items, [{ id: '', tool: 'Bash', summary: 'x' }])).toEqual(items)
  })
})

describe('finishTurn', () => {
  it('says so when the stream ended without a done event', () => {
    const state = finishTurn(run([{ kind: 'text', delta: 'half a sen' }]), 'ended')
    expect(state.items[1]).toEqual({ kind: 'error', text: 'The reply ended unexpectedly.' })
  })

  it('adds nothing when the stream ended after a done event', () => {
    const state = run([{ kind: 'text', delta: 'all of it' }, done(true)])
    expect(finishTurn(state, 'ended').items).toEqual(state.items)
  })

  it('adds nothing when the stream ended after an error event', () => {
    const state = run([{ kind: 'error', message: 'boom' }])
    expect(finishTurn(state, 'ended').items).toEqual(state.items)
  })

  it('names the stop when the person pressed Stop', () => {
    const state = finishTurn(run([{ kind: 'text', delta: 'part' }]), 'stopped')
    expect(state.items[1]).toEqual({ kind: 'note', text: 'You stopped this reply.', stopped: true })
  })
})

describe('statusText', () => {
  it('reads Ready on an empty transcript', () => {
    expect(statusOf(newTranscript(), { live: false }).text).toBe('Ready')
  })

  it('reads Thinking while a run has started no tool', () => {
    expect(statusOf(addUser(newTranscript(), 'hi'), { live: true }).text).toBe('Thinking...')
  })

  it('names the tool that is running', () => {
    const state = run([tool('t1', 'Bash', 'git log')])
    expect(statusOf(state, { live: true }).text).toBe('Running: Bash')
  })

  it('goes back to thinking once every tool has a result', () => {
    const state = run([tool('t1', 'Bash', 'git log'), result('t1', true, 'on main')])
    expect(statusOf(state, { live: true }).text).toBe('Thinking...')
  })

  it('counts the refusals of the turn that just ended', () => {
    const state = run([
      done(true, [
        { id: 'a', tool: 'Bash', summary: 'brew list' },
        { id: 'b', tool: 'Bash', summary: 'brew info' },
      ]),
    ])
    expect(statusOf(state, { live: false }).text).toBe('Refused 2 actions')
  })

  it('counts one refusal as one action', () => {
    const state = run([done(true, [{ id: 'a', tool: 'Bash', summary: 'brew list' }])])
    expect(statusOf(state, { live: false }).text).toBe('Refused 1 action')
  })

  it('reads Stopped after a stop', () => {
    expect(statusOf(finishTurn(run([{ kind: 'text', delta: 'part' }]), 'stopped'), { live: false }).text).toBe('Stopped')
  })

  it('reads Ready again once the next turn starts', () => {
    const refused = run([done(true, [{ id: 'a', tool: 'Bash', summary: 'brew list' }])])
    expect(statusOf(addUser(refused, 'next question'), { live: false }).text).toBe('Ready')
  })
})

describe('results with no call of their own', () => {
  it('shows a parked result as its own line when the turn finishes', () => {
    const state = run([result('gone', false, 'Permission denied'), done(true)])
    expect(state.items[0]).toEqual({
      kind: 'tool',
      id: 'gone',
      name: '',
      summary: 'Result with no matching call',
      status: 'failed',
      result: 'Permission denied',
      writes: false,
    })
    expect(state.waiting).toEqual({})
  })

  it('shows a parked result when the turn ends in an error', () => {
    const state = run([result('gone', true, 'output'), { kind: 'error', message: 'boom' }])
    expect(state.items.map((i) => i.kind)).toEqual(['tool', 'error'])
    expect(state.items[0]).toMatchObject({ status: 'ok', result: 'output' })
    expect(state.waiting).toEqual({})
  })

  it('shows a parked result when the stream ends with no done event', () => {
    const state = finishTurn(run([result('gone', false, 'no')]), 'ended')
    expect(state.items.map((i) => i.kind)).toEqual(['tool', 'error'])
    expect(state.waiting).toEqual({})
  })

  it('shows a parked result when the person stops the reply', () => {
    const state = finishTurn(run([result('gone', false, 'no')]), 'stopped')
    expect(state.items.map((i) => i.kind)).toEqual(['tool', 'note'])
    expect(state.waiting).toEqual({})
  })

  it('still prefers the real tool line when one arrives first', () => {
    const state = run([result('t1', true, 'on main'), tool('t1', 'Bash', 'git log'), done(true)])
    const tools = state.items.filter((i) => i.kind === 'tool')
    expect(tools).toHaveLength(1)
    expect(tools[0]).toMatchObject({ name: 'Bash', summary: 'git log', status: 'ok' })
  })
})

describe('done.changed', () => {
  const changed = (events: ChatEvent[]) => {
    const last = run(events).items.filter((i) => i.kind === 'done')[0]
    return last && last.kind === 'done' ? last.changed : null
  }

  it('is true when a tool that can write ran and worked', () => {
    expect(changed([tool('t1', 'Edit', 'AGENTS.md'), result('t1', true, 'ok'), done(true)])).toBe(true)
    expect(changed([tool('t1', 'Bash', 'git commit'), result('t1', true, 'ok'), done(true)])).toBe(true)
    expect(changed([tool('t1', 'Write', 'note.md'), result('t1', true, 'ok'), done(true)])).toBe(true)
  })

  it('is false when only reading tools ran', () => {
    expect(changed([tool('t1', 'Read', 'AGENTS.md'), result('t1', true, 'ok'), done(true)])).toBe(false)
    expect(changed([tool('t1', 'Grep', 'row'), result('t1', true, 'hit'), done(true)])).toBe(false)
  })

  it('is false when the writing tool failed or was refused', () => {
    expect(changed([tool('t1', 'Bash', 'git commit'), result('t1', false, 'no'), done(true)])).toBe(false)
    expect(changed([
      tool('t1', 'Bash', 'brew list'),
      done(true, [{ id: 't1', tool: 'Bash', summary: 'brew list' }]),
    ])).toBe(false)
  })

  it('is false when no tool ran at all', () => {
    expect(changed([{ kind: 'text', delta: 'just words' }, done(true)])).toBe(false)
  })

  it('reads only the turn that just ended', () => {
    const first = run([tool('t1', 'Write', 'note.md'), result('t1', true, 'ok'), done(true)])
    const second = [{ kind: 'text', delta: 'no tools' } as ChatEvent, done(true)]
      .reduce(applyEvent, addUser(first, 'next question'))
    const dones = second.items.filter((i) => i.kind === 'done')
    expect(dones.map((d) => (d.kind === 'done' ? d.changed : null))).toEqual([true, false])
  })
})

describe('the item cap', () => {
  it('keeps the newest items and drops the oldest', () => {
    let state = newTranscript()
    for (let i = 0; i < ITEM_CAP + 5; i += 1) state = addUser(state, `message ${i}`)
    expect(state.items).toHaveLength(ITEM_CAP)
    expect(state.items[0]).toEqual({ kind: 'user', text: 'message 5' })
    expect(state.items[ITEM_CAP - 1]).toEqual({ kind: 'user', text: `message ${ITEM_CAP + 4}` })
  })

  it('counts what it dropped, so every item keeps the key it was drawn under', () => {
    let state = newTranscript()
    for (let i = 0; i < ITEM_CAP; i += 1) state = addUser(state, `message ${i}`)
    expect(state.base).toBe(0)
    const key = keyOf(state, 10)
    for (let i = 0; i < 5; i += 1) state = addUser(state, `more ${i}`)
    expect(state.base).toBe(5)
    // The item that was at index 10 is now at index 5, under the same key.
    expect(state.items[5]).toEqual({ kind: 'user', text: 'message 10' })
    expect(keyOf(state, 5)).toBe(key)
  })

  it('keeps counting through every kind of change, not only a new message', () => {
    let state = newTranscript()
    for (let i = 0; i < ITEM_CAP; i += 1) state = addUser(state, `message ${i}`)
    state = applyEvent(state, { kind: 'text', delta: 'reply' })
    state = addItem(state, { kind: 'note', text: 'moved', stopped: false })
    expect(state.base).toBe(2)
    expect(state.items).toHaveLength(ITEM_CAP)
    expect(state.items[ITEM_CAP - 1]).toEqual({ kind: 'note', text: 'moved', stopped: false })
  })

  it('starts a restored transcript from zero, after capping what was stored', () => {
    const many: Item[] = Array.from({ length: ITEM_CAP + 3 }, (_, i) => ({ kind: 'user', text: `m${i}` }))
    const state = newTranscript(many)
    expect(state.items).toHaveLength(ITEM_CAP)
    expect(keyOf(state, 0)).toBe(state.base)
  })
})

describe('resendOffer', () => {
  const cut = (message: string) => applyEvent(addUser(newTranscript(), message), { kind: 'text', delta: 'part of a reply' })

  it('offers the message of a turn that never finished', () => {
    expect(resendOffer(cut('write my check-in'), 'write my check-in')).toBe('write my check-in')
  })

  it('offers nothing once that turn finished', () => {
    const finished = applyEvent(addUser(newTranscript(), 'write my check-in'), done(true))
    expect(resendOffer(finished, 'write my check-in')).toBeNull()
  })

  it('offers nothing when a later turn has come and gone', () => {
    const later = applyEvent(addUser(cut('the old one'), 'a new question'), done(true))
    expect(resendOffer(later, 'the old one')).toBeNull()
  })

  it('offers nothing when the stored message is not that turn"s message', () => {
    expect(resendOffer(cut('write my check-in'), 'something else')).toBeNull()
  })

  it('offers nothing when nothing is stored', () => {
    expect(resendOffer(cut('write my check-in'), null)).toBeNull()
    expect(resendOffer(cut('write my check-in'), '')).toBeNull()
  })

  it('offers nothing on an empty transcript', () => {
    expect(resendOffer(newTranscript(), 'anything')).toBeNull()
  })
})

describe('validItems', () => {
  it('keeps items of every known kind', () => {
    const items: Item[] = [
      { kind: 'user', text: 'hi' },
      { kind: 'assistant', text: 'hello' },
      { kind: 'tool', id: 't1', name: 'Bash', summary: 'git log', status: 'ok', result: 'on main', writes: false },
      { kind: 'refusals', denied: [{ id: 'a', tool: 'Bash', summary: 'brew list' }] },
      { kind: 'error', text: 'boom' },
      { kind: 'done', ok: true, turns: 1, ms: 10, changed: false },
      { kind: 'note', text: 'stopped', stopped: true },
    ]
    expect(validItems(items)).toEqual(items)
  })

  it('drops anything that is not one of them', () => {
    expect(validItems([{ kind: 'script', text: 'x' }, { kind: 'user', text: 'kept' }]))
      .toEqual([{ kind: 'user', text: 'kept' }])
  })

  it('drops an item whose fields are the wrong type', () => {
    expect(validItems([
      { kind: 'user', text: 42 },
      { kind: 'tool', id: 't1', name: 'Bash', summary: 'x', status: 'exploded', result: '' },
      { kind: 'done', ok: 'yes', turns: 1, ms: 1, changed: false },
    ])).toEqual([])
  })

  it('drops a refusal list that is not a list of refusals', () => {
    expect(validItems([{ kind: 'refusals', denied: 'lots' }])).toEqual([])
    expect(validItems([{ kind: 'refusals', denied: [{ id: 1 }] }])).toEqual([])
  })

  it('reads anything that is not a list as nothing', () => {
    expect(validItems('[]')).toEqual([])
    expect(validItems(null)).toEqual([])
    expect(validItems({ items: [] })).toEqual([])
  })

  it('keeps at most the cap', () => {
    const many = Array.from({ length: ITEM_CAP + 10 }, (_, i) => ({ kind: 'user', text: `m${i}` }))
    const kept = validItems(many)
    expect(kept).toHaveLength(ITEM_CAP)
    expect(kept[0]).toEqual({ kind: 'user', text: 'm10' })
  })
})

describe('statusOf tone', () => {
  it('is green when nothing is happening', () => {
    expect(statusOf(newTranscript(), { live: false })).toEqual({ text: 'Ready', tone: 'ready' })
  })

  it('is the thinking tone while a reply is being written', () => {
    expect(statusOf(addUser(newTranscript(), 'hi'), { live: true }))
      .toEqual({ text: 'Thinking...', tone: 'thinking' })
  })

  it('is the running tone while a tool runs', () => {
    expect(statusOf(run([tool('t1', 'Bash', 'git log')]), { live: true }))
      .toEqual({ text: 'Running: Bash', tone: 'running' })
  })

  it('is the refused tone after a refusal', () => {
    const state = run([done(true, [{ id: 'a', tool: 'Bash', summary: 'brew list' }])])
    expect(statusOf(state, { live: false })).toEqual({ text: 'Refused 1 action', tone: 'refused' })
  })

  it('is the error tone when the turn ended in an error', () => {
    expect(statusOf(run([{ kind: 'error', message: 'boom' }]), { live: false }))
      .toEqual({ text: 'Something went wrong', tone: 'error' })
  })

  it('is the stopped tone after a stop', () => {
    const state = finishTurn(run([{ kind: 'text', delta: 'part' }]), 'stopped')
    expect(statusOf(state, { live: false })).toEqual({ text: 'Stopped', tone: 'stopped' })
  })

  it('says the message never left when the server refused to take it', () => {
    const state = run([done(true, [{ id: 'a', tool: 'Bash', summary: 'brew list' }])])
    expect(statusOf(state, { live: false, notSent: true })).toEqual({ text: 'Not sent', tone: 'not-sent' })
  })

  it('lets a live run win over a message that was not sent', () => {
    expect(statusOf(newTranscript(), { live: true, notSent: true }).text).toBe('Thinking...')
  })
})

describe('fix round 1 follow-ups', () => {
  it('marks a parked result that was refused as refused, not failed', () => {
    const state = run([
      result('gone', false, 'Permission for this tool use was denied.'),
      done(true, [{ id: 'gone', tool: 'Bash', summary: 'brew list' }]),
    ])
    expect(state.items.map((i) => i.kind)).toEqual(['tool', 'refusals', 'done'])
    expect(state.items[0]).toMatchObject({ id: 'gone', status: 'refused' })
  })

  it('gives a flushed line its name when the call turns up after a mid-stream error', () => {
    // The server's "some reply text was dropped" notice is an error event that the
    // rest of the run follows, so a call can still arrive after its result was shown.
    const state = run([
      result('t1', true, 'on main'),
      { kind: 'error', message: 'Some reply text was dropped because the reply was too long to keep.' },
      tool('t1', 'Bash', 'git log'),
      done(true),
    ])
    const tools = state.items.filter((i) => i.kind === 'tool')
    expect(tools).toHaveLength(1)
    expect(tools[0]).toMatchObject({ name: 'Bash', summary: 'git log', status: 'ok', result: 'on main' })
  })

  it('adds no second ending when the stream ends after an error with a result still parked', () => {
    const errored = run([{ kind: 'error', message: 'claude stopped without a reply (exit code 2). The server log has the details.' }])
    const parked = applyEvent(errored, result('late', false, 'no'))
    const state = finishTurn(parked, 'ended')
    expect(state.items.filter((i) => i.kind === 'error')).toHaveLength(1)
    expect(state.items.map((i) => i.kind)).toEqual(['error', 'tool'])
  })
})

describe('errorText', () => {
  it('names where the server log is when an error points at it', () => {
    expect(errorText('Could not start claude. The server log has the details.'))
      .toBe('Could not start claude. The server log has the details: /tmp/pfc-web.log')
  })

  it('leaves every other error as it came', () => {
    expect(errorText('Some reply text was dropped because the reply was too long to keep.'))
      .toBe('Some reply text was dropped because the reply was too long to keep.')
  })
})

describe('drawer follow-ups', () => {
  const changed = (events: ChatEvent[]) => {
    const last = run(events).items.at(-1)
    return last && last.kind === 'done' ? last.changed : null
  }

  it('does not count a Bash command that only reads as a change', () => {
    expect(changed([tool('t1', 'Bash', 'git log --oneline -1'), result('t1', true, 'abc'), done(true)])).toBe(false)
    expect(changed([tool('t1', 'Bash', "TZ=America/Denver date '+%Y-%m-%d'"), result('t1', true, 'x'), done(true)])).toBe(false)
    expect(changed([tool('t1', 'Bash', 'jq -c . 6-tasks/_data/tasks.ndjson | head -3'), result('t1', true, 'x'), done(true)])).toBe(false)
    expect(changed([tool('t1', 'Bash', 'git status 2>&1'), result('t1', true, 'x'), done(true)])).toBe(false)
  })

  it('counts a Bash command that writes as a change', () => {
    expect(changed([
      tool('t1', 'Bash', "jq 'del(.x)' data/a.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp data/a.ndjson"),
      result('t1', true, ''), done(true),
    ])).toBe(true)
    expect(changed([tool('t1', 'Bash', 'git commit -m x'), result('t1', true, 'ok'), done(true)])).toBe(true)
    expect(changed([tool('t1', 'Bash', 'echo x >> notes/a.md'), result('t1', true, ''), done(true)])).toBe(true)
  })

  it('still counts Edit, Write, and NotebookEdit as a change', () => {
    expect(changed([tool('t1', 'NotebookEdit', 'a.ipynb'), result('t1', true, 'ok'), done(true)])).toBe(true)
  })

  it('reads the writes flag on the tool event, never the summary', () => {
    // The summary is cut at 160 characters, so a write late in a long command is
    // not in it: the flag was computed from the whole command before the cut.
    expect(changed([tool('t1', 'Bash', 'jq -c . a.ndjson | head -3 && ...', true), result('t1', true, ''), done(true)])).toBe(true)
    expect(changed([tool('t1', 'Bash', 'git commit -m x', false), result('t1', true, ''), done(true)])).toBe(false)
  })

  it('reads a stored tool line with no writes field as one that did not write', () => {
    const kept = validItems([{ kind: 'tool', id: 't1', name: 'Bash', summary: 'git commit', status: 'ok', result: '' }])
    expect(kept).toEqual([{ kind: 'tool', id: 't1', name: 'Bash', summary: 'git commit', status: 'ok', result: '', writes: false }])
  })

  it('reads Not sent, not the refusals, when a refused message follows a turn with refusals, after a reload', () => {
    const refusedTurn = applyEvent(addUser(newTranscript(), 'first'), done(true, [{ id: 'a', tool: 'Bash', summary: 'brew list' }]))
    const withError = { ...refusedTurn, items: [...refusedTurn.items, { kind: 'error' as const, text: 'That message is too long.' }] }
    const reloaded = newTranscript(validItems(JSON.parse(JSON.stringify(withError.items))), null)
    expect(statusOf(reloaded, { live: false })).toEqual({ text: 'Not sent', tone: 'not-sent' })
  })

  it('reads Not sent for an error after a stopped turn', () => {
    const stopped = finishTurn(addUser(newTranscript(), 'first'), 'stopped')
    const withError = { ...stopped, items: [...stopped.items, { kind: 'error' as const, text: 'Could not reach the local server.' }] }
    expect(statusOf(withError, { live: false }).text).toBe('Not sent')
  })

  it('takes back a message the server never accepted', () => {
    const sent = addUser(applyEvent(addUser(newTranscript(), 'first'), done(true)), 'second')
    const back = dropUser(sent, 'second')
    expect(back.items.map((i) => i.kind)).toEqual(['user', 'done'])
  })

  it('leaves the transcript alone when its last line is not that message', () => {
    const sent = addUser(newTranscript(), 'first')
    expect(dropUser(sent, 'other')).toBe(sent)
    const answered = applyEvent(sent, { kind: 'text', delta: 'hi' })
    expect(dropUser(answered, 'first')).toBe(answered)
  })

  it('offers the message again after a leave before the run started', () => {
    const left = addUser(newTranscript(), 'send me')
    expect(resendOffer(left, 'send me')).toBe('send me')
  })
})
