from typing import Annotated

from fastapi import APIRouter, Depends, Request

from python_backend.algorithms.registry import AlgorithmRegistry
from python_backend.schemas.api import AlgorithmCapabilityData, AlgorithmListData
from python_backend.web.dependencies import get_registry
from python_backend.web.responses import success_response

router = APIRouter(prefix="/api/v1", tags=["algorithms"])


@router.get("/algorithms")
async def list_algorithms(
    request: Request,
    registry: Annotated[AlgorithmRegistry, Depends(get_registry)],
):
    items = [
        AlgorithmCapabilityData(
            id=descriptor.algorithm_id,
            version=descriptor.version,
            is_default=descriptor.is_default,
            requires_gpu=descriptor.requires_gpu,
            supports_batching=descriptor.supports_batching,
            removes_background=descriptor.removes_background,
            available=descriptor.available,
            unavailable_reason=descriptor.unavailable_reason,
            parameter_schema=dict(descriptor.parameter_schema),
        )
        for descriptor in registry.descriptors()
    ]
    return success_response(request, AlgorithmListData(items=items))
