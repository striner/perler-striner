from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from python_backend.algorithms.errors import InvalidRequestError

_PARAMETER_NAMES = {
    "analysis_token",
    "selected_object_ids",
    "foreground_coverage_threshold",
    "edge_strength",
    "outline_strength",
    "max_colors",
}


@dataclass(frozen=True, slots=True)
class TinyModelParams:
    analysis_token: str
    selected_object_ids: tuple[str, ...]
    foreground_coverage_threshold: float = 0.2
    edge_strength: float = 0.65
    outline_strength: float = 0.1
    max_colors: int = 16


def parse_params(values: Mapping[str, Any]) -> TinyModelParams:
    unknown = set(values) - _PARAMETER_NAMES
    if unknown:
        raise InvalidRequestError(f"unsupported tiny_model parameter: {sorted(unknown)[0]}")
    token = values.get("analysis_token")
    if not isinstance(token, str) or not token or len(token) > 32_768:
        raise InvalidRequestError("analysis_token is required")
    object_ids = values.get("selected_object_ids")
    if not isinstance(object_ids, list) or not 1 <= len(object_ids) <= 24:
        raise InvalidRequestError("selected_object_ids must contain 1 to 24 items")
    if any(not isinstance(item, str) or not item or len(item) > 64 for item in object_ids):
        raise InvalidRequestError("selected_object_ids contains an invalid item")
    if len(set(object_ids)) != len(object_ids):
        raise InvalidRequestError("selected_object_ids must not contain duplicates")
    return TinyModelParams(
        analysis_token=token,
        selected_object_ids=tuple(object_ids),
        foreground_coverage_threshold=_number(
            values.get("foreground_coverage_threshold", 0.2),
            "foreground_coverage_threshold",
            0.05,
            0.8,
        ),
        edge_strength=_number(values.get("edge_strength", 0.65), "edge_strength", 0, 1.5),
        outline_strength=_number(values.get("outline_strength", 0.1), "outline_strength", 0, 0.3),
        max_colors=_integer(values.get("max_colors", 16), "max_colors", 4, 20),
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
