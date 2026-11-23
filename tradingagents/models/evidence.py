from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


def sha256_payload(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class ProcessingLevel:
    """证据处理层级"""
    RAW = "raw"          # 原始数据
    ENRICHED = "enriched"  # 清洗/丰富后
    DERIVED = "derived"    # 衍生/计算后


class EvidenceMetadata(BaseModel):
    """证据元数据"""
    source_provider: str = ""              # 来源提供商
    source_method: str = ""                # 获取方法
    fetched_at: Optional[datetime] = None  # 获取时间
    processing_level: str = "raw"          # 处理层级
    processing_chain: list[str] = Field(default_factory=list)  # 处理链路
    quality_scores: dict[str, float] = Field(default_factory=dict)  # 质量评分
    expires_at: Optional[datetime] = None  # 过期时间


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
    metadata: "EvidenceMetadata" = Field(default_factory=EvidenceMetadata)  # 元数据
    lineage: list[str] = Field(default_factory=list)  # 基因链：祖先证据ID列表

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
    items: list["EvidenceItem"] = Field(default_factory=list)
    citations: list["Citation"] = Field(default_factory=list)

    def last_hash(self) -> str:
        return self.items[-1].self_hash if self.items else ""