import { describe, expect, it } from 'vitest'
import { getAreas, getDailyFocus, getProjects, getTasks, getValues, getVisions, taskTitles } from '../src/lib/repo'

describe('typed getters', () => {
  it('reads tasks and projects', () => {
    expect(getTasks()).toHaveLength(2)
    expect(getProjects()[0].name).toBe('Project Foo')
  })
  it('builds one title map from open tasks and the archive, with the open task winning', () => {
    const titles = taskTitles()
    expect(titles.get('task-1')).toBe('Renew passport')
    expect(titles.get('task-7')).toBe('Donate old clothes')
    expect(titles.get('task-404')).toBeUndefined()
  })
  it('reads daily focus', () => {
    expect(getDailyFocus()[0].critical).toEqual(['task-1', 'task-404'])
  })
  it('parses a vision file and skips the template', () => {
    expect(getVisions()).toEqual([
      { slug: 'tidy-home', area: 'household', status: 'active', title: 'A home where everything has a place', statement: 'Every room resets in ten minutes.' },
    ])
  })
  it('reads values in order without bold markers', () => {
    expect(getValues()).toEqual(['Health', 'Learning'])
  })
  it('reads area statements', () => {
    expect(getAreas()).toEqual([{ slug: 'household', statement: 'A tidy home that runs itself.' }])
  })
})
