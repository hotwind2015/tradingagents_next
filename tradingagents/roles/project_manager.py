from __future__ import annotations

import json
from datetime import datetime
from typing import Any, TYPE_CHECKING
from tradingagents.evidence.view import EvidenceView
from tradingagents.roles.base import ProjectManager as ProjectManagerBase, RoleOutput, RoleBase
from tradingagents.utils.json_parser import extract_json
from tradingagents.utils import get_i18n, set_i18n
from tradingagents.report.extractor import EvidenceChainExtractor
from tradingagents.report.generator import ReportGenerator

if TYPE_CHECKING:
    from tradingagents.report.reporter import ReporterFactory
    from tradingagents.run.context import AnalystContext


class ProjectManager(RoleBase, ProjectManagerBase):
    role_id = "project_manager"
    consumes = []  # 空 = 默认消费所有 analyst 的输出
    template = "project_manager.j2"

    def __init__(self):
        self.reporters: list = []  # 支持多个 reporter
        self.generator = ReportGenerator()

    def configure(self, args: dict[str, Any]) -> None:
        """接收 recipe.args 配置，创建 Reporter(s)
        
        支持单个或多个 reporter：
        - 单个: {"preset": "us-professional"}
        - 多个: [{"preset": "us-professional"}, {"preset": "cn-professional"}]
        - 带参数: [{"preset": "us-professional", "output_formats": ["md", "html"]}, ...]
        """
        from tradingagents.report.reporter import ReporterFactory
        reporter_spec = args.get("reporter")
        
        if not reporter_spec:
            # 默认单个
            self.reporters = [ReporterFactory.create({"preset": "us-professional"}, self.generator)]
            return
        
        # 支持列表或单个
        specs = reporter_spec if isinstance(reporter_spec, list) else [reporter_spec]
        self.reporters = []
        for spec in specs:
            self.reporters.append(ReporterFactory.create(spec, self.generator))

    def prepare_context(self, ctx: "AnalystContext") -> dict[str, Any]:
        # 1. 收集分析师输出
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

        # 2. 证据数据（供 LLM 参考）
        extractor = EvidenceChainExtractor(ctx.evidence)
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

        # 3. 编译结构化章节数据（纯数据，无预格式化字符串）
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

        # 4. 返回给 LLM 的上下文（精简，纯数据结构）
        if ctx.lang:
            set_i18n(ctx.lang)

        return {
            "ticker": ctx.ticker,
            "analyst_data": analyst_data,
            "evidence_data": evidence_data,
            "compiled_sections": compiled_sections,  # 纯数据结构
            "output_language": ctx.lang,
            "run_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "i18n": get_i18n(),
            "final_rating_placeholder": "BUY|HOLD|SELL",
        }

    def _get_display_name(self, role_id: str) -> str:
        """获取分析师显示名称"""
        i18n = get_i18n()
        names = {
            "market_analyst": i18n.t("report.analyst_views.market_analyst", default="Market Analyst"),
            "sentiment_analyst": i18n.t("report.analyst_views.sentiment_analyst", default="Sentiment Analyst"),
            "news_analyst": i18n.t("report.analyst_views.news_analyst", default="News Analyst"),
            "fundamentals_analyst": i18n.t("report.analyst_views.fundamentals_analyst", default="Fundamentals Analyst"),
            "research_manager": i18n.t("report.sections.research_team", default="Research Manager"),
            "trader": i18n.t("report.sections.trading_team", default="Trader"),
            "risk_manager": i18n.t("report.sections.risk_team", default="Risk Manager"),
            "project_manager": i18n.t("report.sections.portfolio_manager", default="Project Manager"),
        }
        return names.get(role_id, role_id.replace("_", " ").title())

    def _compile_executive_summary(self, ctx: dict, analyst_data: dict, evidence_data: dict) -> dict:
        rating = self._determine_rating(analyst_data)
        return {
            "rating": rating,
            "narrative": self._build_executive_narrative(analyst_data, rating),
            "risk_reward_matrix": self._build_risk_reward_matrix(),
            "action_plan": self._compile_action_plan(analyst_data),
        }

    def _compile_analyst_views(self, analyst_data: dict) -> list[dict]:
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
            if "technical_indicators" in fields:
                result["render_hint"] = "technical_indicators"
            elif "financial_ratios" in fields:
                result["render_hint"] = "financial_ratios"
            elif "core_signals" in fields:
                result["render_hint"] = "core_signals"
            views.append(result)
        return views

    def _compile_technical_analysis(self, evidence_data: dict, analyst_data: dict) -> dict:
        indicators = evidence_data.get("technical_indicators", {})
        market_analyst = analyst_data.get("market_analyst", {})
        return {
            "indicators": indicators,
            "key_levels": market_analyst.get("fields", {}).get("key_levels", {}),
            "signals": market_analyst.get("fields", {}).get("signals", {}),
            "trend_analysis": market_analyst.get("narrative", ""),
        }

    def _compile_fundamental_analysis(self, evidence_data: dict, analyst_data: dict) -> dict:
        fund_overview = evidence_data.get("fundamentals_overview", {})
        fund_analyst = analyst_data.get("fundamentals_analyst", {})
        insider = evidence_data.get("insider_transactions", [])
        financials = evidence_data.get("financial_statements", {})
        return {
            "fundamentals_overview": fund_overview,
            "fund_analyst_fields": fund_analyst.get("fields", {}),
            "insider_transactions": insider,
            "financial_statements": financials,
            "narrative": fund_analyst.get("narrative", ""),
        }

    def _compile_sentiment_analysis(self, evidence_data: dict, analyst_data: dict) -> dict:
        sentiment_data = evidence_data.get("sentiment_data", {})
        sent_analyst = analyst_data.get("sentiment_analyst", {})
        return {
            "sentiment_data": sentiment_data,
            "narrative": sent_analyst.get("narrative", ""),
        }

    def _compile_news_macro(self, evidence_data: dict, analyst_data: dict) -> dict:
        news_timeline = evidence_data.get("news_timeline", [])
        macro = evidence_data.get("macro_indicators", {})
        news_analyst = analyst_data.get("news_analyst", {})
        return {
            "news_timeline": news_timeline,
            "macro_indicators": macro,
            "news_analyst_fields": news_analyst.get("fields", {}),
            "narrative": news_analyst.get("narrative", ""),
        }

    def _compile_risk_reward(self, evidence_data: dict, analyst_data: dict) -> dict:
        risk_analyst = analyst_data.get("risk_manager", {})
        trader_analyst = analyst_data.get("trader", {})
        return {
            "risk_reward_matrix": self._build_risk_reward_matrix(),
            "risk_analyst_fields": risk_analyst.get("fields", {}),
            "trader_view": trader_analyst.get("narrative", ""),
            "risk_manager_view": risk_analyst.get("narrative", ""),
        }

    def _compile_action_plan(self, analyst_data: dict) -> list[dict]:
        trader_fields = analyst_data.get("trader", {}).get("fields", {})
        risk_fields = analyst_data.get("risk_manager", {}).get("fields", {})

        plan = trader_fields.get("action_plan", [])
        if plan:
            return plan

        i18n = get_i18n()
        return [
            {
                "timeframe": i18n.t("report.timeframe_short", default="短期(0-1月)"),
                "action": i18n.t("report.action_batch_build", default="分批建仓，首单30%"),
                "levels": i18n.t("report.levels_entry_stop", default="入场价参考当前价±2% / 止损-5%"),
                "risk": i18n.t("report.risk_overbought_atr", default="超买回调、ATR放大"),
            },
            {
                "timeframe": i18n.t("report.timeframe_medium", default="中期(1-3月)"),
                "action": i18n.t("report.action_resistance_add", default="关注关键阻力位，突破后加仓30%"),
                "levels": i18n.t("report.levels_dynamic_tp", default="止盈位根据波动率动态调整"),
                "risk": i18n.t("report.risk_resistance_insider", default="关键阻力位、内部人动态"),
            },
            {
                "timeframe": i18n.t("report.timeframe_long", default="长期(>3个月)"),
                "action": i18n.t("report.action_core_hold", default="维持核心仓位，财报指引不及预期则减仓"),
                "levels": i18n.t("report.levels_break_support", default="止损位：日线收盘破关键支撑确认破位"),
                "risk": i18n.t("report.risk_earnings_policy_hedge", default="业绩趋势、政策/持股风险、对冲工具"),
            },
        ]

    def _determine_rating(self, analyst_data: dict) -> str:
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

        bullish = sum(1 for s in signals if s in ("bullish", "buy", "strong_buy", "positive"))
        bearish = sum(1 for s in signals if s in ("bearish", "sell", "strong_sell", "negative"))

        if bullish > bearish * 1.5:
            return "BUY"
        elif bearish > bullish * 1.5:
            return "SELL"
        return "HOLD"

    def _build_executive_narrative(self, analyst_data: dict, rating: str) -> str:
        i18n = get_i18n()
        parts = [f"{i18n.t('report.rating', default='Rating')}: {rating}"]
        for role_id, data in analyst_data.items():
            if role_id == "project_manager":
                continue
            narrative = data.get("narrative", "")
            if narrative:
                name = self._get_display_name(role_id)
                summary = narrative[:200] + "..." if len(narrative) > 200 else narrative
                parts.append(f"\n{name}：{summary}")
        return "\n".join(parts)

    def _build_risk_reward_matrix(self) -> list[dict]:
        i18n = get_i18n()
        return [
            {
                "scenario": i18n.t("report.scenario_bullish", default="乐观"),
                "trigger": i18n.t("report.trigger_bullish", default="核心业务超预期+政策利好+资金回流"),
                "outcome": i18n.t("report.outcome_bullish", default="+20%~+35%"),
                "probability": i18n.t("report.prob_bullish", default="25%"),
                "ratio": i18n.t("report.ratio_bullish", default="1:3"),
            },
            {
                "scenario": i18n.t("report.scenario_base", default="基准"),
                "trigger": i18n.t("report.trigger_base", default="业绩符合预期+估值消化+等待催化剂"),
                "outcome": i18n.t("report.outcome_base", default="-5%~+10%"),
                "probability": i18n.t("report.prob_base", default="50%"),
                "ratio": i18n.t("report.ratio_base", default="1:1"),
            },
            {
                "scenario": i18n.t("report.scenario_bearish", default="悲观"),
                "trigger": i18n.t("report.trigger_bearish", default="核心业务放缓+宏观恶化+估值杀估值"),
                "outcome": i18n.t("report.outcome_bearish", default="-15%~-25%"),
                "probability": i18n.t("report.prob_bearish", default="25%"),
                "ratio": i18n.t("report.ratio_bearish", default="1:2"),
            },
        ]

    def parse_output(self, raw_response: str) -> RoleOutput:
        """LLM 返回 JSON，解析为结构化输出"""
        data = extract_json(raw_response)
        if data:
            return RoleOutput(
                role_id=self.role_id,
                fields={
                    "final_rating": data.get("final_rating", "HOLD"),
                    "risk_reward_matrix": data.get("risk_reward_matrix", []),
                    "action_plan": data.get("action_plan", []),
                    "evidence_chain_analysis": data.get("evidence_chain_analysis", {}),
                    "final_report_structured": data.get("final_report_structured", {}),
                },
                narrative=data.get("narrative", ""),
                cited_evidence=data.get("cited_evidence", []),
            )
        return RoleOutput(role_id=self.role_id, narrative=raw_response)

    def analyze(self, ctx: "AnalystContext") -> RoleOutput:
        """完整的分析流程：LLM 决策 -> Reporter(s) 生成报告"""
        # 1. 准备 LLM 上下文（同时编译章节数据）
        prompt_ctx = self.prepare_context(ctx)
        
        # 提取编译好的章节数据，存入 decision fields 供 Reporter 使用
        compiled_sections = prompt_ctx.get("compiled_sections", {})
        
        prompt_ctx["output_language"] = ctx.lang
        prompt_ctx["ticker"] = ctx.ticker

        # 2. 渲染提示词
        from tradingagents.prompt.renderer import PromptRenderer
        renderer = ctx.shared_state.get("prompt_renderer") or PromptRenderer(ctx.recipe.template_dir if hasattr(ctx.recipe, 'template_dir') else "templates")
        prompt_text = renderer.render(self.template, prompt_ctx)

        # 3. 调用 LLM
        llm_client = ctx.shared_state.get("llm_client")
        if not llm_client:
            raise RuntimeError("LLM client not found in shared_state")
        
        raw_response = llm_client.invoke(prompt_text, ctx.model_config)

        # 4. 解析 LLM 输出
        decision = self.parse_output(raw_response)

        # 5. 将编译好的章节数据存入 decision fields，供 Reporter 使用
        decision.fields["compiled_sections"] = compiled_sections

        # 6. 生成报告（委托给所有 Reporter）
        report_bundles = []
        for reporter in self.reporters:
            bundle = reporter.generate_report(
                ctx=ctx,
                pm_decision=decision,
                output_formats=reporter.config.get("output_formats", ["md", "html"]),
                lang=ctx.lang
            )
            report_bundles.append({
                "reporter_config": reporter.config,
                "metadata": bundle.metadata,
            })
        
        decision.fields["report_bundles"] = report_bundles
        # 兼容旧字段
        if report_bundles:
            decision.fields["report_bundle"] = report_bundles[0]["metadata"]

        return decision