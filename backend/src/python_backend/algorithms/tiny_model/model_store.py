from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    relative_path: str
    size: int
    sha256: str
    url: str


DETECTOR_ARTIFACT = ModelArtifact(
    "yolov8s-worldv2.pt",
    25_923_032,
    "9b2c17ab6124a913e9b3a5c170617920d91b0f01111a8479da69f00e2cf27792",
    "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8s-worldv2.pt",
)
SEGMENTER_ARTIFACT = ModelArtifact(
    "mobile_sam.pt",
    40_728_226,
    "6dbb90523a35330fedd7f1d3dfc66f995213d81b29a5ca8108dbcdd4e37d6c2f",
    "https://github.com/ultralytics/assets/releases/download/v8.4.0/mobile_sam.pt",
)
TEXT_ENCODER_ARTIFACT = ModelArtifact(
    "clip/ViT-B-32.pt",
    353_976_522,
    "40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af",
    "https://openaipublic.azureedge.net/clip/models/"
    "40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt",
)
ARTIFACTS = (DETECTOR_ARTIFACT, SEGMENTER_ARTIFACT, TEXT_ENCODER_ARTIFACT)


class ModelStoreError(RuntimeError):
    pass


class ModelStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    @property
    def detector_path(self) -> Path:
        return self.root / DETECTOR_ARTIFACT.relative_path

    @property
    def segmenter_path(self) -> Path:
        return self.root / SEGMENTER_ARTIFACT.relative_path

    def validate(self) -> None:
        for artifact in ARTIFACTS:
            path = self.root / artifact.relative_path
            if not path.is_file():
                raise ModelStoreError(f"model file is missing: {artifact.relative_path}")
            if path.stat().st_size != artifact.size:
                raise ModelStoreError(f"model size is invalid: {artifact.relative_path}")
            if _sha256(path) != artifact.sha256:
                raise ModelStoreError(f"model checksum is invalid: {artifact.relative_path}")

    def validate_artifact(self, artifact: ModelArtifact) -> None:
        path = self.root / artifact.relative_path
        if not path.is_file() or path.stat().st_size != artifact.size:
            raise ModelStoreError(f"model file is invalid: {artifact.relative_path}")
        if _sha256(path) != artifact.sha256:
            raise ModelStoreError(f"model checksum is invalid: {artifact.relative_path}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
