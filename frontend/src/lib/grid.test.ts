import { describe, expect, it } from "vitest";

import { removeBackgroundFromGrid, type RgbaGrid } from "./grid";

function subjectOnWhite(): RgbaGrid {
  const width = 15;
  const height = 15;
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const pixel = (y * width + x) * 4;
      const subject = x >= 5 && x <= 9 && y >= 5 && y <= 9;
      data[pixel] = subject ? 200 : 255;
      data[pixel + 1] = subject ? 30 : 255;
      data[pixel + 2] = subject ? 40 : 255;
      data[pixel + 3] = 255;
    }
  }
  return { width, height, data };
}

describe("removeBackgroundFromGrid", () => {
  it("always clears border-connected background and preserves the subject", () => {
    const result = removeBackgroundFromGrid(subjectOnWhite());
    expect(result.data[3]).toBe(0);
    const centerAlpha = result.data[((7 * result.width + 7) * 4) + 3];
    expect(centerAlpha).toBe(255);
  });

  it("keeps source transparency empty", () => {
    const result = removeBackgroundFromGrid({
      width: 1,
      height: 1,
      data: new Uint8ClampedArray([100, 100, 100, 0]),
    });
    expect([...result.data]).toEqual([100, 100, 100, 0]);
  });
});
