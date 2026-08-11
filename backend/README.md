# Python Backend

This subproject is the GPU-ready processing framework for Perler Striner. It
uses FastAPI for HTTP concerns and BentoML as the serving boundary for future
GPU workers, resource allocation, concurrency limits, batching, and replicas.

No production image algorithm is included. The production registry is empty;
`POST /api/v1/process` therefore returns `501` with
`exec: "AlgorithmNotImplementedError"`. The frontend treats that response as a
signal to run its browser fallback.

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
batch settings all use the `PYTHON_BACKEND_` prefix.

## API

- `GET /health`: liveness and registered-algorithm count.
- `GET /api/v1/algorithms`: registered algorithm capabilities. It is empty in
  the current production assembly.
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

`remove_background` is deliberately not accepted. Every future algorithm must
remove the background and return a row-major RGBA grid. Algorithm parameters
cannot disable that invariant.

All JSON responses use this envelope:

```json
{
  "code": 501,
  "msg": "requested algorithm is not registered",
  "data": null,
  "exec": "AlgorithmNotImplementedError",
  "meta": {
    "accept_id": "request-uuid",
    "perf_time_use": 1.25
  }
}
```

## Adding An Algorithm Later

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
