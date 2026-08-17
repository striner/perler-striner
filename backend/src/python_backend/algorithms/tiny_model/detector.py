from __future__ import annotations

from typing import Any

import numpy as np

from .types import Detection


class UltralyticsDetector:
    def __init__(self, model: Any, device: str, *, half: bool) -> None:
        self.model = model
        self.device = device
        self.half = half

    def detect(
        self,
        image: np.ndarray,
        prompts: tuple[str, ...],
        confidence_threshold: float,
        max_instances: int,
    ) -> list[Detection]:
        classes = list(prompts)
        self.model.set_classes(classes)
        results = self.model.predict(
            source=image,
            device=self.device,
            conf=confidence_threshold,
            iou=0.7,
            max_det=max_instances,
            imgsz=640,
            half=self.half,
            verbose=False,
        )
        if not results or results[0].boxes is None:
            return []
        boxes = results[0].boxes
        coordinates = boxes.xyxy.detach().cpu().numpy()
        scores = boxes.conf.detach().cpu().numpy()
        class_ids = boxes.cls.detach().cpu().numpy().astype(int)
        detections = []
        for box, score, class_id in zip(coordinates, scores, class_ids, strict=True):
            phrase = classes[class_id] if 0 <= class_id < len(classes) else "subject"
            detections.append(
                Detection(
                    box=tuple(float(value) for value in box),
                    score=float(score),
                    phrase=phrase,
                )
            )
        return detections
