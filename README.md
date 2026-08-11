# Perler Striner

Perler Striner converts uploaded images into fuse-bead patterns. The repository
contains two independently runnable applications:

```text
frontend/  Astro + React static application
backend/   FastAPI + BentoML processing-service framework
```

The frontend first calls a configured Python processor. A valid backend result
is converted to a bead palette, counted, rendered, and exported in the browser.
If the backend is unavailable, has no registered algorithm, times out, or
returns invalid data, the existing browser processor runs automatically.

The current backend intentionally contains no production image algorithm. Its
algorithm registry is empty, so processing requests return `501` and exercise
the frontend fallback. Future algorithms must return a background-removed RGBA
grid through the shared algorithm contract.

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

When both a processor URL and algorithm identifier are configured, an uploaded
image is sent to that backend before local processing. The backend framework
does not persist uploads. Deployments must use HTTPS and configure explicit
CORS origins. Without backend configuration, or whenever the request fails,
the image is processed locally in the browser.
