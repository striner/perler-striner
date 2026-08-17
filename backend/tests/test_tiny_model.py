from __future__ import annotations

import asyncio
import threading

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from python_backend.algorithms.contracts import (
    AlgorithmIdentity,
    AlgorithmInput,
    GridTarget,
    ImagePayload,
)
from python_backend.algorithms.errors import AlgorithmProcessingError, InvalidRequestError
from python_backend.algorithms.tiny_model.framing import normalize_subject_frame
from python_backend.algorithms.tiny_model.params import TinyModelParams, parse_params, parse_prompt
from python_backend.algorithms.tiny_model.pipeline import (
    _prepare_masks,
    _select_salient_candidate,
    run_pipeline,
)
from python_backend.algorithms.tiny_model.service import TinyModelService
from python_backend.algorithms.tiny_model.types import Detection, MaskCandidate
from python_backend.core.config import Settings
from python_backend.web.app import create_app


class FakeRuntime:
    def __init__(self, candidates: list[MaskCandidate]) -> None:
        self.candidates = candidates
        self.detect_calls = 0
        self.automatic_calls = 0
        self.thread_ids: list[int] = []

    def detect(self, image, prompts, confidence_threshold, max_instances):
        self.detect_calls += 1
        return [Detection((10, 10, 70, 70), 0.9, prompts[0])]

    def segment_boxes(self, image, detections):
        self.thread_ids.append(threading.get_ident())
        return self.candidates

    def automatic_masks(self, image):
        self.automatic_calls += 1
        self.thread_ids.append(threading.get_ident())
        return self.candidates


def _encoded_image() -> bytes:
    image = np.zeros((80, 100, 3), dtype=np.uint8)
    image[20:70, 30:80] = (40, 90, 210)
    success, encoded = cv2.imencode(".png", image)
    assert success
    return encoded.tobytes()


def _request(params=None) -> AlgorithmInput:
    return AlgorithmInput(
        schema_version=1,
        image=ImagePayload(_encoded_image(), "image/png", "subject.png"),
        target=GridTarget(20, 20),
        algorithm=AlgorithmIdentity("tiny_model", "1.0.0"),
        params=params or {},
    )


def _subject_candidate() -> MaskCandidate:
    mask = np.zeros((80, 100), dtype=np.uint8)
    mask[20:70, 30:80] = 1
    return MaskCandidate(mask, 0.95)


def test_prompt_parser_accepts_multiple_separators_and_enforces_limits() -> None:
    assert parse_prompt("person, cat，painting\ndog") == (
        "person",
        "cat",
        "painting",
        "dog",
    )
    assert parse_prompt("  ") == ()
    with pytest.raises(InvalidRequestError, match="at most 8"):
        parse_prompt(",".join(str(index) for index in range(9)))
    with pytest.raises(InvalidRequestError, match="64"):
        parse_prompt("x" * 65)
    with pytest.raises(InvalidRequestError, match="string"):
        parse_prompt(3)


def test_parameter_schema_defaults_and_unknown_values_are_controlled() -> None:
    params = parse_params({})
    assert params == TinyModelParams()
    with pytest.raises(InvalidRequestError, match="unsupported"):
        parse_params({"remove_background": False})
    with pytest.raises(InvalidRequestError, match="out of range"):
        parse_params({"max_instances": 6})


def test_subject_framing_trims_padding_without_distortion_or_cropping() -> None:
    image = np.zeros((100, 100, 3), dtype=np.uint8)
    image[20:80, 30:70] = (20, 80, 180)
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[20:80, 30:70] = 255

    framed_image, framed_mask = normalize_subject_frame(image, mask, 50, 50)
    points = cv2.findNonZero((framed_mask > 0).astype(np.uint8))
    assert points is not None
    x, y, width, height = cv2.boundingRect(points)
    assert framed_image.shape == (100, 100, 3)
    assert height == 100
    assert width in {66, 67}
    assert y == 0
    assert abs((x * 2 + width) - 100) <= 1
    assert width / height == pytest.approx(40 / 60, abs=0.02)


def test_subject_framing_keeps_an_already_full_frame_unchanged() -> None:
    image = np.full((40, 60, 3), 80, dtype=np.uint8)
    mask = np.full((40, 60), 255, dtype=np.uint8)
    framed_image, framed_mask = normalize_subject_frame(image, mask, 20, 20)
    assert np.array_equal(framed_image, image)
    assert np.array_equal(framed_mask, mask)


def test_mask_preparation_deduplicates_overlapping_instances() -> None:
    first = np.zeros((80, 100), dtype=np.uint8)
    first[20:70, 30:80] = 1
    duplicate = first.copy()
    duplicate[20:22, 30:32] = 0
    separate = np.zeros_like(first)
    separate[8:18, 8:18] = 1
    masks = _prepare_masks(
        [MaskCandidate(first, 0.9), MaskCandidate(duplicate, 0.8), MaskCandidate(separate, 0.7)],
        first.shape,
        20,
        20,
        0.7,
        5,
    )
    assert len(masks) == 2


def test_salient_selection_prefers_complete_subject_and_rejects_large_edge_background() -> None:
    face = np.zeros((100, 120), dtype=np.uint8)
    face[20:60, 45:75] = 1
    person = np.zeros_like(face)
    person[10:100, 25:120] = 1
    sky = np.zeros_like(face)
    sky[:45, :] = 1

    selected = _select_salient_candidate(
        [
            MaskCandidate(face, 0.99),
            MaskCandidate(person, 1.0),
            MaskCandidate(sky, 1.0),
        ],
        face.shape,
    )

    assert selected is not None
    assert np.array_equal(selected.mask, person.astype(bool))


def test_prompt_pipeline_returns_framed_rgba_grid() -> None:
    runtime = FakeRuntime([_subject_candidate()])
    output = run_pipeline(
        _request({"prompt": "person"}),
        parse_params({"prompt": "person"}),
        runtime,
        max_decoded_pixels=1_000_000,
        work_max_edge=256,
    )
    rgba = np.frombuffer(output.rgba, dtype=np.uint8).reshape(20, 20, 4)
    assert runtime.detect_calls == 1
    assert runtime.automatic_calls == 0
    assert np.count_nonzero(rgba[:, :, 3]) > 200
    assert np.count_nonzero(rgba[:, 0, 3]) + np.count_nonzero(rgba[:, -1, 3]) > 0


def test_empty_prompt_uses_automatic_candidates_and_rejects_empty_results() -> None:
    runtime = FakeRuntime([_subject_candidate()])
    output = run_pipeline(
        _request(),
        TinyModelParams(),
        runtime,
        max_decoded_pixels=1_000_000,
        work_max_edge=256,
    )
    assert len(output.rgba) == 20 * 20 * 4
    assert runtime.automatic_calls == 1

    with pytest.raises(AlgorithmProcessingError, match="reliable subject"):
        run_pipeline(
            _request(),
            TinyModelParams(),
            FakeRuntime([]),
            max_decoded_pixels=1_000_000,
            work_max_edge=256,
        )


def test_unavailable_tiny_model_is_exposed_and_returns_standard_error() -> None:
    settings = Settings(tiny_model_enabled=False, max_upload_bytes=1_000_000)
    app = create_app(settings=settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        capabilities = client.get("/api/v1/algorithms").json()["data"]["items"]
        response = client.post(
            "/api/v1/process",
            files={"image": ("subject.png", _encoded_image(), "image/png")},
            data={
                "width": "20",
                "height": "20",
                "algorithm": "tiny_model",
                "algorithm_version": "1.0.0",
                "algorithm_params": '{"prompt":"person"}',
            },
        )
    capability = next(item for item in capabilities if item["id"] == "tiny_model")
    assert capability["available"] is False
    assert capability["unavailable_reason"] == "tiny-model runtime is disabled"
    assert response.status_code == 503
    assert response.json()["exec"] == "AlgorithmUnavailableError"


def test_service_runs_model_pipeline_outside_event_loop() -> None:
    runtime = FakeRuntime([_subject_candidate()])
    service = TinyModelService(
        runtime=runtime,
        unavailable_reason=None,
        max_decoded_pixels=1_000_000,
        work_max_edge=256,
        max_concurrency=1,
        queue_timeout_seconds=1,
    )

    async def execute() -> tuple[int, int]:
        event_loop_thread = threading.get_ident()
        await service.process(_request({"prompt": "person"}))
        return event_loop_thread, runtime.thread_ids[0]

    event_loop_thread, worker_thread = asyncio.run(execute())
    assert worker_thread != event_loop_thread
