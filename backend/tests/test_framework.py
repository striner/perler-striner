import pytest

from python_backend.algorithms.contracts import AlgorithmDescriptor
from python_backend.algorithms.registry import AlgorithmRegistry
from python_backend.core.config import Settings
from python_backend.serving.config import GpuServingProfile
from tests.fakes import FakeAlgorithm


def test_registry_rejects_algorithms_that_do_not_remove_background() -> None:
    algorithm = FakeAlgorithm("subject-grid", "1.0.0", (0, 0, 0, 0))
    algorithm._descriptor = AlgorithmDescriptor(
        algorithm_id="subject-grid",
        version="1.0.0",
        removes_background=False,
    )
    with pytest.raises(ValueError, match="remove backgrounds"):
        AlgorithmRegistry([algorithm])


def test_gpu_serving_profile_maps_framework_configuration() -> None:
    settings = Settings(
        gpu_resource_count=2,
        bento_workers=3,
        bento_replicas=4,
        bento_max_concurrency=24,
        queue_timeout_seconds=7,
        max_batch_size=6,
        max_batch_latency_ms=40,
    )
    profile = GpuServingProfile.from_settings(settings)
    assert profile.gpu_resources == 2
    assert profile.workers == 3
    assert profile.replicas == 4
    assert profile.max_concurrency == 24
    assert profile.queue_timeout_seconds == 7
    assert profile.max_batch_size == 6
    assert profile.max_batch_latency_ms == 40
