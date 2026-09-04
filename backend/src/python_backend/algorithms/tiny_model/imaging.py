from __future__ import annotations

import cv2
import numpy as np

from python_backend.algorithms.errors import AlgorithmProcessingError


def decode_image(data: bytes, max_decoded_pixels: int) -> tuple[np.ndarray, np.ndarray | None]:
    encoded = np.frombuffer(data, dtype=np.uint8)
    decoded = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
    if decoded is None or decoded.size == 0:
        raise AlgorithmProcessingError("image could not be decoded")
    height, width = decoded.shape[:2]
    if height * width > max_decoded_pixels:
        raise AlgorithmProcessingError("decoded image is too large")

    alpha = None
    if decoded.ndim == 3 and decoded.shape[2] == 4:
        image = decoded[:, :, :3]
        alpha = decoded[:, :, 3]
    else:
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise AlgorithmProcessingError("image channels are unsupported")
    return image, alpha


def working_image(image: np.ndarray, maximum_edge: int) -> np.ndarray:
    height, width = image.shape[:2]
    scale = min(1.0, maximum_edge / max(height, width))
    if scale == 1.0:
        return image.copy()
    target = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(image, target, interpolation=cv2.INTER_AREA)
