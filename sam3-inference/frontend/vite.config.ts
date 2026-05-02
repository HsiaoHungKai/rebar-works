import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execFile } from 'node:child_process'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'

const configDirectory = path.dirname(fileURLToPath(import.meta.url))
const imageDirectory = path.resolve(configDirectory, '../images')
const resultsDirectory = path.resolve(configDirectory, '../results')
const sourceImageCacheDirectory = path.resolve(configDirectory, 'node_modules/.vite/source-images')
const thumbnailDirectory = path.resolve(configDirectory, 'node_modules/.vite/source-image-thumbnails')
const pointPromptOverlayDirectory = path.resolve(configDirectory, 'node_modules/.vite/point-prompt-overlays')
const textBatchOverlayDirectory = path.resolve(configDirectory, 'node_modules/.vite/text-batch-overlays')
const overlayRendererPath = path.resolve(configDirectory, 'scripts/render_point_prompt_overlay.py')
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

interface PointPromptMetadata {
  image_filename?: unknown
  npz_filename?: unknown
  input_points?: unknown
  input_labels?: unknown
  [key: string]: unknown
}

type SavedResultMetadata = PointPromptMetadata

interface SavedResultPayload {
  metadata?: SavedResultMetadata
}

function isInsideDirectory(parentDirectory: string, childPath: string): boolean {
  const relativePath = path.relative(parentDirectory, childPath)
  return relativePath !== '' && !relativePath.startsWith('..') && !path.isAbsolute(relativePath)
}

function sendJson(response: { statusCode: number; setHeader(name: string, value: string): void; end(data: string): void }, statusCode: number, payload: unknown): void {
  response.statusCode = statusCode
  response.setHeader('Content-Type', 'application/json')
  response.end(JSON.stringify(payload))
}

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

  await execFileAsync('ffmpeg', [
    '-hide_banner',
    '-loglevel',
    'error',
    '-y',
    '-i',
    imagePath,
    '-frames:v',
    '1',
    '-vf',
    'scale=160:-1',
    thumbnailPath,
  ])
  return { contentType: 'image/jpeg', image: await fs.readFile(thumbnailPath) }
}

async function getSourceImage(filename: string): Promise<{ contentType: string; image: Buffer }> {
  const extension = path.extname(filename).toLowerCase()
  const imagePath = path.join(imageDirectory, filename)

  if (extension !== '.heic') {
    const image = await fs.readFile(imagePath)
    return { contentType: mimeTypes[extension] ?? 'application/octet-stream', image }
  }

  await fs.mkdir(sourceImageCacheDirectory, { recursive: true })
  const convertedPath = path.join(sourceImageCacheDirectory, `${filename}.jpg`)

  try {
    const [sourceStat, convertedStat] = await Promise.all([fs.stat(imagePath), fs.stat(convertedPath)])
    if (convertedStat.mtimeMs >= sourceStat.mtimeMs) {
      return { contentType: 'image/jpeg', image: await fs.readFile(convertedPath) }
    }
  } catch {
    // Generate the normalized source image below when the cache is missing or stale.
  }

  await execFileAsync('ffmpeg', [
    '-hide_banner',
    '-loglevel',
    'error',
    '-y',
    '-i',
    imagePath,
    '-frames:v',
    '1',
    convertedPath,
  ])
  return { contentType: 'image/jpeg', image: await fs.readFile(convertedPath) }
}

async function getSavedOverlayResult(
  filename: string,
  options: {
    resultSuffix: 'point_prompt' | 'text_batch'
    label: string
    overlayDirectory: string
    overlayRoute: string
    color: 'blue' | 'green'
  },
): Promise<{ metadata: SavedResultMetadata; overlayUrl: string }> {
  const extension = path.extname(filename).toLowerCase()

  if (!imageExtensions.has(extension)) {
    throw Object.assign(new Error('Unsupported image type.'), { statusCode: 400 })
  }

  const safeFilename = path.basename(filename)
  if (safeFilename !== filename) {
    throw Object.assign(new Error('Invalid image filename.'), { statusCode: 400 })
  }

  const imagePath = path.resolve(imageDirectory, safeFilename)
  if (!isInsideDirectory(imageDirectory, imagePath)) {
    throw Object.assign(new Error('Invalid image path.'), { statusCode: 400 })
  }

  const imageStem = path.parse(safeFilename).name
  const resultFilename = `${imageStem}_${options.resultSuffix}.json`
  const metadataPath = path.resolve(resultsDirectory, resultFilename)
  if (!isInsideDirectory(resultsDirectory, metadataPath)) {
    throw Object.assign(new Error('Invalid result path.'), { statusCode: 400 })
  }

  let payload: SavedResultPayload
  try {
    payload = JSON.parse(await fs.readFile(metadataPath, 'utf8')) as SavedResultPayload
  } catch {
    throw Object.assign(new Error(`Missing saved ${options.label} result: ${resultFilename}.`), { statusCode: 404 })
  }

  const metadata = payload.metadata
  if (!metadata || typeof metadata !== 'object') {
    throw Object.assign(new Error(`Saved ${options.label} result is missing metadata.`), { statusCode: 422 })
  }

  if (metadata.image_filename !== safeFilename) {
    throw Object.assign(new Error(`Saved ${options.label} result does not match the selected image.`), { statusCode: 422 })
  }

  if (typeof metadata.npz_filename !== 'string' || path.basename(metadata.npz_filename) !== metadata.npz_filename) {
    throw Object.assign(new Error(`Saved ${options.label} result has an invalid npz filename.`), { statusCode: 422 })
  }

  const npzPath = path.resolve(resultsDirectory, metadata.npz_filename)
  if (!isInsideDirectory(resultsDirectory, npzPath)) {
    throw Object.assign(new Error(`Saved ${options.label} result has an invalid npz path.`), { statusCode: 422 })
  }

  const cacheName = `${imageStem}_${options.resultSuffix}_overlay.png`
  const overlayPath = path.resolve(options.overlayDirectory, cacheName)
  const [imageStat, metadataStat, npzStat] = await Promise.all([fs.stat(imagePath), fs.stat(metadataPath), fs.stat(npzPath)])
  const newestInputMtime = Math.max(imageStat.mtimeMs, metadataStat.mtimeMs, npzStat.mtimeMs)

  let shouldRender = true
  try {
    const overlayStat = await fs.stat(overlayPath)
    shouldRender = overlayStat.mtimeMs < newestInputMtime
  } catch {
    // Render when the cache is missing.
  }

  if (shouldRender) {
    await fs.mkdir(options.overlayDirectory, { recursive: true })
    await execFileAsync('python3', [
      overlayRendererPath,
      '--image',
      imagePath,
      '--npz',
      npzPath,
      '--output',
      overlayPath,
      '--color',
      options.color,
    ])
  }

  return {
    metadata,
    overlayUrl: `${options.overlayRoute}/${encodeURIComponent(cacheName)}?v=${Math.round(newestInputMtime)}`,
  }
}

async function getPointPromptResult(filename: string): Promise<{ metadata: SavedResultMetadata; overlayUrl: string }> {
  return getSavedOverlayResult(filename, {
    resultSuffix: 'point_prompt',
    label: 'point-prompt',
    overlayDirectory: pointPromptOverlayDirectory,
    overlayRoute: '/point-prompt-overlays',
    color: 'blue',
  })
}

async function getTextBatchResult(filename: string): Promise<{ metadata: SavedResultMetadata; overlayUrl: string }> {
  return getSavedOverlayResult(filename, {
    resultSuffix: 'text_batch',
    label: 'text-batch',
    overlayDirectory: textBatchOverlayDirectory,
    overlayRoute: '/text-batch-overlays',
    color: 'green',
  })
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

              const sourceImage = await getSourceImage(filename)
              response.setHeader('Content-Type', sourceImage.contentType)
              response.setHeader('Cache-Control', 'public, max-age=300')
              response.end(sourceImage.image)
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

          if (requestUrl.startsWith('/api/point-prompt-result')) {
            const url = new URL(requestUrl, 'http://localhost')
            const image = url.searchParams.get('image')

            if (!image) {
              sendJson(response, 400, { error: 'Missing image query parameter.' })
              return
            }

            try {
              const result = await getPointPromptResult(image)
              sendJson(response, 200, result)
            } catch (error) {
              const statusCode = typeof error === 'object' && error !== null && 'statusCode' in error
                ? Number((error as { statusCode: unknown }).statusCode)
                : 500
              const message = error instanceof Error ? error.message : 'Unable to load saved point-prompt result.'
              sendJson(response, Number.isFinite(statusCode) ? statusCode : 500, { error: message })
            }
            return
          }

          if (requestUrl.startsWith('/api/text-batch-result')) {
            const url = new URL(requestUrl, 'http://localhost')
            const image = url.searchParams.get('image')

            if (!image) {
              sendJson(response, 400, { error: 'Missing image query parameter.' })
              return
            }

            try {
              const result = await getTextBatchResult(image)
              sendJson(response, 200, result)
            } catch (error) {
              const statusCode = typeof error === 'object' && error !== null && 'statusCode' in error
                ? Number((error as { statusCode: unknown }).statusCode)
                : 500
              const message = error instanceof Error ? error.message : 'Unable to load saved text-batch result.'
              sendJson(response, Number.isFinite(statusCode) ? statusCode : 500, { error: message })
            }
            return
          }

          if (requestUrl.startsWith('/point-prompt-overlays/')) {
            try {
              const encodedFilename = requestUrl.slice('/point-prompt-overlays/'.length).split('?')[0]
              const filename = path.basename(decodeURIComponent(encodedFilename))
              const overlayPath = path.resolve(pointPromptOverlayDirectory, filename)

              if (path.extname(filename).toLowerCase() !== '.png' || !isInsideDirectory(pointPromptOverlayDirectory, overlayPath)) {
                response.statusCode = 404
                response.end('Not found')
                return
              }

              response.setHeader('Content-Type', 'image/png')
              response.setHeader('Cache-Control', 'public, max-age=300')
              response.end(await fs.readFile(overlayPath))
            } catch {
              response.statusCode = 404
              response.end('Not found')
            }
            return
          }

          if (requestUrl.startsWith('/text-batch-overlays/')) {
            try {
              const encodedFilename = requestUrl.slice('/text-batch-overlays/'.length).split('?')[0]
              const filename = path.basename(decodeURIComponent(encodedFilename))
              const overlayPath = path.resolve(textBatchOverlayDirectory, filename)

              if (path.extname(filename).toLowerCase() !== '.png' || !isInsideDirectory(textBatchOverlayDirectory, overlayPath)) {
                response.statusCode = 404
                response.end('Not found')
                return
              }

              response.setHeader('Content-Type', 'image/png')
              response.setHeader('Cache-Control', 'public, max-age=300')
              response.end(await fs.readFile(overlayPath))
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
