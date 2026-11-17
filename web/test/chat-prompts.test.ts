import { describe, expect, it } from 'vitest'
import { COMMANDS, PROMPTS, chatPrompt, promptSkills } from '../src/lib/chat/prompts'

describe('chatPrompt', () => {
  it('fills each placeholder with the record value', () => {
    expect(chatPrompt(PROMPTS.complete, { title: 'Call the dentist', id: 'task-20250901-001' }))
      .toBe('Complete the task "Call the dentist" (task-20250901-001).')
  })

  it('keeps a double quote, an apostrophe, and a less-than sign in a title exactly', () => {
    const title = `Fix the "team's" <watch> dates`
    expect(chatPrompt(PROMPTS.handOff, { title, id: 'task-1' }))
      .toBe(`Do this task for me, start to finish, then mark it complete: "Fix the "team's" <watch> dates" (task-1).`)
  })

  it('never expands a placeholder that arrives inside a value', () => {
    expect(chatPrompt(PROMPTS.complete, { title: '{id}', id: 'task-1' }))
      .toBe('Complete the task "{id}" (task-1).')
  })

  it('writes a value that runs over several lines as one line', () => {
    expect(chatPrompt(PROMPTS.logHabit, { id: 'walk\n  daily' })).toBe('Log the habit walk daily as done for today.')
  })

  it('refuses a template whose placeholder has no value, rather than sending a gap', () => {
    expect(() => chatPrompt(PROMPTS.complete, { title: 'x' })).toThrow(/id/)
  })

  it('writes the project skills with the name after them', () => {
    expect(chatPrompt(PROMPTS.summarize, { name: 'Web UI' })).toBe('/pfc-summarize-project Web UI')
    expect(chatPrompt(PROMPTS.revive, { name: 'Web UI' })).toBe('/pfc-revive Web UI')
  })

  it('hands a filled review form to the review skill', () => {
    expect(chatPrompt(PROMPTS.reviewAnswers, { id: 'life-wheel', json: '{"review":"life-wheel"}' }))
      .toBe('/pfc-review life-wheel answers {"review":"life-wheel"}')
  })
})

describe('the one-page buttons', () => {
  it('ask for a question edit in the questions file', () => {
    expect(PROMPTS.editQuestions).toBe('Help me edit my life questions in 0-me/questions.md: add, reword, or retire one. Ask me which.')
  })

  it('ask for the life wheel to be rated', () => {
    expect(PROMPTS.rateAreas).toBe('Walk me through my area check-in: each area\'s item questions, one area at a time, and a color for any area with no items.')
  })

  it('ask for a vision update, and start the brainstorm at once', () => {
    expect(PROMPTS.updateVision).toBe('Help me update one of my visions in 3-visions/. Ask me which one and what changed.')
    expect(COMMANDS.visionBrainstorm).toBe('/pfc-vision-brainstorm')
  })

  it('add or re-pick a focus through the focus skill', () => {
    expect(PROMPTS.addFocus).toBe('/pfc-focus add a focus')
    expect(PROMPTS.repickFocus).toBe('/pfc-focus re-pick focuses')
  })

  it('name the anchor to edit, and ask for wording to add one', () => {
    expect(chatPrompt(PROMPTS.editAnchor, { title: 'One thing at a time', id: 'ground-20250627-001' }))
      .toBe('Edit the Front-of-Mind anchor "One thing at a time" (ground-20250627-001). Ask me what to change.')
    expect(PROMPTS.addAnchor).toBe('Add a Front-of-Mind anchor. Ask me for the wording.')
  })
})

describe('promptSkills', () => {
  it('names every skill a page button starts', () => {
    expect(promptSkills()).toEqual([
      'pfc-focus', 'pfc-pick-tasks', 'pfc-plan-open-day', 'pfc-review', 'pfc-revive', 'pfc-stuck', 'pfc-summarize-project',
      'pfc-vision-brainstorm',
    ])
  })
})

describe('the skills page buttons start', () => {
  it('are all installed under the real repo .agents/skills', async () => {
    const { existsSync } = await import('node:fs')
    const { fileURLToPath } = await import('node:url')
    // The tests read a fixture repo; this one checks the real one the buttons run in.
    const skills = fileURLToPath(new URL('../../.agents/skills/', import.meta.url))
    for (const name of promptSkills()) expect(existsSync(`${skills}${name}/SKILL.md`), name).toBe(true)
  })
})
