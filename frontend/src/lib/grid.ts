export interface RgbaGrid {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

export interface GridSource {
  image: CanvasImageSource;
  width: number;
  height: number;
}

type BackgroundSample = {
  r: number;
  g: number;
  b: number;
  tolerance: number;
  weight?: number;
};

const WHITE_THRESHOLD = 246;

/** Build a local grid, optionally removing its border-connected background. */
export function prepareLocalGrid(
  source: GridSource,
  width: number,
  height: number,
  removeBackground = true
): RgbaGrid {
  const grid = downsample(source, width, height);
  return removeBackground ? removeBackgroundFromGrid(grid) : grid;
}

/** Downscale in halving steps so small grids keep detail instead of aliasing. */
export function downsample(
  source: GridSource,
  width: number,
  height: number
): ImageData {
  let image: CanvasImageSource = source.image;
  let sourceWidth = source.width;
  let sourceHeight = source.height;
  while (sourceWidth / 2 >= width * 2 && sourceHeight / 2 >= height * 2) {
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(sourceWidth / 2);
    canvas.height = Math.round(sourceHeight / 2);
    const context = canvas.getContext("2d")!;
    context.imageSmoothingQuality = "high";
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    image = canvas;
    sourceWidth = canvas.width;
    sourceHeight = canvas.height;
  }

  const output = document.createElement("canvas");
  output.width = width;
  output.height = height;
  const context = output.getContext("2d", { willReadFrequently: true })!;
  context.imageSmoothingQuality = "high";
  context.drawImage(image, 0, 0, width, height);
  return context.getImageData(0, 0, width, height);
}

export function removeBackgroundFromGrid(grid: RgbaGrid): RgbaGrid {
  const { width, height } = grid;
  const cellCount = width * height;
  const solid = new Uint8Array(cellCount);
  const rgb = new Float32Array(cellCount * 3);
  for (let i = 0; i < cellCount; i++) {
    const pixel = i * 4;
    if (grid.data[pixel + 3]! < 128) continue;
    solid[i] = 1;
    rgb[i * 3] = grid.data[pixel]!;
    rgb[i * 3 + 1] = grid.data[pixel + 1]!;
    rgb[i * 3 + 2] = grid.data[pixel + 2]!;
  }

  removeBorderBackground(solid, rgb, width, height, WHITE_THRESHOLD);
  const data = new Uint8ClampedArray(grid.data);
  for (let i = 0; i < cellCount; i++) {
    if (!solid[i]) data[i * 4 + 3] = 0;
  }
  return { width, height, data };
}

function pixelAt(buffer: Float32Array, index: number): [number, number, number] {
  return [buffer[index * 3]!, buffer[index * 3 + 1]!, buffer[index * 3 + 2]!];
}

function colorDistance2(
  r1: number,
  g1: number,
  b1: number,
  r2: number,
  g2: number,
  b2: number
): number {
  const red = r1 - r2;
  const green = g1 - g2;
  const blue = b1 - b2;
  return red * red + green * green + blue * blue;
}

function isNearWhite(r: number, g: number, b: number, threshold: number): boolean {
  return Math.min(r, g, b) >= threshold && Math.max(r, g, b) - Math.min(r, g, b) <= 16;
}

function collectBorderSamples(
  solid: Uint8Array,
  buffer: Float32Array,
  width: number,
  height: number
): [number, number, number][] {
  const samples: [number, number, number][] = [];
  const add = (x: number, y: number) => {
    const index = y * width + x;
    if (solid[index]) samples.push(pixelAt(buffer, index));
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
  buffer: Float32Array,
  width: number,
  height: number,
  whiteThreshold: number
): BackgroundSample | null {
  const samples = collectBorderSamples(solid, buffer, width, height);
  if (!samples.length) return null;

  const nearWhite = samples.filter(([r, g, b]) => isNearWhite(r, g, b, whiteThreshold));
  const source =
    nearWhite.length >= Math.max(4, samples.length * 0.12)
      ? nearWhite
      : dominantColorCluster(samples);
  const sortedRed = source.map(([r]) => r).sort((a, b) => a - b);
  const sortedGreen = source.map(([, g]) => g).sort((a, b) => a - b);
  const sortedBlue = source.map(([, , b]) => b).sort((a, b) => a - b);
  const middle = Math.floor(source.length / 2);
  const r = sortedRed[middle]!;
  const g = sortedGreen[middle]!;
  const b = sortedBlue[middle]!;
  const distances = source
    .map(([sr, sg, sb]) => Math.sqrt(colorDistance2(sr, sg, sb, r, g, b)))
    .sort((a, b) => a - b);
  const percentile75 = distances[Math.floor(distances.length * 0.75)] ?? 0;
  const percentile90 = distances[Math.floor(distances.length * 0.9)] ?? percentile75;
  const baseTolerance = nearWhite.length ? 34 : 26;
  const tolerance = Math.max(
    baseTolerance,
    Math.min(72, percentile75 * 1.8 + percentile90 * 0.35 + 18)
  );
  return { r, g, b, tolerance };
}

function estimateBackgroundClusters(
  solid: Uint8Array,
  buffer: Float32Array,
  width: number,
  height: number,
  whiteThreshold: number
): BackgroundSample[] {
  const samples = collectBorderSamples(solid, buffer, width, height);
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

  const clusters: BackgroundSample[] = [...buckets.values()]
    .sort((a, b) => b.count - a.count)
    .slice(0, 6)
    .map((bucket) => {
      const r = bucket.r / bucket.count;
      const g = bucket.g / bucket.count;
      const b = bucket.b / bucket.count;
      return {
        r,
        g,
        b,
        tolerance: isNearWhite(r, g, b, whiteThreshold) ? 58 : 48,
        weight: bucket.count / samples.length,
      };
    });
  const white = estimateBackground(solid, buffer, width, height, whiteThreshold);
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

  let best: { count: number; r: number; g: number; b: number } | null = null;
  for (const bucket of buckets.values()) {
    if (!best || bucket.count > best.count) best = bucket;
  }
  if (!best) return samples;
  const centerRed = best.r / best.count;
  const centerGreen = best.g / best.count;
  const centerBlue = best.b / best.count;
  const cluster = samples.filter(
    ([r, g, b]) =>
      Math.sqrt(colorDistance2(r, g, b, centerRed, centerGreen, centerBlue)) <= 52
  );
  return cluster.length >= Math.max(3, samples.length * 0.08) ? cluster : samples;
}

function isBackgroundPixel(
  buffer: Float32Array,
  index: number,
  background: BackgroundSample,
  whiteThreshold: number
): boolean {
  const [r, g, b] = pixelAt(buffer, index);
  if (isNearWhite(r, g, b, whiteThreshold)) return true;
  const distance = Math.sqrt(
    colorDistance2(r, g, b, background.r, background.g, background.b)
  );
  if (distance <= background.tolerance) return true;

  const pixelChroma = Math.max(r, g, b) - Math.min(r, g, b);
  const backgroundChroma =
    Math.max(background.r, background.g, background.b) -
    Math.min(background.r, background.g, background.b);
  const pixelLuma = (r + g + b) / 3;
  const backgroundLuma = (background.r + background.g + background.b) / 3;
  return (
    backgroundChroma <= 24 &&
    pixelChroma <= 30 &&
    Math.abs(pixelLuma - backgroundLuma) <= background.tolerance * 0.9
  );
}

function isBackgroundLike(
  buffer: Float32Array,
  index: number,
  clusters: BackgroundSample[],
  whiteThreshold: number
): boolean {
  const [r, g, b] = pixelAt(buffer, index);
  if (isNearWhite(r, g, b, whiteThreshold)) return true;
  return clusters.some((background) =>
    isBackgroundPixel(buffer, index, background, whiteThreshold)
  );
}

function localEdgeStrength(
  buffer: Float32Array,
  x: number,
  y: number,
  width: number,
  height: number
): number {
  const [r, g, b] = pixelAt(buffer, y * width + x);
  let strongest = 0;
  const check = (otherX: number, otherY: number) => {
    if (otherX < 0 || otherX >= width || otherY < 0 || otherY >= height) return;
    const [nr, ng, nb] = pixelAt(buffer, otherY * width + otherX);
    strongest = Math.max(strongest, Math.sqrt(colorDistance2(r, g, b, nr, ng, nb)));
  };
  check(x - 1, y);
  check(x + 1, y);
  check(x, y - 1);
  check(x, y + 1);
  return strongest;
}

function buildSubjectProtectionMask(
  solid: Uint8Array,
  buffer: Float32Array,
  width: number,
  height: number,
  whiteThreshold: number
): Uint8Array {
  const cellCount = width * height;
  const clusters = estimateBackgroundClusters(solid, buffer, width, height, whiteThreshold);
  if (!clusters.length) return new Uint8Array(cellCount);

  const seed = new Uint8Array(cellCount);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const index = y * width + x;
      if (!solid[index]) continue;
      const [r, g, b] = pixelAt(buffer, index);
      const chroma = Math.max(r, g, b) - Math.min(r, g, b);
      const backgroundLike = isBackgroundLike(buffer, index, clusters, whiteThreshold);
      const edge = localEdgeStrength(buffer, x, y, width, height);
      if (!backgroundLike || (edge >= 46 && chroma >= 18)) seed[index] = 1;
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
  const cellCount = width * height;
  const visited = new Uint8Array(cellCount);
  const keep = new Uint8Array(cellCount);
  const minimumArea = Math.max(6, Math.round(cellCount * 0.0025));
  const centerX = (width - 1) / 2;
  const centerY = (height - 1) / 2;
  const maximumCenterDistance = Math.hypot(width, height) * 0.42;

  for (let start = 0; start < cellCount; start++) {
    if (!seed[start] || visited[start]) continue;
    const queue = [start];
    const component: number[] = [];
    visited[start] = 1;
    let minimumX = width;
    let maximumX = 0;
    let minimumY = height;
    let maximumY = 0;
    for (let queueIndex = 0; queueIndex < queue.length; queueIndex++) {
      const index = queue[queueIndex]!;
      component.push(index);
      const x = index % width;
      const y = Math.floor(index / width);
      minimumX = Math.min(minimumX, x);
      maximumX = Math.max(maximumX, x);
      minimumY = Math.min(minimumY, y);
      maximumY = Math.max(maximumY, y);
      const push = (otherX: number, otherY: number) => {
        if (otherX < 0 || otherX >= width || otherY < 0 || otherY >= height) return;
        const otherIndex = otherY * width + otherX;
        if (!seed[otherIndex] || visited[otherIndex]) return;
        visited[otherIndex] = 1;
        queue.push(otherIndex);
      };
      push(x + 1, y);
      push(x - 1, y);
      push(x, y + 1);
      push(x, y - 1);
    }

    const area = component.length;
    const componentX = (minimumX + maximumX) / 2;
    const componentY = (minimumY + maximumY) / 2;
    const nearCenter =
      Math.hypot(componentX - centerX, componentY - centerY) <= maximumCenterDistance;
    const tallOrWide =
      maximumX - minimumX >= width * 0.08 || maximumY - minimumY >= height * 0.08;
    const shouldKeep =
      area >= minimumArea && (nearCenter || area >= cellCount * 0.012 || tallOrWide);
    if (shouldKeep) {
      for (const index of component) keep[index] = 1;
    }
  }
  return keep;
}

function dilateMask(
  mask: Uint8Array,
  width: number,
  height: number,
  radius: number
): Uint8Array {
  const output = new Uint8Array(mask);
  const squaredRadius = radius * radius;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      if (!mask[y * width + x]) continue;
      for (let deltaY = -radius; deltaY <= radius; deltaY++) {
        for (let deltaX = -radius; deltaX <= radius; deltaX++) {
          if (deltaX * deltaX + deltaY * deltaY > squaredRadius) continue;
          const otherX = x + deltaX;
          const otherY = y + deltaY;
          if (otherX < 0 || otherX >= width || otherY < 0 || otherY >= height) continue;
          output[otherY * width + otherX] = 1;
        }
      }
    }
  }
  return output;
}

function fillProtectedHoles(
  protectedMask: Uint8Array,
  solid: Uint8Array,
  width: number,
  height: number
): void {
  const outside = new Uint8Array(width * height);
  const queue: number[] = [];
  const push = (x: number, y: number) => {
    if (x < 0 || x >= width || y < 0 || y >= height) return;
    const index = y * width + x;
    if (!solid[index] || protectedMask[index] || outside[index]) return;
    outside[index] = 1;
    queue.push(index);
  };
  for (let x = 0; x < width; x++) {
    push(x, 0);
    push(x, height - 1);
  }
  for (let y = 1; y < height - 1; y++) {
    push(0, y);
    push(width - 1, y);
  }
  for (let queueIndex = 0; queueIndex < queue.length; queueIndex++) {
    const index = queue[queueIndex]!;
    const x = index % width;
    const y = Math.floor(index / width);
    push(x + 1, y);
    push(x - 1, y);
    push(x, y + 1);
    push(x, y - 1);
  }
  for (let index = 0; index < solid.length; index++) {
    if (solid[index] && !outside[index]) protectedMask[index] = 1;
  }
}

function removeBorderBackground(
  solid: Uint8Array,
  buffer: Float32Array,
  width: number,
  height: number,
  whiteThreshold: number
): void {
  const background = estimateBackground(solid, buffer, width, height, whiteThreshold);
  if (!background) return;
  const protectedMask = buildSubjectProtectionMask(
    solid,
    buffer,
    width,
    height,
    whiteThreshold
  );
  const protectedCount = protectedMask.reduce((sum, value) => sum + value, 0);
  const solidCount = solid.reduce((sum, value) => sum + value, 0);
  const useSubjectBarrier =
    protectedCount >= Math.max(8, solidCount * 0.025) && protectedCount <= solidCount * 0.82;
  const queue: number[] = [];
  const pushIfBackground = (x: number, y: number) => {
    if (x < 0 || x >= width || y < 0 || y >= height) return;
    const index = y * width + x;
    if (!solid[index]) return;
    if (useSubjectBarrier) {
      if (protectedMask[index]) return;
    } else if (!isBackgroundPixel(buffer, index, background, whiteThreshold)) {
      return;
    }
    solid[index] = 0;
    queue.push(index);
  };
  for (let x = 0; x < width; x++) {
    pushIfBackground(x, 0);
    pushIfBackground(x, height - 1);
  }
  for (let y = 1; y < height - 1; y++) {
    pushIfBackground(0, y);
    pushIfBackground(width - 1, y);
  }
  for (let queueIndex = 0; queueIndex < queue.length; queueIndex++) {
    const index = queue[queueIndex]!;
    const x = index % width;
    const y = Math.floor(index / width);
    pushIfBackground(x + 1, y);
    pushIfBackground(x - 1, y);
    pushIfBackground(x, y + 1);
    pushIfBackground(x, y - 1);
  }
}
