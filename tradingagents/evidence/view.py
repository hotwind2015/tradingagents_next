from __future__ import annotations

from typing import Any

from tradingagents.models.evidence import EvidenceItem


class EvidenceView:
    def __init__(self, items: list[EvidenceItem]):
        self._items = list(items)

    def by_type(self, evidence_type: str) -> list[EvidenceItem]:
        return [i for i in self._items if i.evidence_type == evidence_type]

    def for_types(self, types: set[str]) -> list[EvidenceItem]:
        return [i for i in self._items if i.evidence_type in types]

    def get(self, evidence_id: str) -> EvidenceItem | None:
        for item in self._items:
            if item.evidence_id == evidence_id:
                return item
        return None

    def to_prompt_items(self, types: set[str] | None = None) -> list[dict[str, Any]]:
        items = self._items if types is None else self.for_types(types)
        return [
            {
                "evidence_id": i.evidence_id,
                "type": i.evidence_type,
                "provider": i.provider,
                "summary": i.summary,
            }
            for i in items
        ]

    def __len__(self) -> int:
        return len(self._items)