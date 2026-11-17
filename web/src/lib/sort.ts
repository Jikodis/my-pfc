/**
 * Worst first: every colour-coded list on every surface reads red, then yellow,
 * then green, so whatever needs fixing is read first. Anything that is not one of
 * the three words (a lever with no reading, an empty string) sinks to the bottom.
 */
const ORDER: Record<string, number> = { red: 0, yellow: 1, green: 2 }

export function byLight<T>(rows: T[], key: (row: T) => string): T[] {
  const rank = (row: T) => ORDER[(key(row) ?? '').toLowerCase()] ?? 3
  return rows
    .map((row, i) => ({ row, i }))
    .sort((a, b) => rank(a.row) - rank(b.row) || a.i - b.i)
    .map((x) => x.row)
}

/**
 * The Tasks tab's sort control. Each row carries stored fields only, written into
 * the table by the server: `priority` is the row's place in the server's own
 * priority order (`byPriority`), so every sort breaks ties by it. Nothing here
 * judges a task; it only reorders the table.
 */
export type TaskSort = 'priority' | 'deadline' | 'area' | 'size' | 'age'
export const TASK_SORTS: [TaskSort, string][] = [
  ['priority', 'Priority'], ['deadline', 'Deadline'], ['area', 'Area'], ['size', 'Size'], ['age', 'Age'],
]
export type TaskSortRow = { id: string; priority: number; deadline: string; area: string; size: string; created: string }

/** The size enum in config/task_schema.yaml, smallest first. */
const SIZES = ['XS', 'S', 'M', 'L', 'XL']

export function sortTaskRows<T extends TaskSortRow>(rows: T[], key: TaskSort): T[] {
  const sizeRank = (s: string) => (SIZES.includes(s) ? SIZES.indexOf(s) : SIZES.length)
  const primary = (a: T, b: T): number => {
    switch (key) {
      // No deadline sorts after every date.
      case 'deadline': return (a.deadline || '9999').localeCompare(b.deadline || '9999')
      case 'area': return (a.area || '~').localeCompare(b.area || '~')
      case 'size': return sizeRank(a.size) - sizeRank(b.size)
      // Oldest first: the created date, earliest at the top.
      case 'age': return a.created.localeCompare(b.created)
      default: return 0
    }
  }
  return [...rows].sort((a, b) => primary(a, b) || a.priority - b.priority)
}
