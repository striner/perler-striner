from __future__ import annotations

import cv2
import numpy as np

from python_backend.algorithms.contracts import AlgorithmIdentity, AlgorithmInput, AlgorithmOutput
from python_backend.algorithms.errors import AlgorithmProcessingError

from .descriptor import DESCRIPTOR
from .edges import enhance_foreground_edges
from .params import CvNativeParams
from .pixelize import pixelize
from .segmentation import segment_foreground


def run_pipeline(
    request: AlgorithmInput,
    params: CvNativeParams,
    max_decoded_pixels: int,
    work_max_edge: int,
) -> AlgorithmOutput:
    image, source_alpha = _decode(request.image.data, max_decoded_pixels)
    working_image = _working_image(image, work_max_edge)
    working_alpha = None
    if source_alpha is not None and np.any(source_alpha < 250):
        working_alpha = cv2.resize(
            source_alpha,
            (working_image.shape[1], working_image.shape[0]),
            interpolation=cv2.INTER_AREA,
        )

    denoised = cv2.GaussianBlur(working_image, (3, 3), 0.65)
    segmentation = segment_foreground(
        denoised,
        working_alpha,
        request.target.width,
        request.target.height,
        params,
    )
    edge_result = enhance_foreground_edges(
        working_image,
        segmentation.mask,
        params.edge_strength,
        params.outline_strength,
    )
    rgba = pixelize(
        edge_result.image,
        segmentation.mask,
        edge_result.edge_band,
        request.target.width,
        request.target.height,
        params.foreground_coverage_threshold,
    )
    if len(rgba) != request.target.width * request.target.height * 4:
        raise AlgorithmProcessingError("target grid could not be generated")
    return AlgorithmOutput(
        schema_version=request.schema_version,
        algorithm=AlgorithmIdentity(DESCRIPTOR.algorithm_id, DESCRIPTOR.version),
        width=request.target.width,
        height=request.target.height,
        rgba=rgba,
    )


def _decode(data: bytes, max_decoded_pixels: int) -> tuple[np.ndarray, np.ndarray | None]:
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
        # IMREAD_COLOR applies supported EXIF orientation, unlike IMREAD_UNCHANGED.
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise AlgorithmProcessingError("image channels are unsupported")
    return image, alpha


def _working_image(image: np.ndarray, maximum_edge: int) -> np.ndarray:
    height, width = image.shape[:2]
    scale = min(1.0, maximum_edge / max(height, width))
    if scale == 1.0:
        return image.copy()
    target = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(image, target, interpolation=cv2.INTER_AREA)
