from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from python_backend.algorithms.errors import BackendError
from python_backend.web.responses import envelope_response

logger = logging.getLogger(__name__)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BackendError)
    async def backend_error_handler(request: Request, error: BackendError):
        logger.warning(
            "Backend request failed accept_id=%s type=%s message=%s",
            getattr(request.state, "accept_id", "unknown"),
            error.__class__.__name__,
            error.public_message,
        )
        return envelope_response(
            request,
            status_code=error.status_code,
            message=error.public_message,
            error=error,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, error: RequestValidationError):
        return envelope_response(
            request,
            status_code=422,
            message="request validation failed",
            error=error,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, error: StarletteHTTPException):
        message = error.detail if isinstance(error.detail, str) else "http request failed"
        return envelope_response(
            request,
            status_code=error.status_code,
            message=message,
            error=error,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception):
        logger.exception(
            "Unhandled backend error accept_id=%s type=%s",
            getattr(request.state, "accept_id", "unknown"),
            error.__class__.__name__,
        )
        return envelope_response(
            request,
            status_code=500,
            message="internal server error",
            error=error,
        )
