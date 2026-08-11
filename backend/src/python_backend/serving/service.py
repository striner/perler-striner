import bentoml

from python_backend.core.config import get_settings
from python_backend.web.app import app

settings = get_settings()


@bentoml.service(
    name="PythonBackend",
    workers=settings.bento_workers,
    traffic={
        "timeout": settings.request_timeout_seconds,
        "max_concurrency": settings.bento_max_concurrency,
    },
)
@bentoml.asgi_app(app, path="/")
class PythonBackendService:
    """Empty BentoML service shell; algorithms are registered in later changes."""
