import { join } from 'node:path'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import type * as RepoModule from '../src/lib/repo'
import { useTempRepo } from './helpers/temp-repo'

// This file creates and deletes folders, so it works in its own copy of the fixtures.
const temp = useTempRepo('repo-test')
let REPO: string
let ndjson: typeof RepoModule.ndjson
let text: typeof RepoModule.text
let yaml: typeof RepoModule.yaml

beforeAll(async () => {
  ;({ REPO, ndjson, text, yaml } = await import('../src/lib/repo'))
})

describe('repo readers', () => {
  it('uses PFC_REPO_ROOT when set', () => {
    expect(REPO).toBe(temp.root())
  })
  it('refuses a PFC_REPO_ROOT that is not a PFC repo, rather than serving an empty system', async () => {
    vi.stubEnv('PFC_REPO_ROOT', join(REPO, 'no-such-folder'))
    vi.resetModules()
    await expect(import('../src/lib/repo')).rejects.toThrow(/PFC_REPO_ROOT points at .*no-such-folder/)
    vi.stubEnv('PFC_REPO_ROOT', temp.root())
    vi.resetModules()
  })
  it('parses NDJSON and skips blank lines', () => {
    const rows = ndjson<{ id: string }>('6-tasks/_data/tasks.ndjson')
    expect(rows.map((r) => r.id)).toEqual(['task-1', 'task-2'])
  })
  it('returns an empty list for a missing file', () => {
    expect(ndjson('nope/missing.ndjson')).toEqual([])
  })
  it('names the file and line when a row is not valid JSON', () => {
    expect(() => ndjson('6-tasks/_data/bad.ndjson')).toThrow('6-tasks/_data/bad.ndjson:2')
  })
  it('parses YAML', () => {
    expect(yaml<{ daily_habits: { id: string }[] }>('config/sample.yaml')?.daily_habits[0].id).toBe('walk')
  })
  it('returns null for missing text', () => {
    expect(text('missing.md')).toBeNull()
  })
})
