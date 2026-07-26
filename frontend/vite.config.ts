import path from 'node:path'
import { fileURLToPath } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const root = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(root, 'src'),
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:9983',
      '/health': 'http://127.0.0.1:9983',
      '/ws': { target: 'ws://127.0.0.1:9983', ws: true },
    },
  },
  preview: {
    port: 4174,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:9983',
      '/health': 'http://127.0.0.1:9983',
      '/ws': { target: 'ws://127.0.0.1:9983', ws: true },
    },
  },
})
