from __future__ import annotations
import json
from datetime import datetime
from typing import Any
from tradingagents.evidence.view import EvidenceView
from tradingagents.models.evidence import EvidenceItem, EvidenceMetadata
from tradingagents.roles.base import ProjectManager as ProjectManagerBase, RoleOutput, RoleBase
from tradingagents.run.context import RunContext
from tradingagents.utils.json_parser import extract_json
from tradingagents.utils import get_i18n, set_i18n


class EvidenceChainExtractor:
    """从证据链中提取结构化数据供报告编译使用"""
    
    def __init__(self, evidence_view: EvidenceView):
        self.evidence_view = evidence_view
    
    def _get_raw(self, ev_id: str) -> dict | None:
        """获取原始数据"""
        return self.evidence_view.get_raw(ev_id)
    
    def get_cited_evidence_items(self, cited_ids: set[str]) -> list:
        """获取被引用的证据项"""
        items = []
        for ev_id in cited_ids:
            ev = self.evidence_view.get(ev_id)
            if ev:
                items.append(ev)
        return items
    
    def get_technical_indicators(self, cited_ids: set[str]) -> dict:
        """提取技术指标数据"""
        indicators = {}
        for ev in self.evidence_view.for_types({"market_indicators"}):
            raw = self._get_raw(ev.evidence_id)
            if raw and raw.get("values"):
                indicator_name = raw.get("indicator", "")
                indicators[indicator_name] = raw["values"]
        return indicators
    
    def get_financial_statements(self, cited_ids: set[str]) -> dict:
        """提取财务报表数据"""
        statements = {}
        for ev in self.evidence_view.for_types({"financials_raw"}):
            raw = self._get_raw(ev.evidence_id)
            if raw:
                stmt_type = raw.get("statement_type", "unknown")
                statements[stmt_type] = raw.get("csv", "")
        return statements
    
    def get_fundamentals_overview(self, cited_ids: set[str]) -> dict:
        """提取基本面概览数据"""
        for ev in self.evidence_view.for_types({"fundamentals_raw"}):
            raw = self._get_raw(ev.evidence_id)
            if raw:
                return raw.get("fields", {})
        return {}
    
    def get_insider_transactions(self, cited_ids: set[str]) -> list:
        """获取内部人交易数据"""
        for ev in self.evidence_view.for_types({"insider_raw"}):
            raw = self._get_raw(ev.evidence_id)
            if raw:
                return raw.get("insider_transactions", [])
        return []
    
    def get_news_timeline(self, cited_ids: set[str]) -> list:
        """获取新闻时间线"""
        articles = []
        for ev in self.evidence_view.for_types({"news_raw", "global_news_raw"}):
            raw = self._get_raw(ev.evidence_id)
            if raw and raw.get("articles"):
                articles.extend(raw["articles"])
        return articles
    
    def get_sentiment_data(self, cited_ids: set[str]) -> dict:
        """获取情绪分析数据"""
        for ev in self.evidence_view.for_types({"sentiment_social_stocktwits", "sentiment_social_reddit"}):
            raw = self._get_raw(ev.evidence_id)
            if raw:
                return raw
        return {}
    
    def get_macro_indicators(self, cited_ids: set[str]) -> dict:
        """获取宏观指标"""
        for ev in self.evidence_view.for_types({"macro_raw"}):
            raw = self._get_raw(ev.evidence_id)
            if raw:
                return raw
        return {}
    
    def get_evidence_chains(self, cited_ids: set[str]) -> list[dict]:
        """获取完整证据链信息"""
        chains = []
        for ev_id in cited_ids:
            ev = self.evidence_view.get(ev_id)
            if ev:
                chains.append({
                    "evidence_id": ev.evidence_id,
                    "evidence_type": ev.evidence_type,
                    "provider": ev.provider,
                    "lineage": ev.lineage,
                    "processing_chain": ev.metadata.processing_chain if ev.metadata else [],
                    "quality_scores": ev.metadata.quality_scores if ev.metadata else {},
                    "processing_level": ev.metadata.processing_level if ev.metadata else "raw",
                    "summary": ev.summary,
                })
        return chains


class ProjectManager(RoleBase, ProjectManagerBase):
    role_id = "project_manager"
    consumes = []  # 空 = 默认消费所有 analyst 的输出
    template = "project_manager.j2"

    def prepare_context(self, ctx: "AnalystContext") -> dict[str, Any]:
        # 收集所有分析师的结构化输出
        analyst_data = {}
        all_cited_ids = set()
        
        for role_id, output in ctx.prior_outputs.items():
            analyst_data[role_id] = {
                "role_id": output.role_id,
                "display_name": self._get_display_name(role_id),
                "narrative": output.narrative,
                "fields": output.fields,
                "cited_evidence": output.cited_evidence,
            }
            all_cited_ids.update(output.cited_evidence)
        
        # 创建证据链提取器
        extractor = EvidenceChainExtractor(ctx.evidence)
        all_cited_ids = set()
        for output in ctx.prior_outputs.values():
            all_cited_ids.update(output.cited_evidence)
        
        evidence_data = {
            "technical_indicators": extractor.get_technical_indicators(all_cited_ids),
            "financial_statements": extractor.get_financial_statements(all_cited_ids),
            "fundamentals_overview": extractor.get_fundamentals_overview(all_cited_ids),
            "insider_transactions": extractor.get_insider_transactions(all_cited_ids),
            "news_timeline": extractor.get_news_timeline(all_cited_ids),
            "sentiment_data": extractor.get_sentiment_data(all_cited_ids),
            "macro_indicators": extractor.get_macro_indicators(all_cited_ids),
            "evidence_chains": extractor.get_evidence_chains(all_cited_ids),
            "total_evidence": len(all_cited_ids),
        }
        
        # 编译各专业章节
        compiled_sections = {
            "executive_summary": self._compile_executive_summary(ctx, analyst_data, evidence_data),
            "analyst_views": self._compile_analyst_views(analyst_data),
            "technical_analysis": self._compile_technical_analysis(evidence_data, analyst_data),
            "fundamental_analysis": self._compile_fundamental_analysis(evidence_data, analyst_data),
            "sentiment_analysis": self._compile_sentiment_analysis(evidence_data, analyst_data),
            "news_macro": self._compile_news_macro(evidence_data, analyst_data),
            "risk_reward": self._compile_risk_reward(evidence_data, analyst_data),
            "action_plan": self._compile_action_plan(analyst_data),
        }
        
        # 预格式化复杂结构为字符串，避免模板中使用 | tojson 导致 Unicode 转义
        formatted_sections = {k: self._format_compiled_section(v) for k, v in compiled_sections.items()}
        formatted_evidence = {k: self._format_compiled_section(v) for k, v in evidence_data.items()}
        formatted_analyst = {k: {
            **v, 
            "fields_str": self._format_compiled_section(v.get("fields", {}))
        } for k, v in analyst_data.items()}
        
        # 设置 i18n 语言
        if ctx.lang:
            set_i18n(ctx.lang)
        
        # 获取 i18n 实例
        i18n = get_i18n()
        
        # 构建最终上下文 - 使用预格式化的字符串，避免模板中 | tojson 导致 Unicode 转义
        context = {
            "ticker": ctx.ticker,
            "analyst_data": formatted_analyst,
            "evidence_data": formatted_evidence,
            "compiled_sections": formatted_sections,
            "output_language": ctx.lang,
            "run_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "i18n": i18n,
            "final_rating_placeholder": "BUY|HOLD|SELL",
        }
        
        return context

    def _format_compiled_section(self, value: Any, max_chars: int = 8000) -> str:
        """
        将编译章节的复杂结构格式化为字符串，避免模板中 | tojson 导致 Unicode 转义。
        
        兼容 dict、list、primitive 类型，输出紧凑的 JSON 字符串（保留 Unicode 字符）。
        """
        if value is None:
            return ""
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        # dict/list 等复杂结构：JSON 序列化，保留 Unicode，必要时截断
        payload_str = json.dumps(value, ensure_ascii=False, default=str)
        if len(payload_str) > max_chars:
            payload_str = payload_str[:max_chars] + "... [truncated]"
        return payload_str
    
    def _get_display_name(self, role_id: str) -> str:
        """获取分析师显示名称"""
        names = {
            "market_analyst": "市场技术面",
            "sentiment_analyst": "情绪面",
            "news_analyst": "新闻事件面",
            "fundamentals_analyst": "基本面估值",
            "research_manager": "研究经理",
            "trader": "交易员",
            "risk_manager": "风险经理",
            "project_manager": "项目经理",
        }
        return names.get(role_id, role_id.replace("_", " ").title())
    
    def _compile_executive_summary(self, ctx: dict, analyst_data: dict, evidence_data: dict) -> dict:
        """编译核心结论章节"""
        rating = self._determine_rating(analyst_data)
        return {
            "rating": rating,
            "narrative": self._build_executive_narrative(analyst_data, rating),
            "risk_reward_matrix": self._build_risk_reward_matrix(),
            "action_plan": self._compile_action_plan(analyst_data),
        }
    
    def _compile_analyst_views(self, analyst_data: dict) -> list[dict]:
        """编译分析师视角汇总"""
        views = []
        for role_id, data in analyst_data.items():
            if role_id == "project_manager":
                continue
            fields = data.get("fields", {})
            result = {
                "role": self._get_display_name(role_id),
                "role_id": role_id,
                "narrative": data.get("narrative", ""),
                "fields": fields,
                "cited_evidence": data.get("cited_evidence", []),
            }
            # 根据角色类型添加结构化字段渲染提示
            if "technical_indicators" in fields:
                result["render_hint"] = "technical_indicators"
            elif "financial_ratios" in fields:
                result["render_hint"] = "financial_ratios"
            elif "core_signals" in fields:
                result["render_hint"] = "core_signals"
            views.append(result)
        return views
    
    def _compile_technical_analysis(self, evidence_data: dict, analyst_data: dict) -> dict:
        """编译技术分析章节"""
        indicators = evidence_data.get("technical_indicators", {})
        market_analyst = analyst_data.get("market_analyst", {})
        return {
            "indicators_table": self._render_technical_indicators_table(indicators),
            "key_levels_table": self._render_key_levels_table(indicators, market_analyst.get("fields", {})),
            "signals_table": self._render_signals_table(market_analyst.get("fields", {})),
            "trend_analysis": market_analyst.get("narrative", ""),
        }
    
    def _compile_fundamental_analysis(self, evidence_data: dict, analyst_data: dict) -> dict:
        """编译基本面分析章节"""
        fund_overview = evidence_data.get("fundamentals_overview", {})
        fund_analyst = analyst_data.get("fundamentals_analyst", {})
        insider = evidence_data.get("insider_transactions", [])
        financials = evidence_data.get("financial_statements", {})
        return {
            "financial_ratios_table": self._render_financial_ratios_table(fund_overview, fund_analyst.get("fields", {})),
            "growth_metrics_table": self._render_growth_metrics_table(fund_overview),
            "valuation_table": self._render_valuation_table(fund_overview),
            "profitability_table": self._render_profitability_table(fund_overview),
            "balance_sheet_table": self._render_balance_sheet_table(financials),
            "cash_flow_table": self._render_cash_flow_table(financials),
            "insider_table": self._render_insider_table(insider),
            "narrative": fund_analyst.get("narrative", ""),
        }
    
    def _compile_sentiment_analysis(self, evidence_data: dict, analyst_data: dict) -> dict:
        """编译情绪分析章节"""
        sentiment_data = evidence_data.get("sentiment_data", {})
        sent_analyst = analyst_data.get("sentiment_analyst", {})
        return {
            "sentiment_table": self._render_sentiment_table(sentiment_data),
            "platform_breakdown_table": self._render_platform_breakdown_table(sentiment_data),
            "narrative": sent_analyst.get("narrative", ""),
        }
    
    def _compile_news_macro(self, evidence_data: dict, analyst_data: dict) -> dict:
        """编译新闻宏观章节"""
        news_timeline = evidence_data.get("news_timeline", [])
        macro = evidence_data.get("macro_indicators", {})
        news_analyst = analyst_data.get("news_analyst", {})
        return {
            "news_table": self._render_news_table(news_timeline),
            "macro_table": self._render_macro_table(macro),
            "industry_table": self._render_industry_table(news_analyst.get("fields", {})),
            "company_table": self._render_company_table(news_analyst.get("fields", {})),
            "strategies_table": self._render_strategies_table(news_analyst.get("fields", {})),
            "narrative": news_analyst.get("narrative", ""),
        }
    
    def _compile_risk_reward(self, evidence_data: dict, analyst_data: dict) -> dict:
        """编译风险收益分析章节"""
        risk_analyst = analyst_data.get("risk_manager", {})
        trader_analyst = analyst_data.get("trader", {})
        return {
            "risk_reward_matrix": self._build_risk_reward_matrix(),
            "risk_factors_table": self._render_risk_factors_table(risk_analyst.get("fields", {})),
            "catalysts_table": self._render_catalysts_table(risk_analyst.get("fields", {})),
            "trader_view": trader_analyst.get("narrative", ""),
            "risk_manager_view": risk_analyst.get("narrative", ""),
        }
    
    def _compile_action_plan(self, analyst_data: dict) -> list[dict]:
        """编译行动计划"""
        # 从 trader 和 risk_manager 提取
        trader_fields = analyst_data.get("trader", {}).get("fields", {})
        risk_fields = analyst_data.get("risk_manager", {}).get("fields", {})
        
        plan = trader_fields.get("action_plan", [])
        if plan:
            return plan
        
        # 默认计划
        return [
            {
                "timeframe": "短期(0-1月)",
                "action": "分批建仓，首单30%",
                "levels": "入场价参考当前价±2% / 止损-5%",
                "risk": "超买回调、ATR放大",
            },
            {
                "timeframe": "中期(1-3月)",
                "action": "关注关键阻力位，突破后加仓30%",
                "levels": "止盈位根据波动率动态调整",
                "risk": "关键阻力位、内部人动态",
            },
            {
                "timeframe": "长期(>3个月)",
                "action": "维持核心仓位，财报指引不及预期则减仓",
                "levels": "止损位：日线收盘破关键支撑确认破位",
                "risk": "业绩趋势、政策/持股风险、对冲工具",
            },
        ]
    
    def _determine_rating(self, analyst_data: dict) -> str:
        """基于风险收益比、证据强度、共识度综合评级"""
        # 简化：基于各分析师的信号加权
        signals = []
        for role_id, data in analyst_data.items():
            if role_id == "project_manager":
                continue
            fields = data.get("fields", {})
            if "core_signals" in fields:
                signals.extend(fields["core_signals"])
            elif "technical_indicators" in fields:
                for ind_name, ind_data in fields["technical_indicators"].items():
                    if isinstance(ind_data, dict) and "signal" in ind_data:
                        signals.append(ind_data["signal"])
        
        bullish = sum(1 for s in signals if s in ("bullish", "buy", "strong_buy", "positive", "bullish"))
        bearish = sum(1 for s in signals if s in ("bearish", "sell", "strong_sell", "negative", "bearish"))
        
        if bullish > bearish * 1.5:
            return "BUY"
        elif bearish > bullish * 1.5:
            return "SELL"
        return "HOLD"
    
    def _build_executive_narrative(self, analyst_data: dict, rating: str) -> str:
        """构建核心结论叙述"""
        parts = [f"综合评级：{rating}"]
        
        # 收集关键观点
        for role_id, data in analyst_data.items():
            if role_id == "project_manager":
                continue
            narrative = data.get("narrative", "")
            if narrative:
                name = self._get_display_name(role_id)
                # 取前200字符作为摘要
                summary = narrative[:200] + "..." if len(narrative) > 200 else narrative
                parts.append(f"\n{name}：{summary}")
        
        return "\n".join(parts)
    
    def _build_risk_reward_matrix(self) -> list[dict]:
        """构建风险收益矩阵"""
        return [
            {
                "scenario": "乐观",
                "trigger": "核心业务超预期+政策利好+资金回流",
                "outcome": "+20%~+35%",
                "probability": "25%",
                "ratio": "1:3",
            },
            {
                "scenario": "基准",
                "trigger": "业绩符合预期+估值消化+等待催化剂",
                "outcome": "-5%~+10%",
                "probability": "50%",
                "ratio": "1:1",
            },
            {
                "scenario": "悲观",
                "trigger": "核心业务放缓+宏观恶化+估值杀估值",
                "outcome": "-15%~-25%",
                "probability": "25%",
                "ratio": "1:2",
            },
        ]
    
    # ===== 表格渲染方法 =====
    
    def _render_technical_indicators_table(self, indicators: dict) -> list[dict]:
        """渲染技术指标表格数据"""
        rows = []
        for name, values in indicators.items():
            if isinstance(values, list) and values:
                latest = values[-1] if isinstance(values[-1], (int, float)) else values[-1].get("value", "")
                signal = values[-1].get("signal", "") if isinstance(values[-1], dict) else ""
            else:
                latest = ""
                signal = ""
            rows.append({
                "indicator": name.upper(),
                "value": latest,
                "signal": signal,
                "threshold": "",
                "meaning": "",
            })
        return rows
    
    def _render_key_levels_table(self, indicators: dict, fields: dict) -> list[dict]:
        """渲染关键价位表格数据"""
        levels = fields.get("key_levels", {})
        rows = []
        for level_type, price in levels.items():
            rows.append({
                "level_type": level_type.replace("_", " ").title(),
                "price": price,
                "description": level_type.replace("_", " ").title(),
            })
        return rows
    
    def _render_signals_table(self, fields: dict) -> list[dict]:
        """渲染信号汇总表格数据"""
        signals = fields.get("signals", {})
        rows = []
        for name, data in signals.items():
            if isinstance(data, dict):
                rows.append({
                    "indicator": name,
                    "value": data.get("value", ""),
                    "signal": data.get("signal", ""),
                    "trend": data.get("trend", ""),
                })
            else:
                rows.append({
                    "indicator": name,
                    "value": data,
                    "signal": "-",
                    "trend": "-",
                })
        return rows
    
    def _render_financial_ratios_table(self, fund_overview: dict, fields: dict) -> list[dict]:
        """渲染财务比率表格数据"""
        ratios = fund_overview.get("ratios", {})
        if not ratios:
            ratios = fields.get("financial_ratios", {})
        rows = []
        for name, data in ratios.items():
            if isinstance(data, dict):
                rows.append({
                    "metric": name,
                    "value": data.get("value", ""),
                    "benchmark": data.get("benchmark", ""),
                    "assessment": data.get("assessment", ""),
                })
            else:
                rows.append({
                    "metric": name,
                    "value": data,
                    "benchmark": "-",
                    "assessment": "-",
                })
        return rows
    
    def _render_growth_metrics_table(self, fund_overview: dict) -> list[dict]:
        """渲染增长指标表格数据"""
        growth = fund_overview.get("growth", {})
        rows = []
        for name, data in growth.items():
            if isinstance(data, dict):
                rows.append({
                    "metric": name,
                    "value": data.get("value", ""),
                    "yoy": data.get("yoy", ""),
                    "trend": data.get("trend", ""),
                })
            else:
                rows.append({
                    "metric": name,
                    "value": data,
                    "yoy": "-",
                    "trend": "-",
                })
        return rows
    
    def _render_valuation_table(self, fund_overview: dict) -> list[dict]:
        """渲染估值指标表格数据"""
        valuation = fund_overview.get("valuation", {})
        rows = []
        for name, data in valuation.items():
            if isinstance(data, dict):
                rows.append({
                    "metric": name,
                    "value": data.get("value", ""),
                    "benchmark": data.get("benchmark", ""),
                    "assessment": data.get("assessment", ""),
                })
            else:
                rows.append({
                    "metric": name,
                    "value": data,
                    "benchmark": "-",
                    "assessment": "-",
                })
        return rows
    
    def _render_profitability_table(self, fund_overview: dict) -> list[dict]:
        """渲染盈利能力指标表格数据"""
        profit = fund_overview.get("profitability", {})
        rows = []
        for name, data in profit.items():
            if isinstance(data, dict):
                rows.append({
                    "metric": name,
                    "value": data.get("value", ""),
                    "benchmark": data.get("benchmark", ""),
                    "assessment": data.get("assessment", ""),
                })
            else:
                rows.append({
                    "metric": name,
                    "value": data,
                    "benchmark": "-",
                    "assessment": "-",
                })
        return rows
    
    def _render_balance_sheet_table(self, financials: dict) -> list[dict]:
        """渲染资产负债表健康度数据"""
        rows = []
        for stmt_type, csv_data in financials.items():
            if "balance" in stmt_type.lower():
                rows.append({
                    "metric": stmt_type,
                    "value": "见详细报表",
                    "benchmark": "-",
                    "assessment": "-",
                })
        return rows
    
    def _render_cash_flow_table(self, financials: dict) -> list[dict]:
        """渲染现金流分析数据"""
        rows = []
        for stmt_type, csv_data in financials.items():
            if "cash" in stmt_type.lower() or "flow" in stmt_type.lower():
                rows.append({
                    "metric": stmt_type,
                    "value": "见详细报表",
                    "trend": "-",
                    "assessment": "-",
                })
        return rows
    
    def _render_insider_table(self, insider: list) -> list[dict]:
        """渲染内部人交易表格数据"""
        rows = []
        for item in insider[:10]:  # 只显示前10条
            rows.append({
                "date": item.get("date", ""),
                "insider": item.get("insider", ""),
                "action": item.get("action", ""),
                "shares": item.get("shares", ""),
                "price": item.get("price", ""),
            })
        return rows
    
    def _render_sentiment_table(self, sentiment_data: dict) -> list[dict]:
        """渲染情绪分布表格数据"""
        rows = []
        for platform, data in sentiment_data.items():
            if isinstance(data, dict):
                rows.append({
                    "platform": platform,
                    "bullish": data.get("bullish", 0),
                    "bearish": data.get("bearish", 0),
                    "neutral": data.get("neutral", 0),
                    "total": data.get("total", 0),
                })
        return rows
    
    def _render_platform_breakdown_table(self, sentiment_data: dict) -> list[dict]:
        """渲染平台细分表格数据"""
        rows = []
        for platform, data in sentiment_data.items():
            if isinstance(data, dict):
                topics = ", ".join(data.get("topics", []))
                sentiment = data.get("sentiment", "")
                rows.append({
                    "platform": platform,
                    "sentiment": sentiment,
                    "key_topics": topics,
                })
        return rows
    
    def _render_news_table(self, news_timeline: list) -> list[dict]:
        """渲染新闻事件表格数据"""
        rows = []
        for article in news_timeline[:15]:  # 只显示前15条
            rows.append({
                "date": article.get("date", ""),
                "event": article.get("title", "")[:100],
                "impact": article.get("impact", ""),
                "category": article.get("category", ""),
            })
        return rows
    
    def _render_macro_table(self, macro: dict) -> list[dict]:
        """渲染宏观环境表格数据"""
        rows = []
        for theme, data in macro.items():
            rows.append({
                "theme": theme,
                "key_points": data.get("points", "") if isinstance(data, dict) else str(data),
                "impact": data.get("impact", "") if isinstance(data, dict) else "",
            })
        return rows
    
    def _render_industry_table(self, fields: dict) -> list[dict]:
        """渲染行业趋势表格数据"""
        industry = fields.get("industry", {})
        rows = []
        for sector, data in industry.items():
            if isinstance(data, dict):
                rows.append({
                    "sector": sector,
                    "trend": data.get("trend", ""),
                    "impact": data.get("impact", ""),
                })
            else:
                rows.append({
                    "sector": sector,
                    "trend": data,
                    "impact": "-",
                })
        return rows
    
    def _render_company_table(self, fields: dict) -> list[dict]:
        """渲染公司最新信息表格数据"""
        company = fields.get("company", {})
        rows = []
        for item, detail in company.items():
            rows.append({
                "item": item,
                "detail": detail,
            })
        return rows
    
    def _render_strategies_table(self, fields: dict) -> list[dict]:
        """渲染策略建议表格数据"""
        strategies = fields.get("strategies", {})
        rows = []
        for name, data in strategies.items():
            if isinstance(data, dict):
                rows.append({
                    "strategy": name,
                    "action_points": data.get("action", ""),
                    "risk_points": data.get("risk", ""),
                })
            else:
                rows.append({
                    "strategy": name,
                    "action_points": data,
                    "risk_points": "-",
                })
        return rows
    
    def _render_risk_factors_table(self, fields: dict) -> list[dict]:
        """渲染风险因子表格数据"""
        risks = fields.get("risks", [])
        rows = []
        for r in risks:
            if isinstance(r, dict):
                rows.append({
                    "risk": r.get("risk", ""),
                    "trigger": r.get("trigger", ""),
                    "impact": r.get("impact", ""),
                    "mitigation": r.get("mitigation", ""),
                })
        return rows
    
    def _render_catalysts_table(self, fields: dict) -> list[dict]:
        """渲染催化剂表格数据"""
        catalysts = fields.get("catalysts", [])
        rows = []
        for c in catalysts:
            if isinstance(c, dict):
                rows.append({
                    "catalyst": c.get("catalyst", ""),
                    "timing": c.get("timing", ""),
                    "impact": c.get("impact", ""),
                    "probability": c.get("probability", ""),
                })
        return rows

    def parse_output(self, raw_response: str) -> RoleOutput:
        data = extract_json(raw_response)
        if data:
            return RoleOutput(
                role_id=self.role_id,
                fields={
                    "final_rating": data.get("final_rating", "HOLD"),
                    "risk_reward_matrix": data.get("risk_reward_matrix", []),
                    "action_plan": data.get("action_plan", []),
                    "evidence_chain_analysis": data.get("evidence_chain_analysis", {}),
                    "final_report": data.get("final_report", ""),
                },
                narrative=data.get("narrative", ""),
                cited_evidence=data.get("cited_evidence", []),
            )
        return RoleOutput(role_id=self.role_id, narrative=raw_response)


ProjectManager = ProjectManager