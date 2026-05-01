import { useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, MouseEvent } from 'react'
import './App.css'
import type { AnnotationPoint, PointLabel, UploadedImage } from './types'
import { buildMockMaskRegions } from './mockSegmentation'

const POINT_COLORS: Record<PointLabel, string> = {
  1: '#22c55e',
  0: '#ef4444',
}

interface ImageListResponse {
  images: string[]
}

interface PointPromptResultResponse {
  metadata?: {
    input_points?: unknown
    input_labels?: unknown
    [key: string]: unknown
  }
  overlayUrl?: unknown
  error?: string
}

function toLabelText(label: PointLabel): string {
  return label === 1 ? 'positive' : 'negative'
}

function buildPointsFromMetadata(metadata: PointPromptResultResponse['metadata']): AnnotationPoint[] {
  const inputPoints = metadata?.input_points
  const inputLabels = metadata?.input_labels

  if (!Array.isArray(inputPoints) || !Array.isArray(inputLabels)) {
    return []
  }

  return inputPoints.flatMap((point, index) => {
    if (!Array.isArray(point) || point.length < 2) {
      return []
    }

    const x = Number(point[0])
    const y = Number(point[1])
    const label = Number(inputLabels[index])

    if (!Number.isFinite(x) || !Number.isFinite(y) || (label !== 0 && label !== 1)) {
      return []
    }

    return [{
      id: `saved-${index}-${x}-${y}-${label}`,
      x: Math.round(x),
      y: Math.round(y),
      label: label as PointLabel,
    }]
  })
}

function App() {
  const [activeLabel, setActiveLabel] = useState<PointLabel>(1)
  const [points, setPoints] = useState<AnnotationPoint[]>([])
  const [image, setImage] = useState<UploadedImage | null>(null)
  const [availableImages, setAvailableImages] = useState<string[]>([])
  const [imageLoadError, setImageLoadError] = useState<string | null>(null)
  const [selectedLibraryImage, setSelectedLibraryImage] = useState<string | null>(null)
  const [isImageLoading, setIsImageLoading] = useState(false)
  const [isPointPromptLoading, setIsPointPromptLoading] = useState(false)
  const [hasSavedPointPromptOverlay, setHasSavedPointPromptOverlay] = useState(false)
  const imageRef = useRef<HTMLImageElement | null>(null)
  const imageRequestIdRef = useRef(0)

  const maskRegions = useMemo(() => {
    if (!image) {
      return []
    }
    return buildMockMaskRegions(points, image.width, image.height)
  }, [image, points])

  const canLoadPointPromptResult = image?.source === 'library' && !isImageLoading && !isPointPromptLoading

  useEffect(() => {
    let isMounted = true

    async function loadAvailableImages(): Promise<void> {
      try {
        const response = await fetch('/api/images')
        if (!response.ok) {
          throw new Error('Unable to load image list.')
        }
        const payload = (await response.json()) as ImageListResponse
        if (isMounted) {
          setAvailableImages(Array.isArray(payload.images) ? payload.images : [])
        }
      } catch {
        if (isMounted) {
          setImageLoadError('Unable to load images from ./images.')
        }
      }
    }

    void loadAvailableImages()

    return () => {
      isMounted = false
    }
  }, [])

  function replaceImage(nextImage: UploadedImage): void {
    setImage((previousImage) => {
      if (previousImage?.source === 'upload') {
        URL.revokeObjectURL(previousImage.url)
      }
      return nextImage
    })
    setPoints([])
    setImageLoadError(null)
    setHasSavedPointPromptOverlay(false)
  }

  function loadImage(name: string, url: string, source: UploadedImage['source']): void {
    const requestId = imageRequestIdRef.current + 1
    imageRequestIdRef.current = requestId
    setIsImageLoading(true)
    setImageLoadError(null)
    setSelectedLibraryImage(source === 'library' ? name : null)

    const previewImage = new Image()
    previewImage.onload = () => {
      if (imageRequestIdRef.current !== requestId) {
        if (source === 'upload') {
          URL.revokeObjectURL(url)
        }
        return
      }
      replaceImage({
        name,
        url,
        width: previewImage.naturalWidth,
        height: previewImage.naturalHeight,
        source,
      })
      setIsImageLoading(false)
    }
    previewImage.onerror = () => {
      if (imageRequestIdRef.current !== requestId) {
        if (source === 'upload') {
          URL.revokeObjectURL(url)
        }
        return
      }
      if (source === 'upload') {
        URL.revokeObjectURL(url)
      }
      setIsImageLoading(false)
      setImageLoadError(`Unable to load ${name}.`)
    }
    previewImage.src = url
  }

  function handleImageUpload(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }

    const nextUrl = URL.createObjectURL(file)
    loadImage(file.name, nextUrl, 'upload')
    event.target.value = ''
  }

  function handleLibraryImageSelect(filename: string): void {
    loadImage(filename, `/source-images/${encodeURIComponent(filename)}`, 'library')
  }

  function handleImageStageClick(event: MouseEvent<HTMLDivElement>): void {
    if (!image || !imageRef.current) {
      return
    }

    const rect = imageRef.current.getBoundingClientRect()
    const xRatio = image.width / rect.width
    const yRatio = image.height / rect.height
    const x = Math.max(0, Math.min(image.width, Math.round((event.clientX - rect.left) * xRatio)))
    const y = Math.max(0, Math.min(image.height, Math.round((event.clientY - rect.top) * yRatio)))

    const newPoint: AnnotationPoint = {
      id: `${Date.now()}-${Math.random()}`,
      x,
      y,
      label: activeLabel,
    }
    setPoints((previousPoints) => [...previousPoints, newPoint])
  }

  function clearPoints(): void {
    setPoints([])
  }

  function undoLastPoint(): void {
    setPoints((previousPoints) => previousPoints.slice(0, -1))
  }

  async function handleStartPointInference(): Promise<void> {
    if (!image || image.source !== 'library') {
      return
    }

    setIsPointPromptLoading(true)
    setImageLoadError(null)

    try {
      const response = await fetch(`/api/point-prompt-result?image=${encodeURIComponent(image.name)}`)
      const payload = (await response.json()) as PointPromptResultResponse

      if (!response.ok || typeof payload.overlayUrl !== 'string') {
        throw new Error(payload.error ?? `Unable to load saved point-prompt result for ${image.name}.`)
      }

      setImage((previousImage) => {
        if (!previousImage || previousImage.name !== image.name || previousImage.source !== 'library') {
          return previousImage
        }

        return {
          ...previousImage,
          url: payload.overlayUrl as string,
        }
      })
      setPoints(buildPointsFromMetadata(payload.metadata))
      setHasSavedPointPromptOverlay(true)
    } catch (error) {
      setImageLoadError(error instanceof Error ? error.message : `Unable to load saved point-prompt result for ${image.name}.`)
    } finally {
      setIsPointPromptLoading(false)
    }
  }

  return (
    <main className="app">
      <header className="panel">
        <h1>Point Prompt Annotation</h1>
        <p>Select an image from ./images or upload one, then click to add positive (green) or negative (red) points.</p>
        <div className="controls">
          <label className="upload">
            <span>Image</span>
            <input
              aria-label="Upload image"
              data-testid="image-upload-input"
              type="file"
              accept="image/*"
              onChange={handleImageUpload}
            />
          </label>

          <div className="mode-group" role="group" aria-label="Point label mode">
            <button
              data-testid="mode-positive"
              type="button"
              className={activeLabel === 1 ? 'active positive' : 'positive'}
              onClick={() => setActiveLabel(1)}
            >
              Positive
            </button>
            <button
              data-testid="mode-negative"
              type="button"
              className={activeLabel === 0 ? 'active negative' : 'negative'}
              onClick={() => setActiveLabel(0)}
            >
              Negative
            </button>
          </div>

          <button data-testid="undo-point" type="button" onClick={undoLastPoint} disabled={points.length === 0}>
            Undo
          </button>
          <button data-testid="clear-points" type="button" onClick={clearPoints} disabled={points.length === 0}>
            Clear
          </button>
          <button
            data-testid="start-point-inference"
            type="button"
            onClick={handleStartPointInference}
            disabled={!canLoadPointPromptResult}
          >
            Start point inference
          </button>
        </div>
      </header>

      <section className="workspace">
        <div className="canvas-panel">
          <div className="canvas-shell" data-testid="annotation-canvas">
            {image ? (
              <div className="image-stage" data-testid="annotation-stage" onClick={handleImageStageClick}>
                <img
                  ref={imageRef}
                  className="annotated-image"
                  src={image.url}
                  alt={image.name}
                  data-testid="annotation-image"
                />
                <svg
                  className="mask-overlay"
                  viewBox={`0 0 ${image.width} ${image.height}`}
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  {hasSavedPointPromptOverlay ? null : maskRegions.map((region) => (
                    <circle
                      key={region.id}
                      cx={region.cx}
                      cy={region.cy}
                      r={region.radius}
                      fill={region.fill}
                    />
                  ))}
                </svg>
                {points.map((point, index) => (
                  <span
                    key={point.id}
                    data-testid={`point-${index}`}
                    className="point-marker"
                    style={{
                      left: `${(point.x / image.width) * 100}%`,
                      top: `${(point.y / image.height) * 100}%`,
                      backgroundColor: POINT_COLORS[point.label],
                    }}
                    aria-label={`${toLabelText(point.label)} point ${index + 1}`}
                  />
                ))}
              </div>
            ) : (
              <div className="empty-state">Select or upload an image to start annotating.</div>
            )}
            {isImageLoading || isPointPromptLoading ? (
              <div className="loading-overlay" data-testid="image-loading-indicator">
                {isPointPromptLoading ? 'Loading saved point-prompt result...' : `Loading ${selectedLibraryImage ?? 'image'}...`}
              </div>
            ) : null}
          </div>
        </div>

        <aside className="panel side-panel">
          <section className="image-browser" aria-label="Images from ./images">
            <h2>Images ({availableImages.length})</h2>
            {imageLoadError ? <p className="error-message">{imageLoadError}</p> : null}
            {availableImages.length === 0 ? (
              <p className="muted">No images found in ./images.</p>
            ) : (
              <div className="image-browser-list" data-testid="image-browser-list">
                {availableImages.map((filename) => {
                  const thumbnailUrl = `/source-image-thumbnails/${encodeURIComponent(filename)}`
                  const isActive = selectedLibraryImage === filename || (image?.source === 'library' && image.name === filename)

                  return (
                    <button
                      key={filename}
                      type="button"
                      className={isActive ? 'image-option active' : 'image-option'}
                      data-testid={`image-option-${filename}`}
                      onClick={() => handleLibraryImageSelect(filename)}
                      aria-pressed={isActive}
                    >
                      <img src={thumbnailUrl} alt="" loading="lazy" />
                      <span>{filename}</span>
                    </button>
                  )
                })}
              </div>
            )}
          </section>

          <section className="point-list-panel">
            <h2>Points ({points.length})</h2>
            {points.length === 0 ? (
              <p className="muted">No points added yet.</p>
            ) : (
              <ol data-testid="point-list">
                {points.map((point, index) => (
                  <li key={point.id}>
                    <span className="dot" style={{ backgroundColor: POINT_COLORS[point.label] }} />
                    {index + 1}. {toLabelText(point.label)} ({point.x}, {point.y})
                  </li>
                ))}
              </ol>
            )}
            {hasSavedPointPromptOverlay ? (
              <p className="muted">Saved point-prompt mask loaded.</p>
            ) : (
              <p className="muted">
                Mock mask visualization is shown as translucent circles and can be replaced with backend output later.
              </p>
            )}
          </section>
        </aside>
      </section>
    </main>
  )
}

export default App
