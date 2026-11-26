# AWAGO image prompts (manual generation guide)

During the build of this project the image-generation service was
**unavailable**, so the ten curated dashboard images could not be generated.
Per the project specification, this file records every prompt, filename and
size so you can generate the images yourself and drop them into
`app/static/img/`. The dashboard **automatically picks up** generated files:
it loads the `.webp`/`.png` listed below first and falls back to the bundled
SVG placeholders (`*.svg`) when the file is missing.

## How to use this file

1. Generate each image with any capable image model using the exact prompt
   (the shared style suffix is already appended).
2. Save it under `app/static/img/` with the **exact filename** given below.
3. Recommended: WebP at quality ~85 for photos/illustrations, PNG where
   transparency is needed. Keep each file under 300 KB
   (resize/compress with e.g. Pillow).
4. Rules that applied to the original generation (please keep them):
   - **No text** inside any image — no letters, numbers, logos of real
     companies, real currency symbols, flags, or real people.
   - Images must work on both dark and light themes and must never reduce
     the readability of charts, numbers, or text.
   - All images are local files; no hotlinking.
5. For `logo-mark.png`, also export 32x32 (`favicon-32x32.png`) and 180x180
   (`apple-touch-icon-180x180.png`) versions into the same folder.
6. Update `app/static/img/manifest.json` (set `"status": "generated"` and a
   `generation_date`) or regenerate it manually.

The current bundled placeholders were produced by
`python scripts/make_placeholder_images.py` and are recorded in
`app/static/img/manifest.json` (status `fallback-placeholder`).

## Shared style suffix (appended to every prompt)

> Cohesive visual style: modern fintech aesthetic, deep navy and midnight blue base (#0B1220 to #14213D), teal (#2DD4BF) and warm gold (#F5B942) accents, soft glow, subtle grid and data-line motifs, clean vector-like 3D-flat illustration, high-end, minimal, lots of negative space, no text, no letters, no numbers, no watermark, no logos, no people.

## The 10 images

| # | Filename | Size | Use |
|---|----------|------|-----|
| 1 | `hero-bg.webp` | 1920x800 | Dashboard header/hero background, behind a dark gradient overlay |
| 2 | `logo-mark.png` | 1024x1024 (transparent) | AWAGO emblem in the header; favicon source (also export 32x32 and 180x180) |
| 3 | `empty-state.webp` | 800x600 | Shown when no data is available for the selected pair/range |
| 4 | `error-state.webp` | 800x600 | Shown on API/network errors |
| 5 | `training-state.webp` | 800x600 | Shown while a model training or data collection job is running |
| 6 | `demo-banner-bg.webp` | 1600x300 | Background of the prominent "Demo data" banner |
| 7 | `card-forecast.webp` | 640x400 | Forecast feature card illustration |
| 8 | `card-trend.webp` | 640x400 | Trend-analysis feature card illustration |
| 9 | `card-evaluation.webp` | 640x400 | Model-evaluation feature card illustration |
| 10 | `og-image.webp` | 1200x630 | Social preview (Open Graph / Twitter card) |

### 1. `hero-bg.webp` (1920x800)

> Wide abstract banner background representing global currency markets: flowing luminous candlestick-like bars and smooth glowing price curves over a faint world-grid, depth of field, calm and professional, leave the center-right area relatively empty for overlay text. Cohesive visual style: modern fintech aesthetic, deep navy and midnight blue base (#0B1220 to #14213D), teal (#2DD4BF) and warm gold (#F5B942) accents, soft glow, subtle grid and data-line motifs, clean vector-like 3D-flat illustration, high-end, minimal, lots of negative space, no text, no letters, no numbers, no watermark, no logos, no people.

### 2. `logo-mark.png` (1024x1024, transparent background)

> Minimal abstract emblem for a forecasting platform: a stylized upward-curving arrow blended with a wave and a subtle compass-like ring, geometric, symmetrical, teal and gold gradient on a transparent background, flat vector look, no text. Cohesive visual style: modern fintech aesthetic, deep navy and midnight blue base (#0B1220 to #14213D), teal (#2DD4BF) and warm gold (#F5B942) accents, soft glow, subtle grid and data-line motifs, clean vector-like 3D-flat illustration, high-end, minimal, lots of negative space, no text, no letters, no numbers, no watermark, no logos, no people.

### 3. `empty-state.webp` (800x600)

> Illustration of an empty chart panel: a clean dashboard frame with a faint dotted baseline and a small magnifying glass hovering over blank space, soft glow, friendly and calm mood. Cohesive visual style: modern fintech aesthetic, deep navy and midnight blue base (#0B1220 to #14213D), teal (#2DD4BF) and warm gold (#F5B942) accents, soft glow, subtle grid and data-line motifs, clean vector-like 3D-flat illustration, high-end, minimal, lots of negative space, no text, no letters, no numbers, no watermark, no logos, no people.

### 4. `error-state.webp` (800x600)

> Illustration of a disconnected data link: two glowing nodes with a gently broken connecting line and small sparks, a subtle warning-amber accent, calm rather than alarming, tidy composition. Cohesive visual style: modern fintech aesthetic, deep navy and midnight blue base (#0B1220 to #14213D), teal (#2DD4BF) and warm gold (#F5B942) accents, soft glow, subtle grid and data-line motifs, clean vector-like 3D-flat illustration, high-end, minimal, lots of negative space, no text, no letters, no numbers, no watermark, no logos, no people.

### 5. `training-state.webp` (800x600)

> Illustration of a machine-learning model being trained: layered translucent neural-network nodes connected by glowing lines feeding into a rising line chart, sense of motion and progress. Cohesive visual style: modern fintech aesthetic, deep navy and midnight blue base (#0B1220 to #14213D), teal (#2DD4BF) and warm gold (#F5B942) accents, soft glow, subtle grid and data-line motifs, clean vector-like 3D-flat illustration, high-end, minimal, lots of negative space, no text, no letters, no numbers, no watermark, no logos, no people.

### 6. `demo-banner-bg.webp` (1600x300)

> Wide thin strip pattern in amber and navy: diagonal soft hatching with faint broken chart lines, indicating a simulated environment, subtle, low contrast, seamless feel. Cohesive visual style: modern fintech aesthetic, deep navy and midnight blue base (#0B1220 to #14213D), teal (#2DD4BF) and warm gold (#F5B942) accents, soft glow, subtle grid and data-line motifs, clean vector-like 3D-flat illustration, high-end, minimal, lots of negative space, no text, no letters, no numbers, no watermark, no logos, no people.

### 7. `card-forecast.webp` (640x400)

> A smooth price line that continues into the future as a dashed glowing path, surrounded by a translucent widening cone representing uncertainty, on a dark grid. Cohesive visual style: modern fintech aesthetic, deep navy and midnight blue base (#0B1220 to #14213D), teal (#2DD4BF) and warm gold (#F5B942) accents, soft glow, subtle grid and data-line motifs, clean vector-like 3D-flat illustration, high-end, minimal, lots of negative space, no text, no letters, no numbers, no watermark, no logos, no people.

### 8. `card-trend.webp` (640x400)

> A noisy price series with a clean bright trend line cutting through it and a subtle directional arrow, layered moving-average ribbons in teal and gold, dark grid. Cohesive visual style: modern fintech aesthetic, deep navy and midnight blue base (#0B1220 to #14213D), teal (#2DD4BF) and warm gold (#F5B942) accents, soft glow, subtle grid and data-line motifs, clean vector-like 3D-flat illustration, high-end, minimal, lots of negative space, no text, no letters, no numbers, no watermark, no logos, no people.

### 9. `card-evaluation.webp` (640x400)

> Two competing glowing curves, one labeled-by-color as the model and one as the baseline, with a magnified comparison zone and a small balance-scale motif, dark grid, no text. Cohesive visual style: modern fintech aesthetic, deep navy and midnight blue base (#0B1220 to #14213D), teal (#2DD4BF) and warm gold (#F5B942) accents, soft glow, subtle grid and data-line motifs, clean vector-like 3D-flat illustration, high-end, minimal, lots of negative space, no text, no letters, no numbers, no watermark, no logos, no people.

### 10. `og-image.webp` (1200x630)

> Cinematic wide composition of a futuristic currency analytics dashboard floating in space: glowing charts, forecast bands, and a faint globe made of data points, centered focal point with generous margins, no text. Cohesive visual style: modern fintech aesthetic, deep navy and midnight blue base (#0B1220 to #14213D), teal (#2DD4BF) and warm gold (#F5B942) accents, soft glow, subtle grid and data-line motifs, clean vector-like 3D-flat illustration, high-end, minimal, lots of negative space, no text, no letters, no numbers, no watermark, no logos, no people.
