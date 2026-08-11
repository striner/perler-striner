from dataclasses import dataclass

from python_backend.core.config import Settings


@dataclass(frozen=True, slots=True)
class GpuServingProfile:
    gpu_resources: float
    workers: int
    replicas: int
    max_concurrency: int
    queue_timeout_seconds: float
    max_batch_size: int
    max_batch_latency_ms: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "GpuServingProfile":
        return cls(
            gpu_resources=settings.gpu_resource_count,
            workers=settings.bento_workers,
            replicas=settings.bento_replicas,
            max_concurrency=settings.bento_max_concurrency,
            queue_timeout_seconds=settings.queue_timeout_seconds,
            max_batch_size=settings.max_batch_size,
            max_batch_latency_ms=settings.max_batch_latency_ms,
        )
