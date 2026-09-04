from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from python_backend.algorithms.contracts import (
    AlgorithmAnalysisInput,
    AlgorithmAnalysisOutput,
    AlgorithmDescriptor,
    AlgorithmInput,
    AlgorithmOutput,
)
from python_backend.algorithms.errors import (
    AlgorithmUnavailableError,
    BackendBusyError,
    InvalidRequestError,
)
from python_backend.core.config import Settings

from .analysis import run_analysis
from .analysis_token import AnalysisTokenSigner
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
        analysis_confidence: float,
        analysis_max_objects: int,
        token_signer: AnalysisTokenSigner,
    ) -> None:
        self.runtime = runtime
        self.unavailable_reason = unavailable_reason
        self.max_decoded_pixels = max_decoded_pixels
        self.work_max_edge = work_max_edge
        self.queue_timeout_seconds = queue_timeout_seconds
        self.analysis_confidence = analysis_confidence
        self.analysis_max_objects = analysis_max_objects
        self.token_signer = token_signer
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

    async def analyze(self, request: AlgorithmAnalysisInput) -> AlgorithmAnalysisOutput:
        runtime = self._require_runtime()
        return await self._execute(
            run_analysis,
            request,
            runtime,
            self.token_signer,
            self.max_decoded_pixels,
            self.work_max_edge,
            self.analysis_confidence,
            self.analysis_max_objects,
        )

    async def process(self, request: AlgorithmInput) -> AlgorithmOutput:
        runtime = self._require_runtime()
        params = parse_params(request.params)
        token_objects = self.token_signer.verify(params.analysis_token, request.image.data)
        by_id = {item.object_id: item for item in token_objects}
        try:
            selected = [by_id[object_id] for object_id in params.selected_object_ids]
        except KeyError as error:
            raise InvalidRequestError("selected object is not present in analysis token") from error
        return await self._execute(
            run_pipeline,
            request,
            params,
            runtime,
            selected,
            self.max_decoded_pixels,
            self.work_max_edge,
        )

    def _require_runtime(self) -> InferenceRuntime:
        if self.runtime is None:
            raise AlgorithmUnavailableError(self.unavailable_reason)
        return self.runtime

    async def _execute(self, function: Callable[..., Any], *args: Any):
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self.queue_timeout_seconds,
            )
        except TimeoutError as error:
            raise BackendBusyError() from error

        try:
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(self._executor, function, *args)
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
        analysis_confidence=settings.tiny_model_analysis_confidence,
        analysis_max_objects=settings.tiny_model_analysis_max_objects,
        token_signer=AnalysisTokenSigner(
            settings.tiny_model_analysis_token_secret,
            settings.tiny_model_analysis_token_ttl_seconds,
        ),
    )
