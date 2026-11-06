import { execFileSync } from 'node:child_process'
import { existsSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { AGENT_ONLY_DATA, HOME_DATA } from '../src/lib/data-files'

const root = execFileSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8' }).trim()
const dataDirs = ['data', '2-areas/_data', '3-visions/_data', '4-focus/_data', '5-projects/_data', '6-tasks/_data', '7-habits/_data']
const allFiles = dataDirs.flatMap((d) => (existsSync(join(root, d)) ? readdirSync(join(root, d)).filter((f) => f.endsWith('.ndjson')).map((f) => `${d}/${f}`) : []))

describe('data files', () => {
  it('places every NDJSON data file on the home page or in the agent-only list', () => {
    const covered = new Set([...HOME_DATA, ...AGENT_ONLY_DATA])
    expect(allFiles.filter((f) => !covered.has(f))).toEqual([])
  })
  it('lists a file in one place only', () => {
    expect(HOME_DATA.filter((f) => AGENT_ONLY_DATA.includes(f))).toEqual([])
  })
  it('points only at files that exist', () => {
    expect([...HOME_DATA, ...AGENT_ONLY_DATA].filter((f) => !existsSync(join(root, f)))).toEqual([])
  })
})
