from __future__ import annotations

from typing import Any

import numpy as np

from .types import Detection, MaskCandidate


class UltralyticsSegmenter:
    def __init__(self, model: Any, device: str, *, half: bool) -> None:
        self.model = model
        self.device = device
        self.half = half

    def segment_boxes(
        self,
        image: np.ndarray,
        detections: list[Detection],
    ) -> list[MaskCandidate]:
        if not detections:
            return []
        results = self.model.predict(
            source=image,
            bboxes=[list(detection.box) for detection in detections],
            device=self.device,
            **({"quantize": 16} if self.half else {}),
            verbose=False,
        )
        return _mask_candidates(
            results,
            fallback_scores=[item.score for item in detections],
        )


def _mask_candidates(
    results: list[Any],
    fallback_scores: list[float] | None = None,
) -> list[MaskCandidate]:
    if not results or results[0].masks is None:
        return []
    result = results[0]
    masks = result.masks.data.detach().cpu().numpy()
    scores: list[float] = []
    if result.boxes is not None and result.boxes.conf is not None:
        scores = [float(value) for value in result.boxes.conf.detach().cpu().numpy()]
    candidates = []
    for index, mask in enumerate(masks):
        fallback = (
            fallback_scores[index] if fallback_scores and index < len(fallback_scores) else 0.5
        )
        quality = fallback
        if not fallback_scores and index < len(scores):
            quality = scores[index]
        candidates.append(MaskCandidate(mask=mask, quality=quality))
    return candidates
