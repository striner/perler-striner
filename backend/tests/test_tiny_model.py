from __future__ import annotations

import asyncio
import threading
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from python_backend.algorithms.contracts import (
    AlgorithmAnalysisInput,
    AlgorithmIdentity,
    AlgorithmInput,
    GridTarget,
    ImagePayload,
)
from python_backend.algorithms.errors import (
    AlgorithmProcessingError,
    InvalidRequestError,
)
from python_backend.algorithms.registry import AlgorithmRegistry
from python_backend.algorithms.tiny_model.analysis import run_analysis
from python_backend.algorithms.tiny_model.analysis_token import AnalysisTokenSigner
from python_backend.algorithms.tiny_model.framing import normalize_subject_frame
from python_backend.algorithms.tiny_model.params import TinyModelParams, parse_params
from python_backend.algorithms.tiny_model.pipeline import _prepare_masks, run_pipeline
from python_backend.algorithms.tiny_model.quantize import (
    quantize_foreground,
    snap_rgba_to_palette,
)
from python_backend.algorithms.tiny_model.service import TinyModelService
from python_backend.algorithms.tiny_model.types import Detection, MaskCandidate
from python_backend.core.config import Settings
from python_backend.web.app import create_app


class FakeRuntime:
    def __init__(
        self,
        detections: list[Detection] | None = None,
        candidates: list[MaskCandidate] | None = None,
    ) -> None:
        self.detections = detections if detections is not None else [_detection()]
        self.candidates = candidates if candidates is not None else [_subject_candidate()]
        self.analyze_calls = 0
        self.segment_calls = 0
        self.stylize_calls = 0
        self.thread_ids: list[int] = []
        self.last_detections: list[Detection] = []

    def analyze(self, image, confidence_threshold, max_objects):
        self.analyze_calls += 1
        self.thread_ids.append(threading.get_ident())
        return self.detections[:max_objects]

    def segment_boxes(self, image, detections):
        self.segment_calls += 1
        self.thread_ids.append(threading.get_ident())
        self.last_detections = detections
        return self.candidates[: len(detections)]

    def stylize(self, image, mask):
        self.stylize_calls += 1
        return image.copy()


def _encoded_image() -> bytes:
    image = np.zeros((80, 100, 3), dtype=np.uint8)
    image[20:70, 30:80] = (40, 90, 210)
    success, encoded = cv2.imencode(".png", image)
    assert success
    return encoded.tobytes()


def _payload(image_data: bytes | None = None) -> ImagePayload:
    return ImagePayload(image_data or _encoded_image(), "image/png", "subject.png")


def _analysis_request(image_data: bytes | None = None) -> AlgorithmAnalysisInput:
    return AlgorithmAnalysisInput(
        schema_version=1,
        image=_payload(image_data),
        algorithm=AlgorithmIdentity("tiny_model", "1.0.0"),
    )


def _process_request(params: dict, image_data: bytes | None = None) -> AlgorithmInput:
    return AlgorithmInput(
        schema_version=1,
        image=_payload(image_data),
        target=GridTarget(20, 20),
        algorithm=AlgorithmIdentity("tiny_model", "1.0.0"),
        params=params,
    )


def _detection(
    box: tuple[float, float, float, float] = (30, 20, 80, 70),
    *,
    score: float = 0.95,
    type_id: int = 0,
    type_name_en: str = "person",
    salience: float = 0.9,
) -> Detection:
    return Detection(box, score, type_id, type_name_en, salience)


def _subject_candidate() -> MaskCandidate:
    mask = np.zeros((80, 100), dtype=np.uint8)
    mask[20:70, 30:80] = 1
    return MaskCandidate(mask, 0.95)


def _service(runtime: FakeRuntime | None) -> TinyModelService:
    return TinyModelService(
        runtime=runtime,
        unavailable_reason=None if runtime else "tiny-model runtime is disabled",
        max_decoded_pixels=1_000_000,
        work_max_edge=256,
        max_concurrency=1,
        queue_timeout_seconds=1,
        analysis_confidence=0.15,
        analysis_max_objects=24,
        token_signer=AnalysisTokenSigner("test-secret-value", 900),
    )


def test_parameter_schema_requires_analysis_and_unique_selected_objects() -> None:
    params = parse_params(
        {
            "analysis_token": "signed-token",
            "selected_object_ids": ["object_1", "object_2"],
        }
    )
    assert params == TinyModelParams("signed-token", ("object_1", "object_2"))
    assert params.max_colors == 16

    with pytest.raises(InvalidRequestError, match="analysis_token"):
        parse_params({"selected_object_ids": ["object_1"]})
    with pytest.raises(InvalidRequestError, match="1 to 24"):
        parse_params({"analysis_token": "token", "selected_object_ids": []})
    with pytest.raises(InvalidRequestError, match="duplicates"):
        parse_params(
            {
                "analysis_token": "token",
                "selected_object_ids": ["object_1", "object_1"],
            }
        )
    with pytest.raises(InvalidRequestError, match="unsupported"):
        parse_params(
            {
                "analysis_token": "token",
                "selected_object_ids": ["object_1"],
                "prompt": "person",
            }
        )
    assert (
        parse_params(
            {
                "analysis_token": "token",
                "selected_object_ids": ["object_1"],
                "max_colors": 20,
            }
        ).max_colors
        == 20
    )
    with pytest.raises(InvalidRequestError, match="out of range"):
        parse_params(
            {
                "analysis_token": "token",
                "selected_object_ids": ["object_1"],
                "max_colors": 21,
            }
        )


def test_analysis_normalizes_boxes_and_defaults_to_salience_order() -> None:
    runtime = FakeRuntime(
        detections=[
            _detection(),
            _detection(
                (5, 8, 25, 28),
                score=0.7,
                type_id=4,
                type_name_en="cat",
                salience=0.4,
            ),
        ]
    )
    signer = AnalysisTokenSigner("test-secret-value", 900)
    output = run_analysis(
        _analysis_request(),
        runtime,
        signer,
        max_decoded_pixels=1_000_000,
        work_max_edge=256,
        confidence_threshold=0.15,
        max_objects=24,
    )

    assert output.algorithm == AlgorithmIdentity("tiny_model", "1.0.0")
    assert (output.image_width, output.image_height) == (100, 80)
    assert [item.object_id for item in output.objects] == ["object_1", "object_2"]
    assert output.objects[0].type_name_en == "person"
    assert output.objects[0].bbox.x == pytest.approx(0.3)
    assert output.objects[0].bbox.y == pytest.approx(0.25)
    assert output.objects[0].bbox.width == pytest.approx(0.5)
    assert output.objects[0].bbox.height == pytest.approx(0.625)
    verified = signer.verify(output.analysis_token, _encoded_image())
    assert [item.object_id for item in verified] == ["object_1", "object_2"]


def test_analysis_rejects_an_empty_object_result() -> None:
    with pytest.raises(AlgorithmProcessingError, match="reliable entity"):
        run_analysis(
            _analysis_request(),
            FakeRuntime(detections=[]),
            AnalysisTokenSigner("test-secret-value", 900),
            max_decoded_pixels=1_000_000,
            work_max_edge=256,
            confidence_threshold=0.15,
            max_objects=24,
        )


def test_analysis_token_rejects_tampering_wrong_image_and_expiry() -> None:
    signer = AnalysisTokenSigner("test-secret-value", 30)
    token, objects = signer.issue(_encoded_image(), [_detection((0.3, 0.25, 0.8, 0.875))], 100, 80)
    assert signer.verify(token, _encoded_image()) == objects

    encoded, signature = token.split(".")
    tampered = f"{encoded[:-1]}A.{signature}"
    with pytest.raises(InvalidRequestError, match="invalid"):
        signer.verify(tampered, _encoded_image())
    with pytest.raises(InvalidRequestError, match="invalid"):
        signer.verify(token, b"different-image")
    with patch("python_backend.algorithms.tiny_model.analysis_token.time.time", return_value=0):
        expired_token, _ = signer.issue(_encoded_image(), [_detection()], 100, 80)
    with patch("python_backend.algorithms.tiny_model.analysis_token.time.time", return_value=31):
        with pytest.raises(InvalidRequestError, match="invalid"):
            signer.verify(expired_token, _encoded_image())


def test_selected_object_pipeline_returns_framed_rgba_grid() -> None:
    image_data = _encoded_image()
    signer = AnalysisTokenSigner("test-secret-value", 900)
    token, objects = signer.issue(
        image_data,
        [_detection((0.3, 0.25, 0.8, 0.875))],
        100,
        80,
    )
    runtime = FakeRuntime()
    params = parse_params({"analysis_token": token, "selected_object_ids": ["object_1"]})
    output = run_pipeline(
        _process_request({"analysis_token": token, "selected_object_ids": ["object_1"]}),
        params,
        runtime,
        objects,
        max_decoded_pixels=1_000_000,
        work_max_edge=256,
    )
    rgba = np.frombuffer(output.rgba, dtype=np.uint8).reshape(20, 20, 4)
    assert runtime.segment_calls == 1
    assert runtime.stylize_calls == 1
    assert runtime.last_detections[0].box == pytest.approx((30, 20, 80, 70))
    assert np.count_nonzero(rgba[:, :, 3]) > 200


def test_pipeline_merges_multiple_selected_instances_and_rejects_empty_masks() -> None:
    image_data = _encoded_image()
    signer = AnalysisTokenSigner("test-secret-value", 900)
    token, objects = signer.issue(
        image_data,
        [
            _detection((0.3, 0.25, 0.55, 0.875)),
            _detection(
                (0.6, 0.25, 0.8, 0.875),
                type_id=4,
                type_name_en="cat",
            ),
        ],
        100,
        80,
    )
    first = np.zeros((80, 100), dtype=np.uint8)
    first[20:70, 30:55] = 1
    second = np.zeros_like(first)
    second[20:70, 60:80] = 1
    params = parse_params(
        {
            "analysis_token": token,
            "selected_object_ids": ["object_1", "object_2"],
        }
    )
    output = run_pipeline(
        _process_request(
            {
                "analysis_token": token,
                "selected_object_ids": ["object_1", "object_2"],
            }
        ),
        params,
        FakeRuntime(candidates=[MaskCandidate(first, 0.9), MaskCandidate(second, 0.8)]),
        objects,
        max_decoded_pixels=1_000_000,
        work_max_edge=256,
    )
    assert len(output.rgba) == 20 * 20 * 4

    with pytest.raises(AlgorithmProcessingError, match="reliable subject"):
        run_pipeline(
            _process_request({"analysis_token": token, "selected_object_ids": ["object_1"]}),
            parse_params({"analysis_token": token, "selected_object_ids": ["object_1"]}),
            FakeRuntime(candidates=[]),
            objects[:1],
            max_decoded_pixels=1_000_000,
            work_max_edge=256,
        )


def test_service_rejects_unknown_selected_object_and_wrong_image() -> None:
    runtime = FakeRuntime()
    service = _service(runtime)
    image_data = _encoded_image()
    analysis = asyncio.run(service.analyze(_analysis_request(image_data)))

    with pytest.raises(InvalidRequestError, match="not present"):
        asyncio.run(
            service.process(
                _process_request(
                    {
                        "analysis_token": analysis.analysis_token,
                        "selected_object_ids": ["object_99"],
                    },
                    image_data,
                )
            )
        )
    with pytest.raises(InvalidRequestError, match="invalid"):
        asyncio.run(
            service.process(
                _process_request(
                    {
                        "analysis_token": analysis.analysis_token,
                        "selected_object_ids": ["object_1"],
                    },
                    b"different-image",
                )
            )
        )


def test_foreground_quantization_is_deterministic_and_respects_color_budget() -> None:
    yy, xx = np.indices((64, 80))
    image = np.stack(
        [
            (xx * 3 + yy * 2) % 256,
            (xx * 7 + 40) % 256,
            (yy * 9 + xx) % 256,
        ],
        axis=2,
    ).astype(np.uint8)
    mask = np.zeros((64, 80), dtype=np.uint8)
    mask[8:58, 10:72] = 255
    edge = np.zeros_like(mask)
    edge[8:11, 10:72] = 255
    edge[55:58, 10:72] = 255
    edge[8:58, 10:13] = 255
    edge[8:58, 69:72] = 255

    first = quantize_foreground(image, mask, edge, max_colors=7)
    second = quantize_foreground(image, mask, edge, max_colors=7)

    assert np.array_equal(first.image, second.image)
    assert np.array_equal(first.palette_rgb, second.palette_rgb)
    assert 1 <= len(first.palette_rgb) <= 7
    assert len(np.unique(first.image[mask > 0], axis=0)) <= 7
    assert np.array_equal(first.image[mask == 0], image[mask == 0])


def test_animegan_cartoonizer_only_replaces_masked_foreground(tmp_path) -> None:
    torch = pytest.importorskip("torch")
    from python_backend.algorithms.tiny_model.cartoonizer import (
        AnimeGanCartoonizer,
        AnimeGanGenerator,
    )

    model_path = tmp_path / "cartoonizer.pt"
    torch.save(AnimeGanGenerator().state_dict(), model_path)
    cartoonizer = AnimeGanCartoonizer(model_path, "cpu", maximum_edge=32)
    image = np.full((32, 40, 3), (40, 100, 180), dtype=np.uint8)
    mask = np.zeros((32, 40), dtype=np.uint8)
    mask[4:28, 8:32] = 255

    output = cartoonizer.stylize(image, mask)

    assert output.shape == image.shape
    assert output.dtype == np.uint8
    assert np.array_equal(output[mask == 0], image[mask == 0])
    assert not np.array_equal(output[mask > 0], image[mask > 0])


def test_grid_colors_are_snapped_to_palette_without_changing_alpha() -> None:
    palette = np.array([[240, 30, 20], [20, 210, 60], [30, 50, 230]], dtype=np.uint8)
    rgba = np.array(
        [
            [[230, 45, 25, 255], [40, 190, 70, 255], [17, 19, 23, 0]],
            [[50, 55, 210, 255], [120, 100, 80, 255], [0, 0, 0, 0]],
        ],
        dtype=np.uint8,
    )

    snapped = np.frombuffer(
        snap_rgba_to_palette(rgba.tobytes(), 3, 2, palette),
        dtype=np.uint8,
    ).reshape(2, 3, 4)
    foreground_colors = np.unique(snapped[:, :, :3][snapped[:, :, 3] >= 128], axis=0)
    assert len(foreground_colors) <= len(palette)
    assert all(any(np.array_equal(color, item) for item in palette) for color in foreground_colors)
    assert np.array_equal(snapped[:, :, 3], rgba[:, :, 3])


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


def test_mask_preparation_keeps_requested_instances() -> None:
    first = np.zeros((80, 100), dtype=np.uint8)
    first[20:70, 30:80] = 1
    second = np.zeros_like(first)
    second[8:18, 8:18] = 1
    masks = _prepare_masks(
        [MaskCandidate(first, 0.9), MaskCandidate(second, 0.7)],
        first.shape,
        20,
        20,
        max_instances=2,
    )
    assert len(masks) == 2


def test_analyze_endpoint_returns_standard_envelope_and_original_object_names() -> None:
    service = _service(FakeRuntime())
    registry = AlgorithmRegistry([service])
    app = create_app(
        settings=Settings(max_upload_bytes=1_000_000),
        registry=registry,
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/analyze",
            files={"image": ("subject.png", _encoded_image(), "image/png")},
            data={"algorithm": "tiny_model"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"code", "msg", "data", "exec", "meta"}
    assert payload["code"] == 200
    assert payload["exec"] is None
    assert payload["data"]["algorithm"] == {"id": "tiny_model", "version": "1.0.0"}
    assert payload["data"]["image"] == {"width": 100, "height": 80}
    assert payload["data"]["objects"][0]["type_name_en"] == "person"
    assert "type_name_zh" not in payload["data"]["objects"][0]
    assert payload["data"]["objects"][0]["id"] == "object_1"


def test_unavailable_tiny_model_is_exposed_and_returns_standard_error() -> None:
    settings = Settings(tiny_model_enabled=False, max_upload_bytes=1_000_000)
    app = create_app(settings=settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        capabilities = client.get("/api/v1/algorithms").json()["data"]["items"]
        response = client.post(
            "/api/v1/analyze",
            files={"image": ("subject.png", _encoded_image(), "image/png")},
            data={"algorithm": "tiny_model", "algorithm_version": "1.0.0"},
        )
    capability = next(item for item in capabilities if item["id"] == "tiny_model")
    assert capability["available"] is False
    assert capability["unavailable_reason"] == "tiny-model runtime is disabled"
    assert response.status_code == 503
    assert response.json()["exec"] == "AlgorithmUnavailableError"


def test_service_runs_analysis_and_pipeline_outside_event_loop() -> None:
    runtime = FakeRuntime()
    service = _service(runtime)

    async def execute() -> tuple[int, list[int]]:
        event_loop_thread = threading.get_ident()
        analysis = await service.analyze(_analysis_request())
        await service.process(
            _process_request(
                {
                    "analysis_token": analysis.analysis_token,
                    "selected_object_ids": ["object_1"],
                }
            )
        )
        return event_loop_thread, runtime.thread_ids

    event_loop_thread, worker_threads = asyncio.run(execute())
    assert worker_threads
    assert all(thread_id != event_loop_thread for thread_id in worker_threads)
