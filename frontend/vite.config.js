import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The Python API runs on :8000. In development, /api/* is proxied there so the
// browser only ever talks to localhost:5173 and no keys live in the frontend.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
});
