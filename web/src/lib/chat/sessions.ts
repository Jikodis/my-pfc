/**
 * The conversations this server started, so a resume can only reach its own.
 *
 * A session id that reads like a session id is not enough. Claude Code stores every
 * conversation on this machine under ids of the same shape, so a request carrying any
 * one of them would continue somebody's unrelated work session inside this repo,
 * with the repo's own permissions. So every run writes its id here when the `init`
 * line arrives, and the endpoint resumes an id only when it is in this file.
 *
 * The list lives on disk rather than in memory because a server restart must not
 * throw away the conversation the drawer is holding in its browser tab. It is a
 * plain JSON array of ids, newest last, written whole.
 *
 * Nothing here throws. A missing file, a truncated file, or a file somebody edited
 * into nonsense all read as "no conversations", which costs one resume and never a
 * request.
 */
import { readFileSync, renameSync, unlinkSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { REPO } from '../repo'

/** Overridable so a test never writes to the file the running server reads. */
const FILE = process.env.PFC_CHAT_SESSIONS_FILE || join(REPO, 'web', '.chat-sessions.json')

/** Ids kept. Far more than a person revisits, and small enough to read in one gulp. */
const CAP = 200

function read(): string[] {
  try {
    const parsed: unknown = JSON.parse(readFileSync(FILE, 'utf8'))
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : []
  } catch {
    return []
  }
}

/** Whether this server is the one that started that conversation. */
export function ownsSession(id: string): boolean {
  return read().includes(id)
}

/**
 * Record a conversation this server started.
 *
 * Written to a temporary file and renamed, so a reader either sees the whole old
 * list or the whole new one. Two runs finishing together can still lose one id to
 * the other's copy of the list, which costs that conversation its resume and
 * nothing else, so the write stays this simple.
 */
export function rememberSession(id: string): void {
  const kept = [...read().filter((known) => known !== id), id].slice(-CAP)
  const temp = `${FILE}.${process.pid}.tmp`
  try {
    writeFileSync(temp, `${JSON.stringify(kept)}\n`, { mode: 0o600 })
    renameSync(temp, FILE)
  } catch {
    try {
      unlinkSync(temp)
    } catch {
      // The temp file is already gone, which is the outcome this line wanted.
    }
  }
}
