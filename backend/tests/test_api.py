from __future__ import annotations

import base64
import uuid

from fastapi.testclient import TestClient

from python_backend.algorithms.registry import AlgorithmRegistry
from python_backend.core.config import Settings
from python_backend.web.app import create_app
from tests.fakes import FakeAlgorithm


def make_settings(**overrides) -> Settings:
    values = {
        "cors_origins": "http://localhost:8082",
        "max_upload_bytes": 1024,
        "max_grid_size": 150,
        "request_timeout_seconds": 2,
        "queue_timeout_seconds": 1,
    }
    values.update(overrides)
    return Settings(**values)


def client_for(registry: AlgorithmRegistry | None = None, **settings) -> TestClient:
    active_registry = registry if registry is not None else AlgorithmRegistry()
    app = create_app(settings=make_settings(**settings), registry=active_registry)
    return TestClient(app, raise_server_exceptions=False)


def processing_request(**overrides):
    data = {
        "width": "2",
        "height": "1",
        "algorithm": "subject-grid",
        "algorithm_version": "1.0.0",
        "algorithm_params": '{"quality":"balanced"}',
    }
    data.update(overrides)
    return {
        "files": {"image": ("source.png", b"image-content", "image/png")},
        "data": data,
    }


def assert_envelope(payload: dict, code: int) -> None:
    assert set(payload) == {"code", "msg", "data", "exec", "meta"}
    assert payload["code"] == code
    uuid.UUID(payload["meta"]["accept_id"])
    assert payload["meta"]["perf_time_use"] >= 0


def test_health_and_empty_algorithm_capabilities() -> None:
    with client_for() as client:
        health = client.get("/health")
        algorithms = client.get("/api/v1/algorithms")

    assert health.status_code == 200
    assert_envelope(health.json(), 200)
    assert health.json()["data"] == {"status": "ok", "registered_algorithms": 0}
    assert algorithms.status_code == 200
    assert algorithms.json()["data"] == {"items": []}


def test_configured_cors_origin_is_allowed() -> None:
    with client_for(cors_origins="http://127.0.0.1:4321") as client:
        response = client.options(
            "/api/v1/process",
            headers={
                "Origin": "http://127.0.0.1:4321",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:4321"


def test_production_registry_returns_not_implemented_envelope() -> None:
    with client_for() as client:
        response = client.post("/api/v1/process", **processing_request())

    assert response.status_code == 501
    payload = response.json()
    assert_envelope(payload, 501)
    assert payload["data"] is None
    assert payload["exec"] == "AlgorithmNotImplementedError"


def test_registered_fake_algorithm_uses_shared_contract() -> None:
    algorithm = FakeAlgorithm("subject-grid", "1.0.0", (10, 20, 30, 0), is_default=True)
    registry = AlgorithmRegistry([algorithm])
    with client_for(registry) as client:
        response = client.post("/api/v1/process", **processing_request())

    assert response.status_code == 200
    payload = response.json()
    assert_envelope(payload, 200)
    assert payload["exec"] is None
    assert payload["data"]["algorithm"] == {"id": "subject-grid", "version": "1.0.0"}
    assert base64.b64decode(payload["data"]["rgba_base64"]) == bytes([10, 20, 30, 0]) * 2
    assert algorithm.last_params == {"quality": "balanced"}


def test_default_version_routes_between_two_shared_contract_algorithms() -> None:
    first = FakeAlgorithm("subject-grid", "1.0.0", (1, 2, 3, 0))
    second = FakeAlgorithm("subject-grid", "2.0.0", (4, 5, 6, 0), is_default=True)
    registry = AlgorithmRegistry([first, second])
    request = processing_request()
    request["data"].pop("algorithm_version")

    with client_for(registry) as client:
        response = client.post("/api/v1/process", **request)

    assert response.status_code == 200
    assert response.json()["data"]["algorithm"]["version"] == "2.0.0"
    assert second.last_params == {"quality": "balanced"}
    assert first.last_params is None


def test_invalid_algorithm_output_is_rejected() -> None:
    invalid = FakeAlgorithm(
        "subject-grid",
        "1.0.0",
        (1, 2, 3, 0),
        invalid_length=True,
    )
    with client_for(AlgorithmRegistry([invalid])) as client:
        response = client.post("/api/v1/process", **processing_request())

    assert response.status_code == 502
    assert response.json()["exec"] == "AlgorithmContractError"


def test_non_contract_algorithm_output_is_rejected() -> None:
    invalid = FakeAlgorithm("subject-grid", "1.0.0", (1, 2, 3, 0))

    async def return_invalid(_request):
        return None

    invalid.process = return_invalid
    with client_for(AlgorithmRegistry([invalid])) as client:
        response = client.post("/api/v1/process", **processing_request())

    assert response.status_code == 502
    assert response.json()["exec"] == "AlgorithmContractError"


def test_removed_background_parameter_is_rejected() -> None:
    request = processing_request(remove_background="false")
    with client_for() as client:
        response = client.post("/api/v1/process", **request)
    assert response.status_code == 422
    assert response.json()["exec"] == "InvalidRequestError"


def test_background_control_is_rejected_inside_algorithm_params() -> None:
    request = processing_request(algorithm_params='{"nested":{"removeBackground":false}}')
    with client_for() as client:
        response = client.post("/api/v1/process", **request)
    assert response.status_code == 422
    assert response.json()["exec"] == "InvalidRequestError"


def test_non_finite_algorithm_parameter_is_rejected() -> None:
    request = processing_request(algorithm_params='{"threshold":NaN}')
    with client_for() as client:
        response = client.post("/api/v1/process", **request)
    assert response.status_code == 422
    assert response.json()["exec"] == "InvalidRequestError"


def test_validation_errors_use_the_envelope() -> None:
    with client_for() as client:
        response = client.post(
            "/api/v1/process",
            data={"width": "1", "height": "1", "algorithm": "subject-grid"},
        )
    assert response.status_code == 422
    assert_envelope(response.json(), 422)
    assert response.json()["exec"] == "RequestValidationError"


def test_upload_limit_is_enforced_without_persistence() -> None:
    request = processing_request()
    request["files"] = {"image": ("large.png", b"12345", "image/png")}
    with client_for(max_upload_bytes=4) as client:
        response = client.post("/api/v1/process", **request)
    assert response.status_code == 413
    assert response.json()["exec"] == "UploadTooLargeError"
