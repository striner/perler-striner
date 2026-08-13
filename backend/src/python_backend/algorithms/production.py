from python_backend.algorithms.registry import AlgorithmRegistry
from python_backend.core.config import Settings


def build_production_registry(settings: Settings) -> AlgorithmRegistry:
    from python_backend.algorithms.cv_native import CvNativeService

    return AlgorithmRegistry(
        [
            CvNativeService(
                max_decoded_pixels=settings.max_decoded_pixels,
                work_max_edge=settings.cv_work_max_edge,
                max_concurrency=settings.cv_max_concurrency,
                opencv_threads=settings.cv_opencv_threads,
                queue_timeout_seconds=settings.queue_timeout_seconds,
            )
        ]
    )
