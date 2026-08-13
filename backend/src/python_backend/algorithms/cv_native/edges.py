from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class EdgeResult:
    image: np.ndarray
    edge_band: np.ndarray


def enhance_foreground_edges(
    image: np.ndarray,
    mask: np.ndarray,
    edge_strength: float,
    outline_strength: float,
) -> EdgeResult:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    median = float(np.median(gray[mask > 0]))
    low = max(12, round(0.66 * median))
    high = max(low + 12, min(255, round(1.33 * median)))
    edges = cv2.Canny(gray, low, high, L2gradient=True)

    mask_radius = max(1, round(min(mask.shape) * 0.004))
    kernel_size = mask_radius * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    foreground_neighborhood = cv2.dilate(mask, kernel)
    edges = cv2.bitwise_and(edges, foreground_neighborhood)
    edge_band = cv2.dilate(edges, kernel)
    edge_band = cv2.bitwise_and(edge_band, mask)

    blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=1.0, sigmaY=1.0)
    sharpened = cv2.addWeighted(image, 1.0 + edge_strength, blurred, -edge_strength, 0)
    alpha = (edge_band.astype(np.float32) / 255.0 * min(1.0, edge_strength))[:, :, None]
    enhanced = np.clip(
        image.astype(np.float32) * (1.0 - alpha) + sharpened.astype(np.float32) * alpha,
        0,
        255,
    )

    if outline_strength > 0:
        local_dark = cv2.erode(image, np.ones((3, 3), np.uint8)).astype(np.float32)
        outline_alpha = (edges.astype(np.float32) / 255.0 * outline_strength)[:, :, None]
        enhanced = enhanced * (1.0 - outline_alpha) + local_dark * outline_alpha

    output = image.copy()
    writable = mask > 0
    output[writable] = enhanced.astype(np.uint8)[writable]
    return EdgeResult(image=output, edge_band=edge_band)
