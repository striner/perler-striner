from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from python_backend.algorithms.contracts import AlgorithmDescriptor, AlgorithmInput, AlgorithmOutput
from python_backend.algorithms.errors import AlgorithmUnavailableError, BackendBusyError
from python_backend.core.config import Settings

from .descriptor import build_descriptor
from .model_store import ModelStore, ModelStoreError
from .params import parse_params
from .pipeline import run_pipeline
from .runtime import RuntimeInitializationError, UltralyticsRuntime, validate_device
from .types import InferenceRuntime

LOGGER = logging.getLogger(__name__)


class TinyModelService:
    def __init__(
        self,
        *,
        runtime: InferenceRuntime | None,
        unavailable_reason: str | None,
        max_decoded_pixels: int,
        work_max_edge: int,
        max_concurrency: int,
        queue_timeout_seconds: float,
    ) -> None:
        self.runtime = runtime
        self.unavailable_reason = unavailable_reason
        self.max_decoded_pixels = max_decoded_pixels
        self.work_max_edge = work_max_edge
        self.queue_timeout_seconds = queue_timeout_seconds
        self._descriptor = build_descriptor(
            available=runtime is not None,
            unavailable_reason=unavailable_reason,
        )
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrency,
            thread_name_prefix="tiny-model",
        )

    @property
    def descriptor(self) -> AlgorithmDescriptor:
        return self._descriptor

    async def process(self, request: AlgorithmInput) -> AlgorithmOutput:
        params = parse_params(request.params)
        if self.runtime is None:
            raise AlgorithmUnavailableError(self.unavailable_reason)
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self.queue_timeout_seconds,
            )
        except TimeoutError as error:
            raise BackendBusyError() from error

        try:
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(
                self._executor,
                run_pipeline,
                request,
                params,
                self.runtime,
                self.max_decoded_pixels,
                self.work_max_edge,
            )
        except Exception:
            self._semaphore.release()
            raise

        future.add_done_callback(lambda _future: self._semaphore.release())
        return await asyncio.shield(future)


def build_tiny_model_service(settings: Settings) -> TinyModelService:
    runtime: InferenceRuntime | None = None
    reason: str | None = None
    if not settings.tiny_model_enabled:
        reason = "tiny-model runtime is disabled"
    else:
        try:
            validate_device(settings.tiny_model_device)
            runtime = UltralyticsRuntime(
                ModelStore(settings.tiny_model_dir),
                settings.tiny_model_device,
                warmup=settings.tiny_model_warmup,
            )
        except (ModelStoreError, RuntimeInitializationError) as error:
            reason = str(error)
        except Exception:
            LOGGER.exception("tiny-model initialization failed")
            reason = "tiny-model initialization failed"
    return TinyModelService(
        runtime=runtime,
        unavailable_reason=reason,
        max_decoded_pixels=settings.max_decoded_pixels,
        work_max_edge=settings.tiny_model_work_max_edge,
        max_concurrency=settings.tiny_model_max_concurrency,
        queue_timeout_seconds=settings.queue_timeout_seconds,
    )
