from __future__ import annotations
from typing import Any
from tradingagents.roles.base import AnalystRole, RoleOutput, RoleBase
from tradingagents.run.analyst_context import AnalystContext
from tradingagents.utils.json_parser import extract_json


class SentimentAnalyst(RoleBase, AnalystRole):
    role_id = "sentiment_analyst"
    consumes = {"news_raw", "sentiment_social_stocktwits", "sentiment_social_reddit"}
    produces = {"sentiment_report"}
    template = "analysts/sentiment.j2"

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
                    "overall_band": data.get("overall_band", "Neutral"),
                    "overall_score": data.get("overall_score", 5),
                    "confidence": data.get("confidence", "medium"),
                    "core_signals": data.get("core_signals", {}),
                    "data_suggestions": data.get("data_suggestions", []),
                },
                narrative=data.get("narrative", ""),
                cited_evidence=data.get("cited_evidence", []),
            )
        return RoleOutput(role_id=self.role_id, narrative=raw_response)


SentimentAnalyst = SentimentAnalyst