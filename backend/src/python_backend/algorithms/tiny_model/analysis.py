from __future__ import annotations

from python_backend.algorithms.contracts import (
    AlgorithmAnalysisInput,
    AlgorithmAnalysisOutput,
    AlgorithmIdentity,
    AnalysisBox,
    AnalysisObject,
)
from python_backend.algorithms.errors import AlgorithmProcessingError

from .analysis_token import AnalysisTokenSigner
from .imaging import decode_image, working_image
from .types import InferenceRuntime


def run_analysis(
    request: AlgorithmAnalysisInput,
    runtime: InferenceRuntime,
    signer: AnalysisTokenSigner,
    max_decoded_pixels: int,
    work_max_edge: int,
    confidence_threshold: float,
    max_objects: int,
) -> AlgorithmAnalysisOutput:
    image, _ = decode_image(request.image.data, max_decoded_pixels)
    source_height, source_width = image.shape[:2]
    working = working_image(image, work_max_edge)
    height, width = working.shape[:2]
    raw = runtime.analyze(working, confidence_threshold, max_objects)
    if not raw:
        raise AlgorithmProcessingError("object analysis did not return a reliable entity")

    normalized = [
        detection.__class__(
            box=(
                detection.box[0] / width,
                detection.box[1] / height,
                detection.box[2] / width,
                detection.box[3] / height,
            ),
            score=detection.score,
            type_id=detection.type_id,
            type_name_en=detection.type_name_en,
            salience=detection.salience,
        )
        for detection in raw
    ]
    token, token_objects = signer.issue(
        request.image.data,
        normalized,
        source_width,
        source_height,
    )
    objects = tuple(
        AnalysisObject(
            object_id=item.object_id,
            type_id=item.type_id,
            type_name_en=item.type_name_en,
            confidence=item.score,
            salience=item.salience,
            bbox=AnalysisBox(
                x=item.box[0],
                y=item.box[1],
                width=item.box[2] - item.box[0],
                height=item.box[3] - item.box[1],
            ),
        )
        for item in token_objects
    )
    return AlgorithmAnalysisOutput(
        schema_version=1,
        algorithm=AlgorithmIdentity("tiny_model", "1.0.0"),
        image_width=source_width,
        image_height=source_height,
        analysis_token=token,
        objects=objects,
    )
