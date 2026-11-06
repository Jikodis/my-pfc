/**
 * The skills pinned at the top of the drawer's skill list, in the order they are wanted.
 *
 * Its own file so `pfc-repo-maintenance` can read the names and fail when one is
 * renamed, and so a test can check each is installed. The daily summary is pinned
 * first; the daily spine itself is the home page's tour, not a skill. `pfc-review`
 * is last, for catching up on every due rolling review at once.
 */
export const PINNED: readonly string[] = ['pfc-daily-summary', 'pfc-pick-tasks', 'pfc-add-task', 'pfc-stuck', 'pfc-review']
