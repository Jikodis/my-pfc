/**
 * The headers every response carries.
 *
 * A meta tag cannot say `frame-ancestors`, and a chat panel that can start a
 * process in this repo is exactly what a page in a frame would want to click for
 * somebody. So the policy is set here as a real header, on every response this
 * server sends: pages, API routes, the page for an address that does not exist, and
 * the page a failure lands on.
 *
 * The body is never read, copied, or cloned here. One response is a chat run
 * streaming out over minutes, and reading it to pass it on would hold every event
 * until the run ended.
 */
import { defineMiddleware } from 'astro:middleware'
import { HEADER_POLICY } from './lib/csp'

export const onRequest = defineMiddleware(async (_context, next) => {
  const response = await next()
  const headers = response.headers
  headers.set('content-security-policy', HEADER_POLICY)
  // The old header, for the same thing, because it is still the one some browsers read.
  headers.set('x-frame-options', 'DENY')
  headers.set('x-content-type-options', 'nosniff')
  // Nothing outside this machine should ever learn which page of this app was open.
  headers.set('referrer-policy', 'no-referrer')
  return response
})
