from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from python_backend.algorithms.production import build_production_registry
from python_backend.algorithms.registry import AlgorithmRegistry
from python_backend.core.config import Settings, get_settings
from python_backend.services.processing import ProcessingService
from python_backend.web.errors import install_exception_handlers
from python_backend.web.middleware import install_request_middleware
from python_backend.web.routes.algorithms import router as algorithms_router
from python_backend.web.routes.health import router as health_router
from python_backend.web.routes.process import router as process_router


def create_app(
    settings: Settings | None = None,
    registry: AlgorithmRegistry | None = None,
) -> FastAPI:
    active_settings = settings or get_settings()
    active_registry = (
        registry if registry is not None else build_production_registry(active_settings)
    )
    application = FastAPI(
        title="Python Backend",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )
    application.state.settings = active_settings
    application.state.registry = active_registry
    application.state.processing_service = ProcessingService(
        active_registry,
        timeout_seconds=active_settings.request_timeout_seconds,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    install_request_middleware(application, active_settings)
    install_exception_handlers(application)
    application.include_router(health_router)
    application.include_router(algorithms_router)
    application.include_router(process_router)
    return application


app = create_app()
