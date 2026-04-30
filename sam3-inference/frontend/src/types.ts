export type PointLabel = 1 | 0

export interface AnnotationPoint {
  id: string
  x: number
  y: number
  label: PointLabel
}

export interface UploadedImage {
  name: string
  url: string
  width: number
  height: number
}

export interface MockMaskRegion {
  id: string
  cx: number
  cy: number
  radius: number
  fill: string
}
