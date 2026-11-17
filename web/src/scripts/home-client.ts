/**
 * The in-place light editor on the home page's Areas band: each life-wheel area and
 * household room row has three color buttons (G, Y, R), a note box, and Save.
 *
 * A color tap only marks the choice; Save posts once to `set-area` or `set-room`
 * (`lightRequest` in `src/lib/write-ui.ts`) with the chosen light and the note as
 * typed, and the reply is put into words with `outcome`. A saved change reloads the
 * page so the band shows the new snapshot. It decides nothing.
 */
import { PENDING, WRITE_HEADERS, lightRequest, outcome } from '../lib/write-ui'

async function save(row: HTMLElement, button: HTMLButtonElement): Promise<void> {
  const kind = row.dataset.lightKind === 'room' ? 'room' : 'area'
  const key = row.dataset.key ?? ''
  const light = row.dataset.light ?? ''
  const note = row.querySelector<HTMLInputElement>('.light-note')?.value ?? ''
  const status = row.querySelector<HTMLElement>('.light-status')
  if (!key || !light || row.dataset.busy === '1') return
  row.dataset.busy = '1'
  button.disabled = true
  button.textContent = PENDING
  const { url, body } = lightRequest(kind, key, light, note)
  let code: number | null = null
  let reply: unknown = null
  try {
    const response = await fetch(url, { method: 'POST', headers: WRITE_HEADERS, body })
    code = response.status
    reply = await response.json().catch(() => null)
  } catch {
    code = null
  }
  const result = outcome(code, reply)
  if (status) {
    status.textContent = result.text
    status.className = `light-status sub write-${result.tone}`
  }
  if (result.reloadAfterMs !== null) {
    button.textContent = 'Saved'
    setTimeout(() => window.location.reload(), result.reloadAfterMs)
    return
  }
  button.textContent = 'Save'
  button.disabled = false
  delete row.dataset.busy
}

document.addEventListener('click', (event) => {
  const target = event.target
  if (!(target instanceof Element)) return
  const row = target.closest<HTMLElement>('.light-edit')
  if (!row) return
  const tap = target.closest<HTMLButtonElement>('button[data-set-light]')
  if (tap) {
    row.dataset.light = tap.dataset.setLight ?? row.dataset.light
    for (const b of row.querySelectorAll<HTMLButtonElement>('button[data-set-light]')) {
      b.setAttribute('aria-pressed', String(b === tap))
    }
    return
  }
  const button = target.closest<HTMLButtonElement>('button.light-save')
  if (button) void save(row, button)
})

// Enter in a note box saves that row.
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' || !(event.target instanceof HTMLInputElement) || !event.target.classList.contains('light-note')) return
  const row = event.target.closest<HTMLElement>('.light-edit')
  const button = row?.querySelector<HTMLButtonElement>('button.light-save')
  if (row && button) {
    event.preventDefault()
    void save(row, button)
  }
})
