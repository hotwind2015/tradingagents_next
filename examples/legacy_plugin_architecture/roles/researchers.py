from __future__ import annotations
import json
from typing import Any
from tradingagents.evidence.view import EvidenceView
from tradingagents.roles.base import AnalystRole, RoleOutput, RoleBase
from tradingagents.run.context import RunContext

class BaseResearcher(RoleBase, AnalystRole):
    def prepare_context(self, evidence: EvidenceView, ctx: RunContext) -> dict[str, Any]:
        # 将上下文传给 prompt
        return {
            "ticker": ctx.recipe.target_profile,
            "market_data": evidence.to_prompt_items({"market_data"}),
            "fundamentals_data": evidence.to_prompt_items({"fundamentals_data"}),
            "news_data": evidence.to_prompt_items({"news_data"}),
        }

    def parse_output(self, raw_response: str) -> RoleOutput:
        clean_res = raw_response.strip().removeprefix("```json").removesuffix("```").strip()
        try:
            data = json.loads(clean_res)
            return RoleOutput(
                role_id=self.role_id,
                fields={"researcher_thesis": data.get("thesis", "")},
                narrative=data.get("thesis", ""),
                cited_evidence=data.get("cited_evidence", []),
            )
        except json.JSONDecodeError:
            return RoleOutput(role_id=self.role_id, narrative=raw_response)

class BullResearcher(BaseResearcher):
    role_id = "bull_researcher"
    consumes = {"market_data", "fundamentals_data"}
    produces = {"researcher_thesis"}
    template = "analysts/bull.j2"

class BearResearcher(BaseResearcher):
    role_id = "bear_researcher"
    consumes = {"market_data", "fundamentals_data"}
    produces = {"researcher_thesis"}
    template = "analysts/bear.j2"