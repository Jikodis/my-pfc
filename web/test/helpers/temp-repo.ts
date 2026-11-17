/**
 * A private copy of the fixture repo for one test file.
 *
 * A test file that creates or deletes folders inside the fixture tree works in its
 * own copy, so a folder it removes can never vanish under another file's walk, and
 * the suite can run its files in parallel. Call `useTempRepo()` at the top of the
 * file; after `beforeAll` has run, `root()` is the copy and PFC_REPO_ROOT points at
 * it, and modules imported after that (with `await import(...)`) read from it.
 */
import { cpSync, mkdtempSync, realpathSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterAll, beforeAll, vi } from 'vitest'

const FIXTURES = fileURLToPath(new URL('../fixtures', import.meta.url))

export function useTempRepo(prefix: string): { root: () => string } {
  let dir = ''
  beforeAll(() => {
    // realpath: on macOS tmpdir() is under /var, a symlink to /private/var, and the
    // wiki's containment check compares resolved paths.
    dir = realpathSync(mkdtempSync(join(tmpdir(), `pfc-${prefix}-`)))
    cpSync(FIXTURES, dir, { recursive: true, verbatimSymlinks: true })
    vi.stubEnv('PFC_REPO_ROOT', dir)
    vi.resetModules()
  })
  afterAll(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
    rmSync(dir, { recursive: true, force: true })
  })
  return {
    root: () => {
      if (!dir) throw new Error('useTempRepo: root() called before beforeAll ran')
      return dir
    },
  }
}
