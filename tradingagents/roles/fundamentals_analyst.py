from __future__ import annotations
import json
from typing import Any
from tradingagents.evidence.view import EvidenceView
from tradingagents.roles.base import AnalystRole, RoleOutput, RoleBase
from tradingagents.run.context import RunContext
from tradingagents.utils.json_parser import extract_json


class FundamentalsAnalyst(RoleBase, AnalystRole):
    role_id = "fundamentals_analyst"
    consumes = {"fundamentals_raw", "financials_raw", "insider_raw"}
    produces = {"fundamental_score"}
    template = "analysts/fundamentals.j2"

    def prepare_context(self, ctx: "AnalystContext") -> dict[str, Any]:
        return {
            "ticker": ctx.ticker,
            "evidence": ctx.evidence.to_prompt_items(ctx.consumes, include_raw=True),
            "output_language": ctx.lang,
        }

    def parse_output(self, raw_response: str) -> RoleOutput:
        data = extract_json(raw_response)
        if data:
            return RoleOutput(
                role_id=self.role_id,
                fields={
                    "fundamental_score": data.get("fundamental_score", 0),
                    "core_findings": data.get("core_findings", {}),
                    "data_suggestions": data.get("data_suggestions", []),
                },
                narrative=data.get("narrative", ""),
                cited_evidence=data.get("cited_evidence", []),
            )
        return RoleOutput(role_id=self.role_id, narrative=raw_response)


FundamentalsAnalyst = FundamentalsAnalyst