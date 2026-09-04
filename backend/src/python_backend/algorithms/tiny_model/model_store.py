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


ANALYZER_ARTIFACT = ModelArtifact(
    "yoloe-26m-seg-pf.pt",
    72_857_475,
    "4a03f83695314f2dfb5fd6ebc3866100af525645b6490907bde31e4c0e4ffbd5",
    "https://github.com/ultralytics/assets/releases/download/v8.4.0/yoloe-26m-seg-pf.pt",
)
SEGMENTER_ARTIFACT = ModelArtifact(
    "sam2.1_s.pt",
    92_319_866,
    "60f9e43f1307be192eef341437e02c40f32cd61cf36a97a203a0998a2952873a",
    "https://github.com/ultralytics/assets/releases/download/v8.4.0/sam2.1_s.pt",
)
CARTOONIZER_ARTIFACT = ModelArtifact(
    "animegan2-celeba-distill.pt",
    8_603_556,
    "a3740d98f99efe2ee6c332de2b800f542ddbb2d15e835c07e9bf667c29cef8a7",
    "https://raw.githubusercontent.com/bryandlee/animegan2-pytorch/"
    "25d7b017267208dfaf34026aa3425e518372aa2f/weights/celeba_distill.pt",
)
ARTIFACTS = (
    ANALYZER_ARTIFACT,
    SEGMENTER_ARTIFACT,
    CARTOONIZER_ARTIFACT,
)


class ModelStoreError(RuntimeError):
    pass


class ModelStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    @property
    def analyzer_path(self) -> Path:
        return self.root / ANALYZER_ARTIFACT.relative_path

    @property
    def segmenter_path(self) -> Path:
        return self.root / SEGMENTER_ARTIFACT.relative_path

    @property
    def cartoonizer_path(self) -> Path:
        return self.root / CARTOONIZER_ARTIFACT.relative_path

    def validate(self) -> None:
        for artifact in ARTIFACTS:
            self.validate_artifact(artifact)

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
