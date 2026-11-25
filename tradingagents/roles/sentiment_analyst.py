from __future__ import annotations
import json
from typing import Any
from tradingagents.evidence.view import EvidenceView
from tradingagents.roles.base import AnalystRole, RoleOutput, RoleBase
from tradingagents.run.context import RunContext
from tradingagents.utils.json_parser import extract_json


class SentimentAnalyst(RoleBase, AnalystRole):
    role_id = "sentiment_analyst"
    consumes = {"news_raw", "sentiment_social_stocktwits", "sentiment_social_reddit"}
    produces = {"sentiment_report"}
    template = "analysts/sentiment.j2"

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