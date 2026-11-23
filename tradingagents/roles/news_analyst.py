from __future__ import annotations

import json
from typing import Any

from tradingagents.evidence.view import EvidenceView
from tradingagents.roles.base import AnalystRole, RoleOutput, RoleBase
from tradingagents.run.context import RunContext
from tradingagents.utils.json_parser import extract_json


class NewsAnalyst(RoleBase, AnalystRole):
    role_id = "news_analyst"
    consumes = {"news_data"}
    produces = {"news_impact"}
    template = "analysts/news.j2"

    def prepare_context(self, evidence: EvidenceView, ctx: RunContext) -> dict[str, Any]:
        return {"ticker": ctx.recipe.target_profile, "evidence": evidence.to_prompt_items(self.consumes)}

    def parse_output(self, raw_response: str) -> RoleOutput:
        data = extract_json(raw_response)
        if data:
            return RoleOutput(
                role_id=self.role_id,
                fields={"news_impact": data.get("news_impact", "neutral")},
                narrative=data.get("narrative", ""),
                cited_evidence=data.get("cited_evidence", []),
            )
        return RoleOutput(role_id=self.role_id, narrative=raw_response)