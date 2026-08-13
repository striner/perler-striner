# Perler Striner 🔴🟡🔵🟢

**Perler Striner** is a browser-based fuse-bead / Perler-bead pattern maker.
Upload an image, choose a bead color system, adjust the pattern width, and export
a pegboard-ready PNG chart with a bead shopping list.

The static frontend can use a configured Python processor for grid preparation.
If that service is unavailable or returns an invalid result, the same operation
falls back to the browser automatically. Palette matching, counting, rendering,
and export always remain in the browser.

## Links

- Live demo: <https://striner.github.io/perler-striner/>
- Chinese UI: <https://striner.github.io/perler-striner/zh/>
- Repository: <https://github.com/striner/perler-striner>
- GitHub profile: <https://github.com/striner>

## Features

- Upload or drag-and-drop local images.
- Select CV Native backend processing or Browser Native local processing.
- Tune CV Native foreground recovery, protection, seed, and edge-enhancement parameters.
- Explicitly generate after input changes; generation locks controls and then enables download.
- Generate bead patterns by width in beads while preserving the source aspect ratio.
- Choose from 7 bead color systems with 1,392 colors in total.
- Match image colors to real bead colors using CIE Lab + CIEDE2000 perceptual distance.
- Toggle Floyd–Steinberg dithering for smoother photo-like gradients.
- Treat transparent pixels as empty pegs.
- Remove backgrounds before generating the bead pattern, through the configured processor or the browser fallback.
- Show grid lines, coordinate labels, and pegboard-friendly guides.
- Calculate bead counts and generate a shopping list sorted by quantity.
- Click a color in the shopping list to highlight its positions on the pattern.
- Export a printable PNG containing the pattern and the color legend.
- Support English and Chinese pages.

## Pattern settings

The main panel exposes the most important generation controls:

| Setting | Description |
| :-- | :-- |
| Processing mode | CV Native uses the configured backend and falls back with a five-second notice; Browser Native stays local. |
| Bead brand | Choose the target bead palette. The same image can produce different results with different real-world color systems. |
| Width in beads | Controls the horizontal bead count. The height is calculated from the original image aspect ratio. |
| Zoom | Changes the preview cell size only. It does not change the generated pattern data. |
| Dithering | Enables Floyd–Steinberg error diffusion for smoother gradients and photo-like results. |
| Grid & pegboard lines | Shows or hides construction guides in the preview. Exported PNGs always keep printable guide information. |

CV Native adds a separate **Hyperparameters** panel below Pattern settings. It
contains the backend-supported foreground recovery, coarse-subject protection,
foreground seed, edge seed, mask dilation, grid coverage, sharpening, and outline
controls. The panel is collapsed by default. **Restore defaults** resets all CV
controls without starting a request.
Uploading a new image or changing the processing mode, target width, or
a CV hyperparameter does not immediately process the image. The main action changes
to **Generate**; during processing it displays **Generating** and locks the controls,
then becomes **Download** after palette matching completes. Brand, dithering, grid,
and zoom changes continue to apply to the current result without another backend call.

### Grid preparation and background removal

For uploaded files, selecting **Generate** asks the configured processor to resize
the source to the target grid and remove its background. A valid response is a
row-major RGBA grid with one pixel per bead. Network errors, timeouts, non-2xx
responses, empty responses, and contract violations automatically select the
browser fallback. Built-in samples also use the browser path directly.

The browser fallback:

1. Samples pixels along the image border.
2. Estimates several likely border background color clusters.
3. Detects subject candidates from pixels that differ from those background
   clusters and from strong local color edges.
4. Keeps larger/central subject components, expands that mask slightly, and fills
   protected holes inside the subject region.
5. Flood-fills from the image border and removes only areas outside the protected
   subject mask.
6. Marks removed background cells as empty pegs.

This means internal subject details are preserved if they are not connected to
the border background. For example, white details inside a character or object
should not be removed just because the outer background is white.

Best suited for:

- transparent PNGs,
- white or light-gray backgrounds,
- solid color backgrounds,
- simple product-photo backgrounds,
- softly varying backgrounds with limited color changes.

Less suited for:

- busy natural scenes,
- backgrounds with colors very close to the subject,
- subjects touching the image border,
- cases that require semantic AI segmentation.

For difficult images, clean the background manually first. Background removal is
a required preprocessing invariant and has no UI or API switch.

## Supported color palettes

| System | Colors | Bead size | Example codes | Data source |
| :-- | --: | :-- | :-- | :-- |
| Perler | 103 | 5 mm midi | `80-15211` | [beadcolors](https://github.com/maxcleme/beadcolors) |
| MARD 221 | 221 | 5 mm midi | `A1`, `F15` | [bitbead.app](https://www.bitbead.app/en/colors/mard) |
| MARD 291 | 291 | 2.6 mm mini | `A1` ... `ZG8` | [bitbead.app](https://www.bitbead.app/en/colors/mard-291) |
| COCO 291 | 291 | 2.6 mm mini | `E02`, `K39` | [bitbead.app](https://www.bitbead.app/en/colors/coco) |
| Hama | 89 | 5 mm midi | `H01` | [bitbead.app](https://www.bitbead.app/en/colors/hama) |
| Artkal S | 176 | 5 mm midi | `S01` | [bitbead.app](https://www.bitbead.app/en/colors/artkal) |
| Artkal Mini | 221 | 2.6 mm mini | `MA1` | [bitbead.app](https://www.bitbead.app/en/colors/artkal-mini) |

## Tech stack

| Area | Choice |
| :-- | :-- |
| Site framework | [Astro](https://astro.build) |
| Interactive app | [React](https://react.dev) island |
| Language | TypeScript |
| Styling | [Tailwind CSS](https://tailwindcss.com) |
| UI components | shadcn/ui-style components + Radix primitives |
| Icons | lucide-react |
| Grid preparation | Python processor when configured; browser Canvas fallback |
| Color matching | CIE Lab + CIEDE2000 |
| Export | Canvas `toBlob()` PNG |
| Hosting | Static output, GitHub Pages |

The frontend production build is fully static. The Python processor is deployed
independently; there is no database or upload persistence in the current backend.

## How it works

The core conversion pipeline is:

```text
Upload image
→ Decode image in the browser
→ Request a resized, background-removed RGBA grid from the configured backend
→ Fall back to browser downsampling and background removal on any failure
→ Convert each grid pixel to a bead color
→ Optionally diffuse color error with dithering
→ Build bead-count statistics
→ Render the pattern and legend to Canvas
→ Export PNG
```

### 1. Decode and prepare the grid

The React app loads the source image with `createImageBitmap()` when available,
falling back to `HTMLImageElement` decoding when needed. The target pattern size
is based on the selected width in beads:

```text
targetHeight = round(targetWidth * sourceHeight / sourceWidth)
```

The original `File`, decoded image, and target dimensions are retained. When
`PUBLIC_PROCESSOR_API_URL` is configured and CV Native is selected, the file is
posted to `/api/v1/process` as `cv_native@1.0.0`. Otherwise it is drawn to an offscreen
Canvas at the target size. At the resulting grid, **one pixel equals one bead**.
The request is sent only after the user selects **Generate**.

### 2. Transparent pixels and background cleanup

Pixels with alpha below the threshold are treated as empty cells. Every backend
algorithm must return an already background-removed grid. The browser fallback
performs its existing border-connected background cleanup:

- Start from the image borders.
- Estimate the dominant background color from border pixels.
- Find background-like pixels connected to the border.
- Mark those cells as empty.
- Preserve internal details that are not connected to the border.

The fallback works well for transparent PNGs, white backgrounds, light gray
backgrounds, and many solid or softly varying backgrounds. It is still a
lightweight browser-side heuristic rather than semantic segmentation.

### 3. Perceptual color matching

For every solid cell, the app maps the RGB color to the nearest real bead color
in the selected palette.

Instead of using plain RGB distance, the matcher uses:

```text
sRGB → CIE Lab → CIEDE2000
```

CIEDE2000 is a perceptual color-difference formula. It better approximates how
humans judge color differences than simple Euclidean distance in RGB space.

The palette colors are pre-converted to Lab and cached per brand. Repeated RGB
lookups are also cached to keep the browser-side generation fast.

### 4. Floyd–Steinberg dithering

When dithering is enabled, the app uses Floyd–Steinberg error diffusion. After a
pixel is replaced by its nearest bead color, the remaining color error is spread
to neighboring unprocessed cells:

```text
        current    7/16
3/16      5/16     1/16
```

This can make photos and gradients look smoother with a limited bead palette,
but it may also introduce more scattered colors, so it is exposed as a toggle.

### 5. Rendering and export

The generated `Pattern` data contains:

- pattern width and height,
- a typed array of palette indexes per cell,
- `-1` for empty cells,
- used colors and bead counts,
- total bead count.

The renderer draws the final pattern to Canvas with:

- cell color blocks,
- readable bead codes,
- coordinate labels,
- grid lines,
- guide lines,
- highlight mode for a selected color,
- export layout with a printable legend.

## Project structure

```text
src/
├── components/
│   ├── HomePage.astro        # Astro page shell and layout
│   ├── PerlerStudio.tsx      # Main React island: upload, controls, preview, export
│   └── ui/                   # shadcn/ui-style components
├── i18n/
│   └── ui.ts                 # English / Chinese UI text
├── lib/
│   ├── color.ts              # sRGB → Lab, CIEDE2000, nearest-bead matcher
│   ├── grid.ts               # Local grid resizing and mandatory background removal
│   ├── palette.ts            # Bead brand and color palette data
│   ├── pattern.ts            # RGBA grid → bead pattern, dithering, statistics
│   ├── processor-client.ts   # Backend contract validation and local fallback
│   ├── render.ts             # Canvas rendering and PNG export
│   └── utils.ts              # Shared utility helpers
├── pages/
│   ├── index.astro           # English page
│   ├── zh/index.astro        # Chinese page
│   └── striner/perler/       # Legacy-compatible route aliases
└── styles/
    └── global.css            # Tailwind and theme variables

docs/
├── PRD.md                    # Product requirements
└── TECH_DESIGN.md            # Technical design notes
```

## Development

Requirements:

- Node.js `>= 22.12.0`
- npm

Commands:

| Command | Description |
| :-- | :-- |
| `npm install` | Install dependencies |
| `npm run dev` | Start Astro dev server |
| `npm run build` | Build static files into `dist/` |
| `npm run preview` | Preview the production build locally |

Processor configuration is read at build time. See `.env.example` for
`PUBLIC_PROCESSOR_API_URL`, optional CV parameters, and timeout. If the URL is
absent, Browser Native is selected and no HTTP request is made.
The default processor timeout is 35 seconds, leaving response overhead above the
backend's 30-second request execution limit.

Local development:

```bash
npm install
npm run dev
```

Production build:

```bash
npm run build
```

The static output is generated in:

```text
dist/
```

## Deployment

### GitHub Pages

This repository is configured for GitHub Pages through GitHub Actions.

- Branch: `master`
- Workflow: `.github/workflows/deploy.yml`
- Build command: `cd frontend && npm run build`
- Output directory: `frontend/dist`
- Astro base path: `/perler-striner`
- Public URL: <https://striner.github.io/perler-striner/>

After pushing to `master`, the workflow builds and deploys the site automatically.

### Static server / Nginx

You can also deploy the static build to any server:

```bash
npm install
npm run build
tar -czf perler-striner-dist.tar.gz dist
```

Example Nginx config:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    root /var/www/perler-striner;
    index index.html;

    location /perler-striner/ {
        try_files $uri $uri/ /index.html;
    }

    location = / {
        return 302 /perler-striner/;
    }
}
```

Then reload Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Privacy

When a processor URL is configured and CV Native is selected, original uploaded
files are sent to that processor before browser fallback. The current backend
keeps uploads in request memory and does not persist them. Deployments must use
HTTPS and explicit CORS origins. With no processor configuration, all image
preparation stays in the browser.

## Acknowledgements

- This project was built with reference to the original Perler Studio code and
  implementation ideas by [real-jiakai](https://github.com/real-jiakai). Thanks
  for the inspiration around the browser-first bead-pattern workflow, palette
  integration, color matching, rendering, and export experience.
- Bead color references from [beadcolors](https://github.com/maxcleme/beadcolors)
  and [bitbead.app](https://www.bitbead.app/en/colors).
- Built with [Astro](https://astro.build), [React](https://react.dev),
  [Tailwind CSS](https://tailwindcss.com), and shadcn/ui-style components.

## Notes

Perler®, Hama, Artkal, MARD, and COCO are trademarks of their respective owners.
This is an unofficial fan-made design tool. Color values are measured or
community-provided approximations and may differ from physical beads.
