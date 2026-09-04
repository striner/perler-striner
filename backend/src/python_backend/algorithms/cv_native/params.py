from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from python_backend.algorithms.errors import InvalidRequestError


@dataclass(frozen=True, slots=True)
class CvNativeParams:
    edge_strength: float = 0.65
    outline_strength: float = 0.1
    background_recovery_distance: float = 6.0
    coarse_subject_count: int = 1
    protection_scale: float = 2.0
    foreground_seed_distance: float = 28.0
    edge_seed_threshold: float = 56.0
    saturation_seed_threshold: float = 18.0
    protection_dilation_radius: int = 2
    recovery_neighborhood_ratio: float = 0.014
    foreground_coverage_threshold: float = 0.2


_PARAMETER_NAMES = {
    "edge_strength",
    "outline_strength",
    "background_recovery_distance",
    "coarse_subject_count",
    "protection_scale",
    "foreground_seed_distance",
    "edge_seed_threshold",
    "saturation_seed_threshold",
    "protection_dilation_radius",
    "recovery_neighborhood_ratio",
    "foreground_coverage_threshold",
}


def parse_params(values: Mapping[str, Any]) -> CvNativeParams:
    unknown = set(values) - _PARAMETER_NAMES
    if unknown:
        raise InvalidRequestError(f"unsupported cv_native parameter: {sorted(unknown)[0]}")
    return CvNativeParams(
        edge_strength=_number(values.get("edge_strength", 0.65), "edge_strength", 0, 1.5),
        outline_strength=_number(values.get("outline_strength", 0.1), "outline_strength", 0, 0.3),
        background_recovery_distance=_number(
            values.get("background_recovery_distance", 6.0),
            "background_recovery_distance",
            0,
            40,
        ),
        coarse_subject_count=_integer(
            values.get("coarse_subject_count", 1), "coarse_subject_count", 1, 5
        ),
        protection_scale=_number(values.get("protection_scale", 2.0), "protection_scale", 1, 4),
        foreground_seed_distance=_number(
            values.get("foreground_seed_distance", 28.0),
            "foreground_seed_distance",
            0,
            80,
        ),
        edge_seed_threshold=_number(
            values.get("edge_seed_threshold", 56.0), "edge_seed_threshold", 0, 255
        ),
        saturation_seed_threshold=_number(
            values.get("saturation_seed_threshold", 18.0),
            "saturation_seed_threshold",
            0,
            255,
        ),
        protection_dilation_radius=_integer(
            values.get("protection_dilation_radius", 2),
            "protection_dilation_radius",
            0,
            12,
        ),
        recovery_neighborhood_ratio=_number(
            values.get("recovery_neighborhood_ratio", 0.014),
            "recovery_neighborhood_ratio",
            0.002,
            0.05,
        ),
        foreground_coverage_threshold=_number(
            values.get("foreground_coverage_threshold", 0.2),
            "foreground_coverage_threshold",
            0.05,
            0.8,
        ),
    )


def _number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidRequestError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise InvalidRequestError(f"{name} is out of range")
    return result


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidRequestError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise InvalidRequestError(f"{name} is out of range")
    return value
