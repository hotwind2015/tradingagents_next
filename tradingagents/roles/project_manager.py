from __future__ import annotations
import json
from typing import Any
from tradingagents.evidence.view import EvidenceView
from tradingagents.roles.base import ProjectManager, RoleOutput
from tradingagents.run.context import RunContext

class ProjectManager(ProjectManager):
    role_id = "project_manager"
    consumes = {"market_outlook"}
    template = "project_manager.j2"

    def prepare_context(self, outputs: list[RoleOutput], evidence: EvidenceView, ctx: RunContext) -> dict[str, Any]:
        summaries = [{"role": o.role_id, "narrative": o.narrative, "fields": o.fields} for o in outputs]
        return {"analyst_outputs": summaries}

    def parse_output(self, raw_response: str) -> RoleOutput:
        return RoleOutput(
            role_id=self.role_id,
            narrative=raw_response,
            fields={"final_report": raw_response},
            cited_evidence=["ev-0001"] # 简单起见，直接在 prompt 中要求提及
        )