/**
 * The small shaping rules that more than one module needs, written once.
 *
 * Nothing here decides anything: rounding, escaping, a percent of two stored counts,
 * and the text of a tooltip. Anything with a rule behind it comes from Python
 * (web/AGENTS.md rule 2).
 */

/** One decimal place, the precision every average and every chart coordinate uses. */
export function round1(n: number): number {
  return Math.round(n * 10) / 10
}

/**
 * Text going into markup, as text. Both angle brackets, both quote characters, and
 * the ampersand itself, so the result is safe inside an element and inside an
 * attribute value alike.
 */
export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * How far a project has got: completed parts over total parts, rounded to a whole
 * percent. A project with no parts recorded reads 0 rather than dividing by zero.
 */
export function percentComplete(done: number, total: number): number {
  return total ? Math.round((done / total) * 100) : 0
}

/**
 * What a row's first cell says when it is hovered: the record's id, and its notes
 * when it has any. An id is never visible text, so this is where it lives.
 */
export function idTooltip(id: unknown, notes: unknown, separator = '\n'): string {
  return [id, notes].filter(Boolean).map(String).join(separator)
}
