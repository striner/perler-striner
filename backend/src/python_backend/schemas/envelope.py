from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

PayloadT = TypeVar("PayloadT")


class ResponseMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accept_id: str = Field(min_length=1)
    perf_time_use: float = Field(ge=0)


class Envelope(BaseModel, Generic[PayloadT]):
    model_config = ConfigDict(extra="forbid")

    code: int
    msg: str
    data: PayloadT | None
    exec: str | None
    meta: ResponseMeta
