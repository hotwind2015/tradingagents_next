from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


def sha256_payload(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class EvidenceItem(BaseModel):
    evidence_id: str
    evidence_type: str
    provider: str
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    summary: str
    raw_ref: str
    fetched_at: datetime
    fallback_hit: bool = False
    prev_hash: str = ""
    self_hash: str = ""

    def seal(self, prev_hash: str) -> "EvidenceItem":
        self.prev_hash = prev_hash
        payload = self.model_dump(mode="json", exclude={"self_hash"})
        self.self_hash = sha256_payload(payload)
        return self


class Citation(BaseModel):
    evidence_id: str
    section: str


class EvidenceManifest(BaseModel):
    schema_version: str = "v1"
    run_id: str
    recipe_id: str
    recipe_version: str
    items: list[EvidenceItem] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)

    def last_hash(self) -> str:
        return self.items[-1].self_hash if self.items else ""