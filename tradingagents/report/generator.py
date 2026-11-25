"""Report Generator - 专业级分析报告生成器。

迁移自原项目 tradingagents/reporting.py，适配新架构：
- 7角色架构 + 内部多轮辩论
- 专业级报告结构：7大章节 + 证据附录 + 证据链
- 结构化数据自动表格化
- 证据链/基因链/处理链深度展示
- 双语言支持
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader

from tradingagents.models.evidence import EvidenceManifest
from tradingagents.roles.base import RoleOutput
from tradingagents.utils import get_i18n, set_i18n
from .extractor import EvidenceChainExtractor


def _analyst_display_name(role_id: str, i18n) -> str:
    """分析师显示名称映射，优先从 i18n 读取。"""
    key = f"report.analyst_views.{role_id}"
    try:
        return i18n.t(key)
    except Exception:
        return role_id.replace("_", " ").title()


def _format_model_info(settings: dict | None) -> str:
    """格式化模型信息字符串。"""
    if not settings:
        return "Unknown"
    s = settings.get
    deep_provider = s("deep_think_provider") or s("llm_provider", "?")
    quick_provider = s("quick_think_provider") or s("llm_provider", "?")
    if deep_provider == quick_provider:
        return f"{deep_provider}, deep {s('deep_think_llm', '?')}, quick {s('quick_think_llm', '?')}"
    else:
        return (f"deep {deep_provider} {s('deep_think_llm', '?')}, "
                f"quick {quick_provider} {s('quick_think_llm', '?')}")


def _format_vendors(settings: dict | None) -> str:
    """格式化数据供应商信息。"""
    if not settings:
        return ""
    s = settings.get
    vendors = {**(s("data_vendors") or {}), **(s("tool_vendors") or {})}
    if not vendors:
        return ""
    return "Data vendors: " + ", ".join(f"{k} {v}" for k, v in vendors.items())


def _build_header(
    ticker: str,
    final_output: RoleOutput,
    analyst_outputs: list[RoleOutput],
    settings: dict | None,
    i18n,
    memory_note: str | None = None,
    run_time: str | None = None,
) -> str:
    """构建报告头部信息。"""
    lines = [f"# {i18n.t('report.title', default='AI Investment Analysis Report')}: {ticker}", ""]

    if hasattr(final_output, 'run_time') and final_output.run_time:
        lines.append(f"- {i18n.t('report.analysis_date', default='Analysis date')}: {final_output.run_time}")

    if final_output.fields.get("final_rating"):
        lines.append(f"- {i18n.t('report.rating', default='Rating')}: {final_output.fields['final_rating']}")

    run_time = run_time or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lines.append(f"- {i18n.t('report.generated_at', default='Generated at')}: {run_time}")

    if settings:
        s = settings.get
        lines.append(f"- {i18n.t('report.version', default='TradingAgents')} {s('version', '?')}: {_format_model_info(settings)}")

        analyst_keys = s("analysts", [])
        analyst_names_list = [_analyst_display_name(k, i18n) for k in analyst_keys]
        lines.append(f"- {i18n.t('report.analysts', default='Analysts')}: {', '.join(analyst_names_list)}; "
                     f"{i18n.t('report.research_rounds', default='research debate rounds')} {s('max_debate_rounds', '?')}, "
                     f"{i18n.t('report.risk_rounds', default='risk debate rounds')} {s('max_risk_discuss_rounds', '?')}")

        vendor_str = _format_vendors(settings)
        if vendor_str:
            lines.append(f"- {vendor_str}")

    if memory_note:
        lines.append(f"- {i18n.t('report.memory_log', default='Memory log')}: {memory_note}")

    return "\n".join(lines) + "\n\n"


def _format_model_info(settings: dict | None) -> str:
    if not settings:
        return "Unknown"
    s = settings.get
    deep_provider = s("deep_think_provider") or s("llm_provider", "?")
    quick_provider = s("quick_think_provider") or s("llm_provider", "?")
    if deep_provider == quick_provider:
        return f"{deep_provider}, deep {s('deep_think_llm', '?')}, quick {s('quick_think_llm', '?')}"
    else:
        return (f"deep {deep_provider} {s('deep_think_llm', '?')}, "
                f"quick {quick_provider} {s('quick_think_llm', '?')}")


def _format_vendors(settings: dict | None) -> str:
    if not settings:
        return ""
    s = settings.get
    vendors = {**(s("data_vendors") or {}), **(s("tool_vendors") or {})}
    if not vendors:
        return ""
    return "Data vendors: " + ", ".join(f"{k} {v}" for k, v in vendors.items())


# ========== 表格渲染函数 ==========

def _render_dict_as_table(data: dict, i18n) -> str:
    """将字典渲染为 Markdown 表格。"""
    if not data:
        return ""
    lines = [
        f"| {i18n.t('report.field', default='Field')} | {i18n.t('report.value', default='Value')} |",
        "| :--- | :--- |",
    ]
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False, indent=2)
        lines.append(f"| **{k}** | {v} |")
    return "\n".join(lines) + "\n"


def _render_list_as_table(items: list[dict], headers: list[str], i18n) -> str:
    """将列表渲染为 Markdown 表格。"""
    if not items:
        return ""
    lines = [
        "| " + " | ".join(f"**{i18n.t(h, default=h)}**" for h in headers) + " |",
        "| " + " | ".join(":---" for _ in headers) + " |",
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


def _render_technical_indicators_table(indicators: list[dict], i18n) -> str:
    """渲染技术指标表格。"""
    if not indicators:
        return ""
    lines = [
        f"## {i18n.t('report.technical_indicators', default='Technical Indicators')}",
        "",
        f"| {i18n.t('report.indicator', default='Indicator')} | "
        f"{i18n.t('report.value', default='Value')} | "
        f"{i18n.t('report.signal', default='Signal')} | "
        f"{i18n.t('report.threshold', default='Threshold')} | "
        f"{i18n.t('report.meaning', default='Meaning')} |",
        "| :--- | :---: | :---: | :---: | :--- |",
    ]
    for ind in indicators:
        lines.append(f"| **{ind.get('indicator','')}** | {ind.get('value','')} | "
                     f"{ind.get('signal','')} | {ind.get('threshold','')} | {ind.get('meaning','')} |")
    return "\n".join(lines) + "\n"


def _render_key_levels_table(levels: dict, i18n) -> str:
    """渲染关键价位表格。"""
    if not levels:
        return ""
    lines = [
        f"## {i18n.t('report.key_levels', default='Key Levels')}",
        "",
        f"| {i18n.t('report.level_type', default='Type')} | "
        f"{i18n.t('report.price', default='Price')} | "
        f"{i18n.t('report.description', default='Description')} |",
        "| :--- | :---: | :--- |",
    ]
    for k, v in levels.items():
        if isinstance(v, list):
            for price in v:
                lines.append(f"| **{k}** | {price} | {k.replace('_',' ').title()} |")
        else:
            lines.append(f"| **{k}** | {v} | {k.replace('_',' ').title()} |")
    return "\n".join(lines) + "\n"


def _render_signals_table(signals: dict, i18n) -> str:
    """渲染信号汇总表格。"""
    if not signals:
        return ""
    lines = [
        f"## {i18n.t('report.signal_summary', default='Signal Summary')}",
        "",
        f"| {i18n.t('report.indicator', default='Indicator')} | "
        f"{i18n.t('report.value', default='Value')} | "
        f"{i18n.t('report.signal', default='Signal')} | "
        f"{i18n.t('report.trend', default='Trend')} |",
        "| :--- | :---: | :---: | :---: |",
    ]
    for k, v in signals.items():
        if isinstance(v, dict):
            lines.append(f"| **{k}** | {v.get('value','')} | {v.get('signal','')} | {v.get('trend','')} |")
        else:
            lines.append(f"| **{k}** | {v} | - | - |")
    return "\n".join(lines) + "\n"


def _render_financial_ratios_table(ratios: dict, i18n) -> str:
    """渲染财务比率表格。"""
    if not ratios:
        return ""
    lines = [
        f"## {i18n.t('report.financial_ratios', default='Financial Ratios')}",
        "",
        f"| {i18n.t('report.metric', default='Metric')} | "
        f"{i18n.t('report.value', default='Value')} | "
        f"{i18n.t('report.benchmark', default='Benchmark')} | "
        f"{i18n.t('report.assessment', default='Assessment')} |",
        "| :--- | :---: | :---: | :--- |",
    ]
    for k, v in ratios.items():
        if isinstance(v, dict):
            lines.append(f"| **{k}** | {v.get('value','')} | {v.get('benchmark','')} | {v.get('assessment','')} |")
        else:
            lines.append(f"| **{k}** | {v} | - | - |")
    return "\n".join(lines) + "\n"


def _render_growth_metrics_table(metrics: dict, i18n) -> str:
    """渲染增长指标表格。"""
    if not metrics:
        return ""
    lines = [
        f"## {i18n.t('report.growth_metrics', default='Growth Metrics')}",
        "",
        f"| {i18n.t('report.metric', default='Metric')} | "
        f"{i18n.t('report.value', default='Value')} | "
        f"{i18n.t('report.yoy', default='YoY')} | "
        f"{i18n.t('report.trend', default='Trend')} |",
        "| :--- | :---: | :---: | :---: |",
    ]
    for k, v in metrics.items():
        if isinstance(v, dict):
            lines.append(f"| **{k}** | {v.get('value','')} | {v.get('yoy','')} | {v.get('trend','')} |")
        else:
            lines.append(f"| **{k}** | {v} | - | - |")
    return "\n".join(lines) + "\n"


def _render_valuation_table(metrics: dict, i18n) -> str:
    """渲染估值指标表格。"""
    if not metrics:
        return ""
    lines = [
        f"## {i18n.t('report.valuation_metrics', default='Valuation Metrics')}",
        "",
        f"| {i18n.t('report.metric', default='Metric')} | "
        f"{i18n.t('report.value', default='Value')} | "
        f"{i18n.t('report.benchmark', default='Benchmark')} | "
        f"{i18n.t('report.assessment', default='Assessment')} |",
        "| :--- | :---: | :---: | :--- |",
    ]
    for k, v in metrics.items():
        if isinstance(v, dict):
            lines.append(f"| **{k}** | {v.get('value','')} | {v.get('benchmark','')} | {v.get('assessment','')} |")
        else:
            lines.append(f"| **{k}** | {v} | - | - |")
    return "\n".join(lines) + "\n"


def _render_profitability_table(metrics: dict, i18n) -> str:
    """渲染盈利能力指标表格。"""
    if not metrics:
        return ""
    lines = [
        f"## {i18n.t('report.profitability', default='Profitability Metrics')}",
        "",
        f"| {i18n.t('report.metric', default='Metric')} | "
        f"{i18n.t('report.value', default='Value')} | "
        f"{i18n.t('report.benchmark', default='Benchmark')} | "
        f"{i18n.t('report.assessment', default='Assessment')} |",
        "| :--- | :---: | :---: | :--- |",
    ]
    for k, v in metrics.items():
        if isinstance(v, dict):
            lines.append(f"| **{k}** | {v.get('value','')} | {v.get('benchmark','')} | {v.get('assessment','')} |")
        else:
            lines.append(f"| **{k}** | {v} | - | - |")
    return "\n".join(lines) + "\n"


def _render_balance_sheet_table(health: dict, i18n) -> str:
    """渲染资产负债表健康度。"""
    if not health:
        return ""
    lines = [
        f"## {i18n.t('report.balance_sheet_health', default='Balance Sheet Health')}",
        "",
        f"| {i18n.t('report.metric', default='Metric')} | "
        f"{i18n.t('report.value', default='Value')} | "
        f"{i18n.t('report.benchmark', default='Benchmark')} | "
        f"{i18n.t('report.assessment', default='Assessment')} |",
        "| :--- | :---: | :---: | :--- |",
    ]
    for k, v in health.items():
        if isinstance(v, dict):
            lines.append(f"| **{k}** | {v.get('value','')} | {v.get('benchmark','')} | {v.get('assessment','')} |")
        else:
            lines.append(f"| **{k}** | {v} | - | - |")
    return "\n".join(lines) + "\n"


def _render_cash_flow_table(cf: dict, i18n) -> str:
    """渲染现金流分析。"""
    if not cf:
        return ""
    lines = [
        f"## {i18n.t('report.cash_flow', default='Cash Flow Analysis')}",
        "",
        f"| {i18n.t('report.metric', default='Metric')} | "
        f"{i18n.t('report.value', default='Value')} | "
        f"{i18n.t('report.trend', default='Trend')} | "
        f"{i18n.t('report.assessment', default='Assessment')} |",
        "| :--- | :---: | :---: | :--- |",
    ]
    for k, v in cf.items():
        if isinstance(v, dict):
            lines.append(f"| **{k}** | {v.get('value','')} | {v.get('trend','')} | {v.get('assessment','')} |")
        else:
            lines.append(f"| **{k}** | {v} | - | - |")
    return "\n".join(lines) + "\n"


def _render_insider_table(activity: dict, i18n) -> str:
    """渲染内部人交易表格。"""
    if not activity:
        return ""
    lines = [
        f"## {i18n.t('report.insider_activity', default='Insider Activity')}",
        "",
        f"| {i18n.t('report.date', default='Date')} | "
        f"{i18n.t('report.insider', default='Insider')} | "
        f"{i18n.t('report.action', default='Action')} | "
        f"{i18n.t('report.shares', default='Shares')} | "
        f"{i18n.t('report.price', default='Price')} |",
        "| :--- | :--- | :--- | :---: | :---: |",
    ]
    for item in activity.get("transactions", []):
        lines.append(f"| {item.get('date','')} | {item.get('insider','')} | {item.get('action','')} | "
                     f"{item.get('shares','')} | {item.get('price','')} |")
    return "\n".join(lines) + "\n"


def _render_sentiment_table(table: list[dict], i18n) -> str:
    """渲染情绪分布表格。"""
    if not table:
        return ""
    lines = [
        f"## {i18n.t('report.sentiment_distribution', default='Sentiment Distribution')}",
        "",
        f"| {i18n.t('report.platform', default='Platform')} | "
        f"{i18n.t('report.bullish', default='Bullish')} | "
        f"{i18n.t('report.bearish', default='Bearish')} | "
        f"{i18n.t('report.neutral', default='Neutral')} | "
        f"{i18n.t('report.total', default='Total')} |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ]
    for row in table:
        lines.append(f"| **{row.get('platform','')}** | {row.get('bullish',0)} | {row.get('bearish',0)} | "
                     f"{row.get('neutral',0)} | {row.get('total',0)} |")
    return "\n".join(lines) + "\n"


def _render_platform_breakdown_table(breakdown: dict, i18n) -> str:
    """渲染平台细分表格。"""
    if not breakdown:
        return ""
    lines = [
        f"## {i18n.t('report.platform_breakdown', default='Platform Breakdown')}",
        "",
        f"| {i18n.t('report.platform', default='Platform')} | "
        f"{i18n.t('report.sentiment', default='Sentiment')} | "
        f"{i18n.t('report.key_topics', default='Key Topics')} |",
        "| :--- | :--- | :--- |",
    ]
    for platform, data in breakdown.items():
        topics = ", ".join(data.get("topics", [])) if isinstance(data, dict) else str(data)
        sentiment = data.get("sentiment", "") if isinstance(data, dict) else str(data)
        lines.append(f"| **{platform}** | {sentiment} | {topics} |")
    return "\n".join(lines) + "\n"


def _render_news_table(table: list[dict], i18n) -> str:
    """渲染新闻事件表格。"""
    if not table:
        return ""
    lines = [
        f"## {i18n.t('report.news_events', default='Key News Events')}",
        "",
        f"| {i18n.t('report.date', default='Date')} | "
        f"{i18n.t('report.event', default='Event')} | "
        f"{i18n.t('report.impact', default='Impact')} | "
        f"{i18n.t('report.category', default='Category')} |",
        "| :--- | :--- | :---: | :--- |",
    ]
    for row in table:
        lines.append(f"| {row.get('date','')} | {row.get('event','')} | {row.get('impact','')} | {row.get('category','')} |")
    return "\n".join(lines) + "\n"


def _render_risk_reward_matrix(risk_data: dict, i18n) -> str:
    """渲染风险收益矩阵表格。"""
    if not risk_data:
        return ""
    lines = [
        f"## {i18n.t('report.risk_reward', default='Risk-Reward Analysis')}",
        "",
        f"| {i18n.t('report.scenario', default='Scenario')} | "
        f"{i18n.t('report.trigger', default='Trigger')} | "
        f"{i18n.t('report.outcome', default='Outcome')} | "
        f"{i18n.t('report.probability', default='Probability')} | "
        f"{i18n.t('report.risk_reward_ratio', default='R/R Ratio')} |",
        "| :--- | :--- | :--- | :---: | :---: |",
    ]
    for scenario, data in risk_data.items():
        lines.append(f"| **{scenario}** | {data.get('trigger','')} | {data.get('outcome','')} | "
                     f"{data.get('probability','')} | {data.get('ratio','')} |")
    return "\n".join(lines) + "\n"


def _render_action_table(actions: list[dict], i18n) -> str:
    """渲染操作建议表格。"""
    if not actions:
        return ""
    lines = [
        f"## {i18n.t('report.action_plan', default='Action Plan')}",
        "",
        f"| {i18n.t('report.timeframe', default='Timeframe')} | "
        f"{i18n.t('report.action', default='Action')} | "
        f"{i18n.t('report.key_levels', default='Key Levels')} | "
        f"{i18n.t('report.risk_control', default='Risk Control')} |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for a in actions:
        lines.append(f"| **{a.get('timeframe','')}** | {a.get('action','')} | "
                     f"{a.get('levels','')} | {a.get('risk','')} |")
    return "\n".join(lines) + "\n"


def _render_bull_bear_table(table: list[dict], i18n) -> str:
    """渲染多空辩论表格。"""
    if not table:
        return ""
    lines = [
        f"## {i18n.t('report.bull_bear_debate', default='Bull vs Bear Debate')}",
        "",
        f"| {i18n.t('report.perspective', default='Perspective')} | "
        f"{i18n.t('report.argument', default='Argument')} | "
        f"{i18n.t('report.evidence', default='Key Evidence')} |",
        "| :--- | :--- | :--- |",
    ]
    for row in table:
        lines.append(f"| **{row.get('perspective','')}** | {row.get('argument','')} | {row.get('evidence','')} |")
    return "\n".join(lines) + "\n"


def _render_macro_table(table: list[dict], i18n) -> str:
    """渲染宏观环境表格。"""
    if not table:
        return ""
    lines = [
        f"## {i18n.t('report.macro_overview', default='Macro Overview')}",
        "",
        f"| {i18n.t('report.theme', default='Theme')} | "
        f"{i18n.t('report.key_points', default='Key Points')} | "
        f"{i18n.t('report.impact', default='Impact')} |",
        "| :--- | :--- | :--- |",
    ]
    for row in table:
        lines.append(f"| **{row.get('theme','')}** | {row.get('points','')} | {row.get('impact','')} |")
    return "\n".join(lines) + "\n"


def _render_industry_table(table: list[dict], i18n) -> str:
    """渲染行业趋势表格。"""
    if not table:
        return ""
    lines = [
        f"## {i18n.t('report.industry_trends', default='Industry Trends')}",
        "",
        f"| {i18n.t('report.sector', default='Sector')} | "
        f"{i18n.t('report.trend', default='Trend')} | "
        f"{i18n.t('report.impact', default='Impact')} |",
        "| :--- | :--- | :--- |",
    ]
    for row in table:
        lines.append(f"| **{row.get('sector','')}** | {row.get('trend','')} | {row.get('impact','')} |")
    return "\n".join(lines) + "\n"


def _render_company_table(table: list[dict], i18n) -> str:
    """渲染公司最新信息表格。"""
    if not table:
        return ""
    lines = [
        f"## {i18n.t('report.company_latest', default='Company Latest Info')}",
        "",
        f"| {i18n.t('report.item', default='Item')} | "
        f"{i18n.t('report.detail', default='Detail')} |",
        "| :--- | :--- |",
    ]
    for row in table:
        lines.append(f"| **{row.get('item','')}** | {row.get('detail','')} |")
    return "\n".join(lines) + "\n"


def _render_strategy_table(table: list[dict], i18n) -> str:
    """渲染策略建议表格。"""
    if not table:
        return ""
    lines = [
        f"## {i18n.t('report.strategies', default='Strategies')}",
        "",
        f"| {i18n.t('report.strategy', default='Strategy')} | "
        f"{i18n.t('report.action_points', default='Action Points')} | "
        f"{i18n.t('report.risk_points', default='Risk Points')} |",
        "| :--- | :--- | :--- |",
    ]
    for row in table:
        lines.append(f"| **{row.get('strategy','')}** | {row.get('action','')} | {row.get('risk','')} |")
    return "\n".join(lines) + "\n"


def _render_key_points_table(table: list[dict], i18n) -> str:
    """渲染关键要点表格。"""
    if not table:
        return ""
    lines = [
        f"## {i18n.t('report.key_points', default='Key Points Summary')}",
        "",
        f"| {i18n.t('report.dimension', default='Dimension')} | "
        f"{i18n.t('report.key_point', default='Key Point')} | "
        f"{i18n.t('report.action', default='Action')} |",
        "| :--- | :--- | :--- |",
    ]
    for row in table:
        lines.append(f"| **{row.get('dimension','')}** | {row.get('point','')} | {row.get('action','')} |")
    return "\n".join(lines) + "\n"


def _render_financials_table(table: list[dict], i18n) -> str:
    """渲染财务报表概览。"""
    if not table:
        return ""
    lines = [
        f"## {i18n.t('report.financials_overview', default='Financial Statements Overview')}",
        "",
        f"| {i18n.t('report.statement', default='Statement')} | "
        f"{i18n.t('report.period', default='Period')} | "
        f"{i18n.t('report.key_items', default='Key Items')} |",
        "| :--- | :--- | :--- |",
    ]
    for row in table:
        lines.append(f"| **{row.get('statement','')}** | {row.get('period','')} | {row.get('items','')} |")
    return "\n".join(lines) + "\n"


def _render_risk_factors_table(risks: list[dict], i18n) -> str:
    """渲染风险因子表格。"""
    if not risks:
        return ""
    lines = [
        f"## {i18n.t('report.risk_factors', default='Risk Factors')}",
        "",
        f"| {i18n.t('report.risk', default='Risk Factor')} | "
        f"{i18n.t('report.trigger', default='Trigger')} | "
        f"{i18n.t('report.impact', default='Impact')} | "
        f"{i18n.t('report.mitigation', default='Mitigation')} |",
        "| :--- | :--- | :---: | :--- |",
    ]
    for r in risks:
        lines.append(f"| **{r.get('risk','')}** | {r.get('trigger','')} | {r.get('impact','')} | {r.get('mitigation','')} |")
    return "\n".join(lines) + "\n"


def _render_catalysts_table(catalysts: list[dict], i18n) -> str:
    """渲染催化剂表格。"""
    if not catalysts:
        return ""
    lines = [
        f"## {i18n.t('report.catalysts', default='Key Catalysts')}",
        "",
        f"| {i18n.t('report.catalyst', default='Catalyst')} | "
        f"{i18n.t('report.timing', default='Timing')} | "
        f"{i18n.t('report.impact', default='Impact')} | "
        f"{i18n.t('report.probability', default='Probability')} |",
        "| :--- | :--- | :---: | :---: |",
    ]
    for c in catalysts:
        lines.append(f"| **{c.get('catalyst','')}** | {c.get('timing','')} | {c.get('impact','')} | {c.get('probability','')} |")
    return "\n".join(lines) + "\n"


def _render_evidence_table(evidence_items: list, i18n) -> str:
    """渲染证据附录表格。"""
    if not evidence_items:
        return ""

    lines = [
        f"## {i18n.t('report.evidence_appendix', default='Evidence Appendix')}",
        "",
        f"| {i18n.t('report.evidence_id', default='Evidence ID')} | "
        f"{i18n.t('report.evidence_type', default='Type')} | "
        f"{i18n.t('report.data_source', default='Data Source')} | "
        f"{i18n.t('report.summary', default='Summary')} | "
        f"{i18n.t('report.processing_level', default='Level')} | "
        f"{i18n.t('report.quality_scores', default='Quality')} |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for ev in evidence_items:
        q = ev.metadata.quality_scores if hasattr(ev, 'metadata') and ev.metadata else {}
        q_str = json.dumps(q, ensure_ascii=False) if q else "-"
        level = ev.metadata.processing_level if hasattr(ev, 'metadata') and ev.metadata else '-'
        lines.append(f"| `{ev.evidence_id}` | {ev.evidence_type} | {ev.provider} | {ev.summary} | {level} | {q_str} |")

    return "\n".join(lines) + "\n"


def _render_evidence_chain(evidence_items: list, i18n) -> str:
    """渲染证据基因链。"""
    if not evidence_items:
        return ""

    lines = [f"## {i18n.t('report.evidence_chain', default='Evidence Chain')}", ""]

    for ev in evidence_items:
        lines.append(f"**`{ev.evidence_id}`** ({ev.evidence_type}, {ev.provider})")
        if ev.lineage:
            lineage_str = " → ".join(f"`{anc}`" for anc in ev.lineage)
            lines.append(f"  ↳ {i18n.t('report.lineage', default='Lineage')}: {lineage_str}")
        if hasattr(ev, 'metadata') and ev.metadata and ev.metadata.processing_chain:
            chain_str = " → ".join(ev.metadata.processing_chain)
            lines.append(f"  ↳ {i18n.t('report.processing_chain', default='Processing Chain')}: {chain_str}")
        if hasattr(ev, 'metadata') and ev.metadata and ev.metadata.quality_scores:
            q_str = json.dumps(ev.metadata.quality_scores, ensure_ascii=False)
            lines.append(f"  ↳ {i18n.t('report.quality', default='Quality')}: {q_str}")
        lines.append("---")

    return "\n".join(lines) + "\n"


def _collect_report_parts(
    final_output: RoleOutput,
    analyst_outputs: list[RoleOutput],
    i18n
) -> list[tuple[str, str, list[tuple[str, str, str]]]]:
    """收集报告各部分内容。"""
    all_outputs = {o.role_id: o for o in analyst_outputs}
    all_outputs[final_output.role_id] = final_output

    team_analysts = ["market_analyst", "sentiment_analyst", "news_analyst", "fundamentals_analyst",
                     "research_manager", "trader", "risk_manager"]
    
    parts = []
    for sec in _infer_sections({}, team_analysts, True, True, i18n):
        heading = i18n.t(sec["title_key"], default=sec["title_key"])
        written = []
        for role_id, filename, field_path in sec["roles"]:
            output = {o.role_id: o for o in analyst_outputs}.get(role_id)
            if not output:
                continue

            if isinstance(field_path, str):
                value = getattr(output, field_path, None) or output.fields.get(field_path)
            else:
                value = None

            if value:
                display_name = _analyst_display_name(role_id, i18n)
                written.append((display_name, filename, str(value)))

        if written:
            parts.append((heading, sec["folder"], written))

    return parts


def _collect_structured_report_parts(
    final_output: RoleOutput,
    analyst_outputs: list[RoleOutput],
    i18n
) -> dict[str, Any]:
    """收集结构化报告内容，用于模板渲染。"""
    all_outputs = {o.role_id: o for o in analyst_outputs}
    all_outputs[final_output.role_id] = final_output

    result = {
        "analyst_sections": [],
        "final_report": final_output,
    }

    # 1. Analyst Team
    core_analysts = ["market_analyst", "sentiment_analyst", "news_analyst", "fundamentals_analyst"]
    for role_id in core_analysts:
        output = all_outputs.get(role_id)
        if output:
            result["analyst_sections"].append({
                "role": _analyst_display_name(role_id, get_i18n()),
                "role_id": role_id,
                "narrative": output.narrative,
                "fields": output.fields,
                "cited_evidence": output.cited_evidence,
            })

    # 2. Research Manager
    rm = all_outputs.get("research_manager")
    if rm:
        result["research_section"] = {
            "role": _analyst_display_name("research_manager", get_i18n()),
            "narrative": rm.narrative,
            "fields": rm.fields,
            "cited_evidence": rm.cited_evidence,
        }

    # 3. Trader
    tr = all_outputs.get("trader")
    if tr:
        result["trading_section"] = {
            "role": _analyst_display_name("trader", get_i18n()),
            "narrative": tr.narrative,
            "fields": tr.fields,
            "cited_evidence": tr.cited_evidence,
        }

    # 4. Risk Manager
    rm = all_outputs.get("risk_manager")
    if rm:
        result["risk_section"] = {
            "role": _analyst_display_name("risk_manager", get_i18n()),
            "narrative": rm.narrative,
            "fields": rm.fields,
            "cited_evidence": rm.cited_evidence,
        }

    return result


def _render_evidence_table(evidence_items: list, i18n) -> str:
    """渲染证据附录表格。"""
    if not evidence_items:
        return ""

    lines = [
        f"## {i18n.t('report.evidence_appendix', default='Evidence Appendix')}",
        "",
        f"| {i18n.t('report.evidence_id', default='Evidence ID')} | "
        f"{i18n.t('report.evidence_type', default='Type')} | "
        f"{i18n.t('report.data_source', default='Data Source')} | "
        f"{i18n.t('report.summary', default='Summary')} | "
        f"{i18n.t('report.processing_level', default='Level')} | "
        f"{i18n.t('report.quality_scores', default='Quality')} |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for ev in evidence_items:
        q = ev.metadata.quality_scores if hasattr(ev, 'metadata') and ev.metadata else {}
        q_str = json.dumps(q, ensure_ascii=False) if q else "-"
        level = ev.metadata.processing_level if hasattr(ev, 'metadata') and ev.metadata else '-'
        lines.append(f"| `{ev.evidence_id}` | {ev.evidence_type} | {ev.provider} | {ev.summary} | {level} | {q_str} |")

    return "\n".join(lines) + "\n"


def _render_evidence_chain(evidence_items: list, i18n) -> str:
    """渲染证据基因链。"""
    if not evidence_items:
        return ""

    lines = [f"## {i18n.t('report.evidence_chain', default='Evidence Chain')}", ""]

    for ev in evidence_items:
        lines.append(f"**`{ev.evidence_id}`** ({ev.evidence_type}, {ev.provider})")
        if ev.lineage:
            lineage_str = " → ".join(f"`{anc}`" for anc in ev.lineage)
            lines.append(f"  ↳ {i18n.t('report.lineage', default='Lineage')}: {lineage_str}")
        if hasattr(ev, 'metadata') and ev.metadata and ev.metadata.processing_chain:
            chain_str = " → ".join(ev.metadata.processing_chain)
            lines.append(f"  ↳ {i18n.t('report.processing_chain', default='Processing Chain')}: {chain_str}")
        if hasattr(ev, 'metadata') and ev.metadata and ev.metadata.quality_scores:
            q_str = json.dumps(ev.metadata.quality_scores, ensure_ascii=False)
            lines.append(f"  ↳ {i18n.t('report.quality', default='Quality')}: {q_str}")
        lines.append("---")

    return "\n".join(lines) + "\n"


# ========== 章节自动推导 ==========

def _infer_sections(team_analysts: list[str], has_research: bool, has_trader: bool, has_risk: bool, i18n) -> list[dict]:
    """根据 Role 拓扑自动推导报告章节。"""
    sections = []

    # 1. Analyst Team - 核心分析师
    core_analysts = [r for r in team_analysts if r in {"market_analyst", "sentiment_analyst", "news_analyst", "fundamentals_analyst"}]
    if core_analysts:
        sections.append({
            "title_key": "report.sections.analyst_team",
            "folder": "1_analysts",
            "roles": [(r, f"{r}.md", "narrative") for r in core_analysts]
        })

    # 2. Research Team
    if has_research or "research_manager" in team_analysts:
        sections.append({
            "title_key": "report.sections.research_team",
            "folder": "2_research",
            "roles": [("research_manager", "manager.md", "narrative")]
        })

    # 3. Trading Team
    if has_trader or "trader" in team_analysts:
        sections.append({
            "title_key": "report.sections.trading_team",
            "folder": "3_trading",
            "roles": [("trader", "trader.md", "narrative")]
        })

    # 4. Risk Team
    if has_risk or "risk_manager" in team_analysts:
        sections.append({
            "title_key": "report.sections.risk_team",
            "folder": "4_risk",
            "roles": [("risk_manager", "manager.md", "narrative")]
        })

    # 5. Portfolio Manager - 总是最后
    sections.append({
        "title_key": "report.sections.portfolio_manager",
        "folder": "5_portfolio",
        "roles": [("project_manager", "decision.md", "narrative")]
    })

    return sections


def _collect_report_parts(
    final_output: RoleOutput,
    analyst_outputs: list[RoleOutput],
    i18n
) -> list[tuple[str, str, list[tuple[str, str, str]]]]:
    """收集报告各部分内容。"""
    all_outputs = {o.role_id: o for o in analyst_outputs}
    all_outputs[final_output.role_id] = final_output

    team_analysts = ["market_analyst", "sentiment_analyst", "news_analyst", "fundamentals_analyst",
                     "research_manager", "trader", "risk_manager"]
    
    parts = []
    for sec in _infer_sections({}, team_analysts, True, True, i18n):
        heading = i18n.t(sec["title_key"], default=sec["title_key"])
        written = []
        for role_id, filename, field_path in sec["roles"]:
            output = {o.role_id: o for o in analyst_outputs}.get(role_id)
            if not output:
                continue

            if isinstance(field_path, str):
                value = getattr(output, field_path, None) or output.fields.get(field_path)
            else:
                value = None

            if value:
                display_name = _analyst_display_name(role_id, i18n)
                written.append((display_name, filename, str(value)))

        if written:
            parts.append((heading, sec["folder"], written))

    return parts


def _collect_structured_report_parts(
    final_output: RoleOutput,
    analyst_outputs: list[RoleOutput],
    i18n
) -> dict[str, Any]:
    """收集结构化报告内容，用于模板渲染。"""
    all_outputs = {o.role_id: o for o in analyst_outputs}
    all_outputs[final_output.role_id] = final_output

    result = {
        "analyst_sections": [],
        "final_report": final_output,
    }

    # 1. Analyst Team
    core_analysts = ["market_analyst", "sentiment_analyst", "news_analyst", "fundamentals_analyst"]
    for role_id in core_analysts:
        output = all_outputs.get(role_id)
        if output:
            result["analyst_sections"].append({
                "role": _analyst_display_name(role_id, get_i18n()),
                "role_id": role_id,
                "narrative": output.narrative,
                "fields": output.fields,
                "cited_evidence": output.cited_evidence,
            })

    # 2. Research Manager
    rm = all_outputs.get("research_manager")
    if rm:
        result["research_section"] = {
            "role": _analyst_display_name("research_manager", get_i18n()),
            "narrative": rm.narrative,
            "fields": rm.fields,
            "cited_evidence": rm.cited_evidence,
        }

    # 3. Trader
    tr = all_outputs.get("trader")
    if tr:
        result["trading_section"] = {
            "role": _analyst_display_name("trader", get_i18n()),
            "narrative": tr.narrative,
            "fields": tr.fields,
            "cited_evidence": tr.cited_evidence,
        }

    # 4. Risk Manager
    rm = all_outputs.get("risk_manager")
    if rm:
        result["risk_section"] = {
            "role": _analyst_display_name("risk_manager", get_i18n()),
            "narrative": rm.narrative,
            "fields": rm.fields,
            "cited_evidence": rm.cited_evidence,
        }

    return result


# ========== 辅助函数 ==========

def _analyst_display_name(role_id: str, i18n) -> str:
    """分析师显示名称映射，优先从 i18n 读取。"""
    key = f"report.analyst_views.{role_id}"
    try:
        return i18n.t(key)
    except Exception:
        return role_id.replace("_", " ").title()


def _format_model_info(settings: dict | None) -> str:
    """格式化模型信息字符串。"""
    if not settings:
        return "Unknown"
    s = settings.get
    deep_provider = s("deep_think_provider") or s("llm_provider", "?")
    quick_provider = s("quick_think_provider") or s("llm_provider", "?")
    if deep_provider == quick_provider:
        return f"{deep_provider}, deep {s('deep_think_llm', '?')}, quick {s('quick_think_llm', '?')}"
    else:
        return (f"deep {deep_provider} {s('deep_think_llm', '?')}, "
                f"quick {quick_provider} {s('quick_think_llm', '?')}")


def _format_vendors(settings: dict | None) -> str:
    """格式化数据供应商信息。"""
    if not settings:
        return ""
    s = settings.get
    vendors = {**(s("data_vendors") or {}), **(s("tool_vendors") or {})}
    if not vendors:
        return ""
    return "Data vendors: " + ", ".join(f"{k} {v}" for k, v in vendors.items())


def _build_header(
    ticker: str,
    final_output: RoleOutput,
    analyst_outputs: list[RoleOutput],
    settings: dict | None,
    i18n,
    memory_note: str | None = None,
    run_time: str | None = None,
) -> str:
    """构建报告头部信息。"""
    lines = [f"# {i18n.t('report.title', default='AI Investment Analysis Report')}: {ticker}", ""]

    if hasattr(final_output, 'run_time') and final_output.run_time:
        lines.append(f"- {i18n.t('report.analysis_date', default='Analysis date')}: {final_output.run_time}")

    if final_output.fields.get("final_rating"):
        lines.append(f"- {i18n.t('report.rating', default='Rating')}: {final_output.fields['final_rating']}")

    run_time = run_time or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lines.append(f"- {i18n.t('report.generated_at', default='Generated at')}: {run_time}")

    if settings:
        s = settings.get
        lines.append(f"- {i18n.t('report.version', default='TradingAgents')} {s('version', '?')}: {_format_model_info(settings)}")

        analyst_keys = s("analysts", [])
        analyst_names_list = [_analyst_display_name(k, i18n) for k in analyst_keys]
        lines.append(f"- {i18n.t('report.analysts', default='Analysts')}: {', '.join(analyst_names_list)}; "
                     f"{i18n.t('report.research_rounds', default='research debate rounds')} {s('max_debate_rounds', '?')}, "
                     f"{i18n.t('report.risk_rounds', default='risk debate rounds')} {s('max_risk_discuss_rounds', '?')}")

        vendor_str = _format_vendors(settings)
        if vendor_str:
            lines.append(f"- {vendor_str}")

    if memory_note:
        lines.append(f"- {i18n.t('report.memory_log', default='Memory log')}: {memory_note}")

    return "\n".join(lines) + "\n\n"


def _format_model_info(settings: dict | None) -> str:
    if not settings:
        return "Unknown"
    s = settings.get
    deep_provider = s("deep_think_provider") or s("llm_provider", "?")
    quick_provider = s("quick_think_provider") or s("llm_provider", "?")
    if deep_provider == quick_provider:
        return f"{deep_provider}, deep {s('deep_think_llm', '?')}, quick {s('quick_think_llm', '?')}"
    else:
        return (f"deep {deep_provider} {s('deep_think_llm', '?')}, "
                f"quick {quick_provider} {s('quick_think_llm', '?')}")


def _format_vendors(settings: dict | None) -> str:
    if not settings:
        return ""
    s = settings.get
    vendors = {**(s("data_vendors") or {}), **(s("tool_vendors") or {})}
    if not vendors:
        return ""
    return "Data vendors: " + ", ".join(f"{k} {v}" for k, v in vendors.items())


def _build_header(
    ticker: str,
    final_output: RoleOutput,
    analyst_outputs: list[RoleOutput],
    settings: dict | None,
    i18n,
    memory_note: str | None = None,
    run_time: str | None = None,
) -> str:
    """构建报告头部信息。"""
    lines = [f"# {i18n.t('report.title', default='AI Investment Analysis Report')}: {ticker}", ""]

    if hasattr(final_output, 'run_time') and final_output.run_time:
        lines.append(f"- {i18n.t('report.analysis_date', default='Analysis date')}: {final_output.run_time}")

    if final_output.fields.get("final_rating"):
        lines.append(f"- {i18n.t('report.rating', default='Rating')}: {final_output.fields['final_rating']}")

    run_time = run_time or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lines.append(f"- {i18n.t('report.generated_at', default='Generated at')}: {run_time}")

    if settings:
        s = settings.get
        lines.append(f"- {i18n.t('report.version', default='TradingAgents')} {s('version', '?')}: {_format_model_info(settings)}")

        analyst_keys = s("analysts", [])
        analyst_names_list = [_analyst_display_name(k, i18n) for k in analyst_keys]
        lines.append(f"- {i18n.t('report.analysts', default='Analysts')}: {', '.join(analyst_names_list)}; "
                     f"{i18n.t('report.research_rounds', default='research debate rounds')} {s('max_debate_rounds', '?')}, "
                     f"{i18n.t('report.risk_rounds', default='risk debate rounds')} {s('max_risk_discuss_rounds', '?')}")

        vendor_str = _format_vendors(settings)
        if vendor_str:
            lines.append(f"- {vendor_str}")

    if memory_note:
        lines.append(f"- {i18n.t('report.memory_log', default='Memory log')}: {memory_note}")

    return "\n".join(lines) + "\n\n"


def _render_evidence_table(evidence_items: list, i18n) -> str:
    """渲染证据附录表格。"""
    if not evidence_items:
        return ""

    lines = [
        f"## {i18n.t('report.evidence_appendix', default='Evidence Appendix')}",
        "",
        f"| {i18n.t('report.evidence_id', default='Evidence ID')} | "
        f"{i18n.t('report.evidence_type', default='Type')} | "
        f"{i18n.t('report.data_source', default='Data Source')} | "
        f"{i18n.t('report.summary', default='Summary')} | "
        f"{i18n.t('report.processing_level', default='Level')} | "
        f"{i18n.t('report.quality_scores', default='Quality')} |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for ev in evidence_items:
        q = ev.metadata.quality_scores if hasattr(ev, 'metadata') and ev.metadata else {}
        q_str = json.dumps(q, ensure_ascii=False) if q else "-"
        level = ev.metadata.processing_level if hasattr(ev, 'metadata') and ev.metadata else '-'
        lines.append(f"| `{ev.evidence_id}` | {ev.evidence_type} | {ev.provider} | {ev.summary} | {level} | {q_str} |")

    return "\n".join(lines) + "\n"


def _render_evidence_chain(evidence_items: list, i18n) -> str:
    """渲染证据基因链。"""
    if not evidence_items:
        return ""

    lines = [f"## {i18n.t('report.evidence_chain', default='Evidence Chain')}", ""]

    for ev in evidence_items:
        lines.append(f"**`{ev.evidence_id}`** ({ev.evidence_type}, {ev.provider})")
        if ev.lineage:
            lineage_str = " → ".join(f"`{anc}`" for anc in ev.lineage)
            lines.append(f"  ↳ {i18n.t('report.lineage', default='Lineage')}: {lineage_str}")
        if hasattr(ev, 'metadata') and ev.metadata and ev.metadata.processing_chain:
            chain_str = " → ".join(ev.metadata.processing_chain)
            lines.append(f"  ↳ {i18n.t('report.processing_chain', default='Processing Chain')}: {chain_str}")
        if hasattr(ev, 'metadata') and ev.metadata and ev.metadata.quality_scores:
            q_str = json.dumps(ev.metadata.quality_scores, ensure_ascii=False)
            lines.append(f"  ↳ {i18n.t('report.quality', default='Quality')}: {q_str}")
        lines.append("---")

    return "\n".join(lines) + "\n"


def generate_report_tree(
    final_output: RoleOutput,
    analyst_outputs: list[RoleOutput],
    manifest: 'EvidenceManifest',
    run_dir: Path,
    ticker: str,
    lang: str = "zh-CN",
    settings: dict | None = None,
    template_dir: str = "templates",
    run_time: str | None = None,
) -> Path:
    """
    生成完整报告树 - 专业版。
    """
    i18n = get_i18n()
    if lang:
        set_i18n(lang)

    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. 构建头部
    memory_note = getattr(final_output, 'memory_note', None)
    run_time = run_time or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    header = _build_header(ticker, final_output, analyst_outputs, None, get_i18n(), memory_note, run_time)

    # 2. 收集证据
    cited_ids = set(final_output.cited_evidence)
    cited_evidence_items = [item for item in manifest.items if item.evidence_id in cited_ids]

    # 3. 收集报告部分
    parts = _collect_report_parts(final_output, analyst_outputs, get_i18n())

    # 3. 渲染各章节
    sections = []
    for heading, folder, written in parts:
        (run_dir / folder).mkdir(exist_ok=True)
        for agent_name, filename, text in written:
            (run_dir / folder / filename).write_text(text, encoding="utf-8")

        content = "\n\n".join(f"### {agent}\n{text}" for agent, _filename, text in written)
        sections.append(f"## {heading}\n\n{content}")

    # 4. 证据附录
    cited_ids = set(final_output.cited_evidence)
    cited_evidence_items = [item for item in manifest.items if item.evidence_id in cited_ids]
    evidence_table = _render_evidence_table(cited_evidence_items, get_i18n())
    if evidence_table:
        sections.append(evidence_table)

    # 5. 证据链
    evidence_chain = _render_evidence_chain(cited_evidence_items, get_i18n())
    if evidence_chain:
        sections.append(evidence_chain)

    # 6. 生成完整 Markdown 报告
    full_md = header + "\n\n".join(sections) + "\n\n---\n\n" + \
              f"*{get_i18n().t('report.footer', default='Generated by TradingAgents. Conclusions are based on the evidence listed in this report.')}*"

    report_path = run_dir / f"complete_report.{lang}.md"
    report_path.write_text(full_md, encoding="utf-8")

    return report_path


def render_report(
    final_output: RoleOutput,
    analyst_outputs: list[RoleOutput],
    manifest: 'EvidenceManifest',
    run_dir: Path,
    ticker: str,
    lang: str = "zh-CN",
    settings: dict | None = None,
) -> Path:
    """Orchestrator 调用的统一入口。"""
    return generate_report_tree(
        final_output=final_output,
        analyst_outputs=analyst_outputs,
        manifest=manifest,
        run_dir=run_dir,
        ticker=ticker,
        lang=lang,
        settings=settings,
    )