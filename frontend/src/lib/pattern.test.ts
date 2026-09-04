import { describe, expect, it } from "vitest";

import type { RgbaGrid } from "./grid";
import { generatePattern } from "./pattern";

function colorfulGrid(): RgbaGrid {
  const width = 24;
  const height = 18;
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const offset = (y * width + x) * 4;
      data[offset] = (x * 37 + y * 13) % 256;
      data[offset + 1] = (x * 11 + y * 41) % 256;
      data[offset + 2] = (x * 29 + y * 17) % 256;
      data[offset + 3] = x === 0 && y === 0 ? 0 : 255;
    }
  }
  return { width, height, data };
}

describe("generatePattern color budget", () => {
  it("restricts direct matching to the selected brand sub-palette", () => {
    const pattern = generatePattern(colorfulGrid(), {
      brand: "mard221",
      dither: false,
      maxColors: 6,
    });
    expect(pattern.used.length).toBeLessThanOrEqual(6);
    expect(pattern.totalBeads).toBe(24 * 18 - 1);
  });

  it("keeps dithering inside the selected brand sub-palette", () => {
    const pattern = generatePattern(colorfulGrid(), {
      brand: "mard221",
      dither: true,
      maxColors: 4,
    });
    expect(pattern.used.length).toBeLessThanOrEqual(4);
  });

  it("preserves unrestricted behavior when no budget is provided", () => {
    const pattern = generatePattern(colorfulGrid(), {
      brand: "mard221",
      dither: false,
    });
    expect(pattern.used.length).toBeGreaterThan(6);
  });
});
