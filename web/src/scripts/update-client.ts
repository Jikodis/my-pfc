/**
 * Reloads an open page once the server runs a newer build.
 *
 * `automations/scripts/run-web.sh` rebuilds and restarts the server by itself when the
 * web code changes. This asks `GET /api/build` every `CHECK_MS`, and again whenever the
 * tab comes back into view, and reloads when the build id differs from the one this page
 * was rendered with (`data-build` on <html>). A failed request means the server is
 * mid-restart, so it waits for the next answer. While a text field holds unsent text the
 * page does not reload: it shows a note with a Reload button and asks again later. The
 * chat transcript lives in sessionStorage, so a reload continues it.
 */
import { updateStep } from '../lib/update-step'

const CHECK_MS = 15_000

const loaded = document.documentElement.dataset.build ?? 'dev'

/** Unsent text a reload would throw away: the chat box, a note, quick add. */
function typing(): boolean {
  for (const field of document.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('textarea, input[type=text]')) {
    if (field.value.trim() !== '') return true
  }
  return false
}

let note: HTMLElement | null = null

function showNote(): void {
  if (note) return
  note = document.createElement('div')
  note.className = 'update-note'
  note.setAttribute('role', 'status')
  note.textContent = 'The web UI was updated. It reloads when the text you are typing is sent or cleared. '
  const button = document.createElement('button')
  button.type = 'button'
  button.textContent = 'Reload now'
  button.addEventListener('click', () => location.reload())
  note.append(button)
  document.body.append(note)
}

let checking = false

async function check(): Promise<void> {
  if (checking || loaded === 'dev') return
  checking = true
  try {
    let answer: unknown = null
    try {
      const response = await fetch('/api/build', { cache: 'no-store' })
      if (response.ok) answer = await response.json()
    } catch {
      answer = null
    }
    const step = updateStep(loaded, answer, typing())
    if (step === 'reload') location.reload()
    else if (step === 'wait') showNote()
  } finally {
    checking = false
  }
}

setInterval(() => { void check() }, CHECK_MS)
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') void check()
})
