/**
 * The chat drawer, in the browser.
 *
 * Astro bundles this file and serves it from this app, so the page's policy needs no
 * exception for it. Everything that can be decided without a document lives in
 * `src/lib/chat/`: the frame parser, the transcript reducer, the one function that
 * turns a reply into safe HTML, and the one that reads a keystroke. This file is the
 * part that has to touch the page, and it is written for a person whose story memory
 * is first percentile, which is why the drawer says where it stands at all times,
 * keeps the transcript when you move between pages, and never throws away what you
 * typed.
 *
 * A reply keeps running when you move to another page. The page that leaves writes
 * down which run it was reading and the last event it applied (`resume.ts`), and the
 * next page picks the run up through `POST /api/chat/attach` from the event after
 * that one. A message sent while a reply is being written waits in a queue above the
 * box (`queue.ts`) and goes when the reply finishes on its own.
 */
import type { ChatEvent } from '../lib/chat/events'
import { parseFrames } from '../lib/chat/frames'
import { promptAction, promptSource, shouldSend, skillAction } from '../lib/chat/input'
import { renderMarkdown } from '../lib/chat/markdown'
import { PINNED } from '../lib/chat/pinned'
import { QUEUE_CAP, enqueue, putBack, removeQueued, restoreQueue, saveQueue, takeNext, type Queue, type Queued } from '../lib/chat/queue'
import { readLiveRun, writeLiveRun, type LiveRunRecord } from '../lib/chat/resume'
import {
  ITEM_CAP,
  addItem,
  addUser,
  dropUser,
  applyEvent,
  errorText,
  finishTurn,
  keyOf,
  newTranscript,
  resendOffer,
  statusOf,
  validItems,
  type Item,
  type Transcript,
} from '../lib/chat/transcript'

type SkillInfo = { name: string; description: string; takesArgs: boolean; prefill?: boolean }

/** How often the transcript is redrawn while text is streaming in. */
const DRAW_MS = 80

/** Distance from the bottom at which new content still follows on its own. */
const STICK_PX = 80

/** Lines of tool output shown before the rest is folded away. */
const OUTPUT_LINES = 6

/** Characters that fill those six lines even when the output holds no newline at all. */
const WIDE_OUTPUT = 380

/** What the fold button says, since one very long line is not "1 line" to a reader. */
const moreLabel = (lines: number) => (lines > 1 ? `Show all ${lines} lines` : 'Show the whole result')

const KEY_SESSION = 'pfc.chat.session'
const KEY_OPEN = 'pfc.chat.open'
const KEY_ITEMS = 'pfc.chat.transcript'
const KEY_RESEND = 'pfc.chat.resend'
const KEY_RUN = 'pfc.chat.run'
const KEY_QUEUE = 'pfc.chat.queue'

/**
 * A queued message sent the moment a reply ends can, in principle, reach the server
 * before it has taken the finished run off its list, and get 409. The stream closes
 * only after that happens, so this is a backstop: a few short waits, then the message
 * goes back to the front of the queue rather than being lost.
 */
const BUSY_RETRIES = 4
const BUSY_WAIT_MS = 500

/** An id for a queued message's row, so its Remove button removes that one. */
function rowId(): string {
  try {
    return crypto.randomUUID()
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
  }
}

/**
 * Storage that is allowed to be missing.
 *
 * A private window, cleared site data, or a browser that refuses both stores is not
 * an error worth showing: the drawer works, it just forgets. Every read and write is
 * wrapped, and a failed read reads as nothing stored.
 */
function get(store: 'local' | 'session', key: string): string | null {
  try {
    return (store === 'local' ? localStorage : sessionStorage).getItem(key)
  } catch {
    return null
  }
}

function put(store: 'local' | 'session', key: string, value: string | null): void {
  try {
    const where = store === 'local' ? localStorage : sessionStorage
    if (value === null) where.removeItem(key)
    else where.setItem(key, value)
  } catch {
    // Nothing to do and nothing to say: the drawer works without it.
  }
}

function el<T extends HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null
}

const drawer = el<HTMLElement>('chat-drawer')
const scroller = el<HTMLElement>('chat-scroll')
const list = el<HTMLElement>('chat-items')
const empty = el<HTMLElement>('chat-empty')
const statusDot = el<HTMLElement>('chat-dot')
const statusWord = el<HTMLElement>('chat-status-text')
const box = el<HTMLTextAreaElement>('chat-text')
const sendButton = el<HTMLButtonElement>('chat-send')
const stopButton = el<HTMLButtonElement>('chat-stop')
const newButton = el<HTMLButtonElement>('chat-new')
const hideButton = el<HTMLButtonElement>('chat-hide')
const tab = el<HTMLButtonElement>('chat-tab')
const tabDot = el<HTMLElement>('chat-tab-dot')
const confirmBar = el<HTMLElement>('chat-confirm')
const confirmYes = el<HTMLButtonElement>('chat-confirm-yes')
const confirmNo = el<HTMLButtonElement>('chat-confirm-no')
const skillsPanel = el<HTMLElement>('chat-skills')
const skillsToggle = el<HTMLButtonElement>('chat-skills-toggle')
const skillsPinned = el<HTMLElement>('chat-skill-pinned')
const skillsDivider = el<HTMLElement>('chat-skill-divider')
const skillsRest = el<HTMLElement>('chat-skill-rest')
const skillFilter = el<HTMLInputElement>('chat-skill-filter')
const after = el<HTMLElement>('chat-after')
const jump = el<HTMLButtonElement>('chat-jump')
const openButton = el<HTMLButtonElement>('chat-open')
const queueBox = el<HTMLElement>('chat-queue')

// Every page carries the drawer, so a missing piece means the markup changed and the
// rest of the page should still work.
if (drawer && scroller && list && statusDot && statusWord && box && sendButton && stopButton && jump && after) {
  start(drawer, scroller, list, statusDot, statusWord, box, sendButton, stopButton, jump, after)
}

function start(
  drawer: HTMLElement,
  scroller: HTMLElement,
  list: HTMLElement,
  statusDot: HTMLElement,
  statusWord: HTMLElement,
  box: HTMLTextAreaElement,
  sendButton: HTMLButtonElement,
  stopButton: HTMLButtonElement,
  jump: HTMLButtonElement,
  after: HTMLElement,
): void {
  let state: Transcript = restore()
  let live = false
  let runId: string | null = null
  let aborter: AbortController | null = null
  /** Set by the Stop button, so the end of the stream reads as a choice, not a fault. */
  let stoppedByHand = false
  /** True while the last thing that happened is a message the server would not take. */
  let notSent = false
  /** The one automatic retry after a session this server no longer owns. */
  let retried = false
  /** Whether the run that starts clears the box: true for a message typed there and sent. */
  let clearBox = false
  /** The queued message in flight, so a refusal puts it back instead of losing it. */
  let fromQueue: Queued | null = null
  /** The last event applied to the transcript, by its place in the run's log. */
  let lastSeq = -1
  /** The kind of the last event applied this turn: a `done` or an `error` means it ended on its own. */
  let endedWith: string | null = null
  /** Messages waiting for the reply in progress to finish. */
  let queue: Queue = restoreQueue(get('session', KEY_QUEUE))
  /** True once the page is going away, so a turn's ending is written only once. */
  let left = false
  let opener: HTMLElement | null = null
  let skills: SkillInfo[] | null = null
  /**
   * The node drawn for each item, by the item's stable key (`keyOf`), not its index.
   * When the cap drops the oldest items every index shifts, and nodes held by index
   * would each be handed a different item: every assistant block re-rendered, and an
   * opened tool line's open state moved onto the wrong tool.
   */
  let nodes = new Map<number, HTMLElement>()
  let drawTimer: ReturnType<typeof setTimeout> | null = null
  let lastDraw = 0
  /** One past the key of the last item drawn, so new content is noticed at the cap too. */
  let drawnEnd = 0
  let lastStatus = ''
  /**
   * Which turn is in flight. A reply that is stopped or cleared while its stream is
   * still unwinding must not write its ending onto the conversation that replaced it.
   */
  let turn = 0

  // ---------------------------------------------------------------- transcript

  function restore(): Transcript {
    const session = get('local', KEY_SESSION)
    const raw = get('session', KEY_ITEMS)
    if (!raw) return newTranscript([], session)
    try {
      // What comes back was written by this app, but it is text, and the renderer
      // reads these fields straight into the document.
      return newTranscript(validItems(JSON.parse(raw)), session)
    } catch {
      return newTranscript([], session)
    }
  }

  /**
   * The transcript and the run it is reading, written together.
   *
   * They have to agree: the next page asks for the event after `lastSeq` and applies
   * it to this transcript, so a transcript saved behind its number would lose events
   * and one saved ahead would show them twice.
   */
  function save(): void {
    put('session', KEY_ITEMS, JSON.stringify(state.items.slice(-ITEM_CAP)))
    const record: LiveRunRecord | null = live && runId ? { id: runId, seq: lastSeq } : null
    put('session', KEY_RUN, record ? writeLiveRun(record) : null)
  }

  function nearBottom(): boolean {
    return scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < STICK_PX
  }

  function mark(item: Extract<Item, { kind: 'tool' }>): HTMLElement {
    const span = document.createElement('span')
    if (item.status === 'running') {
      span.className = 'chat-dots'
      span.title = 'Running'
      span.append(document.createElement('i'), document.createElement('i'), document.createElement('i'))
      return span
    }
    const marks = { ok: ['✓', 'Worked'], failed: ['✗', 'Failed'], refused: ['○', 'Refused'] } as const
    const [glyph, word] = marks[item.status]
    span.className = `chat-mark-${item.status}`
    span.textContent = glyph
    span.title = word
    return span
  }

  function create(item: Item): HTMLElement {
    const node = document.createElement('div')
    node.dataset.kind = item.kind
    switch (item.kind) {
      case 'user':
        node.className = 'chat-user'
        break
      case 'assistant': {
        node.className = 'chat-assistant'
        const copy = document.createElement('button')
        copy.type = 'button'
        copy.className = 'chat-copy'
        copy.textContent = 'Copy'
        const body = document.createElement('div')
        body.className = 'chat-md'
        node.append(copy, body)
        break
      }
      case 'tool': {
        const details = document.createElement('details')
        details.className = 'chat-tool'
        details.dataset.kind = 'tool'
        const summary = document.createElement('summary')
        const tag = document.createElement('span')
        tag.className = 'chat-tool-tag'
        const sum = document.createElement('span')
        sum.className = 'chat-tool-sum'
        summary.append(mark(item), tag, sum)
        const body = document.createElement('div')
        body.className = 'chat-tool-body'
        const out = document.createElement('pre')
        out.className = 'chat-tool-out'
        const more = document.createElement('button')
        more.type = 'button'
        more.className = 'chat-tool-more'
        more.hidden = true
        body.append(out, more)
        details.append(summary, body)
        return details
      }
      case 'refusals': {
        node.className = 'chat-refusals'
        const line = document.createElement('p')
        const items = document.createElement('ul')
        node.append(line, items)
        break
      }
      case 'error':
        node.className = 'chat-error'
        break
      case 'note':
        node.className = 'chat-note'
        break
      case 'done': {
        node.className = 'chat-done'
        const words = document.createElement('span')
        const link = document.createElement('a')
        link.className = 'chat-reload'
        link.textContent = 'Reload page to see changes'
        link.hidden = true
        node.append(words, link)
        break
      }
    }
    return node
  }

  /**
   * One item's node brought up to date.
   *
   * The node is changed in place rather than replaced, so a tool result the person
   * has opened stays open while the rest of the turn streams in, and the assistant
   * block you are reading does not jump under you.
   */
  function update(node: HTMLElement, item: Item, key: number): void {
    switch (item.kind) {
      case 'user':
      case 'error':
      case 'note':
        // Never innerHTML: a tool's output and an error's text are not markup.
        node.textContent = item.text
        break
      case 'assistant': {
        const body = node.querySelector('.chat-md')
        if (body && node.dataset.src !== item.text) {
          node.dataset.src = item.text
          body.innerHTML = renderMarkdown(item.text)
        }
        node.dataset.key = String(key)
        break
      }
      case 'tool': {
        const summary = node.querySelector('summary')
        const tag = node.querySelector('.chat-tool-tag')
        const sum = node.querySelector('.chat-tool-sum')
        const out = node.querySelector('.chat-tool-out')
        const more = node.querySelector('.chat-tool-more')
        if (!summary || !tag || !sum || !(out instanceof HTMLElement) || !(more instanceof HTMLButtonElement)) return
        if (node.dataset.status !== item.status) {
          node.dataset.status = item.status
          const first = summary.firstChild
          if (first) summary.replaceChild(mark(item), first)
          else summary.prepend(mark(item))
        }
        tag.textContent = item.name
        ;(tag as HTMLElement).hidden = !item.name
        sum.textContent = item.summary
        const text = item.result || (item.status === 'running' ? 'Waiting for the result.' : 'No output.')
        if (out.textContent !== text) {
          out.textContent = text
          // Long by lines or by sheer length: one unbroken paragraph of output wraps
          // to a dozen rows and buries the reply under it just as surely.
          const lines = text.split('\n').length
          const long = lines > OUTPUT_LINES || text.length > WIDE_OUTPUT
          // A long result is folded rather than cut: the whole of it is one press away.
          const expanded = node.dataset.expanded === '1'
          out.classList.toggle('chat-clamped', long && !expanded)
          more.hidden = !long
          more.textContent = expanded ? 'Show less' : moreLabel(lines)
        }
        break
      }
      case 'refusals': {
        const line = node.querySelector('p')
        const ul = node.querySelector('ul')
        if (!line || !ul) return
        const count = item.denied.length
        line.textContent = count === 1
          ? 'Refused 1 action. Add it to the allow list in .claude/settings.json if you want it.'
          : `Refused ${count} actions. Add them to the allow list in .claude/settings.json if you want them.`
        ul.textContent = ''
        for (const one of item.denied) {
          const li = document.createElement('li')
          li.textContent = `${one.tool} ${one.summary}`.trim()
          ul.append(li)
        }
        break
      }
      case 'done': {
        const words = node.querySelector('span')
        const link = node.querySelector('.chat-reload')
        if (!words || !(link instanceof HTMLAnchorElement)) return
        const seconds = (item.ms / 1000).toFixed(1)
        words.textContent = item.ok
          ? `Finished in ${seconds} seconds, ${item.turns} turn${item.turns === 1 ? '' : 's'}.`
          : `Ended without finishing, after ${seconds} seconds.`
        // Offered only when the turn ran something that can write, so it stops
        // being a line that appears after every reply and means nothing.
        link.hidden = !item.changed
        link.href = location.href
        break
      }
    }
  }

  function setStatus(): void {
    const status = statusOf(state, { live, notSent })
    // An aria-live region announces every assignment, so it is assigned only when
    // the words actually changed.
    if (status.text !== lastStatus) {
      lastStatus = status.text
      statusWord.textContent = status.text
    }
    statusDot.className = `chat-dot chat-dot-${status.tone}`
    syncTab()
  }

  /** The edge tab: shown only while the drawer is hidden and holds a conversation, with the same dot as the header. */
  function syncTab(): void {
    if (!tab) return
    tab.hidden = isOpen() || state.items.length === 0
    document.documentElement.classList.toggle('chat-tabbed', !tab.hidden)
    if (tabDot) tabDot.className = statusDot.className
  }

  /**
   * The transcript, brought up to date.
   *
   * It follows the bottom only while the person is already there. Once they have
   * scrolled up to read something, new content below is announced and nothing moves
   * under them. `toBottom` is for the moments that are not new content: opening the
   * drawer, and starting over.
   */
  function draw(toBottom = false): void {
    const stick = toBottom || nearBottom()
    const first = state.base
    const end = keyOf(state, state.items.length)
    const grew = end !== drawnEnd
    // Items the cap dropped from the front, and any taken back from the end.
    for (const [key, node] of nodes) {
      if (key >= first && key < end) continue
      node.remove()
      nodes.delete(key)
    }
    state.items.forEach((item, i) => {
      const key = keyOf(state, i)
      const held = nodes.get(key)
      if (held && held.dataset.kind === item.kind) {
        update(held, item, key)
        return
      }
      const node = create(item)
      update(node, item, key)
      // A key not held yet is always past every key that is, so it goes at the end.
      if (held) held.replaceWith(node)
      else list.append(node)
      nodes.set(key, node)
    })
    drawnEnd = end
    if (empty) empty.hidden = state.items.length > 0
    setStatus()
    // Saving is a full serialize and a synchronous write, so it rides with the draw
    // rather than running once per streamed character.
    save()
    if (stick) {
      scroller.scrollTop = scroller.scrollHeight
      jump.hidden = true
    } else if (live || grew) {
      jump.hidden = false
    }
  }

  /** Redrawn at most every eighty milliseconds, because a delta can arrive per character. */
  function schedule(): void {
    const since = Date.now() - lastDraw
    if (since >= DRAW_MS) {
      lastDraw = Date.now()
      draw()
      return
    }
    if (drawTimer) return
    drawTimer = setTimeout(() => {
      drawTimer = null
      lastDraw = Date.now()
      draw()
    }, DRAW_MS - since)
  }

  function show(item: Item): void {
    state = addItem(state, item)
    draw()
  }

  // ---------------------------------------------------------------- the drawer

  function isOpen(): boolean {
    return !drawer.hidden
  }

  function open(from?: HTMLElement | null, focus = true): void {
    if (from) opener = from
    drawer.hidden = false
    document.documentElement.classList.add('chat-docked')
    put('local', KEY_OPEN, '1')
    openButton?.setAttribute('aria-expanded', 'true')
    draw(true)
    syncTab()
    if (focus) box.focus()
  }

  /** Hide, never end: the conversation and a running reply carry on. */
  function close(): void {
    drawer.hidden = true
    document.documentElement.classList.remove('chat-docked')
    put('local', KEY_OPEN, '0')
    openButton?.setAttribute('aria-expanded', 'false')
    syncTab()
    const back = opener && opener.isConnected ? opener : openButton
    back?.focus()
  }

  function toggle(from?: HTMLElement | null): void {
    if (isOpen()) close()
    else open(from)
  }

  /** Text into the box without losing what is already there, caret at the end. */
  function fill(text: string): void {
    const held = box.value.trim()
    box.value = held ? `${box.value.replace(/\s+$/, '')}\n${text}` : text
    grow()
    box.focus()
    box.setSelectionRange(box.value.length, box.value.length)
  }

  function grow(): void {
    const style = getComputedStyle(box)
    const line = parseFloat(style.lineHeight) || 21
    const pad = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom) + 2
    const max = line * 8 + pad
    box.style.height = 'auto'
    const wanted = box.scrollHeight
    box.style.height = `${Math.min(wanted, max)}px`
    box.style.overflowY = wanted > max ? 'auto' : 'hidden'
  }

  function setLive(on: boolean): void {
    live = on
    // Send stays live while a reply is being written: what it sends then waits in
    // the queue for that reply to finish.
    sendButton.title = on ? 'Adds the message to the queue. It is sent when this reply finishes.' : ''
    stopButton.disabled = !on
    // A skill pressed while a reply is being written would go nowhere and say
    // nothing, so it reads as unavailable, the way Send does.
    for (const button of document.querySelectorAll('.chat-skill')) {
      if (button instanceof HTMLButtonElement) button.disabled = on
    }
    setStatus()
    drawQueue()
  }

  // ---------------------------------------------------------------- the queue

  function setQueue(next: Queue): void {
    queue = next
    put('session', KEY_QUEUE, queue.length ? saveQueue(queue) : null)
    drawQueue()
  }

  /**
   * The queue, just above the box: what is waiting, each with its own Remove button,
   * and a Send next button whenever nothing is running to send it on its own.
   */
  function drawQueue(): void {
    if (!queueBox) return
    queueBox.textContent = ''
    queueBox.hidden = queue.length === 0
    if (!queue.length) return
    const head = document.createElement('div')
    head.className = 'chat-queue-head'
    const label = document.createElement('span')
    const full = queue.length >= QUEUE_CAP ? ' The queue is full.' : ''
    label.textContent = live
      ? `Queued: ${queue.length}. The first is sent when this reply finishes.${full}`
      : `Queued: ${queue.length}. Not sent yet.${full}`
    head.append(label)
    if (!live) {
      const next = document.createElement('button')
      next.type = 'button'
      next.className = 'chat-queue-next'
      next.textContent = 'Send next'
      next.addEventListener('click', () => void sendQueued())
      head.append(next)
    }
    const rows = document.createElement('ul')
    for (const item of queue) {
      const row = document.createElement('li')
      const text = document.createElement('span')
      text.className = 'chat-queue-text'
      // Never innerHTML: a queued message is what was typed, not markup.
      text.textContent = item.text
      text.title = item.text
      const remove = document.createElement('button')
      remove.type = 'button'
      remove.className = 'chat-queue-remove'
      remove.textContent = 'Remove'
      remove.setAttribute('aria-label', `Remove queued message: ${item.text.slice(0, 60)}`)
      remove.addEventListener('click', () => setQueue(removeQueued(queue, item.id)))
      row.append(text, remove)
      rows.append(row)
    }
    queueBox.append(head, rows)
  }

  /** The first queued message, sent into this conversation as if Send had been pressed. */
  async function sendQueued(): Promise<void> {
    if (live) return
    const { next, rest } = takeNext(queue)
    if (!next) return
    setQueue(rest)
    retried = false
    await run(next.text, { fromBox: false, queued: next, busyTries: 0 })
  }

  /** The line above the composer: the way back from a reply that was cut off. */
  function offerResend(message: string | null): void {
    after.textContent = ''
    if (!message) return
    const text = document.createElement('span')
    text.textContent = 'That reply was cut off.'
    const again = document.createElement('button')
    again.type = 'button'
    again.textContent = 'Send it again'
    again.addEventListener('click', () => {
      put('session', KEY_RESEND, null)
      after.textContent = ''
      void send(message)
    })
    after.append(text, again)
  }

  // ---------------------------------------------------------------- sending

  function sessionId(): string | null {
    return get('local', KEY_SESSION)
  }

  /**
   * Send pressed, by the button or by Enter.
   *
   * While a reply is being written the message joins the queue and the box empties,
   * the way Claude Code takes what is typed while it works. With nothing running, an
   * empty box sends the first queued message, which is the way to carry on after Stop.
   */
  async function send(text: string): Promise<void> {
    const message = text.trim()
    if (live) {
      if (!message) return
      const next = enqueue(queue, message, rowId())
      // Full, or too long to hold: it stays in the box rather than vanishing.
      if (next === queue) return
      setQueue(next)
      box.value = ''
      grow()
      return
    }
    if (!message) {
      await sendQueued()
      return
    }
    retried = false
    await run(message, { fromBox: true, queued: null, busyTries: 0 })
  }

  type RunOptions = { fromBox: boolean; queued: Queued | null; busyTries: number }

  async function run(message: string, opts: RunOptions): Promise<void> {
    stoppedByHand = false
    notSent = false
    runId = null
    lastSeq = -1
    endedWith = null
    clearBox = opts.fromBox
    fromQueue = opts.queued
    turn += 1
    // On screen and stored before the request goes out, so a page left at any point
    // from here on offers this message again. A refusal takes it back (`unsend`).
    state = addUser(state, message)
    put('session', KEY_RESEND, message)
    after.textContent = ''
    setLive(true)
    draw(true)
    const sent = sessionId()
    aborter = new AbortController()
    let response: Response
    try {
      response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-PFC-Chat': '1' },
        body: JSON.stringify({ message, ...(sent ? { sessionId: sent } : {}) }),
        signal: aborter.signal,
      })
    } catch {
      // Leaving the page aborted this request before the run answered. The message
      // was stored above to offer again on the next page, and no ending is written.
      if (left) return
      unsend(message)
      requeue()
      setLive(false)
      // An abort before the reply arrived is the person's own doing, not a failure.
      if (!stoppedByHand) {
        notSent = true
        show({ kind: 'error', text: 'Could not reach the local server.' })
      }
      return
    }
    if (!response.ok) {
      await refused(response, message, sent !== null, opts)
      return
    }
    await read(response)
  }

  /** A queued message that did not become a turn goes back to the front of the queue. */
  function requeue(): void {
    if (!fromQueue) return
    setQueue(putBack(queue, fromQueue))
    fromQueue = null
  }

  /**
   * Pick up a run that a page before this one started, from the event after the
   * last one that page applied. From here it reads exactly as a run this page
   * started: the same stream, the same Stop, the same ending.
   */
  async function attach(record: LiveRunRecord & { from: number }): Promise<void> {
    stoppedByHand = false
    notSent = false
    clearBox = false
    fromQueue = null
    endedWith = null
    runId = record.id
    lastSeq = record.seq
    turn += 1
    after.textContent = ''
    setLive(true)
    draw()
    aborter = new AbortController()
    let response: Response
    try {
      response = await fetch('/api/chat/attach', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-PFC-Chat': '1' },
        body: JSON.stringify({ id: record.id, from: record.from }),
        signal: aborter.signal,
      })
    } catch {
      if (left) return
      runId = null
      aborter = null
      setLive(false)
      if (stoppedByHand) {
        state = finishTurn(state, 'stopped')
        draw()
      } else {
        show({ kind: 'error', text: 'Could not reach the local server to pick this reply up again.' })
      }
      return
    }
    if (!response.ok) {
      let body = ''
      try {
        body = (await response.text()).trim()
      } catch {
        body = ''
      }
      runId = null
      aborter = null
      setLive(false)
      // Gone means it finished, or was stopped, longer ago than the server keeps it.
      if (response.status === 404) show({ kind: 'note', text: 'This reply ended while you were away.', stopped: false })
      else show({ kind: 'error', text: errorText(body || `The server answered ${response.status}.`) })
      return
    }
    await read(response)
  }

  /**
   * A refusal from the server, said in words that name the next move.
   *
   * What the person typed is still in the box in every one of these, because the box
   * is only cleared when a run has actually started.
   */
  async function refused(response: Response, message: string, hadSession: boolean, opts: RunOptions): Promise<void> {
    let body = ''
    try {
      body = (await response.text()).trim()
    } catch {
      body = ''
    }
    unsend(message)
    setLive(false)
    // A queued message sent as the last reply ended, a moment before the server had
    // let go of that reply: wait briefly and try again, rather than drop it.
    if (response.status === 409 && opts.queued && opts.busyTries < BUSY_RETRIES) {
      await new Promise((r) => setTimeout(r, BUSY_WAIT_MS))
      if (!live && !left) {
        await run(message, { ...opts, busyTries: opts.busyTries + 1 })
        return
      }
    }
    if (response.status === 403 && hadSession && /conversation/i.test(body)) {
      put('local', KEY_SESSION, null)
      state = { ...state, sessionId: null }
      show({ kind: 'note', text: 'That conversation is no longer available here. Starting a new one.', stopped: false })
      if (!retried) {
        retried = true
        await run(message, opts)
        return
      }
    }
    requeue()
    const said = {
      409: 'A reply is still in progress for this conversation.',
      413: 'That message is too long.',
      429: 'Three replies are already running. Stop one or wait.',
    } as Record<number, string>
    notSent = true
    // Anything else is the server's own words, which may be newer than this file.
    show({ kind: 'error', text: said[response.status] ?? errorText(body || `The server answered ${response.status}.`) })
  }

  /** The message never became a turn: out of the transcript, and nothing to resend. */
  function unsend(message: string): void {
    state = dropUser(state, message)
    put('session', KEY_RESEND, null)
    draw()
  }

  async function read(response: Response): Promise<void> {
    const mine = turn
    const body = response.body
    if (!body) {
      setLive(false)
      show({ kind: 'error', text: 'The reply ended unexpectedly.' })
      return
    }
    const reader = body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    try {
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parsed = parseFrames(buffer)
        buffer = parsed.rest
        for (const frame of parsed.frames) take(frame.event, frame.data, frame.id)
        schedule()
      }
    } catch {
      // A stop aborts the reader, and so does the server going away mid-run. Which
      // one it was is settled below, by whether the person pressed the button.
    }
    if (drawTimer) {
      clearTimeout(drawTimer)
      drawTimer = null
    }
    // Started over, or another turn began: this one's ending belongs to a
    // conversation that is no longer on screen. Leaving the page is different: the
    // run carries on without this page, and the next page picks it up from what
    // `leaving` saved, so nothing here may end the turn or forget the run.
    if (mine !== turn || left) return
    // Ended on its own: the stream closed after the run's last event, a reply or an
    // error. The server takes a run off its list before it closes the stream, so a
    // queued message sent now is not refused as a second reply in this conversation.
    const onItsOwn = !stoppedByHand && (endedWith === 'done' || endedWith === 'error')
    state = finishTurn(state, stoppedByHand ? 'stopped' : 'ended')
    // The turn is over either way, so an offer to send it again belongs to this
    // ending and not to the one before it.
    put('session', KEY_RESEND, null)
    after.textContent = ''
    runId = null
    aborter = null
    fromQueue = null
    setLive(false)
    draw()
    // A Stop leaves the queue where it is, for Send next or an empty Send.
    if (onItsOwn && queue.length) void sendQueued()
  }

  function take(event: string | null, data: string, id?: string): void {
    let parsed: unknown
    try {
      parsed = JSON.parse(data)
    } catch {
      return
    }
    if (event === 'run') {
      const run = (parsed as { id?: unknown }).id
      runId = typeof run === 'string' ? run : null
      // The run exists, so the message has become a turn, and a queued one has left
      // the queue for good. A message typed in the box leaves the box now too; a
      // queued one never touches what is being typed there.
      fromQueue = null
      put('session', KEY_RESEND, null)
      after.textContent = ''
      if (clearBox) {
        box.value = ''
        grow()
      }
      draw()
      return
    }
    if (typeof parsed !== 'object' || parsed === null) return
    if (typeof (parsed as { kind?: unknown }).kind !== 'string') return
    // Each event's place in the run's log. One at or before the last applied is one
    // this transcript already has, which a page that picks a run up must not add twice.
    if (id !== undefined && /^\d+$/.test(id)) {
      const seq = Number(id)
      if (seq <= lastSeq) return
      lastSeq = seq
    }
    const chat = parsed as ChatEvent
    endedWith = chat.kind
    state = applyEvent(state, chat)
    if (chat.kind === 'session') put('local', KEY_SESSION, chat.id)
  }

  async function stop(): Promise<void> {
    if (!live) return
    stoppedByHand = true
    // Held now: a message sent while the stop request is in the air must not have
    // its own connection aborted by this one.
    const stopping = runId
    const mine = aborter
    if (stopping) {
      try {
        await fetch('/api/chat/stop', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-PFC-Chat': '1' },
          body: JSON.stringify({ id: stopping }),
        })
      } catch {
        // The run is stopped by the abort below in any case.
      }
    }
    mine?.abort()
  }

  // ---------------------------------------------------------------- skills

  async function loadSkills(): Promise<void> {
    if (skills || !skillsRest) return
    try {
      const response = await fetch('/api/chat/skills', { headers: { 'X-PFC-Chat': '1' } })
      if (!response.ok) throw new Error('no skills')
      const got: unknown = await response.json()
      skills = Array.isArray(got) ? (got as SkillInfo[]) : []
    } catch {
      // Left unset, so the next press tries again instead of showing an empty list
      // for the rest of the page's life.
      skills = null
      showSkillRetry()
      return
    }
    drawSkills()
  }

  function showSkillRetry(): void {
    if (!skillsRest || !skillsPinned) return
    skillsPinned.textContent = ''
    skillsRest.textContent = ''
    if (skillsDivider) skillsDivider.hidden = true
    const retry = document.createElement('button')
    retry.type = 'button'
    retry.className = 'chat-skill'
    retry.textContent = 'Could not load the skill list. Try again.'
    retry.addEventListener('click', () => {
      skillsRest.textContent = ''
      void loadSkills()
    })
    skillsRest.append(retry)
  }

  /** `pfc-daily-summary` reads as `daily summary`, which is what it is called out loud. */
  function plainName(name: string): string {
    return name.replace(/^pfc-/, '').replace(/-/g, ' ')
  }

  function skillButton(skill: SkillInfo): HTMLElement {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'chat-skill'
    button.disabled = live
    const name = document.createElement('span')
    name.textContent = plainName(skill.name)
    const desc = document.createElement('span')
    desc.className = 'chat-skill-desc'
    desc.textContent = skill.description
    button.append(name, desc)
    button.addEventListener('click', () => {
      const action = skillAction(skill)
      if (action.send) void send(action.text)
      else fill(action.text)
    })
    return button
  }

  function drawSkills(): void {
    if (!skillsPinned || !skillsRest || !skills) return
    const query = (skillFilter?.value ?? '').trim().toLowerCase()
    const byName = (skill: SkillInfo) => plainName(skill.name).includes(query) || skill.name.includes(query)
    const matches = (skill: SkillInfo) => !query || byName(skill) || skill.description.toLowerCase().includes(query)
    // A name match comes first. Typing `persona` and being offered `add insight`,
    // because its description holds the word `personal`, is how the wrong skill runs.
    const shown = query
      ? [...skills.filter((s) => byName(s)), ...skills.filter((s) => !byName(s) && matches(s))]
      : skills.filter(matches)
    const pinned = query ? [] : PINNED.map((name) => shown.find((s) => s.name === name)).filter((s): s is SkillInfo => !!s)
    const rest = shown.filter((skill) => !pinned.includes(skill))

    skillsPinned.textContent = ''
    skillsRest.textContent = ''
    for (const skill of pinned) skillsPinned.append(skillButton(skill))
    if (skillsDivider) skillsDivider.hidden = !pinned.length || !rest.length
    for (const skill of rest) skillsRest.append(skillButton(skill))
    if (!shown.length) {
      const none = document.createElement('p')
      none.className = 'chat-skill-note'
      none.textContent = 'No skill matches that.'
      skillsRest.append(none)
    }
  }

  function skillsOpen(): boolean {
    return !!skillsPanel && !skillsPanel.hidden
  }

  function showSkills(on: boolean): void {
    if (!skillsPanel) return
    skillsPanel.hidden = !on
    skillsToggle?.setAttribute('aria-expanded', on ? 'true' : 'false')
    if (on) {
      void loadSkills()
      skillFilter?.focus()
    }
  }

  // ---------------------------------------------------------------- wiring

  sendButton.addEventListener('click', () => void send(box.value))
  stopButton.addEventListener('click', () => void stop())
  hideButton?.addEventListener('click', () => close())
  tab?.addEventListener('click', () => open(tab))
  openButton?.addEventListener('click', () => toggle(openButton))
  jump.addEventListener('click', () => {
    scroller.scrollTop = scroller.scrollHeight
    jump.hidden = true
  })
  scroller.addEventListener('scroll', () => {
    if (nearBottom()) jump.hidden = true
  })
  skillsToggle?.addEventListener('click', () => showSkills(!skillsOpen()))
  skillFilter?.addEventListener('input', () => drawSkills())

  box.addEventListener('input', grow)
  box.addEventListener('keydown', (event) => {
    if (!shouldSend(event)) return
    event.preventDefault()
    void send(box.value)
  })

  // New chat asks first, inside the drawer. A browser confirm box blocks the page and
  // cannot be reached by anything driving the app.
  function confirmOpen(): boolean {
    return !!confirmBar && !confirmBar.hidden
  }
  function askConfirm(on: boolean): void {
    if (!confirmBar) return
    confirmBar.hidden = !on
    if (on) confirmYes?.focus()
    else newButton?.focus()
  }
  newButton?.addEventListener('click', () => {
    if (!state.items.length) {
      clear()
      return
    }
    askConfirm(true)
  })
  confirmNo?.addEventListener('click', () => askConfirm(false))
  confirmYes?.addEventListener('click', () => {
    askConfirm(false)
    clear()
  })

  function clear(): void {
    void stop()
    turn += 1
    state = newTranscript([], null)
    nodes = new Map()
    drawnEnd = 0
    notSent = false
    list.textContent = ''
    put('local', KEY_SESSION, null)
    put('session', KEY_ITEMS, null)
    put('session', KEY_RESEND, null)
    put('session', KEY_RUN, null)
    after.textContent = ''
    setLive(false)
    setQueue([])
    draw(true)
    box.focus()
  }

  // The page's own hook: a button anywhere can hand the drawer a prompt. One
  // listener. It places the prompt in the box for the person to send, except a bare
  // slash command whose button asks to send at once: see `promptAction`.
  document.addEventListener('click', (event) => {
    // Only a button acts, and never a click on a link: see `promptSource`.
    const source = promptSource(event.target)
    if (!source) return
    event.preventDefault()
    // A button with `data-chat-input` adds what its box holds, as the quick-add does.
    const field = source.dataset.chatInput ? document.getElementById(source.dataset.chatInput) : null
    const typed = field instanceof HTMLInputElement ? field.value : undefined
    const action = promptAction(source.dataset.chatPrompt ?? '', { send: source.dataset.chatSend, typed })
    if (field instanceof HTMLInputElement) field.value = ''
    open(source)
    // A reply still being written would swallow a send, so the prompt waits in the box.
    if (action.send && !live) void send(action.text)
    else fill(action.text)
  })

  // Enter in a page box that feeds a prompt button presses that button.
  document.addEventListener('keydown', (event) => {
    const field = event.target
    if (!(field instanceof HTMLInputElement) || !field.dataset.chatEnter || !shouldSend(event)) return
    const button = document.getElementById(field.dataset.chatEnter)
    if (!(button instanceof HTMLButtonElement)) return
    event.preventDefault()
    button.click()
  })

  list.addEventListener('click', (event) => {
    const target = event.target
    if (!(target instanceof Element)) return

    // Fold a long tool result open, or back.
    const more = target.closest('.chat-tool-more')
    if (more instanceof HTMLButtonElement) {
      const tool = more.closest('.chat-tool')
      const out = tool?.querySelector('.chat-tool-out')
      if (tool instanceof HTMLElement && out instanceof HTMLElement) {
        const expanded = tool.dataset.expanded === '1'
        tool.dataset.expanded = expanded ? '0' : '1'
        out.classList.toggle('chat-clamped', expanded)
        const lines = (out.textContent ?? '').split('\n').length
        more.textContent = expanded ? moreLabel(lines) : 'Show less'
      }
      return
    }

    // The copy button on an assistant block copies the markdown it was written in.
    const button = target.closest('.chat-copy')
    if (!(button instanceof HTMLButtonElement)) return
    const block = button.closest('.chat-assistant')
    if (!(block instanceof HTMLElement)) return
    const item = state.items[Number(block.dataset.key) - state.base]
    if (!item || item.kind !== 'assistant') return
    const writing = navigator.clipboard?.writeText(item.text)
    if (!writing) {
      button.textContent = 'Copy failed'
      return
    }
    void writing.then(
      () => {
        button.textContent = 'Copied'
        setTimeout(() => { button.textContent = 'Copy' }, 1500)
      },
      () => { button.textContent = 'Copy failed' },
    )
  })

  /**
   * Whether a keystroke belongs to a field on the page rather than to the drawer.
   *
   * The search box is a field where Cmd+K may well mean something to the browser, so
   * a shortcut pressed inside one with text selected is left alone.
   */
  function inOwnField(target: EventTarget | null): boolean {
    if (!(target instanceof HTMLElement)) return false
    if (drawer.contains(target)) return false
    if (target.isContentEditable) return true
    if (!(target instanceof HTMLInputElement) && !(target instanceof HTMLTextAreaElement)) return false
    return target.selectionStart !== target.selectionEnd
  }

  document.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      if (inOwnField(event.target)) return
      event.preventDefault()
      toggle(event.target instanceof HTMLElement ? event.target : null)
      return
    }
    if (event.key !== 'Escape' || !isOpen()) return
    // Esc closes the drawer only once the two things inside it are closed.
    if (skillsOpen()) {
      showSkills(false)
      event.preventDefault()
      return
    }
    if (confirmOpen()) {
      askConfirm(false)
      event.preventDefault()
      return
    }
    close()
    event.preventDefault()
  })

  /**
   * Leaving the page.
   *
   * The reply keeps running on the server. This writes down the transcript and the
   * run it is reading, together, so the next page can pick the run up from the next
   * event, then closes the connection so the server stops writing to a page that is
   * gone. No ending is written: the turn is not over. Only `pagehide`: it fires on
   * every real leave, including into the back forward cache. `beforeunload` also
   * fires for a download link or a mail link that leaves the page where it is.
   *
   * A message sent a moment before the leave, whose run had not answered yet, is
   * still stored to offer again (`run` stored it before the request went out).
   */
  function leaving(): void {
    if (left || !live) return
    left = true
    if (drawTimer) {
      clearTimeout(drawTimer)
      drawTimer = null
    }
    save()
    aborter?.abort()
  }
  addEventListener('pagehide', leaving)

  /**
   * Pick up whatever the last page left: a run still going, or a message to offer
   * again. Run on load and on a return to a page the browser kept whole. The stored
   * run is read by the caller before anything is drawn, because every draw saves,
   * and a save with nothing live clears it.
   */
  function resume(record: ReturnType<typeof readLiveRun>): void {
    if (record) {
      void attach(record)
      return
    }
    put('session', KEY_RUN, null)
    const waiting = resendOffer(state, get('session', KEY_RESEND))
    if (waiting) offerResend(waiting)
    else put('session', KEY_RESEND, null)
  }

  // Back to a page the browser kept whole. Another page may have read more of the
  // run, or held a whole new turn, since this one was put away, so the transcript,
  // the queue, and the run are read from storage again rather than from memory.
  addEventListener('pageshow', (event) => {
    if (!event.persisted) return
    const record = readLiveRun(get('session', KEY_RUN))
    left = false
    turn += 1
    runId = null
    aborter = null
    state = restore()
    queue = restoreQueue(get('session', KEY_QUEUE))
    nodes = new Map()
    drawnEnd = 0
    list.textContent = ''
    setLive(false)
    draw()
    resume(record)
  })

  // ---------------------------------------------------------------- opening state

  const pending = readLiveRun(get('session', KEY_RUN))

  // Reopening where it was left is not the same as opening it, so the caret stays
  // where the browser put it and the page is not taken over on every load.
  if (get('local', KEY_OPEN) === '1') open(openButton, false)
  else draw(true)
  drawQueue()
  grow()
  resume(pending)
}
