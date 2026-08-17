from __future__ import annotations

import threading
from dataclasses import dataclass

import cv2
import numpy as np

from python_backend.algorithms.errors import AlgorithmProcessingError

from .params import CvNativeParams

_KMEANS_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class SegmentationResult:
    mask: np.ndarray
    confidence: float


@dataclass(frozen=True, slots=True)
class _ColorPrior:
    trimap: np.ndarray
    foreground_core: np.ndarray
    background_distance: np.ndarray
    border_cleanup_threshold: float
    protect_core_during_cleanup: bool


def segment_foreground(
    image: np.ndarray,
    source_alpha: np.ndarray | None,
    target_width: int,
    target_height: int,
    params: CvNativeParams,
) -> SegmentationResult:
    height, width = image.shape[:2]
    if min(height, width) < 3:
        raise AlgorithmProcessingError("image is too small for foreground extraction")

    color_prior = None if source_alpha is not None else _color_prior(image)
    trimap = _alpha_trimap(source_alpha) if source_alpha is not None else color_prior.trimap
    foreground_samples = np.count_nonzero(
        (trimap == cv2.GC_FGD) | (trimap == cv2.GC_PR_FGD)
    )
    background_samples = np.count_nonzero(
        (trimap == cv2.GC_BGD) | (trimap == cv2.GC_PR_BGD)
    )
    if foreground_samples < 4 or background_samples < 4:
        raise AlgorithmProcessingError("foreground and background samples are insufficient")

    background_model = np.zeros((1, 65), np.float64)
    foreground_model = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(
            image,
            trimap,
            None,
            background_model,
            foreground_model,
            4,
            cv2.GC_INIT_WITH_MASK,
        )
    except cv2.error as error:
        raise AlgorithmProcessingError("foreground extraction failed") from error

    mask = np.where(
        (trimap == cv2.GC_FGD) | (trimap == cv2.GC_PR_FGD), 255, 0
    ).astype(np.uint8)
    mask = repair_mask(mask, target_width, target_height)
    foreground_evidence = None
    if color_prior is not None:
        portrait = _refine_centered_portrait(
            image,
            mask,
            color_prior.background_distance,
            target_width,
            target_height,
        )
        if portrait is not None:
            mask, foreground_evidence = portrait
        else:
            dark_subject = _build_dark_subject_candidate(
                image,
                target_width,
                target_height,
            )
            protection = _build_multiscale_protection(
                image,
                color_prior.background_distance,
                target_width,
                target_height,
                params,
            )
            mask = _retain_supported_components(
                image,
                mask,
                color_prior.foreground_core,
                color_prior.background_distance,
                target_width,
                target_height,
                params.foreground_coverage_threshold,
            )
            mask = _remove_border_background_residue(
                mask,
                color_prior.background_distance,
                color_prior.border_cleanup_threshold,
                color_prior.foreground_core,
                color_prior.protect_core_during_cleanup,
            )
            mask = _restore_multiscale_subject(
                mask,
                protection,
                color_prior.background_distance,
                params,
            )
            mask = _fuse_dark_subject_candidate(
                mask,
                dark_subject,
                target_width,
                target_height,
            )
            if np.any(dark_subject):
                foreground_evidence = dark_subject
    coverage = float(np.count_nonzero(mask)) / mask.size
    if coverage < 0.002 or coverage > 0.985:
        raise AlgorithmProcessingError("foreground mask confidence is too low")
    confidence = _mask_confidence(mask, trimap, foreground_evidence)
    if confidence < 0.08:
        raise AlgorithmProcessingError("foreground mask confidence is too low")
    return SegmentationResult(mask=mask, confidence=confidence)


def _alpha_trimap(alpha: np.ndarray) -> np.ndarray:
    trimap = np.full(alpha.shape, cv2.GC_PR_FGD, dtype=np.uint8)
    trimap[alpha <= 8] = cv2.GC_BGD
    trimap[(alpha > 8) & (alpha < 224)] = cv2.GC_PR_BGD
    eroded = cv2.erode((alpha >= 250).astype(np.uint8), np.ones((3, 3), np.uint8))
    trimap[eroded > 0] = cv2.GC_FGD
    return trimap


def _color_prior(image: np.ndarray) -> _ColorPrior:
    height, width = image.shape[:2]
    trimap = np.full((height, width), cv2.GC_PR_FGD, dtype=np.uint8)
    border_size = max(2, round(min(height, width) * 0.06))
    border_mask = np.zeros((height, width), dtype=np.uint8)
    border_mask[:border_size, :] = 1
    border_mask[-border_size:, :] = 1
    border_mask[:, :border_size] = 1
    border_mask[:, -border_size:] = 1

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    border_colors = lab[border_mask > 0]
    centers = _deterministic_color_centers(border_colors, maximum_centers=8)
    distance = _nearest_color_distance(lab, centers)
    border_distance = distance[border_mask > 0]
    likely_threshold = float(
        np.clip(np.percentile(border_distance, 90) + 1.0, 8.0, 12.0)
    )
    foreground_threshold = float(
        np.clip(np.percentile(border_distance, 95) + 14.0, 24.0, 28.0)
    )
    cleanup_threshold = min(20.0, foreground_threshold - 8.0)

    # A border can contain the subject. Only border pixels explained by the learned
    # border color clusters are background samples; the rest stay uncertain.
    trimap[(border_mask > 0) & (distance <= likely_threshold)] = cv2.GC_PR_BGD
    corner_size = max(2, round(min(height, width) * 0.035))
    corner_mask = np.zeros_like(border_mask)
    corner_mask[:corner_size, :corner_size] = 1
    corner_mask[:corner_size, -corner_size:] = 1
    corner_mask[-corner_size:, :corner_size] = 1
    corner_mask[-corner_size:, -corner_size:] = 1
    trimap[(corner_mask > 0) & (distance <= likely_threshold)] = cv2.GC_BGD

    y_coordinates, x_coordinates = np.ogrid[:height, :width]
    center_support = (
        ((x_coordinates - (width - 1) / 2) / max(1.0, width * 0.38)) ** 2
        + ((y_coordinates - (height - 1) / 2) / max(1.0, height * 0.42)) ** 2
        <= 1.0
    )
    foreground_seed = (distance > foreground_threshold) & center_support
    foreground_seed = cv2.morphologyEx(
        foreground_seed.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)
    )
    used_fallback_seed = np.count_nonzero(foreground_seed) < 4
    if used_fallback_seed:
        foreground_seed = _dominant_color_foreground_seed(
            image,
            lab,
            border_colors,
            center_support,
        )
    trimap[foreground_seed > 0] = cv2.GC_FGD

    # Add non-border probable background regions similar to the dominant border color.
    trimap[(distance <= likely_threshold) & (foreground_seed == 0)] = cv2.GC_PR_BGD
    if np.count_nonzero(trimap == cv2.GC_FGD) < 4:
        inner = np.zeros_like(border_mask)
        y0, y1 = height // 5, height - height // 5
        x0, x1 = width // 5, width - width // 5
        inner[y0:y1, x0:x1] = 1
        strongest = distance >= np.percentile(distance[inner > 0], 75)
        trimap[(inner > 0) & strongest] = cv2.GC_PR_FGD
    return _ColorPrior(
        trimap=trimap,
        foreground_core=foreground_seed,
        background_distance=distance,
        border_cleanup_threshold=cleanup_threshold,
        protect_core_during_cleanup=used_fallback_seed,
    )


def _dominant_color_foreground_seed(
    image: np.ndarray,
    lab: np.ndarray,
    border_colors: np.ndarray,
    center_support: np.ndarray,
) -> np.ndarray:
    dominant_color = np.median(border_colors, axis=0)
    dominant_distance = np.linalg.norm(lab - dominant_color, axis=2)
    saturation = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 1] > 42
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    structure = (
        cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 20
    )
    seed = (
        (dominant_distance > 20.0)
        & (saturation | structure)
        & center_support
    )
    return cv2.morphologyEx(
        seed.astype(np.uint8),
        cv2.MORPH_CLOSE,
        np.ones((3, 3), np.uint8),
    )


def _refine_centered_portrait(
    image: np.ndarray,
    initial_mask: np.ndarray,
    background_distance: np.ndarray,
    target_width: int,
    target_height: int,
) -> tuple[np.ndarray, np.ndarray] | None:
    height, width = initial_mask.shape
    # A large, centered skin-tone component is only an anchor for a second graph cut;
    # it is not treated as a general person detector.
    ycrcb = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)
    luminance, red_chroma, blue_chroma = cv2.split(ycrcb)
    saturation = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 1]
    skin = (
        (red_chroma >= 133)
        & (red_chroma <= 178)
        & (blue_chroma >= 75)
        & (blue_chroma <= 135)
        & (luminance >= 50)
        & (saturation >= 15)
    ).astype(np.uint8)
    opening_size = _odd_size(max(7, round(min(height, width) * 0.022)))
    skin = cv2.morphologyEx(
        skin,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (opening_size, opening_size)),
    )

    count, labels, stats, centroids = cv2.connectedComponentsWithStats(
        skin,
        connectivity=8,
    )
    candidates: list[tuple[float, int]] = []
    image_area = height * width
    for label in range(1, count):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        component_width = int(stats[label, cv2.CC_STAT_WIDTH])
        component_height = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        center_x, center_y = centroids[label]
        area_ratio = area / image_area
        aspect_ratio = component_width / max(1, component_height)
        fill_ratio = area / max(1, component_width * component_height)
        component = labels == label
        initial_overlap = float(np.mean(initial_mask[component] > 0))
        if not (
            0.01 <= area_ratio <= 0.1
            and width * 0.3 < center_x < width * 0.7
            and height * 0.18 < center_y < height * 0.72
            and 0.45 < aspect_ratio < 1.0
            and fill_ratio >= 0.35
            and initial_overlap >= 0.8
            and x > 0
            and x + component_width < width
        ):
            continue
        normalized_center_distance = (
            ((center_x - width / 2) / max(1.0, width / 2)) ** 2
            + ((center_y - height * 0.48) / max(1.0, height / 2)) ** 2
        )
        candidates.append((area * fill_ratio / (1.0 + normalized_center_distance), label))

    if not candidates:
        return None

    _, anchor_label = max(candidates)
    y = int(stats[anchor_label, cv2.CC_STAT_TOP])
    anchor_width = int(stats[anchor_label, cv2.CC_STAT_WIDTH])
    anchor_height = int(stats[anchor_label, cv2.CC_STAT_HEIGHT])
    anchor_center_x = float(centroids[anchor_label, 0])
    anchor = labels == anchor_label
    support = _portrait_support(
        initial_mask.shape,
        anchor_center_x,
        y,
        anchor_width,
        anchor_height,
        top_half_width=0.5,
        shoulder_half_width=1.0,
        bottom_half_width=3.0,
    )
    inner_support = _portrait_support(
        initial_mask.shape,
        anchor_center_x,
        y,
        anchor_width,
        anchor_height,
        top_half_width=0.3,
        shoulder_half_width=0.6,
        bottom_half_width=1.0,
    )

    # The narrow support removes distant scenery while the inner multimodal core
    # teaches GrabCut skin, hair, and clothing colors without fixing the silhouette.
    trimap = np.full(initial_mask.shape, cv2.GC_PR_BGD, dtype=np.uint8)
    trimap[support > 0] = cv2.GC_PR_FGD
    border_size = max(2, round(min(height, width) * 0.035))
    border = np.zeros(initial_mask.shape, dtype=bool)
    border[:border_size, :] = True
    border[-border_size:, :] = True
    border[:, :border_size] = True
    border[:, -border_size:] = True
    outside_support = support == 0
    trimap[outside_support & (background_distance <= 12.0)] = cv2.GC_BGD
    trimap[outside_support & border] = cv2.GC_BGD

    core = ((initial_mask > 0) & (inner_support > 0)).astype(np.uint8)
    core_size = _odd_size(max(5, round(min(height, width) * 0.027)))
    core = cv2.erode(
        core,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (core_size, core_size)),
    )
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    core[anchor | ((gray < 70) & (inner_support > 0))] = 1
    if np.count_nonzero(core) < 4:
        return None
    trimap[core > 0] = cv2.GC_FGD

    try:
        cv2.grabCut(
            image,
            trimap,
            None,
            np.zeros((1, 65), np.float64),
            np.zeros((1, 65), np.float64),
            4,
            cv2.GC_INIT_WITH_MASK,
        )
    except cv2.error:
        return None

    refined = np.where(
        (trimap == cv2.GC_FGD) | (trimap == cv2.GC_PR_FGD),
        255,
        0,
    ).astype(np.uint8)
    refined = repair_mask(refined, target_width, target_height)
    refined_coverage = float(np.count_nonzero(refined)) / refined.size
    anchor_retained = float(np.mean(refined[anchor] > 0))
    if not 0.05 <= refined_coverage <= 0.7 or anchor_retained < 0.9:
        return None
    return refined, anchor.astype(np.uint8) * 255


def _portrait_support(
    shape: tuple[int, int],
    center_x: float,
    anchor_y: int,
    anchor_width: int,
    anchor_height: int,
    *,
    top_half_width: float,
    shoulder_half_width: float,
    bottom_half_width: float,
) -> np.ndarray:
    height, width = shape
    top_y = max(0, round(anchor_y - anchor_height * 0.55))
    shoulder_y = min(height - 1, round(anchor_y + anchor_height * 1.05))
    polygon = np.array(
        [
            [round(center_x - anchor_width * top_half_width), top_y],
            [round(center_x + anchor_width * top_half_width), top_y],
            [round(center_x + anchor_width * shoulder_half_width), shoulder_y],
            [round(center_x + anchor_width * bottom_half_width), height - 1],
            [round(center_x - anchor_width * bottom_half_width), height - 1],
            [round(center_x - anchor_width * shoulder_half_width), shoulder_y],
        ],
        dtype=np.int32,
    )
    support = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(support, [polygon], 255)
    return support


def _odd_size(value: int) -> int:
    return value if value % 2 == 1 else value + 1


def _build_dark_subject_candidate(
    image: np.ndarray,
    target_width: int,
    target_height: int,
) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (0, 0), 2.0)
    _, dark = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU,
    )
    cell_width = image.shape[1] / max(1, target_width)
    cell_height = image.shape[0] / max(1, target_height)
    kernel_size = max(3, round(min(cell_width, cell_height) * 0.6))
    if kernel_size % 2 == 0:
        kernel_size += 1
    dark = cv2.morphologyEx(
        dark,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)),
    )

    count, labels, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    height, width = dark.shape
    y_coordinates, x_coordinates = np.ogrid[:height, :width]
    center_support = (
        ((x_coordinates - (width - 1) / 2) / max(1.0, width * 0.44)) ** 2
        + ((y_coordinates - (height - 1) / 2) / max(1.0, height * 0.46)) ** 2
        <= 1.0
    )
    contrast_kernel = np.ones((15, 15), np.uint8)
    candidates: list[tuple[float, int]] = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        area_ratio = area / dark.size
        if not 0.12 <= area_ratio <= 0.55:
            continue

        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        component_width = int(stats[label, cv2.CC_STAT_WIDTH])
        component_height = int(stats[label, cv2.CC_STAT_HEIGHT])
        touched_edges = sum(
            (
                x == 0,
                y == 0,
                x + component_width == width,
                y + component_height == height,
            )
        )
        if touched_edges > 2:
            continue

        component = labels == label
        center_ratio = float(np.count_nonzero(component & center_support)) / area
        if center_ratio < 0.35:
            continue

        neighborhood = cv2.dilate(component.astype(np.uint8), contrast_kernel) > 0
        exterior = neighborhood & ~component
        if not exterior.any():
            continue
        local_contrast = float(np.mean(gray[exterior]) - np.mean(gray[component]))
        if local_contrast < 30.0:
            continue

        score = area * center_ratio * local_contrast / (1.0 + 0.2 * touched_edges)
        candidates.append((score, label))

    output = np.zeros_like(dark)
    if candidates:
        _, selected_label = max(candidates)
        output[labels == selected_label] = 255
    return output


def _fuse_dark_subject_candidate(
    mask: np.ndarray,
    dark_subject: np.ndarray,
    target_width: int,
    target_height: int,
) -> np.ndarray:
    if not np.any(dark_subject):
        return mask

    cell_width = mask.shape[1] / max(1, target_width)
    cell_height = mask.shape[0] / max(1, target_height)
    radius = max(1, round(min(cell_width, cell_height) * 2.0))
    neighborhood = cv2.dilate(
        dark_subject,
        cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (radius * 2 + 1, radius * 2 + 1),
        ),
    )
    nearby_mask = cv2.bitwise_and(mask, neighborhood)
    return cv2.bitwise_or(dark_subject, nearby_mask)


def _deterministic_color_centers(
    samples: np.ndarray,
    maximum_centers: int,
) -> np.ndarray:
    if len(samples) == 0:
        raise AlgorithmProcessingError("background color samples are insufficient")

    center_count = min(maximum_centers, len(samples))
    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        30,
        0.2,
    )
    # OpenCV's RNG is process-global. The short lock makes fixed-seed initialization
    # repeatable when multiple request workers build a background model concurrently.
    with _KMEANS_LOCK:
        cv2.setRNGSeed(42)
        try:
            _, _, centers = cv2.kmeans(
                samples,
                center_count,
                None,
                criteria,
                1,
                cv2.KMEANS_PP_CENTERS,
            )
        except cv2.error as error:
            raise AlgorithmProcessingError("background color modeling failed") from error
    return centers


def _nearest_color_distance(image: np.ndarray, centers: np.ndarray) -> np.ndarray:
    distance = np.full(image.shape[:2], np.inf, dtype=np.float32)
    for center in centers:
        candidate = np.linalg.norm(image - center, axis=2)
        distance = np.minimum(distance, candidate)
    return distance


def _retain_supported_components(
    image: np.ndarray,
    mask: np.ndarray,
    foreground_core: np.ndarray,
    background_distance: np.ndarray,
    target_width: int,
    target_height: int,
    foreground_coverage_threshold: float,
) -> np.ndarray:
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    cell_area = mask.size / max(1, target_width * target_height)
    minimum_area = max(4, round(cell_area * foreground_coverage_threshold))
    output = np.zeros_like(mask)
    supported_labels: list[int] = []
    structured_labels: list[int] = []
    fallback_label = 0
    fallback_score = 0.0
    height, width = mask.shape
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    saturation = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 1]
    gradient = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    edges = cv2.Canny(gray, 60, 140)
    maximum_structured_area = mask.size * 0.03

    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < minimum_area:
            continue
        component = labels == label
        if np.count_nonzero(component & (foreground_core > 0)) >= 4:
            supported_labels.append(label)

        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        component_width = int(stats[label, cv2.CC_STAT_WIDTH])
        component_height = int(stats[label, cv2.CC_STAT_HEIGHT])
        touches_border = (
            x == 0
            or y == 0
            or x + component_width == width
            or y + component_height == height
        )
        if (
            not touches_border
            and area <= maximum_structured_area
            and np.median(background_distance[component]) >= 10.0
            and np.median(saturation[component]) <= 80.0
            and np.mean(gradient[component]) >= 25.0
            and np.mean(edges[component] > 0) >= 0.05
        ):
            structured_labels.append(label)

        center_x, center_y = centroids[label]
        normalized_distance = (
            ((center_x - width / 2) / max(1.0, width / 2)) ** 2
            + ((center_y - height / 2) / max(1.0, height / 2)) ** 2
        )
        score = area / (1.0 + normalized_distance)
        if score > fallback_score:
            fallback_label = label
            fallback_score = score

    selected = supported_labels or ([fallback_label] if fallback_label else [])
    selected = list(dict.fromkeys([*selected, *structured_labels]))
    for label in selected:
        output[labels == label] = 255
    return output


def _remove_border_background_residue(
    mask: np.ndarray,
    background_distance: np.ndarray,
    threshold: float,
    foreground_core: np.ndarray,
    protect_core: bool,
) -> np.ndarray:
    likely_background = ((mask > 0) & (background_distance <= threshold)).astype(np.uint8)
    count, labels, _, _ = cv2.connectedComponentsWithStats(likely_background, connectivity=8)
    output = mask.copy()
    height, width = mask.shape
    for label in range(1, count):
        component = labels == label
        y_coordinates, x_coordinates = np.where(component)
        touches_border = (
            y_coordinates.min() == 0
            or y_coordinates.max() == height - 1
            or x_coordinates.min() == 0
            or x_coordinates.max() == width - 1
        )
        has_foreground_support = protect_core and np.any(component & (foreground_core > 0))
        if touches_border and not has_foreground_support:
            output[component] = 0
    return output


def _restore_multiscale_subject(
    mask: np.ndarray,
    protection: np.ndarray,
    background_distance: np.ndarray,
    params: CvNativeParams,
) -> np.ndarray:
    protected_pixels = np.count_nonzero(protection)
    if protected_pixels == 0:
        return mask

    protected_retained_ratio = float(
        np.count_nonzero((mask > 0) & (protection > 0))
    ) / protected_pixels
    protection_to_mask_ratio = protected_pixels / max(1, np.count_nonzero(mask))

    if protected_retained_ratio < 0.62 and protection_to_mask_ratio > 1.05:
        recovery_distance = max(0.0, params.background_recovery_distance - 3.0)
        recoverable = (protection > 0) & (background_distance > recovery_distance)
        output = mask.copy()
        output[recoverable] = 255
        return output

    if protected_retained_ratio < 0.8:
        recovery_distance = params.background_recovery_distance + 6.0
        recoverable = (protection > 0) & (background_distance > recovery_distance)
        output = mask.copy()
        output[recoverable] = 255
        return output

    return _restore_nearby_subject(
        mask,
        protection,
        background_distance,
        params,
    )


def _build_multiscale_protection(
    image: np.ndarray,
    background_distance: np.ndarray,
    target_width: int,
    target_height: int,
    params: CvNativeParams,
) -> np.ndarray:
    protection_width = max(8, round(target_width * params.protection_scale))
    protection_height = max(8, round(target_height * params.protection_scale))
    protection_size = (protection_width, protection_height)
    reduced_image = cv2.resize(image, protection_size, interpolation=cv2.INTER_AREA)
    reduced_distance = cv2.resize(
        background_distance,
        protection_size,
        interpolation=cv2.INTER_AREA,
    )

    gray = cv2.cvtColor(reduced_image, cv2.COLOR_BGR2GRAY)
    gradient = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    saturation = cv2.cvtColor(reduced_image, cv2.COLOR_BGR2HSV)[:, :, 1]
    y_coordinates, x_coordinates = np.ogrid[:protection_height, :protection_width]
    center_support = (
        (
            (x_coordinates - (protection_width - 1) / 2)
            / max(1.0, protection_width * 0.46)
        )
        ** 2
        + (
            (y_coordinates - (protection_height - 1) / 2)
            / max(1.0, protection_height * 0.48)
        )
        ** 2
        <= 1.0
    )
    seed = (
        (reduced_distance > params.foreground_seed_distance)
        | (
            (gradient > params.edge_seed_threshold)
            & (saturation > params.saturation_seed_threshold)
        )
    ) & center_support
    seed = cv2.morphologyEx(
        seed.astype(np.uint8),
        cv2.MORPH_CLOSE,
        np.ones((3, 3), np.uint8),
    )
    protected = _coarse_subject_components(seed, params.coarse_subject_count)
    if params.protection_dilation_radius > 0:
        dilation_size = params.protection_dilation_radius * 2 + 1
        protected = cv2.dilate(
            protected,
            cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (dilation_size, dilation_size),
            ),
        )
    protected = _fill_mask_holes(protected)
    protected = cv2.resize(
        protected,
        image.shape[1::-1],
        interpolation=cv2.INTER_LINEAR,
    )
    return (protected >= 128).astype(np.uint8) * 255


def _restore_nearby_subject(
    mask: np.ndarray,
    protection: np.ndarray,
    background_distance: np.ndarray,
    params: CvNativeParams,
) -> np.ndarray:
    neighborhood_radius = max(
        1,
        round(min(mask.shape) * params.recovery_neighborhood_ratio),
    )
    neighborhood_size = neighborhood_radius * 2 + 1
    neighborhood = cv2.dilate(
        mask,
        cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (neighborhood_size, neighborhood_size),
        ),
    )
    recoverable = (
        (protection > 0)
        & (neighborhood > 0)
        & (background_distance > params.background_recovery_distance)
    )
    output = mask.copy()
    output[recoverable] = 255
    return output


def _coarse_subject_components(seed: np.ndarray, maximum_components: int) -> np.ndarray:
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(seed, connectivity=8)
    height, width = seed.shape
    minimum_area = max(6, round(seed.size * 0.0015))
    candidates: list[tuple[float, int]] = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        center_x, center_y = centroids[label]
        normalized_distance = (
            ((center_x - width / 2) / max(1.0, width / 2)) ** 2
            + ((center_y - height / 2) / max(1.0, height / 2)) ** 2
        )
        if area >= minimum_area and (normalized_distance < 0.8 or area > seed.size * 0.01):
            candidates.append((area / (1.0 + normalized_distance), label))

    output = np.zeros_like(seed)
    # Recovery favors the dominant subject. Other components keep their GrabCut
    # result but cannot grow a background halo through the coarse protection mask.
    for _, label in sorted(candidates, reverse=True)[:maximum_components]:
        output[labels == label] = 255
    return output


def _fill_mask_holes(mask: np.ndarray) -> np.ndarray:
    padded = cv2.copyMakeBorder(mask, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    outside = padded.copy()
    cv2.floodFill(outside, None, (0, 0), 255)
    holes = cv2.bitwise_not(outside)[1:-1, 1:-1]
    return cv2.bitwise_or(mask, holes)


def repair_mask(mask: np.ndarray, target_width: int, target_height: int) -> np.ndarray:
    cell_width = mask.shape[1] / max(1, target_width)
    cell_height = mask.shape[0] / max(1, target_height)
    scale = max(1, round(min(cell_width, cell_height) * 0.15))
    size = scale * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    repaired = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    repaired = _fill_small_mask_holes(
        repaired,
        maximum_area=max(4, round(cell_width * cell_height * 2.0)),
    )

    count, labels, stats, _ = cv2.connectedComponentsWithStats(repaired, connectivity=8)
    minimum_area = max(4, round(cell_width * cell_height * 0.2))
    output = np.zeros_like(repaired)
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] >= minimum_area:
            output[labels == label] = 255
    return output


def _fill_small_mask_holes(mask: np.ndarray, maximum_area: int) -> np.ndarray:
    inverse = np.where(mask > 0, 0, 1).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(inverse, connectivity=8)
    output = mask.copy()
    height, width = mask.shape
    for label in range(1, count):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        component_width = int(stats[label, cv2.CC_STAT_WIDTH])
        component_height = int(stats[label, cv2.CC_STAT_HEIGHT])
        touches_border = (
            x == 0
            or y == 0
            or x + component_width == width
            or y + component_height == height
        )
        if not touches_border and stats[label, cv2.CC_STAT_AREA] <= maximum_area:
            output[labels == label] = 255
    return output


def _mask_confidence(
    mask: np.ndarray,
    trimap: np.ndarray,
    foreground_evidence: np.ndarray | None = None,
) -> float:
    foreground_seed = (
        foreground_evidence > 0
        if foreground_evidence is not None and np.any(foreground_evidence)
        else trimap == cv2.GC_FGD
    )
    background_seed = trimap == cv2.GC_BGD
    foreground_score = float(np.mean(mask[foreground_seed] > 0)) if foreground_seed.any() else 0.5
    background_score = float(np.mean(mask[background_seed] == 0)) if background_seed.any() else 0.5
    return min(foreground_score, background_score)
