import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    // Bound to localhost only by default, which the backend's SameSite=Lax
    // auth cookie treats as a different site than 127.0.0.1 — the browser
    // then won't attach it on API calls. Listening on both keeps whichever
    // host you open the app on cookie-compatible with the backend.
    host: true,
  },
})
