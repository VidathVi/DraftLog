from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    WrapSerializer,
)


def _ensure_utc(v: Any) -> Any:
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=UTC)
    return v


DateTime = Annotated[
    AwareDatetime,
    BeforeValidator(_ensure_utc),
    WrapSerializer(
        lambda v, nxt: nxt(v.astimezone(UTC)).replace("+00:00", "Z"),
        when_used="json",
    ),
]


class Model(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)


class MessageResponse(Model):
    message: str


class HealthCheckResponse(Model):
    status: str  # "healthy" or "unhealthy"
