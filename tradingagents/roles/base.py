from __future__ import annotations
from typing import Any, Protocol, runtime_checkable, TYPE_CHECKING
import json
from pydantic import BaseModel, Field
from tradingagents.evidence.view import EvidenceView
from tradingagents.run.context import RunContext

if TYPE_CHECKING:
    from tradingagents.run.analyst_context import AnalystContext


class RoleOutput(BaseModel):
    role_id: str
    stance: str = "neutral"
    fields: dict[str, Any] = Field(default_factory=dict)
    narrative: str = ""
    cited_evidence: list[str] = Field(default_factory=list)


class RoleBase:
    """角色基类，提供默认实现，内置角色可直接继承"""
    
    def configure(self, args: dict[str, Any]) -> None:
        """接收扩展参数（默认空实现，子类可重写）"""
        pass

    def analyze(self, ctx: AnalystContext) -> RoleOutput:
        """
        默认分析流程：prepare_context -> render -> llm -> parse_output
        
        子类可重写此方法实现完全自定义的分析逻辑（如使用 LangChain、多轮对话、工具调用等）。
        编排器仅负责调用此方法，不关心内部实现细节。
        """
        # 1. 构建提示词上下文
        prompt_ctx = self.prepare_context(ctx)
        
        # 2. 从 shared_state 获取 renderer 和 llm（由编排器注入）
        renderer = ctx.shared_state.get("prompt_renderer")
        llm = ctx.shared_state.get("llm_client")
        model_config = ctx.model_config
        
        if not renderer or not llm:
            raise RuntimeError(
                "Missing 'prompt_renderer' or 'llm_client' in AnalystContext.shared_state. "
                "Orchestrator must inject these before calling analyze()."
            )
        
        # 3. 渲染模板
        prompt_text = renderer.render(self.template, prompt_ctx)
        
        # 4. 调用 LLM
        raw_res = llm.invoke(prompt_text, model_config)
        
        # 5. 解析输出
        return self.parse_output(raw_res)

    def _format_evidence(self, items: list, max_chars: int = 8000) -> str:
        """
        将证据列表格式化为给 LLM 的文本（默认实现：直接 JSON 序列化）。
        
        子类可重写此方法实现自定义格式化逻辑（如截断、摘要、转表格等）。
        配合极简模板使用：模板中只需 {{evidence}} 即可。
        
        注意：items 可能是 EvidenceItem 对象列表，也可能是 EvidenceView.to_prompt_items()
        返回的 dict 列表。此方法兼容两种格式。
        """
        lines = []
        for ev in items:
            # 兼容 dict 和 object 两种访问方式
            if isinstance(ev, dict):
                ev_id = ev.get("evidence_id", "?")
                ev_type = ev.get("type", ev.get("evidence_type", "?"))
                provider = ev.get("provider", "?")
                summary = ev.get("summary", "")
                raw_payload = ev.get("raw_payload")
            else:
                ev_id = getattr(ev, "evidence_id", "?")
                ev_type = getattr(ev, "evidence_type", getattr(ev, "type", "?"))
                provider = getattr(ev, "provider", "?")
                summary = getattr(ev, "summary", "")
                raw_payload = getattr(ev, "raw_payload", None)
            
            lines.append(f"## Evidence [{ev_id}] ({ev_type})")
            lines.append(f"Source: {provider}")
            lines.append(f"Summary: {summary}")
            if raw_payload:
                # 直接 JSON 序列化，必要时截断
                payload_str = json.dumps(raw_payload, ensure_ascii=False, default=str)
                if len(payload_str) > max_chars:
                    payload_str = payload_str[:max_chars] + "... [truncated]"
                lines.append(f"Raw Data:\n{payload_str}")
            lines.append("---")
        return "\n".join(lines)


@runtime_checkable
class AnalystRole(Protocol):
    plugin_type: str = "role"
    role_id: str
    consumes: set[str]
    produces: set[str]
    template: str

    def prepare_context(self, evidence: EvidenceView, ctx: RunContext) -> dict[str, Any]: ...
    def prepare_context(self, ctx: AnalystContext) -> dict[str, Any]: ...
    def parse_output(self, raw_response: str) -> RoleOutput: ...
    def configure(self, args: dict[str, Any]) -> None: ...
    def analyze(self, ctx: AnalystContext) -> RoleOutput: ...
    def _format_evidence(self, items: list, max_chars: int = 8000) -> str: ...


@runtime_checkable
class ProjectManager(Protocol):
    plugin_type: str = "role"
    role_id: str
    consumes: set[str]
    template: str

    def prepare_context(self, outputs: list[RoleOutput], evidence: EvidenceView, ctx: RunContext) -> dict[str, Any]: ...
    def prepare_context(self, ctx: AnalystContext) -> dict[str, Any]: ...
    def parse_output(self, raw_response: str) -> RoleOutput: ...
    def configure(self, args: dict[str, Any]) -> None: ...
    def analyze(self, ctx: AnalystContext) -> RoleOutput: ...