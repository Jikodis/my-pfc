import { describe, expect, it } from 'vitest'
import { firstSentence, listSkills } from '../src/lib/chat/skills'

/**
 * The fixture repo holds six skill folders: three of this system's own, one from
 * somewhere else, one whose frontmatter is not valid YAML, and one with no SKILL.md
 * at all.
 */
describe('listSkills', () => {
  const skills = listSkills()

  it('lists this system’s own skills, by the name in the file', () => {
    expect(skills.map((s) => s.name)).toEqual(['pfc-add-task', 'pfc-commit-and-push', 'pfc-list-tasks'])
  })

  it('leaves out a skill that is not this system’s', () => {
    expect(skills.some((s) => s.name === 'agent-browser')).toBe(false)
  })

  it('skips a file it cannot read the top of, rather than failing the whole list', () => {
    expect(() => listSkills()).not.toThrow()
    expect(skills.some((s) => s.name === 'pfc-broken')).toBe(false)
  })

  it('shows one sentence of what each skill does', () => {
    const add = skills.find((s) => s.name === 'pfc-add-task')
    expect(add?.description).toBe('Add a new task to the productivity system.')
  })

  it('says which skills need more words before they can do anything', () => {
    expect(skills.find((s) => s.name === 'pfc-add-task')?.takesArgs).toBe(true)
    expect(skills.find((s) => s.name === 'pfc-list-tasks')?.takesArgs).toBe(false)
  })

  it('marks a skill that changes something it cannot take back as prefill only', () => {
    const commit = skills.find((s) => s.name === 'pfc-commit-and-push')
    expect(commit).toMatchObject({ takesArgs: false, prefill: true })
  })

  it('lets a skill that only reads keep sending on one click', () => {
    expect(skills.find((s) => s.name === 'pfc-list-tasks')?.prefill).toBe(false)
    expect(skills.find((s) => s.name === 'pfc-add-task')?.prefill).toBe(false)
  })
})

describe('firstSentence', () => {
  it('ends at the first full stop that ends a sentence', () => {
    expect(firstSentence('Add a task. Use when the user says "add task".'))
      .toBe('Add a task.')
  })
  it('does not end at a full stop inside a file name', () => {
    expect(firstSentence('Capture a hypothesis into data/hypotheses.ndjson. Use when the user says so.'))
      .toBe('Capture a hypothesis into data/hypotheses.ndjson.')
  })
  it('keeps a description that is one sentence with no full stop at all', () => {
    expect(firstSentence('Show every open task')).toBe('Show every open task')
  })
  it('puts the whole description on one line', () => {
    expect(firstSentence('Show my tasks,\n   sorted by area')).toBe('Show my tasks, sorted by area')
  })
  it('cuts a sentence that runs past the limit and says it was cut', () => {
    const long = firstSentence('x'.repeat(400))
    expect(long.length).toBe(143)
    expect(long.endsWith('...')).toBe(true)
  })
  it('cuts between characters, never through one', () => {
    const long = firstSentence('\u{1F600}'.repeat(400))
    expect([...long].length).toBe(143)
    expect(long.endsWith('\u{1F600}...')).toBe(true)
  })
})
