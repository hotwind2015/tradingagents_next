from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProvenanceField(BaseModel):
    value: Any
    source: Literal["cli", "user_config", "default", "env"]


class EffectiveConfig(BaseModel):
    fields: dict[str, ProvenanceField] = Field(default_factory=dict)
    recipe_id: str
    recipe_version: str
    template_versions: dict[str, str] = Field(default_factory=dict)
    evidence_schema: str = "v1"
    redacted_keys: list[str] = Field(default_factory=list)

    def get(self, path: str) -> Any:
        node = self.fields.get(path)
        return node.value if node else None