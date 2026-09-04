from __future__ import annotations

import cv2
import numpy as np

from python_backend.algorithms.contracts import AlgorithmIdentity, AlgorithmInput, AlgorithmOutput
from python_backend.algorithms.cv_native.edges import enhance_foreground_edges
from python_backend.algorithms.cv_native.pixelize import pixelize
from python_backend.algorithms.cv_native.segmentation import repair_mask
from python_backend.algorithms.errors import AlgorithmProcessingError

from .analysis_token import TokenObject
from .framing import normalize_subject_frame
from .imaging import decode_image, working_image
from .params import TinyModelParams
from .quantize import quantize_foreground, snap_rgba_to_palette
from .types import Detection, InferenceRuntime, MaskCandidate


def run_pipeline(
    request: AlgorithmInput,
    params: TinyModelParams,
    runtime: InferenceRuntime,
    selected_objects: list[TokenObject],
    max_decoded_pixels: int,
    work_max_edge: int,
) -> AlgorithmOutput:
    image, source_alpha = decode_image(request.image.data, max_decoded_pixels)
    working = working_image(image, work_max_edge)
    working_alpha = None
    if source_alpha is not None and np.any(source_alpha < 250):
        working_alpha = cv2.resize(
            source_alpha,
            (working.shape[1], working.shape[0]),
            interpolation=cv2.INTER_AREA,
        )

    height, width = working.shape[:2]
    detections = [
        Detection(
            box=(
                item.box[0] * width,
                item.box[1] * height,
                item.box[2] * width,
                item.box[3] * height,
            ),
            score=item.score,
            type_id=item.type_id,
            type_name_en=item.type_name_en,
            salience=item.salience,
        )
        for item in selected_objects
    ]
    candidates = runtime.segment_boxes(working, detections)
    prepared = _prepare_masks(
        candidates,
        working.shape[:2],
        request.target.width,
        request.target.height,
        max_instances=len(detections),
    )
    if not prepared:
        raise AlgorithmProcessingError("segmentation did not return a reliable subject")
    mask = np.maximum.reduce(prepared)
    if working_alpha is not None:
        mask[working_alpha < 16] = 0
    if not np.any(mask):
        raise AlgorithmProcessingError("segmentation mask is empty")

    framed_image, framed_mask = normalize_subject_frame(
        working,
        mask,
        request.target.width,
        request.target.height,
    )
    stylized = runtime.stylize(framed_image, framed_mask)
    if stylized.shape != framed_image.shape or stylized.dtype != np.uint8:
        raise AlgorithmProcessingError("cartoonizer returned an invalid image")
    edge_result = enhance_foreground_edges(
        stylized,
        framed_mask,
        params.edge_strength,
        params.outline_strength,
    )
    quantized = quantize_foreground(
        edge_result.image,
        framed_mask,
        edge_result.edge_band,
        params.max_colors,
    )
    rgba = pixelize(
        quantized.image,
        framed_mask,
        edge_result.edge_band,
        request.target.width,
        request.target.height,
        params.foreground_coverage_threshold,
    )
    rgba = snap_rgba_to_palette(
        rgba,
        request.target.width,
        request.target.height,
        quantized.palette_rgb,
    )
    if len(rgba) != request.target.width * request.target.height * 4:
        raise AlgorithmProcessingError("target grid could not be generated")
    return AlgorithmOutput(
        schema_version=request.schema_version,
        algorithm=AlgorithmIdentity("tiny_model", "1.0.0"),
        width=request.target.width,
        height=request.target.height,
        rgba=rgba,
    )


def _prepare_masks(
    candidates: list[MaskCandidate],
    shape: tuple[int, int],
    target_width: int,
    target_height: int,
    max_instances: int,
) -> list[np.ndarray]:
    prepared: list[np.ndarray] = []
    ordered = sorted(candidates, key=lambda candidate: candidate.quality, reverse=True)
    for candidate in ordered:
        mask = _clean_mask(candidate.mask, shape, target_width, target_height)
        if not np.any(mask):
            continue
        prepared.append(mask)
        if len(prepared) >= max_instances:
            break
    return prepared


def _clean_mask(
    raw_mask: np.ndarray,
    shape: tuple[int, int],
    target_width: int,
    target_height: int,
) -> np.ndarray:
    mask = np.asarray(raw_mask)
    if mask.ndim != 2:
        return np.zeros(shape, dtype=np.uint8)
    mask = np.where(mask > 0.5, 255, 0).astype(np.uint8)
    if mask.shape != shape:
        mask = cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if component_count <= 1:
        return np.zeros(shape, dtype=np.uint8)
    foreground_area = int(np.count_nonzero(mask))
    minimum_area = max(8, round(foreground_area * 0.002))
    cleaned = np.zeros_like(mask)
    for label in range(1, component_count):
        if stats[label, cv2.CC_STAT_AREA] >= minimum_area:
            cleaned[labels == label] = 255
    return repair_mask(cleaned, target_width, target_height)
