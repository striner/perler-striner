# Perler Striner

Perler Striner converts uploaded images into fuse-bead patterns. The repository
contains two independently runnable applications:

```text
frontend/  Astro + React static application
backend/   FastAPI + BentoML processing-service framework
```

The frontend first calls a configured Python processor. A valid backend result
is converted to a bead palette, counted, rendered, and exported in the browser.
If the backend is unavailable, times out, or returns invalid data, the existing
browser processor runs automatically and the page shows a dismissible five-second
fallback notice.

Image upload and processing-parameter changes mark the current result as stale.
Processing starts only when the user selects **Generate**; while it runs, related
controls are locked. Once the pattern is ready, the same action becomes **Download**.
CV Native exposes its supported controls in a separate **Hyperparameters** panel.
Tiny Model remains visible in the mode list and is enabled only when the backend reports
that its model runtime is available; it supports optional multi-subject text Prompts.

The backend registers `cv_native@1.0.0`, a CPU-only OpenCV pipeline. It removes
backgrounds with a conservative GrabCut mask, visually sharpens foreground edges,
and returns an exact-size RGBA grid. Bead-palette quantization remains entirely in
the frontend.

The optional `tiny_model@1.0.0` pipeline uses YOLO-World for open-vocabulary detection
and MobileSAM for segmentation. It removes transparent padding and scales the retained
subject proportionally into the target frame before edge enhancement and grid sampling.
Production targets CUDA; explicit FP32 CPU mode is available for functional development.

## Quick Start

Frontend:

```bash
cd frontend
npm ci
npm run dev -- --background
```

Backend:

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m uvicorn python_backend.web.app:app --port 8000
```

See [frontend/README.md](frontend/README.md) and
[backend/README.md](backend/README.md) for configuration and API details.

## Privacy

When a processor URL is configured and a backend mode is selected, an uploaded image
is sent to that backend before local processing. The backend framework
does not persist uploads. Deployments must use HTTPS and configure explicit
CORS origins. Without backend configuration, or whenever the request fails,
the image is processed locally in the browser.
