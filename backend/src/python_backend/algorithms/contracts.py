from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ImagePayload:
    data: bytes
    media_type: str
    filename: str


@dataclass(frozen=True, slots=True)
class GridTarget:
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class AlgorithmIdentity:
    algorithm_id: str
    version: str | None = None


@dataclass(frozen=True, slots=True)
class AlgorithmInput:
    schema_version: int
    image: ImagePayload
    target: GridTarget
    algorithm: AlgorithmIdentity
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AlgorithmOutput:
    schema_version: int
    algorithm: AlgorithmIdentity
    width: int
    height: int
    rgba: bytes


@dataclass(frozen=True, slots=True)
class AlgorithmDescriptor:
    algorithm_id: str
    version: str
    parameter_schema: Mapping[str, Any] = field(default_factory=dict)
    is_default: bool = False
    requires_gpu: bool = True
    supports_batching: bool = True
    removes_background: bool = True
    available: bool = True
    unavailable_reason: str | None = None


@runtime_checkable
class AlgorithmService(Protocol):
    @property
    def descriptor(self) -> AlgorithmDescriptor: ...

    async def process(self, request: AlgorithmInput) -> AlgorithmOutput: ...
