/**
 * Each Python-backed panel runs its own script, so one broken script must not
 * blank the whole page. Wrapping a call here lets a page render that one panel as
 * a short message and keep the rest of the page intact.
 */
export type Safe<T> = { ok: true; value: T } | { ok: false; error: string }

export function safe<T>(fn: () => T): Safe<T> {
  try {
    return { ok: true, value: fn() }
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) }
  }
}
