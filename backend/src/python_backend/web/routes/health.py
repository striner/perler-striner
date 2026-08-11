from typing import Annotated

from fastapi import APIRouter, Depends, Request

from python_backend.algorithms.registry import AlgorithmRegistry
from python_backend.schemas.api import HealthData
from python_backend.web.dependencies import get_registry
from python_backend.web.responses import success_response

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(
    request: Request,
    registry: Annotated[AlgorithmRegistry, Depends(get_registry)],
):
    data = HealthData(status="ok", registered_algorithms=len(registry.descriptors()))
    return success_response(request, data)
