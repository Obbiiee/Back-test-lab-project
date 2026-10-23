import react from '@vitejs/plugin-react';
import {defineConfig} from 'vite';

export default defineConfig({
  plugins: [react()],
  build: {outDir: 'dist/workspace', rollupOptions: {input: ['staging/workspace.html','staging/home.html']}},
});
