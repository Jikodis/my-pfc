/**
 * Readers for the repo's own files. The web UI holds no state: every page reads
 * the same NDJSON, YAML, and markdown the skills write, on every request.
 */
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { load as loadYaml } from 'js-yaml'
import type { Area, DailyFocus, DayRecord, FocusItem, Grounding, HabitLog, LifeWheel, Project, ReviewItem, Task, Vision } from './types'

const looksLikeRepo = (dir: string) => existsSync(join(dir, 'AGENTS.md')) && existsSync(join(dir, '6-tasks'))

/** Not import.meta.url: Astro bundles this module into dist/, where that URL points elsewhere. */
function findRepoRoot(): string {
  const named = process.env.PFC_REPO_ROOT
  if (named) {
    // Checked rather than trusted: every reader treats a file it cannot find as an
    // empty list, so a variable pointing at the wrong folder would otherwise serve a
    // whole system with nothing in it and no sign that anything was wrong.
    if (looksLikeRepo(named)) return named
    throw new Error(`PFC_REPO_ROOT points at ${named}, which is not a PFC repo (no AGENTS.md and 6-tasks/ there).`)
  }
  let dir = process.cwd()
  for (let i = 0; i < 6; i++) {
    if (looksLikeRepo(dir)) return dir
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`Could not find the PFC repo root above ${process.cwd()} (expected AGENTS.md and 6-tasks/).`)
}

export const REPO = findRepoRoot()
const p = (...parts: string[]) => join(REPO, ...parts)

export function ndjson<T>(relPath: string): T[] {
  const file = p(relPath)
  if (!existsSync(file)) return []
  const out: T[] = []
  readFileSync(file, 'utf8')
    .split('\n')
    .forEach((line, i) => {
      if (!line.trim()) return
      try {
        out.push(JSON.parse(line) as T)
      } catch (err) {
        throw new Error(`${relPath}:${i + 1} is not valid JSON: ${(err as Error).message}`)
      }
    })
  return out
}

export function yaml<T>(relPath: string): T | null {
  const file = p(relPath)
  return existsSync(file) ? (loadYaml(readFileSync(file, 'utf8')) as T) : null
}

export function text(relPath: string): string | null {
  const file = p(relPath)
  return existsSync(file) ? readFileSync(file, 'utf8') : null
}

export const getTasks = () => ndjson<Task>('6-tasks/_data/tasks.ndjson')
export const getArchivedTasks = () => ndjson<Task>('6-tasks/_data/tasks-archive.ndjson')
export const getProjects = () => ndjson<Project>('5-projects/_data/projects.ndjson')
export const getFocusItems = () => ndjson<FocusItem>('4-focus/_data/focus.ndjson')
export const getDailyFocus = () => ndjson<DailyFocus>('6-tasks/_data/daily-focus.ndjson')
export const getHabitLogs = (cadence: 'daily' | 'monthly') => ndjson<HabitLog>(`7-habits/_data/habits-${cadence}.ndjson`)
export const getDayTracking = () => ndjson<DayRecord>('data/day-tracking.ndjson')
export const getReviewLedger = () => ndjson<ReviewItem>('data/review-ledger.ndjson')
export const getGrounding = () => ndjson<Grounding>('data/grounding.ndjson')
export const getLifeWheel = () => ndjson<LifeWheel>('2-areas/_data/life-wheel.ndjson')

/**
 * One read of both task files for a whole page, so a page that names many tasks
 * reads each file once instead of once per name. An open task wins over an archived
 * record with the same id.
 */
export function taskTitles(): Map<string, string> {
  const titles = new Map<string, string>()
  for (const t of getArchivedTasks()) titles.set(t.id, t.description)
  for (const t of getTasks()) titles.set(t.id, t.description)
  return titles
}

export function getValues(): string[] {
  const body = text('1-values/values.md') ?? ''
  return body.split('\n')
    .map((l) => /^\s*(?:\d+\.|[-*])\s+(.*)$/.exec(l)?.[1])
    .filter((v): v is string => Boolean(v))
    .map((v) => v.replace(/\*\*/g, '').trim())
}

export function getAreas(): Area[] {
  const root = p('2-areas')
  if (!existsSync(root)) return []
  return readdirSync(root).sort()
    .filter((slug) => existsSync(join(root, slug, 'statement.md')))
    .map((slug) => ({ slug, statement: readFileSync(join(root, slug, 'statement.md'), 'utf8').trim() }))
}

const NOT_VISIONS = new Set(['_template.md', 'AGENTS.md', 'CLAUDE.md', 'README.md'])

export function getVisions(): Vision[] {
  const root = p('3-visions')
  if (!existsSync(root)) return []
  return readdirSync(root).sort()
    .filter((f) => f.endsWith('.md') && !NOT_VISIONS.has(f))
    .map((f) => {
      const body = readFileSync(join(root, f), 'utf8')
      const fm = /^---\n([\s\S]*?)\n---/.exec(body)?.[1] ?? ''
      const field = (k: string) => new RegExp(`^${k}:\\s*(.*)$`, 'm').exec(fm)?.[1]?.trim() ?? ''
      return {
        slug: f.replace(/\.md$/, ''),
        area: field('area'),
        status: field('status'),
        title: /^#\s+(.*)$/m.exec(body)?.[1]?.trim() ?? f,
        statement: (/^>\s*(.*)$/m.exec(body)?.[1] ?? '').replace(/^"|"$/g, '').trim(),
      }
    })
}
