from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import cv2

from python_backend.algorithms.contracts import AlgorithmDescriptor, AlgorithmInput, AlgorithmOutput
from python_backend.algorithms.errors import BackendBusyError

from .descriptor import DESCRIPTOR
from .params import parse_params
from .pipeline import run_pipeline


class CvNativeService:
    def __init__(
        self,
        *,
        max_decoded_pixels: int,
        work_max_edge: int,
        max_concurrency: int,
        opencv_threads: int,
        queue_timeout_seconds: float,
    ) -> None:
        self.max_decoded_pixels = max_decoded_pixels
        self.work_max_edge = work_max_edge
        self.queue_timeout_seconds = queue_timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrency,
            thread_name_prefix="cv-native",
        )
        cv2.setNumThreads(opencv_threads)

    @property
    def descriptor(self) -> AlgorithmDescriptor:
        return DESCRIPTOR

    async def process(self, request: AlgorithmInput) -> AlgorithmOutput:
        params = parse_params(request.params)
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
                self.max_decoded_pixels,
                self.work_max_edge,
            )
        except Exception:
            self._semaphore.release()
            raise

        # Cancellation cannot stop an OpenCV thread. Keep its permit until the native work exits.
        future.add_done_callback(lambda _future: self._semaphore.release())
        return await asyncio.shield(future)
