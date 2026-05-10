import { expect, test } from '@playwright/test'

const SAMPLE_SVG = Buffer.from(
  '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="240"><rect width="100%" height="100%" fill="#f1f5f9"/><rect x="80" y="40" width="240" height="160" fill="#cbd5e1"/></svg>',
)

const LIBRARY_SVG = Buffer.from(
  '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="200"><rect width="100%" height="100%" fill="#f8fafc"/><circle cx="160" cy="100" r="60" fill="#94a3b8"/></svg>',
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

test('loads images from the right-side browser and clears points when switching', async ({ page }) => {
  await page.route('**/api/images', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ images: ['library-a.svg', 'library-b.svg'] }),
    })
  })
  await page.route('**/source-images/*', async (route) => {
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: LIBRARY_SVG,
    })
  })
  await page.route('**/source-image-thumbnails/*', async (route) => {
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: LIBRARY_SVG,
    })
  })

  await page.goto('/')

  await expect(page.getByTestId('image-browser-list')).toContainText('library-a.svg')
  await page.getByTestId('image-option-library-a.svg').click()

  const stage = page.getByTestId('annotation-stage')
  await expect(page.getByTestId('annotation-image')).toHaveAttribute('alt', 'library-a.svg')

  await stage.click({ position: { x: 40, y: 40 } })
  await expect(page.getByTestId('point-0')).toBeVisible()

  await page.getByTestId('image-option-library-b.svg').click()
  await expect(page.getByTestId('annotation-image')).toHaveAttribute('alt', 'library-b.svg')
  await expect(page.getByTestId('point-0')).toHaveCount(0)
  await expect(page.getByText('No points added yet.')).toBeVisible()
})

test('disables saved point-prompt loading before selecting a repo image', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByTestId('start-point-inference')).toBeDisabled()
})

test('requires a prompt before starting text inference mode', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByTestId('start-text-inference')).toBeDisabled()
  await page.getByTestId('text-prompt-input').fill('rebar')
  await expect(page.getByTestId('start-text-inference')).toBeEnabled()
})

test('serves HEIC source images as normalized JPEGs', async ({ page }) => {
  const response = await page.request.get('/source-images/IMG_7566.HEIC')

  expect(response.ok()).toBeTruthy()
  expect(response.headers()['content-type']).toContain('image/jpeg')
})

test('loads a saved point-prompt overlay and metadata points', async ({ page }) => {
  await page.route('**/api/images', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ images: ['library-a.svg'] }),
    })
  })
  await page.route('**/source-images/*', async (route) => {
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: LIBRARY_SVG,
    })
  })
  await page.route('**/source-image-thumbnails/*', async (route) => {
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: LIBRARY_SVG,
    })
  })
  await page.route('**/api/point-prompt-result?image=library-a.svg', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        metadata: {
          input_points: [[25, 35], [90, 100]],
          input_labels: [1, 0],
        },
        overlayUrl: '/point-prompt-overlays/library-a_point_prompt_overlay.png?v=1',
      }),
    })
  })
  await page.route('**/point-prompt-overlays/*', async (route) => {
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: LIBRARY_SVG,
    })
  })

  await page.goto('/')
  await page.getByTestId('image-option-library-a.svg').click()
  await expect(page.getByTestId('start-point-inference')).toBeEnabled()

  await page.getByTestId('start-point-inference').click()

  await expect(page.getByTestId('annotation-image')).toHaveAttribute(
    'src',
    '/point-prompt-overlays/library-a_point_prompt_overlay.png?v=1',
  )
  await expect(page.getByTestId('point-list')).toContainText('positive (25, 35)')
  await expect(page.getByTestId('point-list')).toContainText('negative (90, 100)')
  await expect(page.getByText('Saved point-prompt mask loaded.')).toBeVisible()
})

test('shows a saved point-prompt missing error and preserves the selected image', async ({ page }) => {
  await page.route('**/api/images', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ images: ['IMG_7566.HEIC'] }),
    })
  })
  await page.route('**/source-images/*', async (route) => {
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: LIBRARY_SVG,
    })
  })
  await page.route('**/source-image-thumbnails/*', async (route) => {
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: LIBRARY_SVG,
    })
  })
  await page.route('**/api/point-prompt-result?image=IMG_7566.HEIC', async (route) => {
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ error: 'Missing saved point-prompt result: IMG_7566_point_prompt.json.' }),
    })
  })

  await page.goto('/')
  await page.getByTestId('image-option-IMG_7566.HEIC').click()
  await expect(page.getByTestId('annotation-image')).toHaveAttribute('src', '/source-images/IMG_7566.HEIC')

  await page.getByTestId('start-point-inference').click()

  await expect(page.getByText('Missing saved point-prompt result: IMG_7566_point_prompt.json.')).toBeVisible()
  await expect(page.getByTestId('annotation-image')).toHaveAttribute('src', '/source-images/IMG_7566.HEIC')
})

test('loads saved text-batch overlays for checked images', async ({ page }) => {
  const requestedTextBatchImages: string[] = []
  const requestedPointPromptImages: string[] = []

  await page.route('**/api/images', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ images: ['library-a.svg', 'library-b.svg'] }),
    })
  })
  await page.route('**/source-images/*', async (route) => {
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: LIBRARY_SVG,
    })
  })
  await page.route('**/source-image-thumbnails/*', async (route) => {
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: LIBRARY_SVG,
    })
  })
  await page.route('**/api/text-batch-result?image=*', async (route) => {
    const requestedImage = new URL(route.request().url()).searchParams.get('image')
    if (requestedImage) {
      requestedTextBatchImages.push(requestedImage)
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        metadata: {},
        overlayUrl: `/text-batch-overlays/${requestedImage?.replace('.svg', '')}_text_batch_overlay.png?v=1`,
      }),
    })
  })
  await page.route('**/api/point-prompt-result?image=library-a.svg', async (route) => {
    requestedPointPromptImages.push(new URL(route.request().url()).searchParams.get('image') ?? '')
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        metadata: {
          input_points: [[25, 35]],
          input_labels: [1],
        },
        overlayUrl: '/point-prompt-overlays/library-a_point_prompt_overlay.png?v=1',
      }),
    })
  })
  await page.route('**/api/point-prompt-result?image=library-b.svg', async (route) => {
    requestedPointPromptImages.push(new URL(route.request().url()).searchParams.get('image') ?? '')
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({
        error: 'Missing saved point-prompt result: library-b_point_prompt.json.',
      }),
    })
  })
  await page.route('**/text-batch-overlays/*', async (route) => {
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: LIBRARY_SVG,
    })
  })

  await page.goto('/')
  await page.getByTestId('text-prompt-input').fill('rebar')
  await page.getByTestId('start-text-inference').click()
  await expect(page.getByText('Text inference mode active. Select an image from the browser.')).toBeVisible()
  await expect(page.getByTestId('text-batch-checkbox-library-a.svg')).toBeVisible()
  await expect(page.getByTestId('text-batch-checkbox-library-b.svg')).toBeVisible()

  await page.getByTestId('text-batch-checkbox-library-a.svg').check()

  expect(requestedTextBatchImages).toContain('library-a.svg')
  expect(requestedPointPromptImages).toContain('library-a.svg')
  await expect(page.getByTestId('annotation-image')).toHaveAttribute(
    'src',
    '/text-batch-overlays/library-a_text_batch_overlay.png?v=1',
  )
  await expect(page.getByTestId('point-list')).toContainText('positive (25, 35)')
  await expect(page.getByTestId('text-batch-status-library-a.svg')).toHaveText('Saved text-batch mask and point markers loaded.')

  await page.getByTestId('text-batch-checkbox-library-b.svg').check()

  expect(requestedTextBatchImages).toContain('library-b.svg')
  expect(requestedPointPromptImages).toContain('library-b.svg')
  await expect(page.getByTestId('annotation-image')).toHaveAttribute(
    'src',
    '/text-batch-overlays/library-b_text_batch_overlay.png?v=1',
  )
  await expect(page.getByText('2 selected for text inference.')).toBeVisible()
  await expect(page.getByTestId('text-batch-status-library-b.svg')).toHaveText('Saved text-batch mask loaded.')
})

test('shows a saved text-batch missing error and preserves the selected image', async ({ page }) => {
  await page.route('**/api/images', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ images: ['IMG_7566.HEIC'] }),
    })
  })
  await page.route('**/source-images/*', async (route) => {
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: LIBRARY_SVG,
    })
  })
  await page.route('**/source-image-thumbnails/*', async (route) => {
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: LIBRARY_SVG,
    })
  })
  await page.route('**/api/text-batch-result?image=IMG_7566.HEIC', async (route) => {
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ error: 'Missing saved text-batch result: IMG_7566_text_batch.json.' }),
    })
  })

  await page.goto('/')
  await page.getByTestId('text-prompt-input').fill('rebar')
  await page.getByTestId('start-text-inference').click()
  await page.getByTestId('text-batch-checkbox-IMG_7566.HEIC').check()

  await expect(page.getByTestId('text-batch-status-IMG_7566.HEIC')).toHaveText('Missing saved text-batch result: IMG_7566_text_batch.json.')
  await expect(page.getByTestId('annotation-image')).toHaveAttribute('src', '/source-images/IMG_7566.HEIC')
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
