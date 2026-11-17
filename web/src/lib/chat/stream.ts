/**
 * One run's events as a server-sent event stream, shared by the route that starts a
 * run and the route a page uses to pick one up again.
 *
 * The shape is the same for both: one `run` frame carrying the id the stop and
 * attach routes take, then one frame per event from the index asked for, each with
 * its place in the run's log as the frame's `id:` field, then the stream closes once
 * the run is over and its log is read out. A comment frame goes out every fifteen
 * seconds while the run is quiet, because a long silence is how a connection with
 * something in between gets closed underneath it.
 *
 * The browser going away ends this stream and nothing else. The run carries on, and
 * the page that comes back reads the rest of it through the attach route.
 */
import type { Run } from './runner'

/**
 * Quiet time before a comment frame goes out, to keep the connection from being
 * closed. Overridable so a test does not have to wait a quarter of a minute, and
 * never under a second, so a mistyped setting cannot turn it into a flood.
 */
const keepAliveMs = () => Math.max(1_000, Number(process.env.PFC_CHAT_KEEPALIVE_MS) || 15_000)

/** How often the quiet is measured. Shorter than the quiet itself, or the first
 * comment frame always lands a whole period late: a timer that ticks every fifteen
 * seconds first compares at fifteen seconds minus a millisecond and says no. */
const CHECKS_PER_PERIOD = 3

/** How long to wait for the browser to take what it has before writing more. */
const ROOM_TICK_MS = 10

export function runStream(run: Run, from: number): Response {
  const encoder = new TextEncoder()
  let keepAlive: ReturnType<typeof setInterval> | null = null
  // Set once the stream is started: it lets `cancel` end a wait for room or for the
  // next event, because a browser that has gone away will never take what it was sent.
  let cancelled = () => {}

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const quiet = keepAliveMs()
      let open = true
      let lastSent = Date.now()
      const gone = new Promise<null>((resolve) => {
        cancelled = () => {
          open = false
          resolve(null)
        }
      })
      const room = () => (controller.desiredSize ?? 1) > 0
      const send = (frame: string) => {
        if (!open) return
        try {
          controller.enqueue(encoder.encode(frame))
          lastSent = Date.now()
        } catch {
          // The browser is gone. Nothing is left to write to; the run carries on for
          // whichever page comes back for it.
          open = false
        }
      }

      send(`event: run\ndata: ${JSON.stringify({ id: run.id })}\n\n`)
      keepAlive = setInterval(() => {
        if (Date.now() - lastSent >= quiet && room()) send(': keep-alive\n\n')
      }, Math.max(1, Math.round(quiet / CHECKS_PER_PERIOD)))

      void (async () => {
        const events = run.read(from)[Symbol.asyncIterator]()
        try {
          while (open) {
            // Raced against the browser leaving, so a stream nobody reads does not
            // wait out a quiet run before it notices.
            const next = await Promise.race([events.next(), gone])
            if (!next || next.done) break
            // The browser has not taken what it already has, so wait rather than
            // pile more into the stream's queue. The run's log is bounded, so a
            // reader that never comes back costs text and not memory. Once the run
            // is over nothing more is coming, so what is left goes into the queue
            // and the stream closes, instead of this loop outliving the run.
            while (open && !room() && !run.over()) await new Promise((r) => setTimeout(r, ROOM_TICK_MS))
            send(`id: ${next.value.seq}\ndata: ${JSON.stringify(next.value.event)}\n\n`)
          }
        } finally {
          if (keepAlive) clearInterval(keepAlive)
          open = false
          try {
            controller.close()
          } catch {
            // Already closed, which is what this line wanted.
          }
        }
      })()
    },
    cancel() {
      // The page closed or the person moved to another page. The run is not this
      // stream's to stop: only the stop route, the timeout, or the server exiting do that.
      if (keepAlive) clearInterval(keepAlive)
      cancelled()
    },
  })

  return new Response(stream, {
    headers: {
      'content-type': 'text/event-stream; charset=utf-8',
      'cache-control': 'no-store',
      // For anything that might sit between this server and the browser one day.
      'x-accel-buffering': 'no',
    },
  })
}
