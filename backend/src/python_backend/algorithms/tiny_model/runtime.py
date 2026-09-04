from __future__ import annotations

import importlib.util

import numpy as np

from .analyzer import UltralyticsAnalyzer
from .model_store import ModelStore
from .segmenter import UltralyticsSegmenter
from .types import Detection, MaskCandidate


class RuntimeInitializationError(RuntimeError):
    pass


class UltralyticsRuntime:
    def __init__(self, store: ModelStore, device: str, *, warmup: bool) -> None:
        if (
            importlib.util.find_spec("torch") is None
            or importlib.util.find_spec("ultralytics") is None
        ):
            raise RuntimeInitializationError("tiny-model optional dependencies are not installed")

        import torch

        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeInitializationError("CUDA is not available")

        store.validate()
        from ultralytics import SAM, YOLOE

        from .cartoonizer import AnimeGanCartoonizer

        self.device = device
        self._analyzer = UltralyticsAnalyzer(
            YOLOE(store.analyzer_path, verbose=False),
            device,
        )
        self._segmenter = UltralyticsSegmenter(
            SAM(store.segmenter_path),
            device,
            half=device == "cuda",
        )
        self._cartoonizer = AnimeGanCartoonizer(store.cartoonizer_path, device)
        if warmup:
            self._warmup()

    def analyze(
        self,
        image: np.ndarray,
        confidence_threshold: float,
        max_objects: int,
    ) -> list[Detection]:
        return self._analyzer.analyze(image, confidence_threshold, max_objects)

    def segment_boxes(
        self,
        image: np.ndarray,
        detections: list[Detection],
    ) -> list[MaskCandidate]:
        return self._segmenter.segment_boxes(image, detections)

    def stylize(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        return self._cartoonizer.stylize(image, mask)

    def _warmup(self) -> None:
        sample = np.zeros((64, 64, 3), dtype=np.uint8)
        sample[16:48, 16:48] = 127
        mask = np.zeros((64, 64), dtype=np.uint8)
        mask[16:48, 16:48] = 255
        self.analyze(sample, 0.25, 1)
        self.segment_boxes(
            sample,
            [Detection((8, 8, 56, 56), 0.9, 0, "object", 0.9)],
        )
        self.stylize(sample, mask)


def validate_device(device: str) -> None:
    if importlib.util.find_spec("torch") is None:
        raise RuntimeInitializationError("tiny-model optional dependencies are not installed")
    import torch

    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeInitializationError("CUDA is not available")
