from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradingagents.models.evidence import EvidenceItem


class EvidenceView:
    def __init__(self, items: list[EvidenceItem], raw_dir: Path | None = None):
        self._items = list(items)
        self._raw_dir = raw_dir
        self._raw_cache: dict[str, dict] = {}
    
    def _get_raw_dir(self) -> Path | None:
        return self._raw_dir

    def by_type(self, evidence_type: str) -> list[EvidenceItem]:
        return [i for i in self._items if i.evidence_type == evidence_type]

    def for_types(self, types: set[str]) -> list[EvidenceItem]:
        return [i for i in self._items if i.evidence_type in types]

    def get(self, evidence_id: str) -> EvidenceItem | None:
        for item in self._items:
            if item.evidence_id == evidence_id:
                return item
        return None

    def get_raw(self, evidence_id: str) -> dict[str, Any] | None:
        """按需加载原始 payload（懒加载 + 缓存）"""
        if evidence_id in self._raw_cache:
            return self._raw_cache[evidence_id]
        if self._raw_dir is None:
            return None
        raw_path = self._raw_dir / f"{evidence_id}.json"
        if raw_path.exists():
            data = json.loads(raw_path.read_text(encoding="utf-8"))
            self._raw_cache[evidence_id] = data
            return data
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
                d["raw"] = self.get_raw(i.evidence_id)
            result.append(d)
        return result

    def __len__(self) -> int:
        return len(self._items)