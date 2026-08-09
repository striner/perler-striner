# Perler Striner 🔴🟡🔵🟢

**Perler Striner** is a browser-based fuse-bead / Perler-bead pattern maker.
Upload an image, choose a bead color system, adjust the pattern width, and export
a pegboard-ready PNG chart with a bead shopping list.

Everything runs in the browser. Images are processed locally with Canvas and are
not uploaded to a backend service.

## Links

- Live demo: <https://striner.github.io/perler-striner/>
- Chinese UI: <https://striner.github.io/perler-striner/zh/>
- Repository: <https://github.com/striner/perler-striner>
- GitHub profile: <https://github.com/striner>

## Features

- Upload or drag-and-drop local images.
- Generate bead patterns by width in beads while preserving the source aspect ratio.
- Choose from 7 bead color systems with 1,392 colors in total.
- Match image colors to real bead colors using CIE Lab + CIEDE2000 perceptual distance.
- Toggle Floyd–Steinberg dithering for smoother photo-like gradients.
- Treat transparent pixels as empty pegs.
- Optionally remove border-connected backgrounds before generating the bead pattern.
- Show grid lines, coordinate labels, and pegboard-friendly guides.
- Calculate bead counts and generate a shopping list sorted by quantity.
- Click a color in the shopping list to highlight its positions on the pattern.
- Export a printable PNG containing the pattern and the color legend.
- Support English and Chinese pages.

## Pattern settings

The main panel exposes the most important generation controls:

| Setting | Description |
| :-- | :-- |
| Bead brand | Choose the target bead palette. The same image can produce different results with different real-world color systems. |
| Width in beads | Controls the horizontal bead count. The height is calculated from the original image aspect ratio. |
| Zoom | Changes the preview cell size only. It does not change the generated pattern data. |
| Dithering | Enables Floyd–Steinberg error diffusion for smoother gradients and photo-like results. |
| Remove background | Estimates and protects the main subject first, then removes border-connected background regions before color matching. Turn it on for product photos, portraits, logos, white/solid backgrounds, or lightly varied backgrounds. Turn it off when you want the full rectangular image, including the background, to become beads. |
| Grid & pegboard lines | Shows or hides construction guides in the preview. Exported PNGs always keep printable guide information. |

### Background removal behavior

`Remove background` is designed for common craft-design inputs where the main
subject is visually separated from the surrounding background. When enabled, the
app:

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

For difficult images, clean the background manually first or disable this option
to keep the full image.

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
| Image processing | Browser Canvas / ImageData |
| Color matching | CIE Lab + CIEDE2000 |
| Export | Canvas `toBlob()` PNG |
| Hosting | Static output, GitHub Pages |

The production build is fully static. There is no application server, database,
or image-upload API.

## How it works

The core conversion pipeline is:

```text
Upload image
→ Decode image in the browser
→ Downsample the image to a bead grid
→ Optionally remove border-connected background regions
→ Convert each grid pixel to a bead color
→ Optionally diffuse color error with dithering
→ Build bead-count statistics
→ Render the pattern and legend to Canvas
→ Export PNG
```

### 1. Decode and downsample

The React app loads the source image with `createImageBitmap()` when available,
falling back to `HTMLImageElement` decoding when needed. The target pattern size
is based on the selected width in beads:

```text
targetHeight = round(targetWidth * sourceHeight / sourceWidth)
```

The image is drawn to an offscreen Canvas at the target bead-grid size. At this
point, **one pixel equals one bead**. Large images are downsampled in multiple
halving steps before the final resize, which helps preserve detail and reduce
aliasing.

### 2. Transparent pixels and background cleanup

Pixels with alpha below the threshold are treated as empty cells. For images with
a removable background, the generator can perform a border-connected background
cleanup:

- Start from the image borders.
- Estimate the dominant background color from border pixels.
- Find background-like pixels connected to the border.
- Mark those cells as empty.
- Preserve internal details that are not connected to the border.

This works well for transparent PNGs, white backgrounds, light gray backgrounds,
and many solid or softly varying background colors. It is still a lightweight
browser-side heuristic, not an AI segmentation model, so very complex backgrounds
or subjects with colors close to the background may still need manual cleanup in
the source image.

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
│   ├── palette.ts            # Bead brand and color palette data
│   ├── pattern.ts            # ImageData → bead pattern, dithering, background cleanup
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
- Build command: `npm run build`
- Output directory: `dist`
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

The app is designed as a zero-backend static tool. Uploaded images are decoded
and processed locally in the browser. They are not sent to a server by this app.

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
