// @ts-check
import { defineConfig } from 'astro/config'
import node from '@astrojs/node'

export default defineConfig({
  // Server mode: pages render per request, so they always show the repo as it is now.
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  server: { host: '127.0.0.1', port: 4323 },
  vite: { server: { fs: { allow: ['..'] } } },
})
