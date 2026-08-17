from __future__ import annotations

import importlib.util

import numpy as np

from .detector import UltralyticsDetector
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
        if importlib.util.find_spec("clip") is None:
            raise RuntimeInitializationError("tiny-model CLIP dependency is not installed")

        import torch

        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeInitializationError("CUDA is not available")

        store.validate()
        self.device = device
        self._half = device == "cuda"
        self._model_dir = store.root

        # YOLO-World resolves its CLIP checkpoint from WEIGHTS_DIR/clip. Point it at
        # the validated local store before any class text is encoded.
        import ultralytics.nn.text_model as text_model
        from ultralytics import SAM, YOLOWorld

        text_model.WEIGHTS_DIR = self._model_dir
        self._detector = UltralyticsDetector(
            YOLOWorld(store.detector_path, verbose=False),
            device,
            half=self._half,
        )
        self._segmenter = UltralyticsSegmenter(
            SAM(store.segmenter_path),
            device,
            half=self._half,
        )
        if warmup:
            self._warmup()

    def detect(
        self,
        image: np.ndarray,
        prompts: tuple[str, ...],
        confidence_threshold: float,
        max_instances: int,
    ) -> list[Detection]:
        return self._detector.detect(
            image,
            prompts,
            confidence_threshold,
            max_instances,
        )

    def segment_boxes(
        self,
        image: np.ndarray,
        detections: list[Detection],
    ) -> list[MaskCandidate]:
        return self._segmenter.segment_boxes(image, detections)

    def automatic_masks(self, image: np.ndarray) -> list[MaskCandidate]:
        return self._segmenter.automatic_masks(image)

    def _warmup(self) -> None:
        sample = np.zeros((64, 64, 3), dtype=np.uint8)
        self.detect(sample, ("object",), 0.35, 1)
        self._segmenter.segment_boxes(
            sample,
            [Detection((8, 8, 56, 56), 0.9, "object")],
        )


def validate_device(device: str) -> None:
    if importlib.util.find_spec("torch") is None:
        raise RuntimeInitializationError("tiny-model optional dependencies are not installed")
    import torch

    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeInitializationError("CUDA is not available")
