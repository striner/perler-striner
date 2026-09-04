from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from python_backend.algorithms.contracts import (
    AlgorithmAnalysisInput,
    AlgorithmIdentity,
    ImagePayload,
)
from python_backend.algorithms.errors import InvalidRequestError, UploadTooLargeError
from python_backend.core.config import Settings
from python_backend.schemas.api import (
    AlgorithmIdentityData,
    AnalysisBoxData,
    AnalysisData,
    AnalysisImageData,
    AnalysisObjectData,
)
from python_backend.services.processing import ProcessingService
from python_backend.web.dependencies import get_processing_service, get_settings_from_app
from python_backend.web.responses import success_response

router = APIRouter(prefix="/api/v1", tags=["processing"])
ALGORITHM_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


@router.post("/analyze")
async def analyze_image(
    request: Request,
    image: Annotated[UploadFile, File()],
    algorithm: Annotated[str, Form()],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    processing_service: Annotated[ProcessingService, Depends(get_processing_service)],
    algorithm_version: Annotated[str | None, Form()] = None,
):
    if not ALGORITHM_PATTERN.fullmatch(algorithm):
        raise InvalidRequestError("algorithm identifier is invalid")
    if algorithm_version is not None and not VERSION_PATTERN.fullmatch(algorithm_version):
        raise InvalidRequestError("algorithm version is invalid")
    media_type = image.content_type or ""
    if not media_type.startswith("image/"):
        raise InvalidRequestError("uploaded file must use an image media type")
    try:
        image_bytes = await image.read(settings.max_upload_bytes + 1)
    finally:
        await image.close()
    if not image_bytes:
        raise InvalidRequestError("uploaded image is empty")
    if len(image_bytes) > settings.max_upload_bytes:
        raise UploadTooLargeError()

    output = await processing_service.analyze(
        AlgorithmAnalysisInput(
            schema_version=1,
            image=ImagePayload(
                data=image_bytes,
                media_type=media_type,
                filename=image.filename or "upload",
            ),
            algorithm=AlgorithmIdentity(algorithm, algorithm_version),
        )
    )
    return success_response(
        request=request,
        data=AnalysisData(
            version=output.schema_version,
            analysis_token=output.analysis_token,
            image=AnalysisImageData(width=output.image_width, height=output.image_height),
            objects=[
                AnalysisObjectData(
                    id=item.object_id,
                    type_id=item.type_id,
                    type_name_en=item.type_name_en,
                    confidence=item.confidence,
                    salience=item.salience,
                    bbox=AnalysisBoxData(
                        x=item.bbox.x,
                        y=item.bbox.y,
                        width=item.bbox.width,
                        height=item.bbox.height,
                    ),
                )
                for item in output.objects
            ],
            algorithm=AlgorithmIdentityData(
                id=output.algorithm.algorithm_id,
                version=output.algorithm.version or "",
            ),
        ),
    )
