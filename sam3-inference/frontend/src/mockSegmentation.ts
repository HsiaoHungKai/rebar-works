import type { AnnotationPoint, MockMaskRegion } from './types'

export function buildMockMaskRegions(
  points: AnnotationPoint[],
  imageWidth: number,
  imageHeight: number,
): MockMaskRegion[] {
  const baseRadius = Math.max(12, Math.round(Math.min(imageWidth, imageHeight) * 0.04))

  return points.map((point, index) => ({
    id: `${point.id}-${index}`,
    cx: point.x,
    cy: point.y,
    radius: point.label === 1 ? baseRadius : Math.round(baseRadius * 0.8),
    fill: point.label === 1 ? 'rgba(34, 197, 94, 0.22)' : 'rgba(239, 68, 68, 0.18)',
  }))
}
