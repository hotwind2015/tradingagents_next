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

@runtime_checkable
class AnalystRole(Protocol):
    plugin_type: str = "role"
    role_id: str
    consumes: set[str]
    produces: set[str]
    template: str

    def prepare_context(self, evidence: EvidenceView, ctx: RunContext) -> dict[str, Any]: ...
    def parse_output(self, raw_response: str) -> RoleOutput: ...

@runtime_checkable
class ProjectManager(Protocol):
    plugin_type: str = "role"
    role_id: str
    consumes: set[str]
    template: str

    def prepare_context(self, outputs: list[RoleOutput], evidence: EvidenceView, ctx: RunContext) -> dict[str, Any]: ...
    def parse_output(self, raw_response: str) -> RoleOutput: ...