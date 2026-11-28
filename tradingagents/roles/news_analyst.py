from __future__ import annotations
from typing import Any
from tradingagents.roles.base import AnalystRole, RoleOutput, RoleBase
from tradingagents.run.analyst_context import AnalystContext
from tradingagents.utils.json_parser import extract_json


class NewsAnalyst(RoleBase, AnalystRole):
    role_id = "news_analyst"
    consumes = {"news_raw", "global_news_raw", "macro_raw"}
    produces = {"news_impact"}
    template = "analysts/news.j2"

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
                    "news_impact": data.get("news_impact", "neutral"),
                    "core_signals": data.get("core_signals", {}),
                    "data_suggestions": data.get("data_suggestions", []),
                },
                narrative=data.get("narrative", ""),
                cited_evidence=data.get("cited_evidence", []),
            )
        return RoleOutput(role_id=self.role_id, narrative=raw_response)


NewsAnalyst = NewsAnalyst