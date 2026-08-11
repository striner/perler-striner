from __future__ import annotations

import base64
import json
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from python_backend.algorithms.contracts import (
    AlgorithmIdentity,
    AlgorithmInput,
    GridTarget,
    ImagePayload,
)
from python_backend.algorithms.errors import InvalidRequestError, UploadTooLargeError
from python_backend.algorithms.validation import validate_algorithm_params
from python_backend.core.config import Settings
from python_backend.schemas.api import AlgorithmIdentityData, GridData
from python_backend.services.processing import ProcessingService
from python_backend.web.dependencies import get_processing_service, get_settings_from_app
from python_backend.web.responses import success_response

router = APIRouter(prefix="/api/v1", tags=["processing"])

ALGORITHM_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


def _parse_algorithm_params(raw: str, settings: Settings) -> dict[str, Any]:
    if len(raw.encode("utf-8")) > settings.max_algorithm_params_bytes:
        raise InvalidRequestError("algorithm_params is too large")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise InvalidRequestError("algorithm_params must be valid JSON") from error
    if not isinstance(parsed, dict):
        raise InvalidRequestError("algorithm_params must be a JSON object")
    validate_algorithm_params(
        parsed,
        max_depth=settings.max_algorithm_params_depth,
        max_fields=settings.max_algorithm_params_fields,
    )
    return parsed


def _validate_request_values(
    width: int,
    height: int,
    algorithm: str,
    algorithm_version: str | None,
    settings: Settings,
) -> None:
    if not 1 <= width <= settings.max_grid_size or not 1 <= height <= settings.max_grid_size:
        raise InvalidRequestError("target grid dimensions are out of range")
    if not ALGORITHM_PATTERN.fullmatch(algorithm):
        raise InvalidRequestError("algorithm identifier is invalid")
    if algorithm_version is not None and not VERSION_PATTERN.fullmatch(algorithm_version):
        raise InvalidRequestError("algorithm version is invalid")


@router.post("/process")
async def process_image(
    request: Request,
    image: Annotated[UploadFile, File()],
    width: Annotated[int, Form()],
    height: Annotated[int, Form()],
    algorithm: Annotated[str, Form()],
    settings: Annotated[Settings, Depends(get_settings_from_app)],
    processing_service: Annotated[ProcessingService, Depends(get_processing_service)],
    algorithm_version: Annotated[str | None, Form()] = None,
    algorithm_params: Annotated[str, Form()] = "{}",
):
    form = await request.form()
    if "remove_background" in form:
        raise InvalidRequestError("remove_background is not a supported parameter")

    _validate_request_values(width, height, algorithm, algorithm_version, settings)
    params = _parse_algorithm_params(algorithm_params, settings)
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

    algorithm_input = AlgorithmInput(
        schema_version=1,
        image=ImagePayload(
            data=image_bytes,
            media_type=media_type,
            filename=image.filename or "upload",
        ),
        target=GridTarget(width=width, height=height),
        algorithm=AlgorithmIdentity(algorithm_id=algorithm, version=algorithm_version),
        params=params,
    )
    output = await processing_service.process(algorithm_input)
    data = GridData(
        version=output.schema_version,
        width=output.width,
        height=output.height,
        rgba_base64=base64.b64encode(output.rgba).decode("ascii"),
        algorithm=AlgorithmIdentityData(
            id=output.algorithm.algorithm_id,
            version=output.algorithm.version or "",
        ),
    )
    return success_response(request, data)
