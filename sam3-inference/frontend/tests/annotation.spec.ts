import { expect, test } from '@playwright/test'

const SAMPLE_SVG = Buffer.from(
  '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="240"><rect width="100%" height="100%" fill="#f1f5f9"/><rect x="80" y="40" width="240" height="160" fill="#cbd5e1"/></svg>',
)

test('annotates positive and negative points', async ({ page }) => {
  await page.goto('/')

  await page.getByTestId('image-upload-input').setInputFiles({
    name: 'sample.svg',
    mimeType: 'image/svg+xml',
    buffer: SAMPLE_SVG,
  })

  const stage = page.getByTestId('annotation-stage')
  await expect(page.getByTestId('annotation-image')).toBeVisible()

  await stage.click({ position: { x: 40, y: 40 } })
  await page.getByTestId('mode-negative').click()
  await stage.click({ position: { x: 80, y: 80 } })

  await expect(page.getByTestId('point-0')).toBeVisible()
  await expect(page.getByTestId('point-1')).toBeVisible()
  await expect(page.getByTestId('point-list')).toContainText('positive')
  await expect(page.getByTestId('point-list')).toContainText('negative')
})

test('supports undo and clear', async ({ page }) => {
  await page.goto('/')
  await page.getByTestId('image-upload-input').setInputFiles({
    name: 'sample.svg',
    mimeType: 'image/svg+xml',
    buffer: SAMPLE_SVG,
  })

  const stage = page.getByTestId('annotation-stage')
  await stage.click({ position: { x: 30, y: 30 } })
  await stage.click({ position: { x: 50, y: 50 } })

  await page.getByTestId('undo-point').click()
  await expect(page.getByTestId('point-1')).toHaveCount(0)

  await page.getByTestId('clear-points').click()
  await expect(page.getByTestId('point-0')).toHaveCount(0)
  await expect(page.getByText('No points added yet.')).toBeVisible()
})

test('maps edge clicks without horizontal drift and ignores shell padding clicks', async ({ page }) => {
  await page.goto('/')
  await page.getByTestId('image-upload-input').setInputFiles({
    name: 'sample.svg',
    mimeType: 'image/svg+xml',
    buffer: SAMPLE_SVG,
  })

  const stage = page.getByTestId('annotation-stage')
  const stageBox = await stage.boundingBox()
  if (!stageBox) {
    throw new Error('annotation-stage bounding box not found')
  }

  await stage.click({ position: { x: 5, y: stageBox.height / 2 } })
  await stage.click({ position: { x: stageBox.width - 5, y: stageBox.height / 2 } })

  const leftStyle = await page.getByTestId('point-0').getAttribute('style')
  const rightStyle = await page.getByTestId('point-1').getAttribute('style')
  const leftPercent = Number((leftStyle ?? '').match(/left:\s*([\d.]+)%/)?.[1] ?? NaN)
  const rightPercent = Number((rightStyle ?? '').match(/left:\s*([\d.]+)%/)?.[1] ?? NaN)

  expect(leftPercent).toBeLessThan(10)
  expect(rightPercent).toBeGreaterThan(90)

  const shell = page.getByTestId('annotation-canvas')
  const shellBox = await shell.boundingBox()
  if (!shellBox) {
    throw new Error('annotation-canvas bounding box not found')
  }

  await shell.click({ position: { x: 10, y: 10 } })
  await expect(page.getByTestId('point-2')).toHaveCount(0)
})
