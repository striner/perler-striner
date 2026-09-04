import { BRANDS, type BrandId } from "./palette";
import { nearestBead, nearestBeadFrom, paletteRgb, whiteBeadIndex } from "./color";
import type { RgbaGrid } from "./grid";

export interface Pattern {
  brand: BrandId;
  width: number;
  height: number;
  /** Palette index per cell (into BRANDS[brand].colors), -1 = empty. */
  cells: Int16Array;
  /** Colors actually used, sorted by bead count descending. */
  used: { index: number; count: number }[];
  totalBeads: number;
}

export interface PatternOptions {
  dither: boolean;
  brand: BrandId;
  whiteThreshold?: number;
  maxColors?: number;
}

/** Quantize a background-removed RGBA grid to a brand's bead palette. */
export function generatePattern(
  img: RgbaGrid,
  opts: PatternOptions
): Pattern {
  const { width, height, data } = img;
  const { brand, whiteThreshold = 246 } = opts;
  const rgb = paletteRgb(brand);
  const white = whiteBeadIndex(brand);
  const allowed = selectBrandPalette(img, brand, opts.maxColors);
  const allowedSet = allowed ? new Set(allowed) : null;
  const n = width * height;
  const cells = new Int16Array(n).fill(-1);
  const counts = new Array<number>(BRANDS[brand].colors.length).fill(0);

  // Float working copy so dither error accumulates without clipping.
  const buf = new Float32Array(n * 3);
  const solid = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const p = i * 4;
    if (data[p + 3]! >= 128) {
      solid[i] = 1;
      buf[i * 3] = data[p]!;
      buf[i * 3 + 1] = data[p + 1]!;
      buf[i * 3 + 2] = data[p + 2]!;
    }
  }

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = y * width + x;
      if (!solid[i]) continue;
      const r = buf[i * 3]!;
      const g = buf[i * 3 + 1]!;
      const b = buf[i * 3 + 2]!;
      const [mr, mg, mb] = enhanceMatchColor(r, g, b);
      const pi =
        white !== null &&
        (!allowedSet || allowedSet.has(white)) &&
        Math.min(mr, mg, mb) >= whiteThreshold &&
        Math.max(mr, mg, mb) - Math.min(mr, mg, mb) <= 10
          ? white
          : allowed
            ? nearestBeadFrom(brand, allowed, mr, mg, mb)
            : nearestBead(brand, mr, mg, mb);
      cells[i] = pi;
      counts[pi]!++;
      if (!opts.dither) continue;
      const [pr, pg, pb] = rgb[pi]!;
      const er = r - pr;
      const eg = g - pg;
      const eb = b - pb;
      const spread = (xx: number, yy: number, weight: number) => {
        if (xx < 0 || xx >= width || yy >= height) return;
        const j = yy * width + xx;
        if (!solid[j]) return;
        buf[j * 3] += er * weight;
        buf[j * 3 + 1] += eg * weight;
        buf[j * 3 + 2] += eb * weight;
      };
      spread(x + 1, y, 7 / 16);
      spread(x - 1, y + 1, 3 / 16);
      spread(x, y + 1, 5 / 16);
      spread(x + 1, y + 1, 1 / 16);
    }
  }

  const used = counts
    .map((count, index) => ({ index, count }))
    .filter((item) => item.count > 0)
    .sort((a, b) => b.count - a.count);

  return {
    brand,
    width,
    height,
    cells,
    used,
    totalBeads: used.reduce((sum, item) => sum + item.count, 0),
  };
}

function selectBrandPalette(
  img: RgbaGrid,
  brand: BrandId,
  maxColors: number | undefined
): number[] | null {
  if (maxColors === undefined) return null;
  const limit = Math.max(1, Math.min(BRANDS[brand].colors.length, Math.floor(maxColors)));
  const counts = new Map<number, number>();
  for (let offset = 0; offset < img.data.length; offset += 4) {
    if (img.data[offset + 3]! < 128) continue;
    const [r, g, b] = enhanceMatchColor(
      img.data[offset]!,
      img.data[offset + 1]!,
      img.data[offset + 2]!
    );
    const index = nearestBead(brand, r, g, b);
    counts.set(index, (counts.get(index) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0] - right[0])
    .slice(0, limit)
    .map(([index]) => index);
}

function enhanceMatchColor(r: number, g: number, b: number): [number, number, number] {
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const chroma = max - min;
  if (chroma < 18) return [r, g, b];

  const [h, s, l] = rgbToHsl(r, g, b);
  if (s < 0.12 || l < 0.08 || l > 0.92) return [r, g, b];

  const isGreen = h >= 70 && h <= 170;
  return hslToRgb(
    h,
    Math.min(1, s * (isGreen ? 1.55 : 1.3)),
    Math.min(0.9, l + (isGreen ? 0.08 : 0.04))
  );
}

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255;
  g /= 255;
  b /= 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  if (d === 0) return [0, 0, l];

  const s = d / (1 - Math.abs(2 * l - 1));
  let h = 0;
  if (max === r) h = ((g - b) / d) % 6;
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  h *= 60;
  if (h < 0) h += 360;
  return [h, s, l];
}

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hp = h / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let r = 0;
  let g = 0;
  let b = 0;
  if (hp < 1) [r, g, b] = [c, x, 0];
  else if (hp < 2) [r, g, b] = [x, c, 0];
  else if (hp < 3) [r, g, b] = [0, c, x];
  else if (hp < 4) [r, g, b] = [0, x, c];
  else if (hp < 5) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];

  const m = l - c / 2;
  return [
    Math.round((r + m) * 255),
    Math.round((g + m) * 255),
    Math.round((b + m) * 255),
  ];
}
