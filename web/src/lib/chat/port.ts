/**
 * The port this server was started on.
 *
 * The chat endpoints compare the request's `Host` header against this, and it has
 * to come from the server rather than from the request. Astro builds
 * `Astro.url` out of the request's own `Host` header, so checking the header
 * against that port compares a claim with itself: a request saying
 * `Host: localhost:1` passed on a server listening on 4325.
 *
 * `run-web.sh` and the launch agent both set PORT, and `web/test/smoke.sh` sets it
 * for the server it starts. `astro dev` sets nothing, so the fallback is the port
 * in `astro.config.mjs`.
 */
const DEFAULT_PORT = '4323'

export function serverPort(): string {
  const named = (process.env.PORT ?? '').trim()
  if (!/^\d{1,5}$/.test(named)) return DEFAULT_PORT
  const number = Number(named)
  return number >= 1 && number <= 65535 ? String(number) : DEFAULT_PORT
}
