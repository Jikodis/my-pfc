/**
 * The bodies the home page's day controls post: the 2+1 picks and the day rating,
 * plus the plain-text form of a review's hint.
 *
 * It decides nothing. Every branch (the evening, an all-done day, a due review) comes
 * from Python through `getHome()` (`automations/scripts/home_data.py`).
 * `src/scripts/day-client.ts` does the posting.
 */
import { plainText } from './text'

/** The set-picks body: the first two taps are the critical picks, a third is the bonus. */
export function picksRequest(date: string, chosen: string[]): string {
  const [first, second, bonus] = chosen
  const critical = second ? [first, second] : [first]
  return JSON.stringify(bonus ? { date, critical, bonus } : { date, critical })
}

/**
 * The set-picks body that adds picks to a day whose picks are all done: the stored
 * critical ids first (done ones stay done), then the new taps, and the stored bonus
 * kept unless it was tapped. The writer refuses more than two open picks.
 */
export function appendPicksRequest(date: string, keep: { critical: string[]; bonus: string | null }, chosen: string[]): string {
  const critical = [...keep.critical, ...chosen.filter((id) => !keep.critical.includes(id))]
  const bonus = keep.bonus && !chosen.includes(keep.bonus) ? keep.bonus : null
  return JSON.stringify(bonus ? { date, critical, bonus } : { date, critical })
}

export type Ratings = { energy: number; mood: number; focus: number; hyperfocused?: boolean }

/** The rate-day body. The optional answer is sent only when tapped. */
export function rateRequest(date: string, r: Ratings): string {
  return JSON.stringify({
    date, energy: r.energy, mood: r.mood, focus: r.focus,
    ...(r.hyperfocused === undefined ? {} : { hyperfocused: r.hyperfocused }),
  })
}

/**
 * A review's skill text, which is copied skill prose with markdown and relative
 * links, as plain words: link text without its target, no backticks, no bold.
 */
export function reviewHint(skill: string | null): string {
  if (!skill) return ''
  return plainText(skill.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1').replace(/`/g, ''))
}
