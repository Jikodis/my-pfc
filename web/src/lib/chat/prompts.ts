/**
 * The prompts the pages hand the drawer from a button.
 *
 * Kept in one place so the wording a button puts in the box is written once, and so
 * `pfc-repo-maintenance` and the tests can list every skill a page button starts.
 * A prompt that names a record is only ever placed in the box; the person reads it
 * and presses Send. Only a bare slash command may send at once (`promptAction`).
 */

/** Prompts that name a record. `{key}` is filled by `chatPrompt`. */
export const PROMPTS = {
  complete: 'Complete the task "{title}" ({id}).',
  handOff: 'Do this task for me, start to finish, then mark it complete: "{title}" ({id}).',
  logHabit: 'Log the habit {id} as done for today.',
  summarize: '/pfc-summarize-project {name}',
  revive: '/pfc-revive {name}',
  review: 'Run the rolling review "{label}" ({id}), then tell me what changed.',
  editQuestions: 'Help me edit my life questions in 0-me/questions.md: add, reword, or retire one. Ask me which.',
  rateAreas: "Walk me through rating my life wheel: each area's color and note.",
  updateVision: 'Help me update one of my visions in 3-visions/. Ask me which one and what changed.',
  addFocus: '/pfc-focus add a focus',
  repickFocus: '/pfc-focus re-pick focuses',
  editAnchor: 'Edit the Front-of-Mind anchor "{title}" ({id}). Ask me what to change.',
  addAnchor: 'Add a Front-of-Mind anchor. Ask me for the wording.',
} as const

/** What the quick-add box puts in front of the words typed into it. */
export const QUICK_ADD = 'add task: '

/**
 * Skills with nothing to add. A page button sends one at once only when it says so
 * with `data-chat-send="1"`; `/pfc-focus` changes the focus list, so its button only
 * fills the box.
 */
export const COMMANDS = {
  pickTasks: '/pfc-pick-tasks',
  stuck: '/pfc-stuck',
  focus: '/pfc-focus',
  planOpenDay: '/pfc-plan-open-day',
  visionBrainstorm: '/pfc-vision-brainstorm',
} as const

/**
 * A template with each `{key}` replaced by that value from the record.
 *
 * One pass, so a title that itself holds `{id}` stays as typed. A value is written
 * on one line, because a newline inside a title would read as a second paragraph of
 * the request. Quotes and angle brackets pass through untouched: Astro escapes the
 * whole string when it becomes an attribute, and the browser hands it back intact.
 * A placeholder with no value throws, so a page cannot put a prompt with a hole in
 * it in front of the person.
 */
export function chatPrompt(template: string, record: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const value = record[key]
    if (value === undefined) throw new Error(`chatPrompt: no value for {${key}}`)
    return value.replace(/\s+/g, ' ').trim()
  })
}

/** Every skill a page button starts, by its full name, sorted. */
export function promptSkills(): string[] {
  const names = [...Object.values(PROMPTS), ...Object.values(COMMANDS)]
    .map((p) => /^\/([a-z0-9-]+)/.exec(p)?.[1])
    .filter((n): n is string => Boolean(n))
  return [...new Set(names)].sort()
}
