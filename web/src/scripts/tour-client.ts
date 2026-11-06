/**
 * The guided tour on the home page (`src/pages/index.astro`).
 *
 * `Walk me through` shows one `[data-band]` at a time, in the order the page wrote
 * into `#tour-bar`'s `data-steps` (`tourSteps` in `src/lib/tour.ts`), with Skip,
 * Next and Close. The current step is kept in sessionStorage, so the reload that
 * follows every saved change lands on the same step, or the next one still there.
 * The music step asks for upbeat music before any choosing; its `Music is on`
 * button moves the tour on, the same as Next.
 *
 * It also runs the three taps that write: the day rating (the tour's step and the
 * optional row in Body first), the picks, and the review stamp. Each posts to its `/api/write/*` route with the guard headers and
 * puts the reply into words with `outcome` from `src/lib/write-ui.ts`. It decides
 * nothing: which steps run and every branch inside them came from Python.
 */
import { TOUR_STORAGE_KEY, appendPicksRequest, picksRequest, rateRequest, resumeIndex, type Ratings, type TourStep } from '../lib/tour'
import { WRITE_HEADERS, outcome, type Outcome } from '../lib/write-ui'

type Step = TourStep & { label: string }
type Saved = { on: boolean; step: string | null }

const root = document.documentElement
const bar = document.getElementById('tour-bar')
const where = document.getElementById('tour-where')
const next = document.getElementById('tour-next') as HTMLButtonElement | null
const steps: Step[] = (() => {
  try {
    return JSON.parse(bar?.dataset.steps ?? '[]') as Step[]
  } catch {
    return []
  }
})()
const baseTitle = document.title

function load(): Saved {
  try {
    const raw = sessionStorage.getItem(TOUR_STORAGE_KEY)
    const v = raw ? (JSON.parse(raw) as Partial<Saved>) : null
    return { on: v?.on === true, step: typeof v?.step === 'string' ? v.step : null }
  } catch {
    return { on: false, step: null }
  }
}

function save(s: Saved): void {
  try {
    sessionStorage.setItem(TOUR_STORAGE_KEY, JSON.stringify(s))
  } catch {
    // A private window can refuse storage; the tour still runs, it just forgets on reload.
  }
}

let on = false
let index = 0

const current = (): Step | undefined => steps[index]

function render(): void {
  root.classList.toggle('touring', on)
  if (bar) bar.hidden = !on
  const step = current()
  for (const band of document.querySelectorAll<HTMLElement>('[data-band]')) {
    band.classList.toggle('tour-off', on && band.dataset.band !== step?.band)
  }
  if (!on || !step) {
    document.title = baseTitle
    return
  }
  if (where) where.textContent = `Step ${index + 1} of ${steps.length}: ${step.label}`
  if (next) next.textContent = index === steps.length - 1 ? 'Finish' : 'Next'
  document.title = `PFC, tour step ${index + 1} of ${steps.length}: ${step.label}`
}

function go(to: number): void {
  if (to >= steps.length) {
    close()
    return
  }
  index = Math.max(0, to)
  save({ on: true, step: current()?.id ?? null })
  render()
  window.scrollTo({ top: 0 })
}

function start(): void {
  if (steps.length === 0) return
  on = true
  go(0)
}

function close(): void {
  on = false
  save({ on: false, step: null })
  render()
}

/** The step after the current one, stored before a reload, so the tour continues there. */
function saveNextStep(): void {
  const after = steps[index + 1]
  save(after ? { on: true, step: after.id } : { on: false, step: null })
}

async function post(url: string, body: string): Promise<Outcome> {
  let status: number | null = null
  let reply: unknown = null
  try {
    const response = await fetch(url, { method: 'POST', headers: WRITE_HEADERS, body })
    status = response.status
    reply = await response.json().catch(() => null)
  } catch {
    status = null
  }
  return outcome(status, reply)
}

function say(near: Element, result: Outcome): void {
  const status = near.parentElement?.querySelector<HTMLElement>('.tour-status')
  if (!status) return
  status.textContent = result.text
  status.className = `tour-status sub write-${result.tone}`
}

/** After a saved change: move on to the next step, then reload to show the new state. */
function afterSave(result: Outcome, advance: boolean): boolean {
  if (result.reloadAfterMs === null) return false
  if (advance && on) saveNextStep()
  setTimeout(() => window.location.reload(), result.reloadAfterMs)
  return true
}

// --- The rating: the tour's rate step, and the optional row in Body first ---

function ratingBlock(rate: HTMLElement): void {
  const saveButton = rate.querySelector<HTMLButtonElement>('.rate-save')
  const chosen: Partial<Record<string, string>> = {}

  const ratings = (): Ratings | null => {
    const n = (k: string) => (chosen[k] ? Number(chosen[k]) : NaN)
    const [energy, mood, focus] = [n('energy'), n('mood'), n('focus')]
    if (![energy, mood, focus].every(Number.isInteger)) return null
    return {
      energy, mood, focus,
      ...(chosen.hyperfocused ? { hyperfocused: chosen.hyperfocused === 'yes' } : {}),
    }
  }

  rate.addEventListener('click', (event) => {
    const tap = (event.target as Element).closest<HTMLButtonElement>('button[data-rate]')
    if (!tap) return
    const key = tap.dataset.rate ?? ''
    // A second tap on the chosen answer clears it, so an optional answer can be taken back.
    const again = chosen[key] === tap.dataset.value
    chosen[key] = again ? undefined : tap.dataset.value
    for (const b of rate.querySelectorAll<HTMLButtonElement>(`button[data-rate="${key}"]`)) {
      b.setAttribute('aria-pressed', String(!again && b === tap))
    }
    if (saveButton) saveButton.disabled = ratings() === null
  })

  saveButton?.addEventListener('click', async () => {
    const r = ratings()
    const date = rate.dataset.rateDate
    if (!r || !date) return
    saveButton.disabled = true
    saveButton.textContent = 'Saving...'
    const result = await post('/api/write/rate-day', rateRequest(date, r))
    say(saveButton, result)
    if (!afterSave(result, true)) {
      saveButton.textContent = 'Save rating'
      saveButton.disabled = false
    }
  })
}

for (const rate of document.querySelectorAll<HTMLElement>('.rate')) ratingBlock(rate)

// --- The picks ---

const suggest = document.querySelector<HTMLElement>('.suggest')
const picksSave = document.getElementById('picks-save') as HTMLButtonElement | null
const picked: string[] = []

suggest?.addEventListener('click', (event) => {
  const choice = (event.target as Element).closest<HTMLButtonElement>('button[data-pick-choice]')
  if (!choice) return
  const id = choice.dataset.pickChoice ?? ''
  const max = Number(suggest.dataset.pickMax ?? '3')
  const at = picked.indexOf(id)
  if (at >= 0) picked.splice(at, 1)
  else if (picked.length < max) picked.push(id)
  for (const b of suggest.querySelectorAll<HTMLButtonElement>('button[data-pick-choice]')) {
    b.setAttribute('aria-pressed', String(picked.includes(b.dataset.pickChoice ?? '')))
  }
  if (picksSave) picksSave.disabled = picked.length === 0
})

picksSave?.addEventListener('click', async () => {
  const date = suggest?.dataset.pickDate
  if (!date || picked.length === 0) return
  const label = picksSave.textContent ?? ''
  picksSave.disabled = true
  picksSave.textContent = 'Saving...'
  // Adding to a day whose picks are all done sends the stored picks back with the new ones.
  let keep: { critical: string[]; bonus: string | null } | null = null
  try {
    keep = suggest?.dataset.keepPicks ? JSON.parse(suggest.dataset.keepPicks) : null
  } catch {
    keep = null
  }
  const body = keep ? appendPicksRequest(date, keep, picked) : picksRequest(date, picked)
  const result = await post('/api/write/set-picks', body)
  say(picksSave, result)
  if (!afterSave(result, true)) {
    picksSave.textContent = label
    picksSave.disabled = false
  }
})

// --- The review stamp: the same click puts the review's prompt in the chat box. ---

document.addEventListener('click', async (event) => {
  const button = (event.target as Element).closest<HTMLButtonElement>('button[data-review-stamp]')
  if (!button || button.dataset.stamped === '1') return
  button.dataset.stamped = '1'
  const result = await post('/api/write/stamp-review', JSON.stringify({ id: button.dataset.reviewStamp }))
  say(button, result.tone === 'ok' ? { ...result, text: `Marked done today. ${result.text}` } : result)
  if (result.tone === 'error') delete button.dataset.stamped
})

// --- Music and the first pick ---

document.getElementById('music-on')?.addEventListener('click', () => {
  if (on && current()?.id === 'music') go(index + 1)
})

document.getElementById('start-pick')?.addEventListener('click', () => {
  close()
  const pick = document.querySelector<HTMLElement>('[data-band="tasks"] .picks li')
  pick?.scrollIntoView({ block: 'center' })
  pick?.querySelector<HTMLButtonElement>('button')?.focus({ preventScroll: true })
})

// --- The bar ---

document.getElementById('tour-start')?.addEventListener('click', start)
document.getElementById('tour-skip')?.addEventListener('click', () => go(index + 1))
next?.addEventListener('click', () => go(index + 1))
document.getElementById('tour-close')?.addEventListener('click', close)
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && on && !(event.target as Element | null)?.closest?.('.chat-drawer, #chat-drawer')) close()
})

// A page opened from another page's Walk me through link starts the tour; a reload
// in the middle of one carries on where it was.
const saved = load()
if (new URLSearchParams(location.search).get('tour') === '1') {
  history.replaceState(null, '', location.pathname)
  start()
} else if (saved.on && steps.length > 0) {
  on = true
  index = resumeIndex(steps, saved.step)
  render()
  window.scrollTo({ top: 0 })
}
