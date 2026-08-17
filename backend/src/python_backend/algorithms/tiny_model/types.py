from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True, slots=True)
class Detection:
    box: tuple[float, float, float, float]
    score: float
    phrase: str


@dataclass(frozen=True, slots=True)
class MaskCandidate:
    mask: np.ndarray
    quality: float


class InferenceRuntime(Protocol):
    def detect(
        self,
        image: np.ndarray,
        prompts: tuple[str, ...],
        confidence_threshold: float,
        max_instances: int,
    ) -> list[Detection]: ...

    def segment_boxes(
        self,
        image: np.ndarray,
        detections: list[Detection],
    ) -> list[MaskCandidate]: ...

    def automatic_masks(self, image: np.ndarray) -> list[MaskCandidate]: ...
