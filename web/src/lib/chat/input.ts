/**
 * What a keystroke in the message box means.
 *
 * Separate from the drawer so the one decision that has bitten dictated text can be
 * tested without a keyboard.
 */

/** The parts of a keyboard event this reads. A real event satisfies it. */
export type KeyLike = {
  key: string
  shiftKey: boolean
  isComposing?: boolean
  keyCode?: number
}

/**
 * Whether this keystroke sends the message.
 *
 * Enter sends and Shift with Enter makes a new line, except while text is being
 * composed. Dictation and every non-Latin keyboard end a composition with Enter,
 * and treating that one as Send cuts the sentence off mid word. Browsers say so in
 * two ways, `isComposing` and the key code 229, and old ones only set the second.
 */
export function shouldSend(event: KeyLike): boolean {
  if (event.isComposing || event.keyCode === 229) return false
  return event.key === 'Enter' && !event.shiftKey
}

/**
 * The element a click hands the drawer a prompt from, or nothing.
 *
 * The page's `data-chat-prompt` hook acts only for a button, or something that says
 * it is one with `role="button"`. The attribute will sit on buttons inside table rows
 * that also hold links, so a click that landed on a link is always the link's, and a
 * link that carries the attribute itself is still a link.
 */
export function promptSource(target: EventTarget | null): HTMLElement | null {
  if (typeof Element === 'undefined' || !(target instanceof Element)) return null
  if (target.closest('a')) return null
  const source = target.closest('[data-chat-prompt]')
  if (!(source instanceof HTMLElement)) return null
  const isButton = source.tagName === 'BUTTON' || source.getAttribute('role') === 'button'
  return isButton ? source : null
}

/** What a page button does with its prompt. */
export type PromptAction = { text: string; send: boolean }

/** A slash command with nothing after it: `/pfc-stuck`, never `/pfc-revive Web UI`. */
const BARE_COMMAND = /^\/[a-z0-9-]+$/

/**
 * Whether a button's prompt is sent at once or only placed in the box.
 *
 * `send` is the button's `data-chat-send` and `typed` is what a box beside it holds,
 * when it has one. Only a bare slash command that asks for it (`data-chat-send="1"`)
 * sends: it names no record, so there is nothing for the person to check first.
 * Anything that names a record, anything with words after the command, and anything
 * built from a typed box is prefilled and waits for Send.
 */
export function promptAction(prompt: string, options: { send?: string; typed?: string }): PromptAction {
  if (options.typed !== undefined) return { text: `${prompt}${options.typed.trim()}`, send: false }
  const text = prompt.trim()
  return { text, send: options.send === '1' && BARE_COMMAND.test(text) }
}

/** The parts of a skill from `/api/chat/skills` that decide what its button does. */
export type SkillChoice = { name: string; takesArgs: boolean; prefill?: boolean }

/**
 * What a skill button in the drawer does.
 *
 * A skill that needs more words, or one marked prefill because it changes something
 * that cannot be taken back, puts `/name ` in the box and waits for Send. Anything
 * else sends at once. Always the real name, prefix and all: that is what the repo
 * calls it.
 */
export function skillAction(skill: SkillChoice): PromptAction {
  return skill.takesArgs || skill.prefill === true
    ? { text: `/${skill.name} `, send: false }
    : { text: `/${skill.name}`, send: true }
}
