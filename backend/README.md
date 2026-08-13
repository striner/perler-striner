# Python Backend

This subproject is the GPU-ready processing framework for Perler Striner. It
uses FastAPI for HTTP concerns and BentoML as the serving boundary for future
GPU workers, resource allocation, concurrency limits, batching, and replicas.

The production registry includes `cv_native@1.0.0`, a deterministic CPU-only
OpenCV algorithm. It performs conservative foreground extraction, mask repair,
foreground edge sharpening with an optional light adaptive outline, and mask-aware
target-grid sampling. It may cluster border samples to model the background, but it does not
quantize output colors with K-Means or a bead palette.

## Install

Python 3.11-3.13 is supported.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

## Run

FastAPI development entry:

```powershell
.venv\Scripts\python -m uvicorn python_backend.web.app:app --host 0.0.0.0 --port 8000
```

BentoML entry:

```powershell
.venv\Scripts\bentoml serve python_backend.serving.service:PythonBackendService
```

Copy `.env.example` to `.env` when local overrides are needed. CORS origins,
upload limits, queue limits, timeouts, worker counts, GPU resource intent, and
batch settings all use the `PYTHON_BACKEND_` prefix. CV Native also supports
`MAX_DECODED_PIXELS`, `CV_WORK_MAX_EDGE`, `CV_MAX_CONCURRENCY`, and
`CV_OPENCV_THREADS` under that prefix.

## API

- `GET /health`: liveness and registered-algorithm count.
- `GET /api/v1/algorithms`: registered algorithm capabilities, currently
  `cv_native@1.0.0`.
- `POST /api/v1/process`: multipart processing contract.

Processing fields:

| Field | Required | Meaning |
| :-- | :-- | :-- |
| `image` | yes | Original image upload |
| `width` | yes | Target grid width |
| `height` | yes | Target grid height |
| `algorithm` | yes | Stable algorithm identifier |
| `algorithm_version` | no | Exact registered version |
| `algorithm_params` | no | JSON object; defaults to `{}` |

### CV Native parameters

All CV Native controls are optional and are passed inside `algorithm_params`.
The capability endpoint exposes the same schema and defaults.

| Parameter | Default | Allowed range |
| :-- | --: | :-- |
| `background_recovery_distance` | `6` | `0` to `40` |
| `coarse_subject_count` | `1` | integer `1` to `5` |
| `protection_scale` | `2` | `1` to `4` |
| `foreground_seed_distance` | `28` | `0` to `80` |
| `edge_seed_threshold` | `56` | `0` to `255` |
| `saturation_seed_threshold` | `18` | `0` to `255` |
| `protection_dilation_radius` | `2` | integer `0` to `12` |
| `recovery_neighborhood_ratio` | `0.014` | `0.002` to `0.05` |
| `foreground_coverage_threshold` | `0.2` | `0.05` to `0.8` |
| `edge_strength` | `0.65` | `0` to `1.5` |
| `outline_strength` | `0.1` | `0` to `0.3` |

Background removal is mandatory and has no disable parameter. Invalid,
out-of-range, unknown, or non-finite values return the standard error envelope.

`remove_background` is deliberately not accepted. Every future algorithm must
remove the background and return a row-major RGBA grid. Algorithm parameters
cannot disable that invariant.

All JSON responses use this envelope:

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "version": 1,
    "width": 87,
    "height": 87,
    "rgba_base64": "...",
    "algorithm": {"id": "cv_native", "version": "1.0.0"}
  },
  "exec": null,
  "meta": {
    "accept_id": "request-uuid",
    "perf_time_use": 1.25
  }
}
```

## Adding Another Algorithm

1. Create an algorithm package outside the shared Web and schema packages.
2. Implement `AlgorithmService` using the shared `AlgorithmInput` and
   `AlgorithmOutput`; do not accept FastAPI or BentoML request objects.
3. Declare a parameter schema and a descriptor with `removes_background=True`.
4. Implement the BentoML service worker and gateway. Synchronous GPU execution
   must stay outside the FastAPI event loop.
5. Configure GPU resources, workers, maximum concurrency, batch size, batch
   latency, queue timeout, and replicas for the actual model.
6. Register the service in environment-specific assembly and expose it through
   `/api/v1/algorithms`.
7. Run contract tests, then benchmark on the target GPU with representative
   inputs and concurrency. The empty framework does not establish model
   throughput or latency.

Uploads are consumed within a request and are not written by application code
to storage, databases, or object stores. Production deployments must use HTTPS
and explicit CORS origins.
