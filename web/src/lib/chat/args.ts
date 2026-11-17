/**
 * The argv for one `claude -p` run.
 *
 * An array, never a string: the message is one element handed straight to
 * `spawn`, so a message reading `--resume evil` or `; rm -rf /` is a message and
 * not a flag and not a command. The permission mode is fixed here and nothing the
 * message says can widen it.
 */
export type ArgOptions = {
  message: string
  /** Set to continue an existing conversation. The guard has already checked its shape. */
  sessionId?: string
  /** Set only when the person picked one. The guard has already checked it is a name we allow. */
  model?: string
  /** The page the message was sent from, as the guard passed it: its title and path. */
  page?: string
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
    // Always, so the allow list does not have to grow one refused command at a
    // time: Claude Code's classifier approves routine actions and blocks
    // risky ones, and allow and deny rules still apply. Whatever it blocks comes back as
    // a refusal the drawer shows, rather than a prompt nobody can answer.
    '--permission-mode', 'auto',
    '--permission-prompts', 'none',
    ...(o.sessionId ? ['--resume', o.sessionId] : []),
    ...(o.model ? ['--model', o.model] : []),
    // The page goes in the system prompt, not the message, so a slash command such
    // as /pfc-focus still reaches its skill unchanged and the page cannot be read as
    // arguments to it.
    ...(o.page
      ? ['--append-system-prompt', `The user sent this message from the PFC web UI page "${o.page}". When they say "this page", "these" or "here", they mean what that page shows.`]
      : []),
    // Every option is above, so nothing after the separator is read as one. The
    // message is last, alone, one argv element, never split or quoted.
    '--', o.message,
  ]
}
