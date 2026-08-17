from __future__ import annotations

import cv2
import numpy as np

from python_backend.algorithms.contracts import AlgorithmIdentity, AlgorithmInput, AlgorithmOutput
from python_backend.algorithms.cv_native.edges import enhance_foreground_edges
from python_backend.algorithms.cv_native.pixelize import pixelize
from python_backend.algorithms.cv_native.segmentation import repair_mask
from python_backend.algorithms.errors import AlgorithmProcessingError

from .framing import normalize_subject_frame
from .params import TinyModelParams
from .types import InferenceRuntime, MaskCandidate


def run_pipeline(
    request: AlgorithmInput,
    params: TinyModelParams,
    runtime: InferenceRuntime,
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

    if params.prompts:
        detections = runtime.detect(
            working_image,
            params.prompts,
            params.confidence_threshold,
            params.max_instances,
        )
        if not detections:
            raise AlgorithmProcessingError("prompt did not detect a reliable subject")
        candidates = runtime.segment_boxes(working_image, detections)
    else:
        automatic = runtime.automatic_masks(working_image)
        selected = _select_salient_candidate(automatic, working_image.shape[:2])
        candidates = [selected] if selected is not None else []

    prepared = _prepare_masks(
        candidates,
        working_image.shape[:2],
        request.target.width,
        request.target.height,
        params.mask_iou_threshold,
        params.max_instances,
    )
    if not prepared:
        raise AlgorithmProcessingError("segmentation did not return a reliable subject")
    mask = np.maximum.reduce(prepared)
    if working_alpha is not None:
        mask[working_alpha < 16] = 0
    if not np.any(mask):
        raise AlgorithmProcessingError("segmentation mask is empty")

    framed_image, framed_mask = normalize_subject_frame(
        working_image,
        mask,
        request.target.width,
        request.target.height,
    )
    edge_result = enhance_foreground_edges(
        framed_image,
        framed_mask,
        params.edge_strength,
        params.outline_strength,
    )
    rgba = pixelize(
        edge_result.image,
        framed_mask,
        edge_result.edge_band,
        request.target.width,
        request.target.height,
        params.foreground_coverage_threshold,
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
    iou_threshold: float,
    max_instances: int,
) -> list[np.ndarray]:
    prepared: list[np.ndarray] = []
    ordered = sorted(candidates, key=lambda candidate: candidate.quality, reverse=True)
    for candidate in ordered:
        mask = _clean_mask(candidate.mask, shape, target_width, target_height)
        if not np.any(mask):
            continue
        if any(_mask_iou(mask, retained) >= iou_threshold for retained in prepared):
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


def _select_salient_candidate(
    candidates: list[MaskCandidate],
    shape: tuple[int, int],
) -> MaskCandidate | None:
    height, width = shape
    image_area = height * width
    center_x = width / 2
    center_y = height / 2
    diagonal = max(1.0, float(np.hypot(center_x, center_y)))
    ranked: list[tuple[float, MaskCandidate]] = []
    for candidate in candidates:
        mask = np.asarray(candidate.mask) > 0.5
        if mask.shape != shape:
            mask = cv2.resize(
                mask.astype(np.uint8),
                (width, height),
                interpolation=cv2.INTER_NEAREST,
            ).astype(bool)
        area = int(np.count_nonzero(mask))
        area_ratio = area / image_area
        if area_ratio < 0.005 or area_ratio > 0.85:
            continue
        points = cv2.findNonZero(mask.astype(np.uint8))
        if points is None:
            continue
        x, y, box_width, box_height = cv2.boundingRect(points)
        candidate_x = x + box_width / 2
        candidate_y = y + box_height / 2
        center_score = max(
            0.0,
            1.0 - np.hypot(candidate_x - center_x, candidate_y - center_y) / diagonal,
        )
        boundary_contacts = sum(
            (x <= 1, y <= 1, x + box_width >= width - 1, y + box_height >= height - 1)
        )
        if boundary_contacts >= 3 and area_ratio >= 0.15:
            continue
        boundary_penalty = boundary_contacts / 4
        area_score = min(1.0, np.sqrt(area_ratio / 0.35))
        quality = min(1.0, max(0.0, candidate.quality))
        score = quality * 0.45 + center_score * 0.35 + area_score * 0.3 - boundary_penalty * 0.15
        ranked.append((float(score), MaskCandidate(mask=mask, quality=candidate.quality)))
    if not ranked:
        return None
    return max(ranked, key=lambda item: item[0])[1]


def _mask_iou(first: np.ndarray, second: np.ndarray) -> float:
    first_foreground = first > 0
    second_foreground = second > 0
    union = np.count_nonzero(first_foreground | second_foreground)
    if union == 0:
        return 0.0
    intersection = np.count_nonzero(first_foreground & second_foreground)
    return float(intersection / union)


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
