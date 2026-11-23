from __future__ import annotations
from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel, Field
from tradingagents.evidence.view import EvidenceView
from tradingagents.run.context import RunContext

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


@runtime_checkable
class AnalystRole(Protocol):
    plugin_type: str = "role"
    role_id: str
    consumes: set[str]
    produces: set[str]
    template: str

    def prepare_context(self, evidence: EvidenceView, ctx: RunContext) -> dict[str, Any]: ...
    def prepare_context(self, ctx: "AnalystContext") -> dict[str, Any]: ...
    def parse_output(self, raw_response: str) -> RoleOutput: ...
    def configure(self, args: dict[str, Any]) -> None: ...


@runtime_checkable
class ProjectManager(Protocol):
    plugin_type: str = "role"
    role_id: str
    consumes: set[str]
    template: str

    def prepare_context(self, outputs: list[RoleOutput], evidence: EvidenceView, ctx: RunContext) -> dict[str, Any]: ...
    def prepare_context(self, ctx: "AnalystContext") -> dict[str, Any]: ...
    def parse_output(self, raw_response: str) -> RoleOutput: ...
    def configure(self, args: dict[str, Any]) -> None: ...