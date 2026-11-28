from __future__ import annotations
from typing import Any
from tradingagents.roles.base import AnalystRole, RoleOutput, RoleBase
from tradingagents.run.analyst_context import AnalystContext
from tradingagents.utils.json_parser import extract_json


class MarketAnalyst(RoleBase, AnalystRole):
    role_id = "market_analyst"
    consumes = {"market_raw_kline", "market_verified_snapshot", "market_indicators"}
    produces = {"market_outlook"}
    template = "analysts/market.j2"

    def prepare_context(self, ctx: AnalystContext) -> dict[str, Any]:
        # 获取原始证据项，使用基类的 _format_evidence 格式化为文本
        items = ctx.evidence.to_prompt_items(self.consumes, include_raw=True)
        evidence_text = self._format_evidence(items)
        
        return {
            "ticker": ctx.ticker,
            "evidence": evidence_text,  # 直接传字符串，模板用 {{evidence}}
            "output_language": ctx.lang,
        }

    def parse_output(self, raw_response: str) -> RoleOutput:
        data = extract_json(raw_response)
        if data:
            return RoleOutput(
                role_id=self.role_id,
                fields={
                    "market_outlook": data.get("market_outlook", "neutral"),
                    "core_signals": data.get("core_signals", {}),
                    "data_suggestions": data.get("data_suggestions", []),
                },
                narrative=data.get("narrative", ""),
                cited_evidence=data.get("cited_evidence", []),
            )
        return RoleOutput(role_id=self.role_id, narrative=raw_response)


MarketAnalyst = MarketAnalyst