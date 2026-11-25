from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class DataRequest(BaseModel):
    evidence_type: str
    ticker: str
    as_of: date
    params: dict[str, Any] = Field(default_factory=dict)


class RawEvidence(BaseModel):
    evidence_type: str
    provider: str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    summary: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class DataProvider(Protocol):
    plugin_type: str = "provider"  
    provider_id: str
    provides: set[str]

    def fetch(self, req: DataRequest) -> list[RawEvidence]: ...