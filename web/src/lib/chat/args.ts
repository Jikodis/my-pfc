/**
 * The argv for one `claude -p` run.
 *
 * An array, never a string: the message is one element handed straight to
 * `spawn`, so a message reading `--resume evil` or `; rm -rf /` is a message and
 * not a flag and not a command. Nothing here ever widens permissions.
 */
export type ArgOptions = {
  message: string
  /** Set to continue an existing conversation. The guard has already checked its shape. */
  sessionId?: string
  /** Set only when the person picked one. The guard has already checked it is a name we allow. */
  model?: string
}

export function buildArgs(o: ArgOptions): string[] {
  return [
    // -p is a switch, not an option that takes a value: `claude --help` prints
    // `Usage: claude [options] [command] [prompt]` and lists `-p, --print` with no
    // value of its own, so the message is the positional prompt. Put next to -p it
    // was still read as a flag when it began with a dash: `claude -p --version`
    // prints the version and never asks the model anything.
    '-p',
    '--output-format', 'stream-json',
    '--verbose',
    '--include-partial-messages',
    // Always. The session follows .claude/settings.json, and anything off the allow
    // list comes back as a refusal the drawer shows rather than a prompt nobody can answer.
    '--permission-prompts', 'none',
    ...(o.sessionId ? ['--resume', o.sessionId] : []),
    ...(o.model ? ['--model', o.model] : []),
    // Every option is above, so nothing after the separator is read as one. The
    // message is last, alone, one argv element, never split or quoted.
    '--', o.message,
  ]
}
