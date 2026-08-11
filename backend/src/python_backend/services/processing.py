from __future__ import annotations

import asyncio

from python_backend.algorithms.contracts import AlgorithmInput, AlgorithmOutput
from python_backend.algorithms.errors import AlgorithmTimeoutError
from python_backend.algorithms.registry import AlgorithmRegistry
from python_backend.algorithms.validation import validate_algorithm_output


class ProcessingService:
    def __init__(self, registry: AlgorithmRegistry, timeout_seconds: float) -> None:
        self.registry = registry
        self.timeout_seconds = timeout_seconds

    async def process(self, request: AlgorithmInput) -> AlgorithmOutput:
        algorithm = self.registry.resolve(
            request.algorithm.algorithm_id,
            request.algorithm.version,
        )
        try:
            output = await asyncio.wait_for(
                algorithm.process(request),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as error:
            raise AlgorithmTimeoutError() from error
        validate_algorithm_output(request, output)
        return output
