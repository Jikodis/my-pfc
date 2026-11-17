import { afterEach, describe, expect, it, vi } from 'vitest'
import { fileURLToPath } from 'node:url'
import { runPythonJson } from '../src/lib/computed'

describe('runPythonJson', () => {
  it('parses the script output as JSON and passes arguments', () => {
    expect(runPythonJson<{ args: string[] }>('echo_json.py', ['--today', '2025-09-20'])).toEqual({ args: ['--today', '2025-09-20'] })
  })
  it('throws with the script path and the error text when the script fails', () => {
    expect(() => runPythonJson('fail.py')).toThrow(/fail\.py[\s\S]*boom: missing file/)
  })
  it('says the script timed out, and for how long, instead of leaving the reason blank', () => {
    // A timeout leaves stderr empty, so the panel used to read "... failed:" with
    // nothing after it and the reason had to be guessed.
    expect(() => runPythonJson('slow.py', [], 500)).toThrow(/slow\.py failed: timed out after 0\.5 seconds/)
  })
  it('names the script when it exits cleanly and prints something that is not JSON', () => {
    expect(() => runPythonJson('not_json.py')).toThrow(/not_json\.py failed:[\s\S]*JSON/)
  })
})

describe('PFC_PYTHON', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })
  it('runs the interpreter named by the environment variable', async () => {
    vi.stubEnv('PFC_PYTHON', fileURLToPath(new URL('./fixtures/fake_python.sh', import.meta.url)))
    vi.resetModules()
    const { runPythonJson: run } = await import('../src/lib/computed')
    expect(run('echo_json.py')).toEqual({ from: 'fake' })
  })
})

describe('getHome', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })
  it('asks web_data.py for --home and parses the JSON', async () => {
    vi.stubEnv('PFC_PYTHON', fileURLToPath(new URL('./fixtures/fake_python_home.sh', import.meta.url)))
    vi.resetModules()
    const { getHome } = await import('../src/lib/computed')
    expect(getHome()).toMatchObject({ args: ['--home'], date: '2025-11-01' })
  })
})

describe('getReview', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.resetModules()
  })
  it('asks web_data.py for --review and parses the JSON', async () => {
    vi.stubEnv('PFC_PYTHON', fileURLToPath(new URL('./fixtures/fake_python_home.sh', import.meta.url)))
    vi.resetModules()
    const { getReview } = await import('../src/lib/computed')
    expect(getReview()).toMatchObject({ args: ['--review'] })
  })
})
