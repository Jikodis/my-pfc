/**
 * The skills the drawer offers as buttons.
 *
 * Read from the repo's own `.agents/skills/*\/SKILL.md` files, so the list is
 * whatever is installed rather than a copy that goes stale. A file whose
 * frontmatter cannot be read is left out instead of taking the list down with it.
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { load as loadYaml } from 'js-yaml'
import { REPO } from '../repo'

export type SkillInfo = {
  name: string
  /** One sentence, which is all a button's line of help has room for. */
  description: string
  /**
   * Whether clicking it should put `/name ` in the box for the person to finish.
   * False sends it straight away.
   */
  takesArgs: boolean
  /**
   * Whether clicking it must only put `/name ` in the box even when it needs no
   * more words, because running it changes something that cannot be taken back.
   */
  prefill: boolean
}

/**
 * The skills that cannot do anything until the person says more, with the reason.
 *
 * Read off each skill's own description. The test is simple: with no
 * words after the name, is there anything for the skill to do? A skill that opens a
 * view, runs a workflow, or has one obvious default answers yes and is not here.
 */
const TAKES_ARGS: Record<string, string> = {
  'pfc-add-hypothesis': 'the claim to test is the argument',
  'pfc-add-insight': 'the noticing is the argument',
  'pfc-add-project': 'the project is the argument',
  'pfc-add-task': 'the task is the argument',
  'pfc-add-vision': 'the direction is the argument',
  'pfc-complete-task': 'which task is done is the argument',
  'pfc-log-day': 'the rating and what happened are the arguments',
  'pfc-log-habit': 'which habit was done is the argument',
  'pfc-persona': 'which persona, or the word list, is the argument',
  'pfc-summarize-project': 'which project is the argument',
  'pfc-supplement': 'add, stop, list, or assess, and of what',
}

/**
 * The skills a click never sends, with the reason.
 *
 * Each one writes, deletes, publishes, or starts a long run of questions, so one
 * stray click must not start it. The button fills `/name ` and the person presses
 * Send. A skill can be here and in TAKES_ARGS at once; the button acts the same.
 */
const PREFILL: Record<string, string> = {
  'pfc-commit-and-push': 'commits and pushes the whole working tree',
  'pfc-trello-inbox': 'deletes Trello cards',
  'pfc-sync-trello': 'writes completions into the repo',
  'pfc-review': 'runs every due rolling review and writes into the repo',
  'pfc-yearly-checkin': 'runs many steps and rewrites values and area statements',
  'pfc-render-trello': 'can rebuild the whole board with its rebuild flag',
  'pfc-log-day': 'writes a day record',
  'pfc-evening-checkin': 'runs many questions and writes a day record',
  'pfc-pull-template-updates': 'merges upstream changes and migrates records',
  'pfc-log-habit': 'writes a habit record',
  'pfc-complete-task': 'marks a task done',
  'pfc-focus': 'changes the quarter\'s focus list',
}

const has = (table: Record<string, string>, name: string) => Object.prototype.hasOwnProperty.call(table, name)

/** How much of a description a button's line shows. */
const DESCRIPTION_LIMIT = 140

type Frontmatter = { name: string; description: string }

/**
 * The name and description at the top of a skill file.
 *
 * Parsed as YAML rather than by pattern, because a description runs to a paragraph
 * and holds colons, quotes, and commas. Null when the file has no frontmatter, when
 * the frontmatter is not valid YAML, or when either field is missing, and the
 * caller then leaves that skill out.
 */
function frontmatter(body: string): Frontmatter | null {
  const block = /^---\r?\n([\s\S]*?)\r?\n---/.exec(body)?.[1]
  if (block === undefined) return null
  let parsed: unknown
  try {
    parsed = loadYaml(block)
  } catch {
    return null
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return null
  const { name, description } = parsed as Record<string, unknown>
  return typeof name === 'string' && typeof description === 'string' ? { name, description } : null
}

/**
 * The first sentence, or the first 140 characters of one that runs longer.
 *
 * The sentence ends at a full stop followed by a space, so `data/tasks.ndjson` in
 * the middle of one does not end it early.
 */
export function firstSentence(text: string, limit = DESCRIPTION_LIMIT): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  const end = flat.search(/[.!?](\s|$)/)
  const sentence = end === -1 ? flat : flat.slice(0, end + 1)
  return [...sentence].length <= limit ? sentence : `${[...sentence].slice(0, limit).join('').trimEnd()}...`
}

export function listSkills(): SkillInfo[] {
  const root = join(REPO, '.agents', 'skills')
  if (!existsSync(root)) return []
  const found: SkillInfo[] = []
  for (const folder of readdirSync(root)) {
    const file = join(root, folder, 'SKILL.md')
    if (!existsSync(file)) continue
    const head = frontmatter(readFileSync(file, 'utf8'))
    // The name in the file, not the folder, and only this system's own skills: a
    // skill from somewhere else is not the drawer's to offer.
    if (!head || !head.name.startsWith('pfc-')) continue
    found.push({
      name: head.name,
      description: firstSentence(head.description),
      takesArgs: has(TAKES_ARGS, head.name),
      prefill: has(PREFILL, head.name),
    })
  }
  return found.sort((a, b) => a.name.localeCompare(b.name))
}
