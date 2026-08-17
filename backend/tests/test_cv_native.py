from __future__ import annotations

import asyncio
import base64
import os
import threading
from pathlib import Path

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
from python_backend.algorithms.cv_native.descriptor import DESCRIPTOR
from python_backend.algorithms.cv_native.edges import enhance_foreground_edges
from python_backend.algorithms.cv_native.params import CvNativeParams
from python_backend.algorithms.cv_native.pipeline import run_pipeline
from python_backend.algorithms.cv_native.segmentation import (
    _build_dark_subject_candidate,
    _fuse_dark_subject_candidate,
    _mask_confidence,
    _refine_centered_portrait,
    _restore_multiscale_subject,
    repair_mask,
)
from python_backend.algorithms.errors import AlgorithmProcessingError, InvalidRequestError
from python_backend.core.config import Settings
from python_backend.web.app import create_app


def encoded_subject(*, touches_edge: bool = False, transparent: bool = False) -> bytes:
    channels = 4 if transparent else 3
    image = np.full((96, 112, channels), 245, dtype=np.uint8)
    if transparent:
        image[:, :, 3] = 0
    x0 = 0 if touches_edge else 28
    image[20:82, x0:84, :3] = (35, 55, 210)
    if transparent:
        image[20:82, x0:84, 3] = 255
    success, encoded = cv2.imencode(".png", image)
    assert success
    return encoded.tobytes()


def request_for(data: bytes, width: int = 28, height: int = 24) -> AlgorithmInput:
    return AlgorithmInput(
        schema_version=1,
        image=ImagePayload(data=data, media_type="image/png", filename="subject.png"),
        target=GridTarget(width=width, height=height),
        algorithm=AlgorithmIdentity("cv_native", "1.0.0"),
    )


@pytest.mark.parametrize("touches_edge", [False, True])
def test_pipeline_removes_plain_background_and_retains_subject(touches_edge: bool) -> None:
    output = run_pipeline(
        request_for(encoded_subject(touches_edge=touches_edge)),
        CvNativeParams(),
        max_decoded_pixels=1_000_000,
        work_max_edge=256,
    )
    rgba = np.frombuffer(output.rgba, dtype=np.uint8).reshape(output.height, output.width, 4)
    assert np.count_nonzero(rgba[:, :, 3] == 0) > 0
    assert np.count_nonzero(rgba[:, :, 3] >= 128) > 40
    if touches_edge:
        assert np.count_nonzero(rgba[:, 0, 3] >= 128) > 4


def test_pipeline_preserves_transparent_input_background() -> None:
    output = run_pipeline(
        request_for(encoded_subject(transparent=True)),
        CvNativeParams(),
        max_decoded_pixels=1_000_000,
        work_max_edge=256,
    )
    rgba = np.frombuffer(output.rgba, dtype=np.uint8).reshape(output.height, output.width, 4)
    assert rgba[0, 0, 3] == 0
    assert rgba[12, 14, 3] >= 128


def test_pipeline_is_repeatable_with_background_color_model() -> None:
    request = request_for(encoded_subject())
    outputs = [
        run_pipeline(
            request,
            CvNativeParams(),
            max_decoded_pixels=1_000_000,
            work_max_edge=256,
        ).rgba
        for _ in range(2)
    ]
    assert outputs[0] == outputs[1]


def test_mask_repair_fills_only_cell_scale_holes_and_keeps_thin_structures() -> None:
    mask = np.zeros((96, 96), dtype=np.uint8)
    mask[8:88, 8:88] = 255
    mask[28:32, 28:32] = 0
    mask[48:72, 48:72] = 0
    mask[40:56, 2:4] = 255

    repaired = repair_mask(mask, target_width=24, target_height=24)

    assert np.all(repaired[28:32, 28:32] == 255)
    assert np.all(repaired[52:68, 52:68] == 0)
    assert np.all(repaired[42:54, 2:4] == 255)


def test_multiscale_recovery_expands_only_when_cleanup_eroded_protected_subject() -> None:
    mask = np.zeros((80, 80), dtype=np.uint8)
    mask[30:50, 30:50] = 255
    protection = np.zeros_like(mask)
    protection[18:62, 18:62] = 255
    background_distance = np.full(mask.shape, 20.0, dtype=np.float32)

    recovered = _restore_multiscale_subject(
        mask,
        protection,
        background_distance,
        CvNativeParams(),
    )

    assert np.all(recovered[18:62, 18:62] == 255)
    assert np.all(recovered[:12, :] == 0)


def test_dark_subject_candidate_requires_centered_bounded_contrast() -> None:
    centered = np.full((120, 160, 3), 225, dtype=np.uint8)
    cv2.ellipse(centered, (80, 64), (44, 34), 0, 0, 360, (30, 30, 30), -1)
    candidate = _build_dark_subject_candidate(centered, 40, 30)

    edge_background = np.full((120, 160, 3), 225, dtype=np.uint8)
    edge_background[:58, :] = 30
    rejected = _build_dark_subject_candidate(edge_background, 40, 30)

    assert np.count_nonzero(candidate) > centered.shape[0] * centered.shape[1] * 0.15
    assert candidate[64, 80] == 255
    assert np.count_nonzero(rejected) == 0


def test_dark_subject_fusion_discards_distant_false_positive_components() -> None:
    mask = np.zeros((80, 120), dtype=np.uint8)
    mask[24:58, 42:78] = 255
    mask[4:8, :] = 255
    dark_subject = np.zeros_like(mask)
    dark_subject[28:54, 46:74] = 255

    fused = _fuse_dark_subject_candidate(mask, dark_subject, 30, 20)

    assert np.all(fused[28:54, 46:74] == 255)
    assert np.count_nonzero(fused[4:8, :]) == 0


def test_dark_subject_evidence_replaces_incorrect_grabcut_foreground_seed() -> None:
    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[6:16, 6:16] = 255
    trimap = np.full((20, 20), cv2.GC_PR_BGD, dtype=np.uint8)
    trimap[1:4, 1:4] = cv2.GC_FGD
    trimap[0, 0] = cv2.GC_BGD
    evidence = np.zeros_like(mask)
    evidence[7:15, 7:15] = 255

    assert _mask_confidence(mask, trimap) == 0.0
    assert _mask_confidence(mask, trimap, evidence) == 1.0


def test_centered_portrait_refinement_recovers_body_without_side_background() -> None:
    image = np.full((240, 320, 3), (205, 150, 105), dtype=np.uint8)
    image[88:118, :] = (150, 145, 140)
    cv2.ellipse(image, (160, 91), (48, 62), 0, 0, 360, (25, 25, 25), -1)
    cv2.ellipse(image, (160, 100), (28, 44), 0, 0, 360, (80, 130, 190), -1)
    cv2.rectangle(image, (150, 130), (170, 164), (80, 130, 190), -1)
    body = np.array([[112, 144], [208, 144], [290, 239], [30, 239]], np.int32)
    cv2.fillPoly(image, [body], (195, 175, 150))

    initial_mask = np.zeros((240, 320), dtype=np.uint8)
    cv2.ellipse(initial_mask, (160, 108), (54, 74), 0, 0, 360, 255, -1)
    initial_mask[88:118, 20:300] = 255
    initial_mask[144:205, 122:198] = 255
    background_distance = np.full(initial_mask.shape, 18.0, dtype=np.float32)
    background_distance[88:118, :] = 4.0

    result = _refine_centered_portrait(
        image,
        initial_mask,
        background_distance,
        target_width=80,
        target_height=60,
    )

    assert result is not None
    refined, evidence = result
    assert refined[210, 160] == 255
    assert refined[100, 30] == 0
    assert refined[100, 290] == 0
    assert np.count_nonzero(evidence) > 100


def test_cat_floor_acceptance_fixture() -> None:
    source_path = os.environ.get("CV_NATIVE_ACCEPTANCE_SOURCE")
    ground_truth_path = os.environ.get("CV_NATIVE_ACCEPTANCE_GT")
    if not source_path or not ground_truth_path:
        pytest.skip("private CV acceptance fixture is not configured")

    source = Path(source_path).read_bytes()
    ground_truth_encoded = np.fromfile(ground_truth_path, dtype=np.uint8)
    ground_truth_rgba = cv2.imdecode(ground_truth_encoded, cv2.IMREAD_UNCHANGED)
    assert ground_truth_rgba is not None and ground_truth_rgba.shape[2] == 4

    output = run_pipeline(
        request_for(source, width=87, height=150),
        CvNativeParams(),
        max_decoded_pixels=40_000_000,
        work_max_edge=1024,
    )
    prediction = np.frombuffer(output.rgba, dtype=np.uint8).reshape(150, 87, 4)
    prediction_mask = prediction[:, :, 3] >= 128
    truth_alpha = cv2.resize(
        ground_truth_rgba[:, :, 3],
        (87, 150),
        interpolation=cv2.INTER_AREA,
    )
    truth_mask = truth_alpha >= 51

    true_positive = np.count_nonzero(prediction_mask & truth_mask)
    false_positive = np.count_nonzero(prediction_mask & ~truth_mask)
    false_negative = np.count_nonzero(~prediction_mask & truth_mask)
    iou = true_positive / (true_positive + false_positive + false_negative)
    precision = true_positive / np.count_nonzero(prediction_mask)
    recall = true_positive / np.count_nonzero(truth_mask)

    assert iou >= 0.77
    assert precision >= 0.81
    assert recall >= 0.93
    assert false_positive <= 410
    assert false_negative <= 125
    assert np.count_nonzero(prediction_mask[:, :2]) <= 10
    assert np.count_nonzero(prediction_mask[115:, 70:]) == 0


def test_edge_enhancement_increases_foreground_gradient_without_touching_background() -> None:
    image = np.full((64, 64, 3), 220, dtype=np.uint8)
    image[12:52, 12:32] = (80, 80, 80)
    image[12:52, 32:52] = (140, 140, 140)
    image = cv2.GaussianBlur(image, (0, 0), 1.4)
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[10:54, 10:54] = 255
    result = enhance_foreground_edges(image, mask, edge_strength=1.0, outline_strength=0.1)
    before = np.abs(np.diff(image[:, :, 0].astype(np.int16), axis=1))
    after = np.abs(np.diff(result.image[:, :, 0].astype(np.int16), axis=1))
    assert after[12:52, 29:35].mean() > before[12:52, 29:35].mean()
    assert np.array_equal(result.image[:8, :8], image[:8, :8])
    assert np.count_nonzero(result.edge_band[mask == 0]) == 0


def test_invalid_image_and_params_are_controlled() -> None:
    with pytest.raises(AlgorithmProcessingError):
        run_pipeline(
            request_for(b"not-an-image"),
            CvNativeParams(),
            max_decoded_pixels=1_000_000,
            work_max_edge=256,
        )

    from python_backend.algorithms.cv_native.params import parse_params

    with pytest.raises(InvalidRequestError):
        parse_params({"unknown": True})
    with pytest.raises(InvalidRequestError):
        parse_params({"coarse_subject_count": 1.5})
    with pytest.raises(InvalidRequestError):
        parse_params({"background_recovery_distance": 41})
    with pytest.raises(InvalidRequestError):
        parse_params({"foreground_coverage_threshold": 0.01})


def test_hyperparameter_schema_and_parser_defaults_stay_aligned() -> None:
    from python_backend.algorithms.cv_native.params import parse_params

    defaults = parse_params({})
    properties = DESCRIPTOR.parameter_schema["properties"]
    assert set(properties) == {
        "edge_strength",
        "outline_strength",
        "background_recovery_distance",
        "coarse_subject_count",
        "protection_scale",
        "foreground_seed_distance",
        "edge_seed_threshold",
        "saturation_seed_threshold",
        "protection_dilation_radius",
        "recovery_neighborhood_ratio",
        "foreground_coverage_threshold",
    }
    assert defaults.background_recovery_distance == properties[
        "background_recovery_distance"
    ]["default"]
    assert defaults.coarse_subject_count == properties["coarse_subject_count"]["default"]
    assert defaults.foreground_coverage_threshold == properties[
        "foreground_coverage_threshold"
    ]["default"]

    custom = parse_params(
        {
            "background_recovery_distance": 12,
            "coarse_subject_count": 3,
            "foreground_coverage_threshold": 0.35,
        }
    )
    assert custom.background_recovery_distance == 12
    assert custom.coarse_subject_count == 3
    assert custom.foreground_coverage_threshold == 0.35


def test_production_registry_and_real_api() -> None:
    settings = Settings(max_upload_bytes=1_000_000, cv_work_max_edge=256)
    app = create_app(settings=settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        capabilities = client.get("/api/v1/algorithms")
        response = client.post(
            "/api/v1/process",
            files={"image": ("subject.png", encoded_subject(), "image/png")},
            data={
                "width": "28",
                "height": "24",
                "algorithm": "cv_native",
                "algorithm_version": "1.0.0",
                "algorithm_params": "{}",
            },
        )

    items = capabilities.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["id"] == "cv_native"
    assert items[0]["requires_gpu"] is False
    assert response.status_code == 200
    payload = response.json()
    assert payload["exec"] is None
    assert len(base64.b64decode(payload["data"]["rgba_base64"])) == 28 * 24 * 4


def test_service_runs_pipeline_outside_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    import python_backend.algorithms.cv_native.service as service_module

    thread_ids: list[int] = []

    def fake_pipeline(request, params, max_decoded_pixels, work_max_edge):
        import threading

        thread_ids.append(threading.get_ident())
        return run_pipeline(request, params, max_decoded_pixels, work_max_edge)

    monkeypatch.setattr(service_module, "run_pipeline", fake_pipeline)
    service = service_module.CvNativeService(
        max_decoded_pixels=1_000_000,
        work_max_edge=256,
        max_concurrency=1,
        opencv_threads=1,
        queue_timeout_seconds=1,
    )

    async def execute() -> tuple[int, int]:
        import threading

        event_loop_thread = threading.get_ident()
        await service.process(request_for(encoded_subject()))
        return event_loop_thread, thread_ids[0]

    event_loop_thread, worker_thread = asyncio.run(execute())
    assert worker_thread != event_loop_thread


def test_cancelled_native_work_keeps_concurrency_permit(monkeypatch: pytest.MonkeyPatch) -> None:
    import python_backend.algorithms.cv_native.service as service_module

    started = threading.Event()
    release = threading.Event()

    def blocked_pipeline(request, params, max_decoded_pixels, work_max_edge):
        started.set()
        release.wait(timeout=2)
        return run_pipeline(request, params, max_decoded_pixels, work_max_edge)

    monkeypatch.setattr(service_module, "run_pipeline", blocked_pipeline)
    service = service_module.CvNativeService(
        max_decoded_pixels=1_000_000,
        work_max_edge=256,
        max_concurrency=1,
        opencv_threads=1,
        queue_timeout_seconds=0.02,
    )

    async def execute() -> None:
        first = asyncio.create_task(service.process(request_for(encoded_subject())))
        await asyncio.to_thread(started.wait, 1)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        with pytest.raises(Exception, match="queue is full"):
            await service.process(request_for(encoded_subject()))
        release.set()
        await asyncio.sleep(0.05)

    try:
        asyncio.run(execute())
    finally:
        release.set()
