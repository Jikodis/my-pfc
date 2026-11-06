/**
 * The guided tour of the home page: which steps run, which band each one shows,
 * and the bodies its taps post.
 *
 * It decides nothing. A step is dropped only when its data is empty, and every
 * branch (a broken night, the evening, a one-pick day) comes from Python through
 * `getHome()` (`automations/scripts/home_data.py`). `src/scripts/tour-client.ts`
 * does the showing and the posting.
 */
import type { Home } from './computed'
import { plainText } from './text'

export type TourStepId = 'welcome' | 'rate' | 'body' | 'music' | 'needs' | 'picks' | 'habits' | 'look' | 'why'
export type TourStep = { id: TourStepId; band: string }

/** The `data-band` each step shows. `body`, `tasks` and `habits` are page bands; the rest show only in the tour. */
export const TOUR_BANDS: Record<TourStepId, string> = {
  welcome: 'tour-welcome',
  rate: 'tour-rate',
  body: 'body',
  music: 'tour-music',
  needs: 'tour-needs',
  picks: 'tasks',
  habits: 'habits',
  look: 'tour-look',
  why: 'tour-why',
}

/** The words the tour bar shows for each step. */
export const STEP_LABELS: Record<TourStepId, string> = {
  welcome: 'Welcome',
  rate: 'Rate a day',
  body: 'Body',
  music: 'Music',
  needs: 'What needs you',
  picks: "Today's picks",
  habits: 'Habits',
  look: 'Look at this',
  why: 'Why',
}

const ORDER: TourStepId[] = ['welcome', 'rate', 'body', 'music', 'needs', 'picks', 'habits', 'look', 'why']

/** Where the tour keeps its place across the reload that follows each saved change. */
export const TOUR_STORAGE_KEY = 'pfc.tour'

export function tourSteps(
  home: Pick<Home, 'welcome_back' | 'rate_target' | 'needs_you' | 'due_review' | 'habits' | 'tour_look'>,
): TourStep[] {
  const empty: Partial<Record<TourStepId, boolean>> = {
    welcome: !home.welcome_back,
    rate: !home.rate_target.unrated,
    needs: home.needs_you.length === 0 && !home.due_review,
    habits: home.habits.length === 0,
    // Python picks the one thing to look at (a stale life wheel, a red focus, a stalled project), or none.
    look: !home.tour_look,
  }
  return ORDER.filter((id) => !empty[id]).map((id) => ({ id, band: TOUR_BANDS[id] }))
}

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
 * Where a resumed tour picks up. A saved change reloads the page and can remove the
 * step it was made on (a rated day drops the rate step), so the tour continues at
 * the first step still there at or after the stored one, and at the start when
 * nothing was stored.
 */
export function resumeIndex(steps: TourStep[], stored: string | null): number {
  const at = ORDER.indexOf(stored as TourStepId)
  if (at < 0) return 0
  const i = steps.findIndex((s) => ORDER.indexOf(s.id) >= at)
  return i < 0 ? steps.length - 1 : i
}

/**
 * A review's skill text, which is copied skill prose with markdown and relative
 * links, as plain words: link text without its target, no backticks, no bold.
 */
export function reviewHint(skill: string | null): string {
  if (!skill) return ''
  return plainText(skill.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1').replace(/`/g, ''))
}
