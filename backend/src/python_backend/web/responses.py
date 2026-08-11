from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from python_backend.schemas.envelope import Envelope, ResponseMeta


def _meta(request: Request) -> ResponseMeta:
    accept_id = getattr(request.state, "accept_id", str(uuid.uuid4()))
    started_at = getattr(request.state, "started_at", time.perf_counter())
    elapsed_ms = max(0.0, (time.perf_counter() - started_at) * 1000)
    return ResponseMeta(accept_id=accept_id, perf_time_use=round(elapsed_ms, 3))


def envelope_response(
    request: Request,
    *,
    status_code: int,
    message: str,
    data: Any = None,
    error: Exception | None = None,
) -> JSONResponse:
    envelope = Envelope[Any](
        code=status_code,
        msg=message,
        data=data,
        exec=error.__class__.__name__ if error is not None else None,
        meta=_meta(request),
    )
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(envelope.model_dump()),
    )


def success_response(request: Request, data: Any, message: str = "success") -> JSONResponse:
    return envelope_response(
        request,
        status_code=200,
        message=message,
        data=data,
    )
