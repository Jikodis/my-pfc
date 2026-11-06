import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
    // Files run in parallel. A test file that creates or deletes folders works in its
    // own copy of the fixture tree (test/helpers/temp-repo.ts), never in this one.
    env: { PFC_REPO_ROOT: fileURLToPath(new URL('./test/fixtures', import.meta.url)), LOCAL_TZ: 'America/Denver' },
  },
})
