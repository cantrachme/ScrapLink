import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // HTTP proxying also streams SSE; do not buffer or rewrite responses.
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      // Prefix matching covers both /health and /health/db.
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/tests/setup.ts'],
    clearMocks: true,
    restoreMocks: true,
    unstubGlobals: true,
  },
})
