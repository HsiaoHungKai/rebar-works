# SAM3 Frontend (React)

Local React frontend for point-prompt annotation with mock visualization.

## Features

- Upload local image files from browser
- Add positive point prompts (green) and negative point prompts (red)
- View point list with coordinates and label type
- Undo last point and clear all points
- Mock segmentation overlay for frontend-only testing

## Run locally

```bash
cd frontend
npm install
npm run dev
```

Then open the printed local URL in Safari (or another browser).

## Run Playwright tests

```bash
cd frontend
npm run test:e2e
```

The Playwright config starts a local Vite server automatically for tests.
