/**
 * One line of `claude -p --output-format stream-json --verbose
 * --include-partial-messages` turned into the events the chat drawer shows.
 *
 * The shapes here were read off a real run, kept in
 * `test/fixtures/chat/sample.jsonl`. Nothing here decides anything about the repo:
 * it reshapes a line of another program's output, and it never throws, because a
 * line the parser cannot read must cost a message, not the whole stream.
 */
import { REPO } from '../repo'

export type ChatEvent =
  | { kind: 'session'; id: string; model: string }
  | { kind: 'text'; delta: string }
  /** `writes` says the call can change a file, read off its whole input (`writesFiles`). */
  | { kind: 'tool'; id: string; name: string; summary: string; writes: boolean }
  | { kind: 'tool_result'; id: string; ok: boolean; text: string }
  /**
   * `denied` carries each refused call's own `tool_use_id`, so a page can mark the
   * tool line it belongs to rather than printing the refusal a second time. A
   * refusal can also arrive with no tool line of its own, so an id that matches
   * nothing on screen is normal and the list still stands by itself.
   */
  | { kind: 'done'; ok: boolean; text: string; turns: number; ms: number; denied: { id: string; tool: string; summary: string }[] }
  | { kind: 'error'; message: string }

/** A tool result can be a whole file, and the drawer shows it as plain text. */
const RESULT_LIMIT = 2_000

/** One line in a list of tool calls, so a long command never breaks the layout. */
const SUMMARY_LIMIT = 160

type Obj = Record<string, unknown>

const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v)
const str = (v: unknown): string => (typeof v === 'string' ? v : '')
const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
const obj = (v: unknown): Obj => (isObj(v) ? v : {})
const blocks = (v: unknown): Obj[] => (Array.isArray(v) ? v.filter(isObj) : [])

/** Repo-relative when the path sits inside the repo, because the repo root is the same on every line. */
function shortPath(path: string): string {
  const root = `${REPO}/`
  return path.startsWith(root) ? path.slice(root.length) : path
}

/** The tools that always leave the repo different from how they found it. */
const WRITING_TOOLS = new Set(['Edit', 'Write', 'NotebookEdit'])

/**
 * A shell command that writes: a commit or staging change, a redirect into a file,
 * a command that makes, moves, copies, or removes one, or one of the repo scripts
 * that change records. Skills run Bash for the date and for `jq` reads on nearly
 * every turn, so counting every Bash call as a change offered a reload after almost
 * every reply.
 */
const WRITING_COMMAND =
  /\bgit (commit|add|mv|rm)\b|\btee\b|\bmv\b|\brm\b|\bcp\b|\bmkdir\b|\btouch\b|\bsed -i\b|\bpython3 automations\/scripts\/(web_write|trello_writeback)\b/

/**
 * A redirect into a file. It is matched against the command with its single-quoted
 * text blanked out, because `jq 'select(.date >= $w)'` and `awk '$2 > 1'` compare
 * rather than redirect. A `>` followed by `=` is a comparison too. A redirect that
 * only merges streams (`2>&1`) or throws output away (`2>/dev/null`) is not a write.
 */
const REDIRECT = />>|(^|[^>])>(?![&=])\s*(?!\/dev\/null)\S/
const SINGLE_QUOTED = /'[^']*'/g

/**
 * Whether a tool call can change a file.
 *
 * Read from the whole input, never from `summarizeInput`'s line: that is cut at
 * 160 characters, and a commit at the end of a long command is past the cut.
 */
export function writesFiles(name: string, input: unknown): boolean {
  if (WRITING_TOOLS.has(name)) return true
  if (name !== 'Bash') return false
  const command = str(obj(input).command)
  return WRITING_COMMAND.test(command) || REDIRECT.test(command.replace(SINGLE_QUOTED, "''"))
}

/** The first string value the input carries, which is the best guess for a tool with no rule here. */
function firstString(input: Obj): string {
  for (const value of Object.values(input)) {
    if (typeof value === 'string' && value) return value
  }
  return ''
}

/**
 * What a tool call did, in one line: the command, the file, the skill, or the pattern.
 *
 * Never the whole input object. A person scanning the drawer wants to know which
 * command ran, and an input rendered as JSON buries that in quoting.
 */
export function summarizeInput(name: string, input: unknown): string {
  const i = obj(input)
  let text: string
  switch (name) {
    case 'Bash':
      text = str(i.command)
      break
    case 'Read':
    case 'Edit':
    case 'Write':
      text = shortPath(str(i.file_path))
      break
    case 'Skill':
      text = [str(i.skill), str(i.args)].filter(Boolean).join(' ')
      break
    case 'Grep':
    case 'Glob':
      text = str(i.pattern)
      break
    default:
      text = firstString(i)
  }
  return cut(text.replace(/\s+/g, ' ').trim(), SUMMARY_LIMIT)
}

/**
 * Cut to a length in characters people would count, not in the units a string is
 * stored in. `slice` counts code units, so a cut can land between the two halves of
 * an emoji and leave half a character that renders as a replacement box.
 */
function cut(text: string, limit: number): string {
  if (text.length <= limit) return text
  return [...text].slice(0, limit).join('')
}

/** A tool result is a string, or a list of blocks of which only the text ones read as words. */
function resultText(content: unknown): string {
  const text = typeof content === 'string'
    ? content
    : blocks(content).filter((b) => b.type === 'text').map((b) => str(b.text)).join('\n')
  return cut(text, RESULT_LIMIT)
}

function fromAssistant(message: Obj): ChatEvent[] {
  return blocks(message.content)
    .filter((b) => b.type === 'tool_use')
    // Text blocks are skipped: the same words already arrived as deltas, and a
    // thinking block is not the drawer's to show.
    .map((b) => ({
      kind: 'tool' as const,
      id: str(b.id),
      name: str(b.name),
      summary: summarizeInput(str(b.name), b.input),
      writes: writesFiles(str(b.name), b.input),
    }))
}

function fromUser(message: Obj): ChatEvent[] {
  return blocks(message.content)
    .filter((b) => b.type === 'tool_result')
    .map((b) => ({
      kind: 'tool_result' as const,
      id: str(b.tool_use_id),
      // A result with no is_error field is a result that worked.
      ok: b.is_error !== true,
      text: resultText(b.content),
    }))
}

function fromResult(row: Obj): ChatEvent[] {
  const denials = Array.isArray(row.permission_denials) ? row.permission_denials.filter(isObj) : []
  return [{
    kind: 'done',
    ok: row.is_error !== true && row.subtype === 'success',
    text: str(row.result),
    turns: num(row.num_turns),
    ms: num(row.duration_ms),
    denied: denials.map((d) => ({
      id: str(d.tool_use_id),
      tool: str(d.tool_name),
      summary: summarizeInput(str(d.tool_name), d.tool_input),
    })),
  }]
}

/**
 * Every event one line carries, which is usually none or one.
 *
 * A line the parser cannot read gives an empty list rather than an exception: the
 * stream is another program's output, a partial line can arrive at any moment, and
 * one unreadable line must not end a conversation.
 */
export function parseLine(line: string): ChatEvent[] {
  if (!line.trim()) return []
  let row: unknown
  try {
    row = JSON.parse(line)
  } catch {
    return []
  }
  if (!isObj(row)) return []

  switch (row.type) {
    case 'system':
      // Only the init line says anything the drawer needs. Every other subtype,
      // the hook lines, the status lines, and the permission_denied notice, is
      // already covered: a refusal reaches the page as a failed tool result and
      // again in the result line's denied list.
      return row.subtype === 'init'
        ? [{ kind: 'session', id: str(row.session_id), model: str(row.model) }]
        : []
    case 'stream_event': {
      const event = obj(row.event)
      const delta = obj(event.delta)
      return event.type === 'content_block_delta' && delta.type === 'text_delta'
        ? [{ kind: 'text', delta: str(delta.text) }]
        : []
    }
    case 'assistant':
      return fromAssistant(obj(row.message))
    case 'user':
      return fromUser(obj(row.message))
    case 'result':
      return fromResult(row)
    default:
      return []
  }
}
