# Carousel · Structure-Aware RAG

A 10-slide LinkedIn carousel built with vanilla HTML + CSS. Exports to a
single multi-page PDF via Playwright. The PDF is vector with embedded
fonts, so text stays selectable and searchable.

## Preview in the browser

```bash
npm run dev
# open http://localhost:8000
```

You'll see all 10 slides stacked vertically. Scroll through to give feedback.

## Export to PDF

First time only:

```bash
npm install
```

Then any time:

```bash
npm run export
```

This produces `carousel.pdf` in this folder. Each PDF page is one slide
(1080×1350 px), ready to upload to LinkedIn as a document attachment for a
carousel post.

## Capture per-slide PNGs

Useful for inspecting individual slides or sharing single panels:

```bash
npm run dev         # start the static server in one terminal
npm run screenshot  # writes screenshots/slide-NN.png in another
```

## Editing

The design system lives in `theme.css` as CSS custom properties. Tweak any
token there and every slide updates:

- `--color-accent`, `--color-text`, `--color-bg-*` for colors
- `--font-sans`, `--font-mono` for fonts
- `--text-hero`, `--text-title`, `--text-body` for the type scale
- `--border-thin/medium/thick` for stroke widths
- `--radius-sm/md/lg/xl` for corner radii
- `--gap-xs/sm/md/lg/xl` for the spacing scale
- `--base-scale` to multiply the whole type scale at once (current: 1.6)

Files:

- `theme.css` design tokens, the source of truth
- `base.css` typography, slide layout, print/screen mode rules
- `components.css` reusable bits (`.card`, `.chip`, `.stat`, etc.)
- `slides.css` per-slide layouts
- `index.html` the slides themselves
- `server.mjs` tiny zero-dependency static server
- `screenshot.mjs` Playwright per-slide PNG capture
- `export.mjs` Playwright multi-page PDF export

## How the export works

`export.mjs`:

1. Spawns the static server on port 8765
2. Launches headless Chromium at 1080×1350 viewport, 2× DPR
3. Switches to `print` media so each `.slide` becomes a page via
   `page-break-after: always` and the @page rule sized to the slide
4. Calls `page.pdf({ width: "1080px", height: "1350px" })` once, producing a
   single PDF with one page per slide

LinkedIn carousels accept multi-page PDFs directly, no combine step needed.
