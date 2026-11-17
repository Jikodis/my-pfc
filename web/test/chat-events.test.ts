/**
 * The parser against output shaped like the real thing. `test/fixtures/chat/sample.jsonl`
 * holds eight lines in the format of one `claude -p --output-format stream-json --verbose
 * --include-partial-messages` run, with synthetic ids and no home paths.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { type ChatEvent, parseLine, summarizeInput, writesFiles } from '../src/lib/chat/events'
import { REPO } from '../src/lib/repo'

const FIXTURE = readFileSync(join(REPO, 'chat', 'sample.jsonl'), 'utf8')
const LINES = FIXTURE.split('\n').filter((l) => l.length > 0)
const [INIT, DELTA, TOOL_USE, TOOL_RESULT, DENIED_RESULT, RESULT, HOOK, NOT_JSON] = LINES

const line = (o: unknown) => JSON.stringify(o)

describe('parseLine on nothing it can use', () => {
  it('has no events for a blank line', () => {
    expect(parseLine('')).toEqual([])
    expect(parseLine('   ')).toEqual([])
  })
  it('has no events for a line that is not JSON, rather than throwing', () => {
    expect(parseLine(NOT_JSON)).toEqual([])
    expect(parseLine('{"type":"result"')).toEqual([])
  })
  it('has no events for JSON that is not an object', () => {
    for (const text of ['42', 'null', 'true', '"x"', '[]', '[{"type":"result"}]']) {
      expect(parseLine(text)).toEqual([])
    }
  })
  it('has no events for an object with no type, or a type it does not know', () => {
    expect(parseLine('{}')).toEqual([])
    expect(parseLine(line({ type: 'rate_limit_event', status: 'ok' }))).toEqual([])
    expect(parseLine(line({ type: 'something_new' }))).toEqual([])
  })
  it('has no events for a system line that is not the init line', () => {
    expect(parseLine(HOOK)).toEqual([])
    expect(parseLine(line({ type: 'system', subtype: 'status' }))).toEqual([])
    expect(parseLine(line({ type: 'system', subtype: 'permission_denied', tool_name: 'Bash' }))).toEqual([])
  })
})

describe('parseLine on the session line', () => {
  it('reads the session id and the model, which is how a follow-up resumes', () => {
    expect(parseLine(INIT)).toEqual([
      { kind: 'session', id: '00000000-0000-4000-8000-000000000000', model: 'claude-sonnet-5' },
    ])
  })
})

describe('parseLine on a stream event', () => {
  it('reads the text of a text delta', () => {
    expect(parseLine(DELTA)).toEqual([{ kind: 'text', delta: '`git log`' }])
  })
  it('ignores every other kind of delta, so thinking and tool input never reach the page', () => {
    const delta = (d: unknown) => line({ type: 'stream_event', event: { type: 'content_block_delta', index: 0, delta: d } })
    expect(parseLine(delta({ type: 'thinking_delta', thinking: 'weighing it up' }))).toEqual([])
    expect(parseLine(delta({ type: 'input_json_delta', partial_json: '{"com' }))).toEqual([])
    expect(parseLine(delta({ type: 'signature_delta', signature: 'abc' }))).toEqual([])
  })
  it('ignores every other kind of stream event', () => {
    for (const type of ['content_block_start', 'content_block_stop', 'message_start', 'message_delta', 'message_stop']) {
      expect(parseLine(line({ type: 'stream_event', event: { type } }))).toEqual([])
    }
  })
})

describe('parseLine on an assistant message', () => {
  it('reports one tool call per tool_use block, summarized', () => {
    expect(parseLine(TOOL_USE)).toEqual([
      { kind: 'tool', id: 'toolu_01Example0000000000001', name: 'Bash', summary: 'git log --oneline -1', writes: false },
    ])
  })
  it('ignores text and thinking blocks, because that text already arrived as deltas', () => {
    const content = [
      { type: 'thinking', thinking: 'weighing it up' },
      { type: 'text', text: 'Reading the file now.' },
      { type: 'tool_use', id: 'toolu_a', name: 'Read', input: { file_path: '/repo/AGENTS.md' } },
    ]
    expect(parseLine(line({ type: 'assistant', message: { role: 'assistant', content } }))).toEqual([
      { kind: 'tool', id: 'toolu_a', name: 'Read', summary: '/repo/AGENTS.md', writes: false },
    ])
  })
  it('has no events when the content is a plain string rather than blocks', () => {
    expect(parseLine(line({ type: 'assistant', message: { role: 'assistant', content: 'Done.' } }))).toEqual([])
    expect(parseLine(line({ type: 'assistant', message: { role: 'assistant' } }))).toEqual([])
    expect(parseLine(line({ type: 'assistant' }))).toEqual([])
  })
})

describe('parseLine on a tool result', () => {
  it('reads a result that worked', () => {
    expect(parseLine(TOOL_RESULT)).toEqual([{
      kind: 'tool_result',
      id: 'toolu_01Example0000000000001',
      ok: true,
      text: 'abc1234 Initial commit',
    }])
  })
  it('marks a refused tool call as failed and keeps what it said', () => {
    const events = parseLine(DENIED_RESULT)
    expect(events.length).toBe(1)
    expect(events[0]).toMatchObject({ kind: 'tool_result', id: 'toolu_01Example0000000000002', ok: false })
    expect((events[0] as { text: string }).text).toContain('Permission for this tool use was denied')
  })
  it('treats a missing is_error as a result that worked', () => {
    const content = [{ type: 'tool_result', tool_use_id: 'toolu_a', content: 'fine' }]
    expect(parseLine(line({ type: 'user', message: { role: 'user', content } }))).toEqual([
      { kind: 'tool_result', id: 'toolu_a', ok: true, text: 'fine' },
    ])
  })
  it('joins the text blocks when the content is a list rather than a string', () => {
    const content = [{
      type: 'tool_result',
      tool_use_id: 'toolu_a',
      content: [{ type: 'text', text: 'first' }, { type: 'image', source: {} }, { type: 'text', text: 'second' }],
    }]
    expect(parseLine(line({ type: 'user', message: { role: 'user', content } }))).toEqual([
      { kind: 'tool_result', id: 'toolu_a', ok: true, text: 'first\nsecond' },
    ])
  })
  it('cuts a long result to two thousand characters', () => {
    const content = [{ type: 'tool_result', tool_use_id: 'toolu_a', content: 'x'.repeat(5000) }]
    const events = parseLine(line({ type: 'user', message: { role: 'user', content } })) as { text: string }[]
    expect(events[0].text.length).toBe(2000)
  })
  it('never cuts a character in half, however many of them are stored in two pieces', () => {
    // An emoji is stored as two code units, so cutting by stored length can leave
    // half of one behind, which renders as a box and breaks the JSON a page reads.
    const content = [{ type: 'tool_result', tool_use_id: 'toolu_a', content: '\u{1F600}'.repeat(3000) }]
    const events = parseLine(line({ type: 'user', message: { role: 'user', content } })) as { text: string }[]
    expect([...events[0].text].length).toBe(2000)
    expect(events[0].text.endsWith('\u{1F600}')).toBe(true)
    // No lone half of a pair anywhere in what is shown.
    expect(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(events[0].text)).toBe(false)
  })
  it('has no events when the content is a plain string rather than blocks', () => {
    expect(parseLine(line({ type: 'user', message: { role: 'user', content: 'hello' } }))).toEqual([])
  })
})

describe('parseLine on the result line', () => {
  it('reads the reply, the turns, the milliseconds, and every refused call', () => {
    expect(parseLine(RESULT)).toEqual([{
      kind: 'done',
      ok: true,
      text: '`git log` shows HEAD at `abc1234` (Initial commit); '
        + '`brew list --versions jq` was blocked — this session has no approval surface, so it was auto-denied and not run.',
      turns: 4,
      ms: 9068,
      denied: [
        { id: 'toolu_01Example0000000000003', tool: 'Bash', summary: 'git log --oneline -1 && brew list --versions jq' },
        { id: 'toolu_01Example0000000000002', tool: 'Bash', summary: 'brew list --versions jq' },
      ],
    }])
  })
  it('carries each refusal’s own tool id, so a page can mark the line it belongs to', () => {
    // The second refusal in the fixture is the one that also arrived as a failed
    // tool result; its id is the same on both, which is the join a page needs.
    const done = parseLine(RESULT)[0] as Extract<ChatEvent, { kind: 'done' }>
    const failed = parseLine(DENIED_RESULT)[0] as Extract<ChatEvent, { kind: 'tool_result' }>
    expect(done.denied.map((d) => d.id)).toContain(failed.id)
    // A refusal with no tool id still reads, with an empty one, because the list
    // stands on its own and a refusal can arrive with no tool line of its own.
    const bare = parseLine(line({
      type: 'result', subtype: 'success', permission_denials: [{ tool_name: 'Bash', tool_input: { command: 'id' } }],
    }))[0] as Extract<ChatEvent, { kind: 'done' }>
    expect(bare.denied).toEqual([{ id: '', tool: 'Bash', summary: 'id' }])
  })
  it('is not ok when the run errored, whichever field says so', () => {
    const done = (o: object) => parseLine(line({ type: 'result', subtype: 'success', ...o }))[0] as { ok: boolean }
    expect(done({ is_error: true }).ok).toBe(false)
    expect(done({ is_error: false }).ok).toBe(true)
    expect(parseLine(line({ type: 'result', subtype: 'error_during_execution' }))[0]).toMatchObject({ ok: false })
  })
  it('falls back to zeros and an empty list rather than undefined fields', () => {
    expect(parseLine(line({ type: 'result', subtype: 'success' }))).toEqual([
      { kind: 'done', ok: true, text: '', turns: 0, ms: 0, denied: [] },
    ])
  })
})

describe('the whole fixture', () => {
  it('turns eight real lines into exactly the events the drawer shows, in order', () => {
    const events = LINES.flatMap(parseLine)
    expect(events.map((e: ChatEvent) => e.kind)).toEqual([
      'session', 'text', 'tool', 'tool_result', 'tool_result', 'done',
    ])
    expect(events[0]).toEqual({ kind: 'session', id: '00000000-0000-4000-8000-000000000000', model: 'claude-sonnet-5' })
    expect(events[2]).toMatchObject({ kind: 'tool', name: 'Bash', summary: 'git log --oneline -1' })
    expect(events[3]).toMatchObject({ kind: 'tool_result', ok: true })
    expect(events[4]).toMatchObject({ kind: 'tool_result', ok: false })
    expect(events[5]).toMatchObject({ kind: 'done', ok: true, turns: 4, ms: 9068 })
  })
})

describe('summarizeInput', () => {
  it('shows the command for Bash', () => {
    expect(summarizeInput('Bash', { command: 'git status --short', description: 'Show the tree' })).toBe('git status --short')
  })
  it('shows the path for a file tool, relative to the repo when it sits inside it', () => {
    expect(summarizeInput('Read', { file_path: join(REPO, '6-tasks', 'AGENTS.md') })).toBe('6-tasks/AGENTS.md')
    expect(summarizeInput('Edit', { file_path: join(REPO, 'AGENTS.md') })).toBe('AGENTS.md')
    expect(summarizeInput('Write', { file_path: '/etc/hosts' })).toBe('/etc/hosts')
  })
  it('shows the skill and its arguments', () => {
    expect(summarizeInput('Skill', { skill: 'pfc-focus', args: 'show my focus' })).toBe('pfc-focus show my focus')
    expect(summarizeInput('Skill', { skill: 'pfc-status' })).toBe('pfc-status')
  })
  it('shows the pattern for a search tool', () => {
    expect(summarizeInput('Grep', { pattern: 'run_label', path: 'web' })).toBe('run_label')
    expect(summarizeInput('Glob', { pattern: '**/*.astro' })).toBe('**/*.astro')
  })
  it('falls back to the first string in the input for any other tool', () => {
    expect(summarizeInput('TodoWrite', { count: 3, note: 'three left' })).toBe('three left')
    expect(summarizeInput('Unknown', {})).toBe('')
    expect(summarizeInput('Unknown', null)).toBe('')
    expect(summarizeInput('Unknown', 'a bare string')).toBe('')
  })
  it('is always one line, cut to a hundred and sixty characters', () => {
    expect(summarizeInput('Bash', { command: 'echo one\necho two\r\necho three' })).toBe('echo one echo two echo three')
    const long = summarizeInput('Bash', { command: 'x'.repeat(400) })
    expect(long.length).toBe(160)
    expect(long).not.toContain('\n')
  })
})

describe('writesFiles', () => {
  const bash = (command: string) => writesFiles('Bash', { command })

  it('counts Edit, Write, and NotebookEdit as writes by name', () => {
    expect(writesFiles('Edit', { file_path: 'a.md' })).toBe(true)
    expect(writesFiles('Write', { file_path: 'a.md' })).toBe(true)
    expect(writesFiles('NotebookEdit', { notebook_path: 'a.ipynb' })).toBe(true)
    expect(writesFiles('Read', { file_path: 'a.md' })).toBe(false)
    expect(writesFiles('Grep', { pattern: 'x' })).toBe(false)
  })

  it('does not count a Bash command that only reads', () => {
    expect(bash('git log --oneline -1')).toBe(false)
    expect(bash("TZ=America/Denver date '+%Y-%m-%d'")).toBe(false)
    expect(bash('jq -c . 6-tasks/_data/tasks.ndjson | head -3')).toBe(false)
    expect(bash('git status 2>&1')).toBe(false)
    expect(bash('ls data 2>/dev/null')).toBe(false)
  })

  it('does not count a comparison as a redirect', () => {
    expect(bash("jq -c --arg w 2025-09-01 'select(.date >= $w)' 7-habits/_data/habits-daily.ndjson")).toBe(false)
    expect(bash("jq -c 'select(.rating > 3)' data/day-tracking.ndjson | wc -l")).toBe(false)
    expect(bash("awk '$2 >> 1' data/x.txt")).toBe(false)
    expect(bash('test "$n" >= 3')).toBe(false)
  })

  it('still counts a redirect after a quoted comparison', () => {
    expect(bash("jq -c 'select(.date >= $w)' a.ndjson > data/.jq_update.tmp")).toBe(true)
    expect(bash("jq -c 'select(.n > 1)' a.ndjson >> notes/b.md")).toBe(true)
  })

  it('counts a Bash command that writes', () => {
    expect(bash("jq 'del(.x)' data/a.ndjson > data/.jq_update.tmp && mv data/.jq_update.tmp data/a.ndjson")).toBe(true)
    expect(bash('git commit -m x')).toBe(true)
    expect(bash('echo x >> notes/a.md')).toBe(true)
  })

  it('counts the repo scripts that write records', () => {
    expect(bash('python3 automations/scripts/web_write.py complete-task task-20250901-001')).toBe(true)
    expect(bash('/opt/homebrew/bin/python3 automations/scripts/trello_writeback.py')).toBe(true)
    expect(bash('python3 automations/scripts/web_data.py')).toBe(false)
  })

  it('reads the whole command, not the summary cut to one line', () => {
    const command = `${'jq -c . 6-tasks/_data/tasks.ndjson | head -3 && '.repeat(5)}git commit -m done`
    expect(summarizeInput('Bash', { command })).not.toContain('git commit')
    expect(bash(command)).toBe(true)
  })

  it('puts the answer on the tool event', () => {
    const content = [{ type: 'tool_use', id: 'toolu_w', name: 'Bash', input: { command: 'git add a.md' } }]
    expect(parseLine(line({ type: 'assistant', message: { role: 'assistant', content } }))).toEqual([
      { kind: 'tool', id: 'toolu_w', name: 'Bash', summary: 'git add a.md', writes: true },
    ])
  })

  it('is false for an input that is not an object', () => {
    expect(writesFiles('Bash', null)).toBe(false)
    expect(writesFiles('Bash', 'git commit')).toBe(false)
  })
})
