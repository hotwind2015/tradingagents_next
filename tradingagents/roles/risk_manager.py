from __future__ import annotations
from typing import Any
from tradingagents.roles.base import AnalystRole, RoleOutput, RoleBase
from tradingagents.run.analyst_context import AnalystContext
from tradingagents.utils.json_parser import extract_json


class RiskManager(RoleBase, AnalystRole):
    role_id = "risk_manager"
    consumes = {"trader_plan", "market_outlook", "sentiment_report", "news_impact", "fundamental_score"}
    produces = {"risk_assessment"}
    template = "risk/manager.j2"

    def prepare_context(self, ctx: AnalystContext) -> dict[str, Any]:
        items = ctx.evidence.to_prompt_items(self.consumes, include_raw=True)
        evidence_text = self._format_evidence(items)
        
        return {
            "ticker": ctx.ticker,
            "evidence": evidence_text,
            "output_language": ctx.lang,
            "trader_plan": ctx.get_prior_narrative("trader"),
            "market_outlook": ctx.get_prior_narrative("market_analyst"),
            "sentiment_report": ctx.get_prior_narrative("sentiment_analyst"),
            "news_impact": ctx.get_prior_narrative("news_analyst"),
            "fundamental_score": ctx.get_prior_narrative("fundamentals_analyst"),
            "trader_fields": ctx.get_prior_fields("trader"),
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
                    "risk_assessment": data.get("risk_assessment", ""),
                    "aggressive_view": data.get("aggressive_view", ""),
                    "conservative_view": data.get("conservative_view", ""),
                    "neutral_view": data.get("neutral_view", ""),
                    "risk_factors": data.get("risk_factors", []),
                    "mitigation_strategies": data.get("mitigation_strategies", []),
                    "position_limits": data.get("position_limits", {}),
                    "stop_loss_rules": data.get("stop_loss_rules", {}),
                    "portfolio_heat": data.get("portfolio_heat", {}),
                    "correlation_analysis": data.get("correlation_analysis", {}),
                    "stress_test_results": data.get("stress_test_results", []),
                    "risk_reward_matrix": data.get("risk_reward_matrix", []),
                    "aggressive_conservative_table": data.get("aggressive_conservative_table", []),
                    "data_suggestions": data.get("data_suggestions", []),
                },
                narrative=data.get("narrative", ""),
                cited_evidence=data.get("cited_evidence", []),
            )
        return RoleOutput(role_id=self.role_id, narrative=raw_response)