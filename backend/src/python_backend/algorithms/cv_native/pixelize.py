from __future__ import annotations

import numpy as np


def pixelize(
    image: np.ndarray,
    mask: np.ndarray,
    edge_band: np.ndarray,
    width: int,
    height: int,
    foreground_coverage_threshold: float,
) -> bytes:
    source_height, source_width = mask.shape
    output = np.zeros((height, width, 4), dtype=np.uint8)
    for target_y in range(height):
        y0 = (target_y * source_height) // height
        y1 = max(y0 + 1, ((target_y + 1) * source_height) // height)
        for target_x in range(width):
            x0 = (target_x * source_width) // width
            x1 = max(x0 + 1, ((target_x + 1) * source_width) // width)
            region_mask = mask[y0:y1, x0:x1]
            foreground = region_mask > 0
            coverage = float(np.mean(foreground))
            if coverage < foreground_coverage_threshold:
                continue

            colors = image[y0:y1, x0:x1][foreground]
            edge = edge_band[y0:y1, x0:x1][foreground] > 0
            weights = np.where(edge, 2.0, 1.0).astype(np.float32)
            bgr = np.average(colors.astype(np.float32), axis=0, weights=weights)
            output[target_y, target_x, :3] = np.clip(bgr[::-1], 0, 255).astype(np.uint8)
            output[target_y, target_x, 3] = 255
    return output.tobytes()
