import { describe, expect, it } from 'vitest'
import type { APIContext } from 'astro'
import { updateStep } from '../src/lib/update-step'
import { buildStatus } from '../src/lib/build'
import { GET } from '../src/pages/api/build'

describe('updateStep', () => {
  it('stays when the server runs the build the page was rendered with', () => {
    expect(updateStep('100', { build: '100', busy: false }, false)).toBe('stay')
  })
  it('reloads when the server runs a newer build', () => {
    expect(updateStep('100', { build: '200', busy: false }, false)).toBe('reload')
  })
  it('waits instead of reloading while text is typed', () => {
    expect(updateStep('100', { build: '200', busy: false }, true)).toBe('wait')
  })
  it('treats no answer as no news (the server is mid-restart)', () => {
    expect(updateStep('100', null, false)).toBe('stay')
    expect(updateStep('100', 'oops', false)).toBe('stay')
    expect(updateStep('100', {}, false)).toBe('stay')
    expect(updateStep('100', { build: '' }, false)).toBe('stay')
  })
  it('never reloads a page rendered by the dev server', () => {
    expect(updateStep('dev', { build: '200' }, false)).toBe('stay')
  })
})

describe('GET /api/build', () => {
  const call = (host: string) =>
    GET({ request: new Request('http://127.0.0.1:4323/api/build', { headers: { host } }) } as unknown as APIContext)

  it('reports the build and that nothing is running', async () => {
    const response = await call('127.0.0.1:4323')
    expect(response.status).toBe(200)
    expect(response.headers.get('cache-control')).toBe('no-store')
    expect(await response.json()).toEqual({ build: 'dev', busy: false })
    expect(buildStatus()).toEqual({ build: 'dev', busy: false })
  })
  it('refuses another host name', async () => {
    expect((await call('evil.example:4323')).status).toBe(403)
  })
})
