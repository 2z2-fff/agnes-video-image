import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // Editors save atomically: they create a temporary sibling directory and
    // rename it into place. Watching those transient paths makes Vite die with
    // "EBUSY: resource busy or locked", so they must be ignored explicitly.
    watch: {
      ignored: ['**/.*.tmpdir/**', '**/*.tmp', '**/.git/**'],
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/uploads': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
