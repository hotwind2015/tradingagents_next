from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    plugin_type: str = "llm" 
    llm_id: str  # <--- 新增标识
    def invoke(self, prompt: str, model_config: dict[str, Any]) -> str: ...