from __future__ import annotations

import asyncio
import time
import uuid

from fastapi import FastAPI, Request

from python_backend.algorithms.errors import BackendBusyError
from python_backend.core.config import Settings
from python_backend.web.responses import envelope_response


def install_request_middleware(app: FastAPI, settings: Settings) -> None:
    semaphore = asyncio.Semaphore(settings.max_inflight_requests)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.accept_id = str(uuid.uuid4())
        request.state.started_at = time.perf_counter()
        acquired = False
        try:
            await asyncio.wait_for(
                semaphore.acquire(),
                timeout=settings.queue_timeout_seconds,
            )
            acquired = True
        except TimeoutError:
            error = BackendBusyError()
            return envelope_response(
                request,
                status_code=error.status_code,
                message=error.public_message,
                error=error,
            )

        try:
            return await call_next(request)
        finally:
            if acquired:
                semaphore.release()
