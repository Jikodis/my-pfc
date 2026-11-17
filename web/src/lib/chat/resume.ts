/**
 * The live run a page leaves behind for the next page to pick up.
 *
 * Moving to another page closes the stream and not the run, so the page that is
 * leaving writes down which run it was reading and the last event it applied, next
 * to the transcript in sessionStorage. The next page reads it back and asks the
 * attach route for the event after that one. Written and read here so the shape is
 * checked in one place: what comes out of storage is text a person or another page
 * can edit, and the id goes into a request.
 */

/** A run id is what `randomUUID` makes. Nothing else is sent to the attach route. */
export const RUN_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

/** `seq` is the last event applied, -1 when none was yet. */
export type LiveRunRecord = { id: string; seq: number }

export function writeLiveRun(record: LiveRunRecord): string {
  return JSON.stringify({ id: record.id, seq: record.seq })
}

/** The stored run and the index to ask for next, or null for anything that is not one. */
export function readLiveRun(raw: string | null): (LiveRunRecord & { from: number }) | null {
  if (!raw) return null
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return null
  const { id, seq } = value as { id?: unknown; seq?: unknown }
  if (typeof id !== 'string' || !RUN_ID.test(id)) return null
  if (typeof seq !== 'number' || !Number.isSafeInteger(seq) || seq < -1) return null
  return { id, seq, from: seq + 1 }
}
