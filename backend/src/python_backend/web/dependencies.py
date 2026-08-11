from fastapi import Request

from python_backend.algorithms.registry import AlgorithmRegistry
from python_backend.core.config import Settings
from python_backend.services.processing import ProcessingService


def get_settings_from_app(request: Request) -> Settings:
    return request.app.state.settings


def get_registry(request: Request) -> AlgorithmRegistry:
    return request.app.state.registry


def get_processing_service(request: Request) -> ProcessingService:
    return request.app.state.processing_service
