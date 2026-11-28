from __future__ import annotations
from typing import Any
from tradingagents.roles.base import AnalystRole, RoleOutput, RoleBase
from tradingagents.run.analyst_context import AnalystContext
from tradingagents.utils.json_parser import extract_json


class FundamentalsAnalyst(RoleBase, AnalystRole):
    role_id = "fundamentals_analyst"
    consumes = {"fundamentals_raw", "financials_raw", "insider_raw"}
    produces = {"fundamental_score"}
    template = "analysts/fundamentals.j2"

    def prepare_context(self, ctx: AnalystContext) -> dict[str, Any]:
        items = ctx.evidence.to_prompt_items(self.consumes, include_raw=True)
        evidence_text = self._format_evidence(items)
        
        return {
            "ticker": ctx.ticker,
            "evidence": evidence_text,
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