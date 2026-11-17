/**
 * The edit buttons (`src/components/ActionButton.astro`): one click listener for the
 * whole page.
 *
 * A button with a confirm text first swaps itself for the question and Yes / No, in
 * the page, never `window.confirm`. Yes posts to the write route with the same
 * guard headers the chat drawer sends. While the write runs the button reads
 * `Saving...` and only the edit buttons in its own row (table row or list item) are
 * disabled: the server queues writes and runs them one at a time, so a person can
 * click Done down a list without waiting. The reply is always put into words next
 * to the button (`outcome` in `src/lib/write-ui.ts`); a saved row fades, and the
 * page reloads once every click has its answer and the last words have had time to
 * be read.
 *
 * These buttons carry `data-write-action`, never `data-chat-prompt`, so the chat
 * drawer's own click handler (`promptSource`) never acts on them.
 */
import { PENDING, WRITE_HEADERS, isButtonAction, outcome, requestFor, type Tone } from '../lib/write-ui'

/** Clicks sent and not answered yet. The page reloads only when this is back to zero. */
let pending = 0
/** The earliest moment the page may reload, so the last success stays readable. */
let reloadAt = 0

const wrapOf = (el: Element): HTMLElement | null => el.closest<HTMLElement>('.write')
// `:scope >` because one wrap can hold another (Drop sits inside Done's row), and each
// must find its own button, question, and status words, never the inner one's.
const mainOf = (wrap: HTMLElement): HTMLButtonElement | null => wrap.querySelector<HTMLButtonElement>(':scope > button[data-write-action]')
const statusOf = (wrap: HTMLElement): HTMLElement | null => wrap.querySelector<HTMLElement>(':scope > .write-status')

function say(wrap: HTMLElement, text: string, tone: Tone | null): void {
  const status = statusOf(wrap)
  if (!status) return
  status.textContent = text
  status.className = tone ? `write-status write-${tone}` : 'write-status'
}

function closeConfirm(wrap: HTMLElement): void {
  wrap.querySelector(':scope > .write-confirm')?.remove()
  const main = mainOf(wrap)
  if (main) main.hidden = false
}

function openConfirm(wrap: HTMLElement, main: HTMLButtonElement, question: string): void {
  say(wrap, '', null)
  const box = document.createElement('span')
  box.className = 'write-confirm'
  const text = document.createElement('span')
  text.textContent = question
  const yes = document.createElement('button')
  yes.type = 'button'
  yes.className = 'act write-yes'
  yes.textContent = 'Yes'
  yes.dataset.writeYes = '1'
  const no = document.createElement('button')
  no.type = 'button'
  no.className = 'act'
  no.textContent = 'No'
  no.dataset.writeNo = '1'
  box.append(text, ' ', yes, ' ', no)
  main.hidden = true
  main.after(box)
  yes.focus()
}

/** The record a button belongs to: its table row or list item, or the button's own wrap. */
const rowOf = (wrap: HTMLElement): HTMLElement => wrap.closest<HTMLElement>('tr, li') ?? wrap

/** The edit buttons in one row on or off, except the ones the server rendered disabled. */
function setRow(row: HTMLElement, disabled: boolean): void {
  for (const b of row.querySelectorAll<HTMLButtonElement>('button[data-write-action]')) {
    if (b.dataset.writeLocked === '1') continue
    b.disabled = disabled
  }
}

function reloadWhenSettled(): void {
  if (pending > 0 || reloadAt === 0) return
  setTimeout(() => {
    if (pending === 0) window.location.reload()
  }, Math.max(0, reloadAt - Date.now()))
}

async function send(wrap: HTMLElement, main: HTMLButtonElement): Promise<void> {
  const action = main.dataset.writeAction
  const id = main.dataset.id
  const row = rowOf(wrap)
  if (!isButtonAction(action) || !id || row.dataset.writeBusy === '1') return
  row.dataset.writeBusy = '1'
  pending++
  closeConfirm(wrap)
  const label = main.dataset.label ?? main.textContent ?? ''
  setRow(row, true)
  main.textContent = PENDING
  say(wrap, '', null)

  const { url, body } = requestFor(action, id, main.dataset.writeExtra)
  let status: number | null = null
  let reply: unknown = null
  try {
    const response = await fetch(url, { method: 'POST', headers: WRITE_HEADERS, body })
    status = response.status
    reply = await response.json().catch(() => null)
  } catch {
    status = null
  }

  const result = outcome(status, reply, action)
  say(wrap, result.text, result.tone)
  pending--
  if (result.reloadAfterMs !== null) {
    // The row stays disabled: its record has changed, and the reload shows how.
    main.textContent = result.tone === 'ok' ? 'Saved' : label
    row.classList.add('write-saved')
    reloadAt = Math.max(reloadAt, Date.now() + result.reloadAfterMs)
  } else {
    main.textContent = label
    setRow(row, false)
    delete row.dataset.writeBusy
  }
  reloadWhenSettled()
}

document.addEventListener('click', (event) => {
  const target = event.target
  if (!(target instanceof Element)) return
  const wrap = wrapOf(target)
  if (!wrap) return
  const main = mainOf(wrap)
  if (!main) return

  if (target.closest('[data-write-yes]')) {
    void send(wrap, main)
    return
  }
  if (target.closest('[data-write-no]')) {
    closeConfirm(wrap)
    main.focus()
    return
  }
  if (target.closest('button[data-write-action]') !== main || main.disabled) return
  const question = main.dataset.writeConfirm
  if (question) openConfirm(wrap, main, question)
  else void send(wrap, main)
})

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || !(event.target instanceof Element)) return
  const wrap = wrapOf(event.target)
  if (wrap?.querySelector(':scope > .write-confirm')) {
    closeConfirm(wrap)
    mainOf(wrap)?.focus()
  }
})
