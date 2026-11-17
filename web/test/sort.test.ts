import { describe, expect, it } from 'vitest'
import { byLight, sortTaskRows, type TaskSortRow } from '../src/lib/sort'

it('sorts red first, then yellow, then green, and keeps ties in order', () => {
  const rows = [{ n: 'a', l: 'green' }, { n: 'b', l: 'RED' }, { n: 'c', l: 'yellow' }, { n: 'd', l: 'red' }]
  expect(byLight(rows, (r) => r.l).map((r) => r.n)).toEqual(['b', 'd', 'c', 'a'])
})

it('puts a value that is not a light word last, keeping those in their original order', () => {
  const rows = [{ n: 'a', l: 'NO DATA' }, { n: 'b', l: 'green' }, { n: 'c', l: '' }, { n: 'd', l: '[-]' }, { n: 'e', l: 'RED' }]
  expect(byLight(rows, (r) => r.l).map((r) => r.n)).toEqual(['e', 'b', 'a', 'c', 'd'])
})

describe('sortTaskRows', () => {
  const rows: TaskSortRow[] = [
    { id: 'a', priority: 2, deadline: '2025-12-01', area: 'health', size: 'L', created: '2025-03-01' },
    { id: 'b', priority: 0, deadline: '', area: 'career', size: 'XS', created: '2025-05-01' },
    { id: 'c', priority: 1, deadline: '2025-11-05', area: 'health', size: 'M', created: '2025-01-01' },
  ]
  const ids = (key: Parameters<typeof sortTaskRows>[1]) => sortTaskRows(rows, key).map((r) => r.id)
  it('sorts by the server priority order', () => expect(ids('priority')).toEqual(['b', 'c', 'a']))
  it('sorts by deadline, soonest first, tasks with none last', () => expect(ids('deadline')).toEqual(['c', 'a', 'b']))
  it('sorts by area name, priority breaking ties', () => expect(ids('area')).toEqual(['b', 'c', 'a']))
  it('sorts by size, smallest first', () => expect(ids('size')).toEqual(['b', 'c', 'a']))
  it('sorts by age, oldest first', () => expect(ids('age')).toEqual(['c', 'a', 'b']))
})
