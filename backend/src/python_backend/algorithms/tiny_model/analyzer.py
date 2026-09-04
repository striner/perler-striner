from __future__ import annotations

from typing import Any

import numpy as np

from .types import Detection

_NON_ENTITY_LABELS = {
    "3D CG rendering",
    "beauty",
    "indoor",
    "kiss",
    "outdoor",
    "smile",
}


class UltralyticsAnalyzer:
    def __init__(
        self,
        model: Any,
        device: str,
    ) -> None:
        self.model = model
        self.device = device

    def analyze(
        self,
        image: np.ndarray,
        confidence_threshold: float,
        max_objects: int,
    ) -> list[Detection]:
        results = self.model.predict(
            source=image,
            device=self.device,
            conf=confidence_threshold,
            iou=0.7,
            max_det=max_objects * 3,
            imgsz=640,
            verbose=False,
        )
        if not results or results[0].boxes is None:
            return []

        result = results[0]
        boxes = result.boxes
        coordinates = boxes.xyxy.detach().cpu().numpy()
        scores = boxes.conf.detach().cpu().numpy()
        class_ids = boxes.cls.detach().cpu().numpy().astype(int)
        height, width = image.shape[:2]
        image_area = max(1, width * height)
        center_x, center_y = width / 2, height / 2
        diagonal = max(1.0, float(np.hypot(center_x, center_y)))
        detections: list[Detection] = []

        for box, score, class_id in zip(coordinates, scores, class_ids, strict=True):
            x0, y0, x1, y1 = (float(value) for value in box)
            x0, y0 = max(0.0, x0), max(0.0, y0)
            x1, y1 = min(float(width), x1), min(float(height), y1)
            if x1 <= x0 or y1 <= y0:
                continue
            area_ratio = ((x1 - x0) * (y1 - y0)) / image_area
            if area_ratio < 0.0005 or area_ratio > 0.98:
                continue
            english = str(result.names.get(class_id, f"object {class_id}"))
            if english.casefold() in {label.casefold() for label in _NON_ENTITY_LABELS}:
                continue
            object_x, object_y = (x0 + x1) / 2, (y0 + y1) / 2
            center_score = max(
                0.0,
                1.0 - np.hypot(object_x - center_x, object_y - center_y) / diagonal,
            )
            area_score = min(1.0, np.sqrt(area_ratio / 0.35))
            salience = float(score) * 0.55 + float(center_score) * 0.25 + area_score * 0.2
            detections.append(
                Detection(
                    box=(x0, y0, x1, y1),
                    score=float(score),
                    type_id=int(class_id),
                    type_name_en=english,
                    salience=salience,
                )
            )

        retained: list[Detection] = []
        for candidate in sorted(detections, key=lambda item: item.salience, reverse=True):
            if any(
                candidate.type_id == existing.type_id
                and _box_iou(candidate.box, existing.box) >= 0.75
                for existing in retained
            ):
                continue
            retained.append(candidate)
            if len(retained) >= max_objects:
                break
        return retained


def _box_iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    x0 = max(first[0], second[0])
    y0 = max(first[1], second[1])
    x1 = min(first[2], second[2])
    y1 = min(first[3], second[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0
