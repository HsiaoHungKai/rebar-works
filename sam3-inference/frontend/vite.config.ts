import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execFile } from 'node:child_process'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'

const configDirectory = path.dirname(fileURLToPath(import.meta.url))
const imageDirectory = path.resolve(configDirectory, '../images')
const thumbnailDirectory = path.resolve(configDirectory, 'node_modules/.vite/source-image-thumbnails')
const imageExtensions = new Set(['.avif', '.bmp', '.gif', '.heic', '.jpeg', '.jpg', '.png', '.svg', '.webp'])
const mimeTypes: Record<string, string> = {
  '.avif': 'image/avif',
  '.bmp': 'image/bmp',
  '.gif': 'image/gif',
  '.heic': 'image/heic',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
}
const execFileAsync = promisify(execFile)

async function listImageFilenames(): Promise<string[]> {
  const entries = await fs.readdir(imageDirectory, { withFileTypes: true })

  return entries
    .filter((entry) => entry.isFile() && imageExtensions.has(path.extname(entry.name).toLowerCase()))
    .map((entry) => entry.name)
    .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }))
}

async function getThumbnail(filename: string): Promise<{ contentType: string; image: Buffer }> {
  const extension = path.extname(filename).toLowerCase()
  const imagePath = path.join(imageDirectory, filename)

  if (extension !== '.heic') {
    const image = await fs.readFile(imagePath)
    return { contentType: mimeTypes[extension] ?? 'application/octet-stream', image }
  }

  await fs.mkdir(thumbnailDirectory, { recursive: true })
  const thumbnailPath = path.join(thumbnailDirectory, `${filename}.jpg`)

  try {
    const [sourceStat, thumbnailStat] = await Promise.all([fs.stat(imagePath), fs.stat(thumbnailPath)])
    if (thumbnailStat.mtimeMs >= sourceStat.mtimeMs) {
      return { contentType: 'image/jpeg', image: await fs.readFile(thumbnailPath) }
    }
  } catch {
    // Generate the thumbnail below when the cache is missing or stale.
  }

  await execFileAsync('sips', ['-Z', '160', '-s', 'format', 'jpeg', imagePath, '--out', thumbnailPath])
  return { contentType: 'image/jpeg', image: await fs.readFile(thumbnailPath) }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    {
      name: 'source-images-middleware',
      configureServer(server) {
        server.middlewares.use(async (request, response, next) => {
          const requestUrl = request.url ?? ''

          if (requestUrl === '/api/images') {
            try {
              const images = await listImageFilenames()
              response.setHeader('Content-Type', 'application/json')
              response.end(JSON.stringify({ images }))
            } catch {
              response.statusCode = 500
              response.end(JSON.stringify({ error: 'Unable to read images directory.' }))
            }
            return
          }

          if (requestUrl.startsWith('/source-images/')) {
            try {
              const encodedFilename = requestUrl.slice('/source-images/'.length).split('?')[0]
              const filename = path.basename(decodeURIComponent(encodedFilename))
              const extension = path.extname(filename).toLowerCase()

              if (!imageExtensions.has(extension)) {
                response.statusCode = 404
                response.end('Not found')
                return
              }

              const imagePath = path.join(imageDirectory, filename)
              const image = await fs.readFile(imagePath)
              response.setHeader('Content-Type', mimeTypes[extension] ?? 'application/octet-stream')
              response.end(image)
            } catch {
              response.statusCode = 404
              response.end('Not found')
            }
            return
          }

          if (requestUrl.startsWith('/source-image-thumbnails/')) {
            try {
              const encodedFilename = requestUrl.slice('/source-image-thumbnails/'.length).split('?')[0]
              const filename = path.basename(decodeURIComponent(encodedFilename))
              const extension = path.extname(filename).toLowerCase()

              if (!imageExtensions.has(extension)) {
                response.statusCode = 404
                response.end('Not found')
                return
              }

              const thumbnail = await getThumbnail(filename)
              response.setHeader('Content-Type', thumbnail.contentType)
              response.setHeader('Cache-Control', 'public, max-age=300')
              response.end(thumbnail.image)
            } catch {
              response.statusCode = 404
              response.end('Not found')
            }
            return
          }

          next()
        })
      },
    },
  ],
})
