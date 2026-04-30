import { useMemo, useRef, useState } from 'react'
import type { ChangeEvent, MouseEvent } from 'react'
import './App.css'
import type { AnnotationPoint, PointLabel, UploadedImage } from './types'
import { buildMockMaskRegions } from './mockSegmentation'

const POINT_COLORS: Record<PointLabel, string> = {
  1: '#22c55e',
  0: '#ef4444',
}

function toLabelText(label: PointLabel): string {
  return label === 1 ? 'positive' : 'negative'
}

function App() {
  const [activeLabel, setActiveLabel] = useState<PointLabel>(1)
  const [points, setPoints] = useState<AnnotationPoint[]>([])
  const [image, setImage] = useState<UploadedImage | null>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)

  const maskRegions = useMemo(() => {
    if (!image) {
      return []
    }
    return buildMockMaskRegions(points, image.width, image.height)
  }, [image, points])

  function handleImageUpload(event: ChangeEvent<HTMLInputElement>): void {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }

    const nextUrl = URL.createObjectURL(file)
    const previewImage = new Image()
    previewImage.onload = () => {
      setImage((previousImage) => {
        if (previousImage) {
          URL.revokeObjectURL(previousImage.url)
        }
        return {
          name: file.name,
          url: nextUrl,
          width: previewImage.naturalWidth,
          height: previewImage.naturalHeight,
        }
      })
      setPoints([])
    }
    previewImage.src = nextUrl
    event.target.value = ''
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

  return (
    <main className="app">
      <header className="panel">
        <h1>Point Prompt Annotation</h1>
        <p>Upload an image, then click to add positive (green) or negative (red) point prompts.</p>
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
                  {maskRegions.map((region) => (
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
              <div className="empty-state">Upload an image to start annotating.</div>
            )}
          </div>
        </div>

        <aside className="panel point-list-panel">
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
          <p className="muted">
            Mock mask visualization is shown as translucent circles and can be replaced with backend output later.
          </p>
        </aside>
      </section>
    </main>
  )
}

export default App
