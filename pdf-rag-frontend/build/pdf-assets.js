import { cpSync, mkdirSync, readFile, readdirSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'

// Serve/copy only the installed PDF.js support assets; no CDN or extra watcher.
export function pdfAssetsPlugin() {
  const root = dirname(createRequire(import.meta.url).resolve('pdfjs-dist/package.json'))
  const folders = ['cmaps', 'standard_fonts', 'wasm', 'iccs']
  const files = new Map()
  for (const folder of folders) for (const name of readdirSync(join(root, folder))) {
    files.set(`${folder}/${name}`, join(root, folder, name))
  }
  let config
  return {
    name: 'local-pdfjs-assets',
    configResolved(value) { config = value },
    configureServer(server) {
      const prefix = `${new URL(config.base, 'http://vite.local').pathname.replace(/\/$/, '')}/pdfjs/`
      server.middlewares.use((request, response, next) => {
        const path = new URL(request.url, 'http://vite.local').pathname
        if (!path.startsWith(prefix)) return next()
        const target = files.get(path.slice(prefix.length))
        if (!target || !['GET', 'HEAD'].includes(request.method)) return next()
        readFile(target, (error, data) => {
          if (error) { response.statusCode = 404; response.end(); return }
          response.setHeader('Content-Type', target.endsWith('.wasm') ? 'application/wasm' : 'application/octet-stream')
          response.end(request.method === 'HEAD' ? undefined : data)
        })
      })
    },
    closeBundle() {
      if (config.command !== 'build') return
      const destination = resolve(config.root, config.build.outDir, 'pdfjs')
      mkdirSync(destination, { recursive: true })
      for (const folder of folders) cpSync(join(root, folder), join(destination, folder), { recursive: true })
    },
  }
}
