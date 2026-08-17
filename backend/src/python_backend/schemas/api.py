from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AlgorithmIdentityData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    version: str = Field(min_length=1)


class GridData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    rgba_base64: str
    algorithm: AlgorithmIdentityData


class AlgorithmCapabilityData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: str
    is_default: bool
    requires_gpu: bool
    supports_batching: bool
    removes_background: bool
    available: bool
    unavailable_reason: str | None
    parameter_schema: dict[str, Any]


class AlgorithmListData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AlgorithmCapabilityData]


class HealthData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    registered_algorithms: int = Field(ge=0)
