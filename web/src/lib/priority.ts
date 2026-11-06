/**
 * The impact x urgency code every list in this system sorts by: impact first,
 * high is A, medium is B, low is C, so AA is the top of the list and CC the bottom.
 *
 * Both halves are optional because the data has a record that carries neither
 * (one project in 5-projects/_data/projects.ndjson). Such a row reads `none` and
 * sorts after every real code rather than pretending to a rank it was never given.
 */
import type { Level } from './types'

const LETTER: Record<Level, string> = { high: 'A', medium: 'B', low: 'C' }

export type Priced = { impact?: Level | null; urgency?: Level | null }

export const NO_PRIORITY = 'none'

export function code(item: Priced): string {
  const { impact, urgency } = item
  return impact && urgency ? LETTER[impact] + LETTER[urgency] : NO_PRIORITY
}

/**
 * Sorts by code ascending, `none` last, stable within a code. The `none` rows are
 * ranked separately rather than by a sentinel string: under the browser's own
 * collation a punctuation character sorts BEFORE a letter, which would have put
 * the unranked rows at the top of the list.
 */
export function byPriority<T extends Priced>(rows: T[]): T[] {
  return rows
    .map((row, i) => ({ row, i, c: code(row) }))
    .sort((a, b) =>
      Number(a.c === NO_PRIORITY) - Number(b.c === NO_PRIORITY) ||
      a.c.localeCompare(b.c) ||
      a.i - b.i)
    .map((x) => x.row)
}
