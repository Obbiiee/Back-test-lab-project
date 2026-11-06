import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('./preview/', import.meta.url))
const outDir = fileURLToPath(new URL('./dist-terminal-preview/', import.meta.url))

export default defineConfig({
  root,
  base: '/preview/terminal/',
  plugins: [react()],
  build: {
    outDir,
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: { input: fileURLToPath(new URL('./preview/index.html', import.meta.url)) },
  },
})
