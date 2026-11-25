from __future__ import annotations
import json
from typing import Any
from tradingagents.evidence.view import EvidenceView
from tradingagents.roles.base import AnalystRole, RoleOutput, RoleBase
from tradingagents.run.context import RunContext
from tradingagents.utils.json_parser import extract_json


class ResearchManager(RoleBase, AnalystRole):
    role_id = "research_manager"
    consumes = {"market_outlook", "sentiment_report", "news_impact", "fundamental_score"}
    produces = {"investment_plan"}
    template = "research/manager.j2"

    def prepare_context(self, ctx: "AnalystContext") -> dict[str, Any]:
        return {
            "ticker": ctx.ticker,
            "evidence": ctx.evidence.to_prompt_items(ctx.consumes, include_raw=True),
            "output_language": ctx.lang,
            "market_outlook": ctx.get_prior_narrative("market_analyst"),
            "sentiment_report": ctx.get_prior_narrative("sentiment_analyst"),
            "news_impact": ctx.get_prior_narrative("news_analyst"),
            "fundamental_score": ctx.get_prior_narrative("fundamentals_analyst"),
            "market_fields": ctx.get_prior_fields("market_analyst"),
            "sentiment_fields": ctx.get_prior_fields("sentiment_analyst"),
            "news_fields": ctx.get_prior_fields("news_analyst"),
            "fundamentals_fields": ctx.get_prior_fields("fundamentals_analyst"),
        }

    def parse_output(self, raw_response: str) -> RoleOutput:
        data = extract_json(raw_response)
        if data:
            return RoleOutput(
                role_id=self.role_id,
                fields={
                    "investment_plan": data.get("investment_plan", ""),
                    "bull_case": data.get("bull_case", ""),
                    "bear_case": data.get("bear_case", ""),
                    "key_drivers": data.get("key_drivers", []),
                    "key_risks": data.get("key_risks", []),
                    "catalysts": data.get("catalysts", []),
                    "risk_factors": data.get("risk_factors", []),
                    "position_sizing": data.get("position_sizing", {}),
                    "entry_exit_strategy": data.get("entry_exit_strategy", {}),
                    "bull_bear_table": data.get("bull_bear_table", []),
                    "key_evidence_summary": data.get("key_evidence_summary", []),
                    "data_suggestions": data.get("data_suggestions", []),
                },
                narrative=data.get("narrative", ""),
                cited_evidence=data.get("cited_evidence", []),
            )
        return RoleOutput(role_id=self.role_id, narrative=raw_response)