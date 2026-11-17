/**
 * The one Content-Security-Policy, written once and used twice.
 *
 * Every page carries it in a meta tag, and `src/middleware.ts` sets it as a
 * response header on everything this server answers. Two copies of a policy drift,
 * and a drifted policy is one that blocks something on one page and nothing on
 * another, so both read this module.
 *
 * The one directive only the header can carry is `frame-ancestors`: a browser
 * ignores it inside a meta tag and logs an error on every page. It is the directive
 * that says nobody may put this app inside a frame, which is what a chat panel
 * holding a button that starts a process in this repo needs.
 *
 * Inline styles and inline scripts stay allowed because the page's own styles and
 * scripts are inline. That means this policy does not stop an inline event
 * handler: the sanitizer in `src/lib/chat/markdown.ts` is the control that does.
 */
const DIRECTIVES = [
  "default-src 'self'",
  // Images come from this server only. data: is deliberately absent: nothing in
  // this app serves one, and it is a way to smuggle markup past a filter.
  "img-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "script-src 'self' 'unsafe-inline'",
  "base-uri 'none'",
  "form-action 'self'",
]

/** For the meta tag in `src/layouts/Base.astro`. */
export const META_POLICY = DIRECTIVES.join('; ')

/** For every response, set in `src/middleware.ts`. */
export const HEADER_POLICY = [...DIRECTIVES, "frame-ancestors 'none'"].join('; ')
