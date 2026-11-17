// @ts-check
import { defineConfig } from 'astro/config'
import node from '@astrojs/node'

// Each build gets its own id, so a page can tell that the server now runs newer code
// (src/pages/api/build.ts, src/scripts/update-client.ts).
const BUILD_ID = String(Date.now())

export default defineConfig({
  // automations/scripts/run-web.sh builds into a second folder while the old build is
  // still being served, then swaps the two, so a failed build never leaves nothing to serve.
  outDir: process.env.PFC_WEB_OUT_DIR || './dist',
  // Server mode: pages render per request, so they always show the repo as it is now.
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  server: { host: '127.0.0.1', port: 4323 },
  vite: {
    server: { fs: { allow: ['..'] } },
    define: { __PFC_BUILD_ID__: JSON.stringify(BUILD_ID) },
  },
})
