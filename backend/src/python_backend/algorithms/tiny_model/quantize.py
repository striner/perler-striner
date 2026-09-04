from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

_MAX_COLOR_SAMPLES = 60_000
_MAX_EDGE_SAMPLES = 20_000
_KMEANS_ITERATIONS = 16


@dataclass(frozen=True, slots=True)
class QuantizedForeground:
    image: np.ndarray
    palette_rgb: np.ndarray


def quantize_foreground(
    image: np.ndarray,
    mask: np.ndarray,
    edge_band: np.ndarray,
    max_colors: int,
) -> QuantizedForeground:
    foreground = mask > 0
    if not np.any(foreground):
        return QuantizedForeground(image.copy(), np.empty((0, 3), dtype=np.uint8))

    foreground_bgr = image[foreground]
    unique_bgr = np.unique(foreground_bgr, axis=0)
    if len(unique_bgr) <= max_colors:
        return QuantizedForeground(image.copy(), unique_bgr[:, ::-1].copy())

    lab_image = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    flat_indices = np.flatnonzero(foreground)
    sampled_indices = _even_sample(flat_indices, _MAX_COLOR_SAMPLES)
    edge_indices = np.flatnonzero(foreground & (edge_band > 0))
    if len(edge_indices):
        sampled_indices = np.concatenate(
            [sampled_indices, _even_sample(edge_indices, _MAX_EDGE_SAMPLES)]
        )

    sampled_lab = lab_image.reshape(-1, 3)[sampled_indices]
    flat_edge = (edge_band > 0).reshape(-1)
    weights = np.where(flat_edge[sampled_indices], 3.0, 1.0).astype(np.float32)
    centers_lab = _weighted_kmeans(sampled_lab, weights, max_colors)
    palette_bgr = cv2.cvtColor(
        np.clip(np.rint(centers_lab), 0, 255).astype(np.uint8).reshape(1, -1, 3),
        cv2.COLOR_LAB2BGR,
    ).reshape(-1, 3)
    palette_bgr = np.unique(palette_bgr, axis=0)

    palette_lab = (
        cv2.cvtColor(palette_bgr.reshape(1, -1, 3), cv2.COLOR_BGR2LAB)
        .reshape(-1, 3)
        .astype(np.float32)
    )
    quantized = image.copy()
    foreground_lab = lab_image[foreground]
    labels = _nearest_centers(foreground_lab, palette_lab)
    quantized[foreground] = palette_bgr[labels]
    return QuantizedForeground(quantized, palette_bgr[:, ::-1].copy())


def snap_rgba_to_palette(
    rgba: bytes,
    width: int,
    height: int,
    palette_rgb: np.ndarray,
) -> bytes:
    output = np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4).copy()
    foreground = output[:, :, 3] >= 128
    if not np.any(foreground) or not len(palette_rgb):
        return output.tobytes()

    colors_rgb = output[:, :, :3][foreground]
    colors_lab = (
        cv2.cvtColor(colors_rgb.reshape(1, -1, 3), cv2.COLOR_RGB2LAB)
        .reshape(-1, 3)
        .astype(np.float32)
    )
    palette_lab = (
        cv2.cvtColor(palette_rgb.reshape(1, -1, 3), cv2.COLOR_RGB2LAB)
        .reshape(-1, 3)
        .astype(np.float32)
    )
    labels = _nearest_centers(colors_lab, palette_lab)
    output[:, :, :3][foreground] = palette_rgb[labels]
    return output.tobytes()


def _even_sample(indices: np.ndarray, limit: int) -> np.ndarray:
    if len(indices) <= limit:
        return indices
    positions = np.linspace(0, len(indices) - 1, num=limit, dtype=np.int64)
    return indices[positions]


def _weighted_kmeans(
    samples: np.ndarray,
    weights: np.ndarray,
    requested_centers: int,
) -> np.ndarray:
    center_count = min(requested_centers, len(samples))
    weighted_mean = np.average(samples, axis=0, weights=weights)
    first = int(np.argmin(np.sum((samples - weighted_mean) ** 2, axis=1)))
    centers = [samples[first].copy()]
    minimum_distance = np.sum((samples - centers[0]) ** 2, axis=1)

    for _ in range(1, center_count):
        score = minimum_distance * np.sqrt(weights)
        next_index = int(np.argmax(score))
        if score[next_index] <= 1e-6:
            break
        centers.append(samples[next_index].copy())
        distance = np.sum((samples - centers[-1]) ** 2, axis=1)
        minimum_distance = np.minimum(minimum_distance, distance)

    result = np.asarray(centers, dtype=np.float32)
    for _ in range(_KMEANS_ITERATIONS):
        labels = _nearest_centers(samples, result)
        updated = result.copy()
        for index in range(len(result)):
            selected = labels == index
            if np.any(selected):
                updated[index] = np.average(
                    samples[selected],
                    axis=0,
                    weights=weights[selected],
                )
        movement = float(np.max(np.linalg.norm(updated - result, axis=1)))
        result = updated
        if movement < 0.25:
            break
    return result


def _nearest_centers(samples: np.ndarray, centers: np.ndarray) -> np.ndarray:
    labels = np.empty(len(samples), dtype=np.int32)
    for start in range(0, len(samples), 65_536):
        chunk = samples[start : start + 65_536]
        distances = np.sum((chunk[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        labels[start : start + len(chunk)] = np.argmin(distances, axis=1)
    return labels
