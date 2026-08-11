from __future__ import annotations

from typing import Any

from python_backend.algorithms.contracts import (
    AlgorithmDescriptor,
    AlgorithmIdentity,
    AlgorithmInput,
    AlgorithmOutput,
)


class FakeAlgorithm:
    def __init__(
        self,
        algorithm_id: str,
        version: str,
        rgba: tuple[int, int, int, int],
        *,
        is_default: bool = False,
        invalid_length: bool = False,
    ) -> None:
        self._descriptor = AlgorithmDescriptor(
            algorithm_id=algorithm_id,
            version=version,
            parameter_schema={"type": "object"},
            is_default=is_default,
            requires_gpu=True,
            supports_batching=True,
            removes_background=True,
        )
        self.rgba = rgba
        self.invalid_length = invalid_length
        self.last_params: dict[str, Any] | None = None

    @property
    def descriptor(self) -> AlgorithmDescriptor:
        return self._descriptor

    async def process(self, request: AlgorithmInput) -> AlgorithmOutput:
        self.last_params = dict(request.params)
        pixel_count = request.target.width * request.target.height
        rgba = bytes(self.rgba) * pixel_count
        if self.invalid_length:
            rgba = rgba[:-1]
        return AlgorithmOutput(
            schema_version=request.schema_version,
            algorithm=AlgorithmIdentity(
                algorithm_id=self.descriptor.algorithm_id,
                version=self.descriptor.version,
            ),
            width=request.target.width,
            height=request.target.height,
            rgba=rgba,
        )
