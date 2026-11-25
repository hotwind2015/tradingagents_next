from __future__ import annotations
import json
from typing import Any
from tradingagents.evidence.view import EvidenceView
from tradingagents.roles.base import AnalystRole, RoleOutput, RoleBase
from tradingagents.run.context import RunContext
from tradingagents.utils.json_parser import extract_json


class NewsAnalyst(RoleBase, AnalystRole):
    role_id = "news_analyst"
    consumes = {"news_raw", "global_news_raw", "macro_raw"}
    produces = {"news_impact"}
    template = "analysts/news.j2"

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
                    "news_impact": data.get("news_impact", "neutral"),
                    "core_signals": data.get("core_signals", {}),
                    "data_suggestions": data.get("data_suggestions", []),
                },
                narrative=data.get("narrative", ""),
                cited_evidence=data.get("cited_evidence", []),
            )
        return RoleOutput(role_id=self.role_id, narrative=raw_response)


NewsAnalyst = NewsAnalyst