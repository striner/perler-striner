import { BRANDS, type BrandId } from "./palette";
import { nearestBead, paletteRgb, whiteBeadIndex } from "./color";

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
  removeWhiteBackground?: boolean;
}

type BackgroundSample = {
  r: number;
  g: number;
  b: number;
  tolerance: number;
  weight?: number;
};

/**
 * Quantize a grid-sized ImageData to a brand's bead palette.
 * With dithering enabled, Floyd–Steinberg error diffusion runs over the
 * bead grid; error is never propagated into or out of empty cells.
 */
export function generatePattern(
  img: ImageData,
  opts: PatternOptions
): Pattern {
  const { width, height, data } = img;
  const {
    brand,
    whiteThreshold = 246,
    removeWhiteBackground = true,
  } = opts;
  const rgb = paletteRgb(brand);
  const white = whiteBeadIndex(brand);
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

  if (removeWhiteBackground) {
    removeBorderBackground(solid, buf, width, height, whiteThreshold);
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
        Math.min(mr, mg, mb) >= whiteThreshold &&
        Math.max(mr, mg, mb) - Math.min(mr, mg, mb) <= 10
          ? white
          : nearestBead(brand, mr, mg, mb);
      cells[i] = pi;
      counts[pi]!++;
      if (!opts.dither) continue;
      const [pr, pg, pb] = rgb[pi]!;
      const er = r - pr;
      const eg = g - pg;
      const eb = b - pb;
      const spread = (xx: number, yy: number, w: number) => {
        if (xx < 0 || xx >= width || yy >= height) return;
        const j = yy * width + xx;
        if (!solid[j]) return;
        buf[j * 3] += er * w;
        buf[j * 3 + 1] += eg * w;
        buf[j * 3 + 2] += eb * w;
      };
      spread(x + 1, y, 7 / 16);
      spread(x - 1, y + 1, 3 / 16);
      spread(x, y + 1, 5 / 16);
      spread(x + 1, y + 1, 1 / 16);
    }
  }

  const used = counts
    .map((count, index) => ({ index, count }))
    .filter((u) => u.count > 0)
    .sort((a, b) => b.count - a.count);

  return {
    brand,
    width,
    height,
    cells,
    used,
    totalBeads: used.reduce((s, u) => s + u.count, 0),
  };
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

function pixelAt(buf: Float32Array, i: number): [number, number, number] {
  const r = buf[i * 3]!;
  const g = buf[i * 3 + 1]!;
  const b = buf[i * 3 + 2]!;
  return [r, g, b];
}

function colorDistance2(
  r1: number,
  g1: number,
  b1: number,
  r2: number,
  g2: number,
  b2: number
): number {
  const dr = r1 - r2;
  const dg = g1 - g2;
  const db = b1 - b2;
  return dr * dr + dg * dg + db * db;
}

function isNearWhite(r: number, g: number, b: number, whiteThreshold: number): boolean {
  return (
    Math.min(r, g, b) >= whiteThreshold &&
    Math.max(r, g, b) - Math.min(r, g, b) <= 16
  );
}

function collectBorderSamples(
  solid: Uint8Array,
  buf: Float32Array,
  width: number,
  height: number
): [number, number, number][] {
  const samples: [number, number, number][] = [];
  const add = (x: number, y: number) => {
    const i = y * width + x;
    if (!solid[i]) return;
    samples.push(pixelAt(buf, i));
  };

  for (let x = 0; x < width; x++) {
    add(x, 0);
    if (height > 1) add(x, height - 1);
  }
  for (let y = 1; y < height - 1; y++) {
    add(0, y);
    if (width > 1) add(width - 1, y);
  }
  return samples;
}

function estimateBackground(
  solid: Uint8Array,
  buf: Float32Array,
  width: number,
  height: number,
  whiteThreshold: number
): BackgroundSample | null {
  const samples = collectBorderSamples(solid, buf, width, height);
  if (!samples.length) return null;

  const nearWhite = samples.filter(([r, g, b]) =>
    isNearWhite(r, g, b, whiteThreshold)
  );
  const source = nearWhite.length >= Math.max(4, samples.length * 0.12)
    ? nearWhite
    : dominantColorCluster(samples);

  const sortedR = source.map(([r]) => r).sort((a, b) => a - b);
  const sortedG = source.map(([, g]) => g).sort((a, b) => a - b);
  const sortedB = source.map(([, , b]) => b).sort((a, b) => a - b);
  const mid = Math.floor(source.length / 2);
  const r = sortedR[mid]!;
  const g = sortedG[mid]!;
  const b = sortedB[mid]!;

  const distances = source
    .map(([sr, sg, sb]) => Math.sqrt(colorDistance2(sr, sg, sb, r, g, b)))
    .sort((a, b) => a - b);
  const p75 = distances[Math.floor(distances.length * 0.75)] ?? 0;
  const p90 = distances[Math.floor(distances.length * 0.9)] ?? p75;
  const baseTolerance = nearWhite.length ? 34 : 26;
  const tolerance = Math.max(baseTolerance, Math.min(72, p75 * 1.8 + p90 * 0.35 + 18));

  return { r, g, b, tolerance };
}

function estimateBackgroundClusters(
  solid: Uint8Array,
  buf: Float32Array,
  width: number,
  height: number,
  whiteThreshold: number
): BackgroundSample[] {
  const samples = collectBorderSamples(solid, buf, width, height);
  if (!samples.length) return [];

  const bucketSize = 28;
  const buckets = new Map<string, { count: number; r: number; g: number; b: number }>();
  for (const [r, g, b] of samples) {
    const key = [
      Math.round(r / bucketSize),
      Math.round(g / bucketSize),
      Math.round(b / bucketSize),
    ].join(",");
    const bucket = buckets.get(key) ?? { count: 0, r: 0, g: 0, b: 0 };
    bucket.count++;
    bucket.r += r;
    bucket.g += g;
    bucket.b += b;
    buckets.set(key, bucket);
  }

  const clusters = [...buckets.values()]
    .sort((a, b) => b.count - a.count)
    .slice(0, 6)
    .map((bucket) => {
      const r = bucket.r / bucket.count;
      const g = bucket.g / bucket.count;
      const b = bucket.b / bucket.count;
      const isWhite = isNearWhite(r, g, b, whiteThreshold);
      return {
        r,
        g,
        b,
        tolerance: isWhite ? 58 : 48,
        weight: bucket.count / samples.length,
      };
    });

  const white = estimateBackground(solid, buf, width, height, whiteThreshold);
  if (white && isNearWhite(white.r, white.g, white.b, whiteThreshold)) {
    clusters.unshift({ ...white, tolerance: Math.max(white.tolerance, 58) });
  }

  return clusters;
}

function dominantColorCluster(
  samples: [number, number, number][]
): [number, number, number][] {
  const bucketSize = 24;
  const buckets = new Map<string, { count: number; r: number; g: number; b: number }>();

  for (const [r, g, b] of samples) {
    const key = [
      Math.round(r / bucketSize),
      Math.round(g / bucketSize),
      Math.round(b / bucketSize),
    ].join(",");
    const bucket = buckets.get(key) ?? { count: 0, r: 0, g: 0, b: 0 };
    bucket.count++;
    bucket.r += r;
    bucket.g += g;
    bucket.b += b;
    buckets.set(key, bucket);
  }

  let best = null as { count: number; r: number; g: number; b: number } | null;
  for (const bucket of buckets.values()) {
    if (!best || bucket.count > best.count) best = bucket;
  }
  if (!best) return samples;

  const cr = best.r / best.count;
  const cg = best.g / best.count;
  const cb = best.b / best.count;
  const cluster = samples.filter(
    ([r, g, b]) => Math.sqrt(colorDistance2(r, g, b, cr, cg, cb)) <= 52
  );

  return cluster.length >= Math.max(3, samples.length * 0.08) ? cluster : samples;
}

function isBackgroundPixel(
  buf: Float32Array,
  i: number,
  bg: BackgroundSample,
  whiteThreshold: number
): boolean {
  const [r, g, b] = pixelAt(buf, i);
  if (isNearWhite(r, g, b, whiteThreshold)) return true;

  const dist = Math.sqrt(colorDistance2(r, g, b, bg.r, bg.g, bg.b));
  if (dist <= bg.tolerance) return true;

  const pixelChroma = Math.max(r, g, b) - Math.min(r, g, b);
  const bgChroma = Math.max(bg.r, bg.g, bg.b) - Math.min(bg.r, bg.g, bg.b);
  const pixelLuma = (r + g + b) / 3;
  const bgLuma = (bg.r + bg.g + bg.b) / 3;

  return (
    bgChroma <= 24 &&
    pixelChroma <= 30 &&
    Math.abs(pixelLuma - bgLuma) <= bg.tolerance * 0.9
  );
}

function isBackgroundLike(
  buf: Float32Array,
  i: number,
  clusters: BackgroundSample[],
  whiteThreshold: number
): boolean {
  const [r, g, b] = pixelAt(buf, i);
  if (isNearWhite(r, g, b, whiteThreshold)) return true;

  for (const bg of clusters) {
    if (isBackgroundPixel(buf, i, bg, whiteThreshold)) return true;
  }
  return false;
}

function localEdgeStrength(
  buf: Float32Array,
  x: number,
  y: number,
  width: number,
  height: number
): number {
  const i = y * width + x;
  const [r, g, b] = pixelAt(buf, i);
  let best = 0;
  const check = (xx: number, yy: number) => {
    if (xx < 0 || xx >= width || yy < 0 || yy >= height) return;
    const j = yy * width + xx;
    const [nr, ng, nb] = pixelAt(buf, j);
    best = Math.max(best, Math.sqrt(colorDistance2(r, g, b, nr, ng, nb)));
  };
  check(x - 1, y);
  check(x + 1, y);
  check(x, y - 1);
  check(x, y + 1);
  return best;
}

function buildSubjectProtectionMask(
  solid: Uint8Array,
  buf: Float32Array,
  width: number,
  height: number,
  whiteThreshold: number
): Uint8Array {
  const n = width * height;
  const clusters = estimateBackgroundClusters(solid, buf, width, height, whiteThreshold);
  if (!clusters.length) return new Uint8Array(n);

  const seed = new Uint8Array(n);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = y * width + x;
      if (!solid[i]) continue;
      const [r, g, b] = pixelAt(buf, i);
      const chroma = Math.max(r, g, b) - Math.min(r, g, b);
      const bgLike = isBackgroundLike(buf, i, clusters, whiteThreshold);
      const edge = localEdgeStrength(buf, x, y, width, height);
      if (!bgLike || (edge >= 46 && chroma >= 18)) {
        seed[i] = 1;
      }
    }
  }

  const keep = keepSubjectComponents(seed, width, height);
  const radius = Math.max(2, Math.round(Math.min(width, height) * 0.045));
  const protectedMask = dilateMask(keep, width, height, radius);
  fillProtectedHoles(protectedMask, solid, width, height);
  return protectedMask;
}

function keepSubjectComponents(
  seed: Uint8Array,
  width: number,
  height: number
): Uint8Array {
  const n = width * height;
  const visited = new Uint8Array(n);
  const keep = new Uint8Array(n);
  const minArea = Math.max(6, Math.round(n * 0.0025));
  const centerX = (width - 1) / 2;
  const centerY = (height - 1) / 2;
  const maxCenterDistance = Math.hypot(width, height) * 0.42;

  for (let start = 0; start < n; start++) {
    if (!seed[start] || visited[start]) continue;
    const queue = [start];
    const component: number[] = [];
    visited[start] = 1;
    let minX = width;
    let maxX = 0;
    let minY = height;
    let maxY = 0;

    for (let qi = 0; qi < queue.length; qi++) {
      const i = queue[qi]!;
      component.push(i);
      const x = i % width;
      const y = Math.floor(i / width);
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);

      const push = (xx: number, yy: number) => {
        if (xx < 0 || xx >= width || yy < 0 || yy >= height) return;
        const j = yy * width + xx;
        if (!seed[j] || visited[j]) return;
        visited[j] = 1;
        queue.push(j);
      };
      push(x + 1, y);
      push(x - 1, y);
      push(x, y + 1);
      push(x, y - 1);
    }

    const area = component.length;
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const nearCenter = Math.hypot(cx - centerX, cy - centerY) <= maxCenterDistance;
    const tallOrWide = maxX - minX >= width * 0.08 || maxY - minY >= height * 0.08;
    const shouldKeep = area >= minArea && (nearCenter || area >= n * 0.012 || tallOrWide);
    if (!shouldKeep) continue;

    for (const i of component) keep[i] = 1;
  }

  return keep;
}

function dilateMask(
  mask: Uint8Array,
  width: number,
  height: number,
  radius: number
): Uint8Array {
  const out = new Uint8Array(mask);
  const r2 = radius * radius;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = y * width + x;
      if (!mask[i]) continue;
      for (let dy = -radius; dy <= radius; dy++) {
        for (let dx = -radius; dx <= radius; dx++) {
          if (dx * dx + dy * dy > r2) continue;
          const xx = x + dx;
          const yy = y + dy;
          if (xx < 0 || xx >= width || yy < 0 || yy >= height) continue;
          out[yy * width + xx] = 1;
        }
      }
    }
  }
  return out;
}

function fillProtectedHoles(
  protectedMask: Uint8Array,
  solid: Uint8Array,
  width: number,
  height: number
): void {
  const n = width * height;
  const outside = new Uint8Array(n);
  const queue: number[] = [];
  const push = (x: number, y: number) => {
    if (x < 0 || x >= width || y < 0 || y >= height) return;
    const i = y * width + x;
    if (!solid[i] || protectedMask[i] || outside[i]) return;
    outside[i] = 1;
    queue.push(i);
  };

  for (let x = 0; x < width; x++) {
    push(x, 0);
    push(x, height - 1);
  }
  for (let y = 1; y < height - 1; y++) {
    push(0, y);
    push(width - 1, y);
  }

  for (let qi = 0; qi < queue.length; qi++) {
    const i = queue[qi]!;
    const x = i % width;
    const y = Math.floor(i / width);
    push(x + 1, y);
    push(x - 1, y);
    push(x, y + 1);
    push(x, y - 1);
  }

  for (let i = 0; i < n; i++) {
    if (solid[i] && !outside[i]) protectedMask[i] = 1;
  }
}

function removeBorderBackground(
  solid: Uint8Array,
  buf: Float32Array,
  width: number,
  height: number,
  whiteThreshold: number
): void {
  const bg = estimateBackground(solid, buf, width, height, whiteThreshold);
  if (!bg) return;

  const protectedMask = buildSubjectProtectionMask(
    solid,
    buf,
    width,
    height,
    whiteThreshold
  );
  const protectedCount = protectedMask.reduce((sum, v) => sum + v, 0);
  const solidCount = solid.reduce((sum, v) => sum + v, 0);
  const useSubjectBarrier =
    protectedCount >= Math.max(8, solidCount * 0.025) &&
    protectedCount <= solidCount * 0.82;

  const queue: number[] = [];
  const pushIfBackground = (x: number, y: number) => {
    if (x < 0 || x >= width || y < 0 || y >= height) return;
    const i = y * width + x;
    if (!solid[i]) return;
    if (useSubjectBarrier) {
      if (protectedMask[i]) return;
    } else if (!isBackgroundPixel(buf, i, bg, whiteThreshold)) {
      return;
    }
    solid[i] = 0;
    queue.push(i);
  };

  for (let x = 0; x < width; x++) {
    pushIfBackground(x, 0);
    pushIfBackground(x, height - 1);
  }
  for (let y = 1; y < height - 1; y++) {
    pushIfBackground(0, y);
    pushIfBackground(width - 1, y);
  }

  for (let qi = 0; qi < queue.length; qi++) {
    const i = queue[qi]!;
    const x = i % width;
    const y = Math.floor(i / width);
    pushIfBackground(x + 1, y);
    pushIfBackground(x - 1, y);
    pushIfBackground(x, y + 1);
    pushIfBackground(x, y - 1);
  }
}
