import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The backend allows http://localhost:5173 in its CORS settings (ALLOWED_ORIGINS), so keep
// this port fixed: if it were taken, Vite must fail loudly instead of picking another one.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    css: false,
  },
})
