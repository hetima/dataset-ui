import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  base: '/daw/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:7869',
      '/daw-media': 'http://127.0.0.1:7869',
    },
  },
})
