from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from python_backend.algorithms.errors import InvalidRequestError

_PROMPT_SEPARATOR = re.compile(r"[,，\r\n]+")
_PARAMETER_NAMES = {
    "prompt",
    "confidence_threshold",
    "max_instances",
    "mask_iou_threshold",
    "foreground_coverage_threshold",
    "edge_strength",
    "outline_strength",
}


@dataclass(frozen=True, slots=True)
class TinyModelParams:
    prompts: tuple[str, ...] = ()
    confidence_threshold: float = 0.35
    max_instances: int = 5
    mask_iou_threshold: float = 0.7
    foreground_coverage_threshold: float = 0.2
    edge_strength: float = 0.65
    outline_strength: float = 0.1


def parse_params(values: Mapping[str, Any]) -> TinyModelParams:
    unknown = set(values) - _PARAMETER_NAMES
    if unknown:
        raise InvalidRequestError(f"unsupported tiny_model parameter: {sorted(unknown)[0]}")
    return TinyModelParams(
        prompts=parse_prompt(values.get("prompt", "")),
        confidence_threshold=_number(
            values.get("confidence_threshold", 0.35),
            "confidence_threshold",
            0.05,
            0.95,
        ),
        max_instances=_integer(values.get("max_instances", 5), "max_instances", 1, 5),
        mask_iou_threshold=_number(
            values.get("mask_iou_threshold", 0.7),
            "mask_iou_threshold",
            0.3,
            0.95,
        ),
        foreground_coverage_threshold=_number(
            values.get("foreground_coverage_threshold", 0.2),
            "foreground_coverage_threshold",
            0.05,
            0.8,
        ),
        edge_strength=_number(values.get("edge_strength", 0.65), "edge_strength", 0, 1.5),
        outline_strength=_number(
            values.get("outline_strength", 0.1), "outline_strength", 0, 0.3
        ),
    )


def parse_prompt(value: Any) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise InvalidRequestError("prompt must be a string")
    phrases = tuple(part.strip() for part in _PROMPT_SEPARATOR.split(value) if part.strip())
    if len(phrases) > 8:
        raise InvalidRequestError("prompt supports at most 8 target phrases")
    if any(len(phrase) > 64 for phrase in phrases):
        raise InvalidRequestError("each prompt phrase supports at most 64 characters")
    return phrases


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
