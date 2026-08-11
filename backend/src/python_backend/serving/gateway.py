from typing import Protocol

from python_backend.algorithms.contracts import AlgorithmInput, AlgorithmOutput


class AlgorithmGateway(Protocol):
    """Boundary implemented by a future BentoML algorithm service handle."""

    async def process(self, request: AlgorithmInput) -> AlgorithmOutput: ...
