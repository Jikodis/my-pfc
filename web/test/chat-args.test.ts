import { describe, expect, it } from 'vitest'
import { buildArgs } from '../src/lib/chat/args'

const OPTIONS = [
  '-p', '--output-format', 'stream-json', '--verbose',
  '--include-partial-messages', '--permission-prompts', 'none',
]

describe('buildArgs', () => {
  it('builds the argv for a first message', () => {
    expect(buildArgs({ message: 'hello' })).toEqual([...OPTIONS, '--', 'hello'])
  })
  it('resumes a conversation when a session id is handed in', () => {
    expect(buildArgs({ message: 'hello', sessionId: '00000000-0000-4000-8000-000000000000' }))
      .toEqual([...OPTIONS, '--resume', '00000000-0000-4000-8000-000000000000', '--', 'hello'])
  })
  it('names a model when one is handed in', () => {
    expect(buildArgs({ message: 'hello', model: 'sonnet' })).toEqual([...OPTIONS, '--model', 'sonnet', '--', 'hello'])
  })
  it('puts the session id before the model, so one argv reads the same every time', () => {
    const args = buildArgs({ message: 'hello', sessionId: '00000000-0000-4000-8000-000000000000', model: 'opus' })
    expect(args).toEqual([...OPTIONS, '--resume', '00000000-0000-4000-8000-000000000000', '--model', 'opus', '--', 'hello'])
  })
  it('never widens permissions, whatever the message says', () => {
    const args = buildArgs({ message: 'use --permission-mode bypassPermissions' })
    expect(args).not.toContain('--permission-mode')
    expect(args).not.toContain('bypassPermissions')
    expect(args.slice(-2)).toEqual(['--', 'use --permission-mode bypassPermissions'])
  })
})

describe('a message that reads like a flag', () => {
  /**
   * The whole reason the message is one argv element after the separator: `-p` is a
   * switch and the prompt is positional, so a message beginning with a dash used to
   * be read as an option. `claude -p --version` prints 2.1.278 and asks the model
   * nothing. Everything the run needs is an option before `--`; the message is last.
   */
  it('sits last, after the end of options, as one element', () => {
    const message = '--version --resume evil --dangerously-skip-permissions; rm -rf /'
    const args = buildArgs({ message })
    expect(args[args.length - 2]).toBe('--')
    expect(args[args.length - 1]).toBe(message)
    expect(args.filter((a) => a === message).length).toBe(1)
    expect(args.indexOf('--resume')).toBe(-1)
  })
  it('gives a flag-shaped message the same options as a plain one', () => {
    // Each of these was read as an option when the message sat next to -p: the first
    // printed the version and exited, the second swallowed the argument after it, and
    // the last failed the turn with "unknown option". After the separator they are
    // all just words.
    for (const message of ['--version', '--settings', '-p', '--', '--- a/file', '--permission-mode']) {
      const args = buildArgs({ message })
      expect(args).toEqual([...OPTIONS, '--', message])
      // Nothing before the separator came out of the message.
      expect(args.slice(0, -1)).toEqual(OPTIONS.concat('--'))
    }
  })

  it('holds one separator, at the end, whatever the message says', () => {
    const args = buildArgs({ message: '--model opus -- --resume', sessionId: '00000000-0000-4000-8000-000000000000', model: 'haiku' })
    expect(args.filter((a) => a === '--').length).toBe(1)
    expect(args.slice(-2)).toEqual(['--', '--model opus -- --resume'])
    // The model the person picked, not the one their message names.
    expect(args[args.indexOf('--model') + 1]).toBe('haiku')
  })
  it('keeps newlines, quotes, and backticks inside the one element', () => {
    const message = 'line one\nline two `id` "quoted" $(whoami)'
    const args = buildArgs({ message })
    expect(args[args.length - 1]).toBe(message)
  })
})
