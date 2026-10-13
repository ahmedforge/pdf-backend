import process from 'node:process'
import { pdfAssetsPlugin } from './build/pdf-assets.js'
import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  if (mode === 'production') {
    if (!env.VITE_API_BASE_URL) throw new Error('Set VITE_API_BASE_URL to your HTTPS backend URL before building.')
    const api = new URL(env.VITE_API_BASE_URL)
    if (api.protocol !== 'https:' || api.pathname !== '/' || api.search || api.hash) {
      throw new Error('Production VITE_API_BASE_URL must be an HTTPS origin, without a path, query, or fragment.')
    }
  }
  return {
    plugins: [react(), tailwindcss(), pdfAssetsPlugin()],
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  }
})
