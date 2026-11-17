/**
 * The home page's day controls (`src/pages/index.astro`): the day rating and the 2+1
 * picks.
 *
 * Each write posts to its `/api/write/*` route with the guard headers and puts the
 * reply into words with `outcome` from `src/lib/write-ui.ts`; a saved change reloads
 * the page so it shows the new state. It decides nothing: what the page offers came
 * from Python.
 */
import { appendPicksRequest, picksRequest, rateRequest, type Ratings } from '../lib/day'
import { WRITE_HEADERS, outcome, type Outcome } from '../lib/write-ui'

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
  const status = near.parentElement?.querySelector<HTMLElement>('.day-status')
  if (!status) return
  status.textContent = result.text
  status.className = `day-status sub write-${result.tone}`
}

/** After a saved change: reload to show the new state. */
function afterSave(result: Outcome): boolean {
  if (result.reloadAfterMs === null) return false
  setTimeout(() => window.location.reload(), result.reloadAfterMs)
  return true
}

// --- The rating ---

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
    if (!afterSave(result)) {
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
  if (!afterSave(result)) {
    picksSave.textContent = label
    picksSave.disabled = false
  }
})

