export const TZ = process.env.LOCAL_TZ || 'America/Denver'

/** en-CA formats as YYYY-MM-DD. */
export function todayLocal(now: Date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(now)
}

/** Noon UTC keeps a plain date on the same calendar day in any US timezone. */
const atNoon = (iso: string) => new Date(`${iso}T12:00:00Z`)

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', weekday: 'short', month: 'short', day: 'numeric' }).format(atNoon(iso))
}

/**
 * A date with its year, for records that span years: `Jan 1, 2025`. A full
 * timestamp keeps its time as well, read in the local timezone. Anything that is
 * not a date is handed back unchanged.
 */
export function formatDateLong(value: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric' })
      .format(atNoon(value))
  }
  // Only a full timestamp, never a loose string: 2025-Q1 and 2025 are not dates here.
  if (!/^\d{4}-\d{2}-\d{2}T[\d:.]+/.test(value)) return value
  const when = new Date(value)
  if (Number.isNaN(when.getTime())) return value
  return new Intl.DateTimeFormat('en-US', {
    timeZone: TZ, month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true,
  }).format(when)
}

/**
 * No page in Part 1 calls this yet. It stays because Part 3 shows calendar slots and
 * habit landing times, and the 12-hour rule they have to follow lives here, tested,
 * rather than being written again at the point of use.
 */
export function formatTime12(value: string): string {
  const clock = /^(\d{1,2}):(\d{2})(?::\d{2})?$/.exec(value)
  if (clock) {
    const h = Number(clock[1])
    return `${h % 12 === 0 ? 12 : h % 12}:${clock[2]} ${h < 12 ? 'AM' : 'PM'}`
  }
  return new Intl.DateTimeFormat('en-US', { timeZone: TZ, hour: 'numeric', minute: '2-digit', hour12: true }).format(new Date(value))
}

export function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((atNoon(toIso).getTime() - atNoon(fromIso).getTime()) / 86_400_000)
}

/**
 * How a deadline reads next to the date itself. Display formatting only: the
 * count comes straight from daysBetween, and nothing here decides what is late.
 */
export function deadlineLabel(todayIso: string, deadlineIso: string): string {
  const days = daysBetween(todayIso, deadlineIso)
  const unit = (n: number) => (n === 1 ? 'day' : 'days')
  if (days === 0) return 'due today'
  if (days > 0) return `due in ${days} ${unit(days)}`
  return `${-days} ${unit(-days)} overdue`
}

/**
 * What a project's deadline cell says. Work that is finished has no deadline left
 * to miss, so it reads as finished, with the date when the record carries one,
 * and is never marked overdue.
 */
export function deadlineCell(
  todayIso: string, record: { deadline?: string | null; completed?: string | null }, finished: boolean,
): { text: string; overdue: boolean } {
  if (finished) {
    return { text: record.completed ? `Finished ${formatDateLong(record.completed)}` : 'Finished', overdue: false }
  }
  if (!record.deadline) return { text: '', overdue: false }
  return { text: deadlineLabel(todayIso, record.deadline), overdue: daysBetween(todayIso, record.deadline) < 0 }
}

/** A plain date moved by whole days: tomorrow is `addDays(today, 1)`. */
export function addDays(iso: string, days: number): string {
  return new Date(atNoon(iso).getTime() + days * 86_400_000).toISOString().slice(0, 10)
}

/** True for a real calendar date written YYYY-MM-DD, so `2025-02-30` is not one. */
export function isIsoDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const when = atNoon(value)
  return !Number.isNaN(when.getTime()) && when.toISOString().slice(0, 10) === value
}

export function lastNDays(n: number, endIso: string): string[] {
  const end = atNoon(endIso).getTime()
  return Array.from({ length: n }, (_, i) => new Date(end - (n - 1 - i) * 86_400_000).toISOString().slice(0, 10))
}

/**
 * A local timestamp as `Mon 5:00 AM`: the weekday from formatDate, the time from
 * formatTime12. Takes `YYYY-MM-DDTHH:MM:SS` as written, with no timezone shift.
 */
export function formatWhen(localIso: string): string {
  const [day, clock] = localIso.split('T')
  const weekday = formatDate(day).split(',')[0]
  return `${weekday} ${formatTime12(clock)}`
}
