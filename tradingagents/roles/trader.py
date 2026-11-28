from __future__ import annotations
from typing import Any
from tradingagents.roles.base import AnalystRole, RoleOutput, RoleBase
from tradingagents.run.analyst_context import AnalystContext
from tradingagents.utils.json_parser import extract_json


class Trader(RoleBase, AnalystRole):
    role_id = "trader"
    consumes = {"investment_plan", "market_outlook"}
    produces = {"trader_plan"}
    template = "trading/trader.j2"

    def prepare_context(self, ctx: AnalystContext) -> dict[str, Any]:
        items = ctx.evidence.to_prompt_items(self.consumes, include_raw=True)
        evidence_text = self._format_evidence(items)
        
        return {
            "ticker": ctx.ticker,
            "evidence": evidence_text,
            "output_language": ctx.lang,
            "investment_plan": ctx.get_prior_narrative("research_manager"),
            "market_outlook": ctx.get_prior_narrative("market_analyst"),
            "investment_plan_fields": ctx.get_prior_fields("research_manager"),
            "market_fields": ctx.get_prior_fields("market_analyst"),
        }

    def parse_output(self, raw_response: str) -> RoleOutput:
        data = extract_json(raw_response)
        if data:
            return RoleOutput(
                role_id=self.role_id,
                fields={
                    "trader_plan": data.get("trader_plan", ""),
                    "action": data.get("action", "HOLD"),
                    "entry_price": data.get("entry_price", 0),
                    "stop_loss": data.get("stop_loss", 0),
                    "target_price": data.get("target_price", 0),
                    "position_sizing": data.get("position_sizing", {}),
                    "entry_strategy": data.get("entry_strategy", {}),
                    "exit_strategy": data.get("exit_strategy", {}),
                    "risk_reward_ratio": data.get("risk_reward_ratio", 0),
                    "trade_management": data.get("trade_management", {}),
                    "action_table": data.get("action_table", []),
                    "key_levels": data.get("key_levels", {}),
                    "data_suggestions": data.get("data_suggestions", []),
                },
                narrative=data.get("narrative", ""),
                cited_evidence=data.get("cited_evidence", []),
            )
        return RoleOutput(role_id=self.role_id, narrative=raw_response)