/**
 * Which build this server is running, and whether it may be restarted now.
 *
 * `astro.config.mjs` stamps every build with its own id. `automations/scripts/run-web.sh`
 * rebuilds when the source changes and swaps the new build in only once this server
 * says it is idle, so a restart never cuts off a chat reply or a save. Pages compare
 * the id they were rendered with against the one the server reports now, and reload
 * when it differs (`src/lib/update-step.ts`, `src/scripts/update-client.ts`). Server only:
 * it imports the chat runner and the writer.
 */
import { liveRuns } from './chat/runner'
import { writeInProgress } from './write'

declare const __PFC_BUILD_ID__: string | undefined

/** `dev` under `astro dev` and in tests, where no build stamped an id. */
export const BUILD_ID: string = typeof __PFC_BUILD_ID__ === 'string' ? __PFC_BUILD_ID__ : 'dev'

/** True while a chat reply is being written or a change is being saved. */
export const serverBusy = (): boolean => liveRuns() > 0 || writeInProgress()

export type BuildStatus = { build: string; busy: boolean }

export const buildStatus = (): BuildStatus => ({ build: BUILD_ID, busy: serverBusy() })
