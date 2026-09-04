from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True, slots=True)
class Detection:
    box: tuple[float, float, float, float]
    score: float
    type_id: int
    type_name_en: str
    salience: float


@dataclass(frozen=True, slots=True)
class MaskCandidate:
    mask: np.ndarray
    quality: float


class InferenceRuntime(Protocol):
    def analyze(
        self,
        image: np.ndarray,
        confidence_threshold: float,
        max_objects: int,
    ) -> list[Detection]: ...

    def segment_boxes(
        self,
        image: np.ndarray,
        detections: list[Detection],
    ) -> list[MaskCandidate]: ...

    def stylize(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray: ...
