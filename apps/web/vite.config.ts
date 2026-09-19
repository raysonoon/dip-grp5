import { defineConfig } from 'vite'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'

// Port the FastAPI backend (apps/api) listens on.
const API_PORT = 8000

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      // Alias @ to the src directory
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/chat': {
        target: `http://localhost:${API_PORT}`,
        changeOrigin: true,
      },
      '/reviews': {
        target: `http://localhost:${API_PORT}`,
        changeOrigin: true,
      },
      '/vendors': {
        target: `http://localhost:${API_PORT}`,
        changeOrigin: true,
        bypass(req) {
          const pathname = req.url?.split('?')[0] ?? ''
          const isVendorPage = /^\/vendors\/\d+\/?$/.test(pathname)
          const acceptsHtml = req.headers.accept?.includes('text/html')
          if (isVendorPage && acceptsHtml) return '/index.html'
        },
      },
      '/media': {
        target: `http://localhost:${API_PORT}`,
        changeOrigin: true,
      },
    },
  },
})
