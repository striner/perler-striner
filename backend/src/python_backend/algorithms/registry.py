from __future__ import annotations

from collections.abc import Iterable

from .contracts import AlgorithmDescriptor, AlgorithmService
from .errors import AlgorithmNotImplementedError, AlgorithmVersionAmbiguousError


class AlgorithmRegistry:
    def __init__(self, services: Iterable[AlgorithmService] = ()) -> None:
        self._services: dict[tuple[str, str], AlgorithmService] = {}
        for service in services:
            self.register(service)

    def register(self, service: AlgorithmService) -> None:
        descriptor = service.descriptor
        key = (descriptor.algorithm_id, descriptor.version)
        if key in self._services:
            raise ValueError(
                f"algorithm already registered: {descriptor.algorithm_id}@{descriptor.version}"
            )
        if not descriptor.removes_background:
            raise ValueError("registered algorithms must remove backgrounds")
        self._services[key] = service

    def resolve(self, algorithm_id: str, version: str | None) -> AlgorithmService:
        if version is not None:
            service = self._services.get((algorithm_id, version))
            if service is None:
                raise AlgorithmNotImplementedError()
            return service

        candidates = [
            service
            for (registered_id, _), service in self._services.items()
            if registered_id == algorithm_id
        ]
        if not candidates:
            raise AlgorithmNotImplementedError()

        defaults = [service for service in candidates if service.descriptor.is_default]
        if len(defaults) == 1:
            return defaults[0]
        if len(candidates) == 1:
            return candidates[0]
        raise AlgorithmVersionAmbiguousError()

    def descriptors(self) -> list[AlgorithmDescriptor]:
        return sorted(
            (service.descriptor for service in self._services.values()),
            key=lambda descriptor: (descriptor.algorithm_id, descriptor.version),
        )
