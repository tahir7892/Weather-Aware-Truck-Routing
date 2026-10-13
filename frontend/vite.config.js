import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // The backend's CORS setting allows http://localhost:5173, so keep this port.
    port: 5173,
    strictPort: true,
  },
  build: {
    // MapLibre GL is ~1 MB on its own; it is loaded lazily, after the page is usable.
    chunkSizeWarningLimit: 1200,
  },
})
