"""统一表格渲染器 - 消除 PM 和 generator.py 中的重复渲染代码"""

from __future__ import annotations

import json
from typing import Any
from tradingagents.utils import get_i18n


class TableRenderer:
    """统一表格渲染器 - 支持市场差异化配置"""

    def __init__(self, i18n=None, market_config: dict = None):
        self.i18n = i18n or get_i18n()
        self.market_config = market_config or {}
        self.market = self.market_config.get("market", "us")
        self.field_mapping = self.market_config.get("field_mapping", {})
        self.unit_mapping = self.market_config.get("unit_mapping", {})

    # ========== 通用渲染方法 ==========

    def render_kv_table(self, data: dict, key_header: str = "Field", value_header: str = "Value") -> str:
        """渲染键值对表格"""
        if not data:
            return ""
        key_header = self.i18n.t(key_header, default=key_header) if hasattr(self.i18n, 't') else key_header
        value_header = self.i18n.t(value_header, default=value_header) if hasattr(self.i18n, 't') else value_header
        
        lines = [
            f"| **{key_header}** | **{value_header}** |",
            "| :--- | :--- |",
        ]
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False, indent=2)
            lines.append(f"| **{k}** | {v} |")
        return "\n".join(lines) + "\n"

    def render_list_table(self, items: list[dict], headers: list[str]) -> str:
        """渲染列表表格"""
        if not items:
            return ""
        
        # 翻译表头
        translated_headers = []
        for h in headers:
            translated_headers.append(self.i18n.t(h, default=h) if hasattr(self.i18n, 't') else h)
        
        lines = [
            "| " + " | ".join(f"**{h}**" for h in translated_headers) + " |",
            "| " + " | ".join(":---" for _ in translated_headers) + " |",
        ]
        for item in items:
            row = []
            for h in headers:
                val = item.get(h, "")
                if isinstance(val, (dict, list)):
                    val = json.dumps(val, ensure_ascii=False)
                row.append(str(val))
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines) + "\n"

    # ========== 专业金融表格 ==========

    def render_technical_indicators(self, indicators: dict) -> str:
        """渲染技术指标表格"""
        if not indicators:
            return ""
        
        t = self._t
        lines = [
            f"## {t('report.technical_indicators', default='Technical Indicators')}",
            "",
            f"| {t('report.indicator', default='Indicator')} | "
            f"{t('report.value', default='Value')} | "
            f"{t('report.signal', default='Signal')} | "
            f"{t('report.threshold', default='Threshold')} | "
            f"{t('report.meaning', default='Meaning')} |",
            "| :--- | :---: | :---: | :---: | :--- |",
        ]
        for name, data in indicators.items():
            value = ""
            signal = ""
            if isinstance(data, dict) and "values" in data:
                values = data["values"]
                # Find the latest non-N/A value
                if isinstance(values, dict):
                    for date in sorted(values.keys(), reverse=True):
                        val = values[date]
                        if val and val != "N/A: Not a trading day (weekend or holiday)":
                            value = str(val)
                            break
            elif isinstance(data, list) and data:
                latest = data[-1]
                if isinstance(latest, dict):
                    value = str(latest.get("value", ""))
                    signal = latest.get("signal", "")
                else:
                    value = str(latest)
                    signal = ""
            
            lines.append(f"| **{name.upper()}** | {value} | {signal} |  |  |")
        return "\n".join(lines) + "\n"

    def render_key_levels(self, indicators: dict, fields: dict) -> str:
        """渲染关键价位表格"""
        if not fields:
            return ""
        
        t = self._t
        levels = fields.get("key_levels", {})
        if not levels:
            return ""
        
        lines = [
            f"## {t('report.key_levels', default='Key Levels')}",
            "",
            f"| {t('report.level_type', default='Type')} | "
            f"{t('report.price', default='Price')} | "
            f"{t('report.description', default='Description')} |",
            "| :--- | :---: | :--- |",
        ]
        for k, v in levels.items():
            if isinstance(v, list):
                for price in v:
                    lines.append(f"| **{k}** | {price} | {k.replace('_', ' ').title()} |")
            else:
                lines.append(f"| **{k}** | {v} | {k.replace('_', ' ').title()} |")
        return "\n".join(lines) + "\n"

    def render_signals(self, fields: dict) -> str:
        """渲染信号汇总表格"""
        if not fields:
            return ""
        
        t = self._t
        signals = fields.get("signals", {})
        if not signals:
            return ""
        
        lines = [
            f"## {t('report.signal_summary', default='Signal Summary')}",
            "",
            f"| {t('report.indicator', default='Indicator')} | "
            f"{t('report.value', default='Value')} | "
            f"{t('report.signal', default='Signal')} | "
            f"{t('report.trend', default='Trend')} |",
            "| :--- | :---: | :---: | :---: |",
        ]
        for name, data in signals.items():
            if isinstance(data, dict):
                lines.append(f"| **{name}** | {data.get('value', '')} | {data.get('signal', '')} | {data.get('trend', '')} |")
            else:
                lines.append(f"| **{name}** | {data} | - | - |")
        return "\n".join(lines) + "\n"

    def render_financial_ratios(self, fund_overview: dict, fields: dict) -> str:
        """渲染财务比率表格"""
        t = self._t
        ratios = fund_overview.get("ratios", {})
        if not ratios:
            ratios = fields.get("financial_ratios", {})
        if not ratios:
            return ""
        
        lines = [
            f"## {t('report.financial_ratios', default='Financial Ratios')}",
            "",
            f"| {t('report.metric', default='Metric')} | "
            f"{t('report.value', default='Value')} | "
            f"{t('report.benchmark', default='Benchmark')} | "
            f"{t('report.assessment', default='Assessment')} |",
            "| :--- | :---: | :---: | :--- |",
        ]
        for name, data in ratios.items():
            if isinstance(data, dict):
                lines.append(f"| **{name}** | {data.get('value', '')} | {data.get('benchmark', '')} | {data.get('assessment', '')} |")
            else:
                lines.append(f"| **{name}** | {data} | - | - |")
        return "\n".join(lines) + "\n"

    def render_growth_metrics(self, fund_overview: dict) -> str:
        """渲染增长指标表格"""
        t = self._t
        growth = fund_overview.get("growth", {})
        if not growth:
            return ""
        
        lines = [
            f"## {t('report.growth_metrics', default='Growth Metrics')}",
            "",
            f"| {t('report.metric', default='Metric')} | "
            f"{t('report.value', default='Value')} | "
            f"{t('report.yoy', default='YoY')} | "
            f"{t('report.trend', default='Trend')} |",
            "| :--- | :---: | :---: | :---: |",
        ]
        for name, data in growth.items():
            if isinstance(data, dict):
                lines.append(f"| **{name}** | {data.get('value', '')} | {data.get('yoy', '')} | {data.get('trend', '')} |")
            else:
                lines.append(f"| **{name}** | {data} | - | - |")
        return "\n".join(lines) + "\n"

    def render_valuation(self, fund_overview: dict) -> str:
        """渲染估值指标表格"""
        t = self._t
        valuation = fund_overview.get("valuation", {})
        if not valuation:
            return ""
        
        lines = [
            f"## {t('report.valuation_metrics', default='Valuation Metrics')}",
            "",
            f"| {t('report.metric', default='Metric')} | "
            f"{t('report.value', default='Value')} | "
            f"{t('report.benchmark', default='Benchmark')} | "
            f"{t('report.assessment', default='Assessment')} |",
            "| :--- | :---: | :---: | :--- |",
        ]
        for name, data in valuation.items():
            if isinstance(data, dict):
                lines.append(f"| **{name}** | {data.get('value', '')} | {data.get('benchmark', '')} | {data.get('assessment', '')} |")
            else:
                lines.append(f"| **{name}** | {data} | - | - |")
        return "\n".join(lines) + "\n"

    def render_profitability(self, fund_overview: dict) -> str:
        """渲染盈利能力指标表格"""
        t = self._t
        profit = fund_overview.get("profitability", {})
        if not profit:
            return ""
        
        lines = [
            f"## {t('report.profitability', default='Profitability Metrics')}",
            "",
            f"| {t('report.metric', default='Metric')} | "
            f"{t('report.value', default='Value')} | "
            f"{t('report.benchmark', default='Benchmark')} | "
            f"{t('report.assessment', default='Assessment')} |",
            "| :--- | :---: | :---: | :--- |",
        ]
        for name, data in profit.items():
            if isinstance(data, dict):
                lines.append(f"| **{name}** | {data.get('value', '')} | {data.get('benchmark', '')} | {data.get('assessment', '')} |")
            else:
                lines.append(f"| **{name}** | {data} | - | - |")
        return "\n".join(lines) + "\n"

    def render_balance_sheet(self, financials: dict) -> str:
        """渲染资产负债表健康度"""
        t = self._t
        rows = []
        for stmt_type, csv_data in financials.items():
            if "balance" in stmt_type.lower():
                rows.append({
                    "metric": stmt_type,
                    "value": "见详细报表",
                    "benchmark": "-",
                    "assessment": "-",
                })
        if not rows:
            return ""
        
        lines = [
            f"## {t('report.balance_sheet_health', default='Balance Sheet Health')}",
            "",
            f"| {t('report.metric', default='Metric')} | "
            f"{t('report.value', default='Value')} | "
            f"{t('report.benchmark', default='Benchmark')} | "
            f"{t('report.assessment', default='Assessment')} |",
            "| :--- | :---: | :---: | :--- |",
        ]
        for r in rows:
            lines.append(f"| **{r['metric']}** | {r['value']} | {r['benchmark']} | {r['assessment']} |")
        return "\n".join(lines) + "\n"

    def render_cash_flow(self, financials: dict) -> str:
        """渲染现金流分析"""
        t = self._t
        rows = []
        for stmt_type, csv_data in financials.items():
            if "cash" in stmt_type.lower() or "flow" in stmt_type.lower():
                rows.append({
                    "metric": stmt_type,
                    "value": "见详细报表",
                    "trend": "-",
                    "assessment": "-",
                })
        if not rows:
            return ""
        
        lines = [
            f"## {t('report.cash_flow', default='Cash Flow Analysis')}",
            "",
            f"| {t('report.metric', default='Metric')} | "
            f"{t('report.value', default='Value')} | "
            f"{t('report.trend', default='Trend')} | "
            f"{t('report.assessment', default='Assessment')} |",
            "| :--- | :---: | :---: | :--- |",
        ]
        for r in rows:
            lines.append(f"| **{r['metric']}** | {r['value']} | {r['trend']} | {r['assessment']} |")
        return "\n".join(lines) + "\n"

    def render_insider(self, insider: list) -> str:
        """渲染内部人交易表格"""
        t = self._t
        if not insider:
            return ""
        
        lines = [
            f"## {t('report.insider_activity', default='Insider Activity')}",
            "",
            f"| {t('report.date', default='Date')} | "
            f"{t('report.insider', default='Insider')} | "
            f"{t('report.action', default='Action')} | "
            f"{t('report.shares', default='Shares')} | "
            f"{t('report.price', default='Price')} |",
            "| :--- | :--- | :--- | :---: | :---: |",
        ]
        for item in insider[:10]:
            lines.append(f"| {item.get('date', '')} | {item.get('insider', '')} | {item.get('action', '')} | "
                         f"{item.get('shares', '')} | {item.get('price', '')} |")
        return "\n".join(lines) + "\n"

    def render_sentiment(self, sentiment_data: dict) -> str:
        """渲染情绪分布表格"""
        t = self._t
        if not sentiment_data:
            return ""
        
        lines = [
            f"## {t('report.sentiment_distribution', default='Sentiment Distribution')}",
            "",
            f"| {t('report.platform', default='Platform')} | "
            f"{t('report.bullish', default='Bullish')} | "
            f"{t('report.bearish', default='Bearish')} | "
            f"{t('report.neutral', default='Neutral')} | "
            f"{t('report.total', default='Total')} |",
            "| :--- | :---: | :---: | :---: | :---: |",
        ]
        for platform, data in sentiment_data.items():
            if isinstance(data, dict):
                lines.append(f"| **{platform}** | {data.get('bullish', 0)} | {data.get('bearish', 0)} | "
                             f"{data.get('neutral', 0)} | {data.get('total', 0)} |")
        return "\n".join(lines) + "\n"

    def render_platform_breakdown(self, sentiment_data: dict) -> str:
        """渲染平台细分表格"""
        t = self._t
        if not sentiment_data:
            return ""
        
        lines = [
            f"## {t('report.platform_breakdown', default='Platform Breakdown')}",
            "",
            f"| {t('report.platform', default='Platform')} | "
            f"{t('report.sentiment', default='Sentiment')} | "
            f"{t('report.key_topics', default='Key Topics')} |",
            "| :--- | :--- | :--- |",
        ]
        for platform, data in sentiment_data.items():
            if isinstance(data, dict):
                topics = ", ".join(data.get("topics", []))
                sentiment = data.get("sentiment", "")
                lines.append(f"| **{platform}** | {sentiment} | {topics} |")
        return "\n".join(lines) + "\n"

    def render_news(self, news_timeline: list) -> str:
        """渲染新闻事件表格"""
        t = self._t
        if not news_timeline:
            return ""
        
        lines = [
            f"## {t('report.news_events', default='Key News Events')}",
            "",
            f"| {t('report.date', default='Date')} | "
            f"{t('report.event', default='Event')} | "
            f"{t('report.impact', default='Impact')} | "
            f"{t('report.category', default='Category')} |",
            "| :--- | :--- | :---: | :--- |",
        ]
        for article in news_timeline[:15]:
            lines.append(f"| {article.get('date', '')} | {article.get('title', '')[:100]} | "
                         f"{article.get('impact', '')} | {article.get('category', '')} |")
        return "\n".join(lines) + "\n"

    def render_risk_reward(self, risk_data: list[dict] | dict) -> str:
        """渲染风险收益矩阵表格"""
        t = self._t
        if not risk_data:
            return ""
        
        lines = [
            f"## {t('report.risk_reward', default='Risk-Reward Analysis')}",
            "",
            f"| {t('report.scenario', default='Scenario')} | "
            f"{t('report.trigger', default='Trigger')} | "
            f"{t('report.outcome', default='Outcome')} | "
            f"{t('report.probability', default='Probability')} | "
            f"{t('report.risk_reward_ratio', default='R/R Ratio')} |",
            "| :--- | :--- | :--- | :---: | :---: |",
        ]
        
        if isinstance(risk_data, dict):
            items = risk_data.items()
        else:
            items = [(row.get('scenario', ''), row) for row in risk_data]
        
        for scenario, data in items:
            lines.append(f"| **{scenario}** | {data.get('trigger', '')} | {data.get('outcome', '')} | "
                         f"{data.get('probability', '')} | {data.get('ratio', '')} |")
        return "\n".join(lines) + "\n"

    def render_action_plan(self, actions: list[dict]) -> str:
        """渲染操作建议表格"""
        t = self._t
        if not actions:
            return ""
        
        lines = [
            f"## {t('report.action_plan', default='Action Plan')}",
            "",
            f"| {t('report.timeframe', default='Timeframe')} | "
            f"{t('report.action', default='Action')} | "
            f"{t('report.key_levels', default='Key Levels')} | "
            f"{t('report.risk_control', default='Risk Control')} |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for a in actions:
            lines.append(f"| **{a.get('timeframe', '')}** | {a.get('action', '')} | "
                         f"{a.get('levels', '')} | {a.get('risk', '')} |")
        return "\n".join(lines) + "\n"

    def render_bull_bear(self, table: list[dict]) -> str:
        """渲染多空辩论表格"""
        t = self._t
        if not table:
            return ""
        
        lines = [
            f"## {t('report.bull_bear_debate', default='Bull vs Bear Debate')}",
            "",
            f"| {t('report.perspective', default='Perspective')} | "
            f"{t('report.argument', default='Argument')} | "
            f"{t('report.evidence', default='Key Evidence')} |",
            "| :--- | :--- | :--- |",
        ]
        for row in table:
            lines.append(f"| **{row.get('perspective', '')}** | {row.get('argument', '')} | {row.get('evidence', '')} |")
        return "\n".join(lines) + "\n"

    def render_macro(self, table: list[dict] | dict) -> str:
        """渲染宏观环境表格"""
        t = self._t
        if not table:
            return ""
        
        lines = [
            f"## {t('report.macro_overview', default='Macro Overview')}",
            "",
            f"| {t('report.theme', default='Theme')} | "
            f"{t('report.key_points', default='Key Points')} | "
            f"{t('report.impact', default='Impact')} |",
            "| :--- | :--- | :--- |",
        ]
        
        # 处理 dict 结构: {theme: {points: ..., impact: ...}}
        if isinstance(table, dict):
            for theme, data in table.items():
                if isinstance(data, dict):
                    points = data.get("points", "")
                    impact = data.get("impact", "")
                else:
                    points = str(data)
                    impact = ""
                lines.append(f"| **{theme}** | {points} | {impact} |")
        else:
            # 处理 list 结构
            for row in table:
                lines.append(f"| **{row.get('theme', '')}** | {row.get('points', '')} | {row.get('impact', '')} |")
        return "\n".join(lines) + "\n"

    def render_industry(self, table: list[dict] | dict) -> str:
        """渲染行业趋势表格"""
        t = self._t
        if not table:
            return ""
        
        lines = [
            f"## {t('report.industry_trends', default='Industry Trends')}",
            "",
            f"| {t('report.sector', default='Sector')} | "
            f"{t('report.trend', default='Trend')} | "
            f"{t('report.impact', default='Impact')} |",
            "| :--- | :--- | :--- |",
        ]
        
        if isinstance(table, dict):
            for sector, data in table.items():
                if isinstance(data, dict):
                    trend = data.get("trend", "")
                    impact = data.get("impact", "")
                else:
                    trend = str(data)
                    impact = ""
                lines.append(f"| **{sector}** | {trend} | {impact} |")
        else:
            for row in table:
                lines.append(f"| **{row.get('sector', '')}** | {row.get('trend', '')} | {row.get('impact', '')} |")
        return "\n".join(lines) + "\n"

    def render_company(self, table: list[dict] | dict) -> str:
        """渲染公司最新信息表格"""
        t = self._t
        if not table:
            return ""
        
        lines = [
            f"## {t('report.company_latest', default='Company Latest Info')}",
            "",
            f"| {t('report.item', default='Item')} | "
            f"{t('report.detail', default='Detail')} |",
            "| :--- | :--- |",
        ]
        
        if isinstance(table, dict):
            for item, detail in table.items():
                lines.append(f"| **{item}** | {detail} |")
        else:
            for row in table:
                lines.append(f"| **{row.get('item', '')}** | {row.get('detail', '')} |")
        return "\n".join(lines) + "\n"

    def render_strategies(self, table: list[dict] | dict) -> str:
        """渲染策略建议表格"""
        t = self._t
        if not table:
            return ""
        
        lines = [
            f"## {t('report.strategies', default='Strategies')}",
            "",
            f"| {t('report.strategy', default='Strategy')} | "
            f"{t('report.action_points', default='Action Points')} | "
            f"{t('report.risk_points', default='Risk Points')} |",
            "| :--- | :--- | :--- |",
        ]
        
        if isinstance(table, dict):
            for strategy, data in table.items():
                if isinstance(data, dict):
                    action = data.get("action", "")
                    risk = data.get("risk", "")
                else:
                    action = str(data)
                    risk = ""
                lines.append(f"| **{strategy}** | {action} | {risk} |")
        else:
            for row in table:
                lines.append(f"| **{row.get('strategy', '')}** | {row.get('action', '')} | {row.get('risk', '')} |")
        return "\n".join(lines) + "\n"

    def render_key_points(self, table: list[dict]) -> str:
        """渲染关键要点表格"""
        t = self._t
        if not table:
            return ""
        
        lines = [
            f"## {t('report.key_points', default='Key Points Summary')}",
            "",
            f"| {t('report.dimension', default='Dimension')} | "
            f"{t('report.key_point', default='Key Point')} | "
            f"{t('report.action', default='Action')} |",
            "| :--- | :--- | :--- |",
        ]
        for row in table:
            lines.append(f"| **{row.get('dimension', '')}** | {row.get('point', '')} | {row.get('action', '')} |")
        return "\n".join(lines) + "\n"

    def render_financials(self, table: list[dict]) -> str:
        """渲染财务报表概览"""
        t = self._t
        if not table:
            return ""
        
        lines = [
            f"## {t('report.financials_overview', default='Financial Statements Overview')}",
            "",
            f"| {t('report.statement', default='Statement')} | "
            f"{t('report.period', default='Period')} | "
            f"{t('report.key_items', default='Key Items')} |",
            "| :--- | :--- | :--- |",
        ]
        for row in table:
            lines.append(f"| **{row.get('statement', '')}** | {row.get('period', '')} | {row.get('items', '')} |")
        return "\n".join(lines) + "\n"

    def render_risk_factors(self, risks: list[dict]) -> str:
        """渲染风险因子表格"""
        t = self._t
        if not risks:
            return ""
        
        lines = [
            f"## {t('report.risk_factors', default='Risk Factors')}",
            "",
            f"| {t('report.risk', default='Risk Factor')} | "
            f"{t('report.trigger', default='Trigger')} | "
            f"{t('report.impact', default='Impact')} | "
            f"{t('report.mitigation', default='Mitigation')} |",
            "| :--- | :--- | :---: | :--- |",
        ]
        for r in risks:
            if isinstance(r, dict):
                lines.append(f"| **{r.get('risk', '')}** | {r.get('trigger', '')} | {r.get('impact', '')} | {r.get('mitigation', '')} |")
        return "\n".join(lines) + "\n"

    def render_catalysts(self, catalysts: list[dict]) -> str:
        """渲染催化剂表格"""
        t = self._t
        if not catalysts:
            return ""
        
        lines = [
            f"## {t('report.catalysts', default='Key Catalysts')}",
            "",
            f"| {t('report.catalyst', default='Catalyst')} | "
            f"{t('report.timing', default='Timing')} | "
            f"{t('report.impact', default='Impact')} | "
            f"{t('report.probability', default='Probability')} |",
            "| :--- | :--- | :---: | :---: |",
        ]
        for c in catalysts:
            if isinstance(c, dict):
                lines.append(f"| **{c.get('catalyst', '')}** | {c.get('timing', '')} | {c.get('impact', '')} | {c.get('probability', '')} |")
        return "\n".join(lines) + "\n"

    def _get_ev_attr(self, ev, attr: str, default=None):
        """从 EvidenceItem 对象或 dict 获取属性"""
        if isinstance(ev, dict):
            return ev.get(attr, default)
        return getattr(ev, attr, default)

    def render_evidence_appendix(self, evidence_items: list) -> str:
        """渲染证据附录表格"""
        t = self._t
        if not evidence_items:
            return ""
        
        lines = [
            f"## {t('report.evidence_appendix', default='Evidence Appendix')}",
            "",
            f"| {t('report.evidence_id', default='Evidence ID')} | "
            f"{t('report.evidence_type', default='Type')} | "
            f"{t('report.data_source', default='Data Source')} | "
            f"{t('report.summary', default='Summary')} | "
            f"{t('report.processing_level', default='Level')} | "
            f"{t('report.quality_scores', default='Quality')} |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for ev in evidence_items:
            q = self._get_ev_attr(ev, 'metadata', {}).get('quality_scores', {}) if self._get_ev_attr(ev, 'metadata') else {}
            q_str = json.dumps(q, ensure_ascii=False) if q else "-"
            level = self._get_ev_attr(ev, 'metadata', {}).get('processing_level', '-') if self._get_ev_attr(ev, 'metadata') else '-'
            lines.append(f"| `{self._get_ev_attr(ev, 'evidence_id')}` | {self._get_ev_attr(ev, 'evidence_type')} | {self._get_ev_attr(ev, 'provider')} | {self._get_ev_attr(ev, 'summary')} | {level} | {q_str} |")

        return "\n".join(lines) + "\n"

    def render_evidence_chain(self, evidence_items: list) -> str:
        """渲染证据基因链"""
        t = self._t
        if not evidence_items:
            return ""
        
        lines = [f"## {t('report.evidence_chain', default='Evidence Chain')}", ""]

        for ev in evidence_items:
            lines.append(f"**`{self._get_ev_attr(ev, 'evidence_id')}`** ({self._get_ev_attr(ev, 'evidence_type')}, {self._get_ev_attr(ev, 'provider')})")
            lines.append(f"  {self._get_ev_attr(ev, 'summary')}")
            lineage = self._get_ev_attr(ev, 'lineage', [])
            if lineage:
                lineage_str = " → ".join(f"`{anc}`" for anc in lineage)
                lines.append(f"  ↳ {t('report.lineage', default='Lineage')}: {lineage_str}")
            metadata = self._get_ev_attr(ev, 'metadata', {})
            if metadata and metadata.get('processing_chain'):
                chain_str = " → ".join(metadata['processing_chain'])
                lines.append(f"  ↳ {t('report.processing_chain', default='Processing Chain')}: {chain_str}")
            if metadata and metadata.get('quality_scores'):
                q_str = json.dumps(metadata['quality_scores'], ensure_ascii=False)
                lines.append(f"  ↳ {t('report.quality', default='Quality')}: {q_str}")
            lines.append("---")

        return "\n".join(lines) + "\n"

    def render_data_suggestions(self, analyst_outputs: list) -> str:
        """渲染数据优化建议"""
        t = self._t
        all_suggestions = []
        for output in analyst_outputs:
            suggestions = output.fields.get("data_suggestions", []) if hasattr(output, 'fields') else []
            if suggestions:
                for s in suggestions:
                    s["analyst"] = output.role_id
                    all_suggestions.append(s)
        
        if not all_suggestions:
            return ""
        
        lines = [f"## {t('report.data_suggestions', default='Data Optimization Suggestions')}", ""]
        lines.append(f"| {t('report.analyst', default='Analyst')} | {t('report.category', default='Category')} | {t('report.suggestion', default='Suggestion')} | {t('report.reason', default='Reason')} | {t('report.priority', default='Priority')} |")
        lines.append("| :--- | :--- | :--- | :--- | :---: |")
        
        for s in all_suggestions:
            analyst = s.get("analyst", "")
            category = s.get("category", "")
            suggestion = s.get("suggestion", "")
            reason = s.get("reason", "")
            priority = s.get("priority", "")
            lines.append(f"| {analyst} | {category} | {suggestion} | {reason} | {priority} |")
        
        return "\n".join(lines) + "\n"

    def _t(self, key: str, default: str = "") -> str:
        """i18n 翻译快捷方法"""
        if hasattr(self.i18n, 't'):
            try:
                return self.i18n.t(key, default=default)
            except Exception:
                return default or key
        return default or key