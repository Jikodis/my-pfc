import { describe, expect, it } from 'vitest'
import { isFocusId, isHabitId, isTaskId } from '../src/lib/chat/ids'

describe('record id shapes', () => {
  it('accepts a task id and nothing near it', () => {
    expect(isTaskId('task-20250901-001')).toBe(true)
    for (const bad of ['task-2025091-001', 'task-20250901-01', 'task-20250901-001\n', ' task-20250901-001',
      'task-20250901-001; rm -rf /', 'TASK-20250901-001', '', 42, null, undefined, ['task-20250901-001']]) {
      expect(isTaskId(bad)).toBe(false)
    }
  })

  it('accepts a habit id of letters, digits, and hyphens, up to 64', () => {
    expect(isHabitId('morning-walk')).toBe(true)
    expect(isHabitId('hydration-2L')).toBe(true)
    expect(isHabitId('a'.repeat(64))).toBe(true)
    for (const bad of ['a'.repeat(65), 'walk_20', 'walk 20', '../etc', '', 'walk\n', 7, null,
      '--dry-run', '-x', '-']) {
      expect(isHabitId(bad), String(bad)).toBe(false)
    }
  })

  it('accepts a focus id and nothing near it', () => {
    expect(isFocusId('focus-20250706-001')).toBe(true)
    for (const bad of ['focus-2025070-001', 'task-20250706-001', 'focus-20250706-001x', '', {}]) {
      expect(isFocusId(bad)).toBe(false)
    }
  })
})
