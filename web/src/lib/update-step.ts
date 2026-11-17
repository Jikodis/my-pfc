/**
 * The browser's half of the auto-update: what an open page does with one answer from
 * `GET /api/build` (`src/lib/build.ts`). Pure, so the page bundle carries no server code.
 */

/** What a page does with one answer from `GET /api/build`. */
export type UpdateStep = 'stay' | 'wait' | 'reload'

/**
 * `loaded` is the id the page was rendered with. `answer` is what the server said,
 * or null when it did not answer (it is down mid-restart): no news is not a reason
 * to reload. `typing` is true while a text field on the page holds unsent text,
 * which a reload would throw away; the page waits and asks again.
 */
export function updateStep(loaded: string, answer: unknown, typing: boolean): UpdateStep {
  if (!answer || typeof answer !== 'object') return 'stay'
  const build = (answer as { build?: unknown }).build
  if (typeof build !== 'string' || build === '' || build === loaded || loaded === 'dev') return 'stay'
  return typing ? 'wait' : 'reload'
}
