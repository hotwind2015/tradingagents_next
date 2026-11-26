from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradingagents.models.evidence import EvidenceItem, ProcessingLevel


class EvidenceView:
    def __init__(self, items: list[EvidenceItem], raw_dir: Path | None = None):
        self._items = list(items)
        self._raw_dir = raw_dir
        self._raw_cache: dict[str, dict] = {}
        # 构建 ID -> Item 索引，用于快速查找
        self._id_index: dict[str, EvidenceItem] = {item.evidence_id: item for item in items}
    
    def _get_raw_dir(self) -> Path | None:
        return self._raw_dir

    def by_type(self, evidence_type: str) -> list[EvidenceItem]:
        return [i for i in self._items if i.evidence_type == evidence_type]

    def for_types(self, types: set[str]) -> list[EvidenceItem]:
        return [i for i in self._items if i.evidence_type in types]

    def get(self, evidence_id: str) -> EvidenceItem | None:
        return self._id_index.get(evidence_id)

    def get_raw(self, evidence_id: str) -> dict[str, Any] | None:
        """按需加载原始 payload（懒加载 + 缓存），只返回 raw_payload 字段"""
        if evidence_id in self._raw_cache:
            return self._raw_cache[evidence_id]
        if self._raw_dir is None:
            return None
        raw_path = self._raw_dir / f"{evidence_id}.json"
        if raw_path.exists():
            try:
                data = json.loads(raw_path.read_text(encoding="utf-8"))
                # 只返回 raw_payload 字段，保持与模板兼容
                payload = data.get("raw_payload", data)
                self._raw_cache[evidence_id] = payload
                return payload
            except json.JSONDecodeError:
                # 原始文件损坏，返回 None 而非抛出异常
                return None
        return None
    
    def get_all_raw(self, evidence_type: str) -> list[dict[str, Any]]:
        """获取某类型的所有原始数据"""
        return [self.get_raw(item.evidence_id) 
                for item in self.by_type(evidence_type) 
                if self.get_raw(item.evidence_id) is not None]

    def to_prompt_items(self, types: set[str] | None = None, include_raw: bool = False) -> list[dict[str, Any]]:
        """可选包含 raw_payload"""
        items = self._items if types is None else self.for_types(types)
        result = []
        for i in items:
            d = {"evidence_id": i.evidence_id, "type": i.evidence_type, 
                 "provider": i.provider, "summary": i.summary}
            if include_raw:
                d["raw_payload"] = self.get_raw(i.evidence_id)
            result.append(d)
        return result

    # === 基因链 API ===

    def get_metadata(self, evidence_id: str) -> Any | None:
        """获取证据元数据"""
        item = self.get(evidence_id)
        return item.metadata if item else None

    def get_lineage(self, evidence_id: str) -> list[str]:
        """获取基因链：正向溯源（祖先链）"""
        item = self.get(evidence_id)
        if not item:
            return []
        return list(item.lineage)  # 返回副本

    def get_descendants(self, evidence_id: str) -> list[str]:
        """获取后代链：反向追踪（所有引用该证据的后代）"""
        descendants = []
        for item in self._items:
            if evidence_id in item.lineage:
                descendants.append(item.evidence_id)
        return descendants

    def get_by_level(self, evidence_type: str, level: str) -> list["EvidenceItem"]:
        """按处理层级筛选证据"""
        result = []
        for item in self.by_type(evidence_type):
            if item.metadata and item.metadata.processing_level == level:
                result.append(item)
        return result

    def __len__(self) -> int:
        return len(self._items)