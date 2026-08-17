from __future__ import annotations

import cv2
import numpy as np

from python_backend.algorithms.errors import AlgorithmProcessingError


def normalize_subject_frame(
    image: np.ndarray,
    mask: np.ndarray,
    target_width: int,
    target_height: int,
) -> tuple[np.ndarray, np.ndarray]:
    foreground = mask > 0
    points = cv2.findNonZero(foreground.astype(np.uint8))
    if points is None:
        raise AlgorithmProcessingError("segmentation mask is empty")
    x, y, width, height = cv2.boundingRect(points)
    source_height, source_width = mask.shape
    if x == 0 and y == 0 and width == source_width and height == source_height:
        return image, mask

    cropped_image = image[y : y + height, x : x + width]
    cropped_mask = mask[y : y + height, x : x + width]
    target_aspect = target_width / target_height
    maximum_edge = max(source_width, source_height)
    if target_aspect >= 1:
        canvas_width = maximum_edge
        canvas_height = max(1, round(maximum_edge / target_aspect))
    else:
        canvas_height = maximum_edge
        canvas_width = max(1, round(maximum_edge * target_aspect))

    scale = min(canvas_width / width, canvas_height / height)
    resized_width = max(1, min(canvas_width, round(width * scale)))
    resized_height = max(1, min(canvas_height, round(height * scale)))
    interpolation = cv2.INTER_LANCZOS4 if scale > 1 else cv2.INTER_AREA
    resized_image = cv2.resize(
        cropped_image,
        (resized_width, resized_height),
        interpolation=interpolation,
    )
    resized_mask = cv2.resize(
        cropped_mask,
        (resized_width, resized_height),
        interpolation=cv2.INTER_NEAREST,
    )

    canvas_image = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
    canvas_mask = np.zeros((canvas_height, canvas_width), dtype=np.uint8)
    offset_x = (canvas_width - resized_width) // 2
    offset_y = (canvas_height - resized_height) // 2
    canvas_image[
        offset_y : offset_y + resized_height,
        offset_x : offset_x + resized_width,
    ] = resized_image
    canvas_mask[
        offset_y : offset_y + resized_height,
        offset_x : offset_x + resized_width,
    ] = resized_mask
    return canvas_image, canvas_mask
