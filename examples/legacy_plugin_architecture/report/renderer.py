from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from tradingagents.models.evidence import EvidenceManifest
from tradingagents.roles.base import RoleOutput
from tradingagents.utils import get_i18n, set_i18n


def render_report(
    final_output: RoleOutput,
    analyst_outputs: list[RoleOutput],
    manifest: EvidenceManifest,
    run_dir: Path,
    ticker: str,
    lang: str = "zh-CN"
) -> Path:
    """使用专业模板渲染完整投资报告"""
    # 设置模板目录 - 优先使用迁移测试的专业模板
    template_dirs = ["tests/migration_plugins/templates", "templates"]
    env = Environment(loader=FileSystemLoader(template_dirs))
    
    # 自定义过滤器：保证中文正常显示并缩进，并处理异常情况
    def tojson_safe(obj, **kwargs):
        try:
            return json.dumps(obj, ensure_ascii=False, **kwargs)
        except Exception:
            return str(obj)
        
    # 注册为 tojson 覆盖内置 filter，供模板 map('tojson') 使用
    env.filters['tojson'] = tojson_safe

    # zip filter for combining multiple sequences (used in template)
    def zip_filter(*iterables):
        return list(zip(*iterables))
    env.filters['zip'] = zip_filter

    # 将宏作为全局函数注册
    def render_table(headers, rows, alignments=None):
        """将表格渲染为 Markdown"""
        if not rows:
            return ""
        if alignments is None:
            alignments = [''] * len(headers)
        lines = []
        lines.append("| " + " | ".join(f"**{h}**" for h in headers) + " |")
        lines.append("| " + " | ".join("---" + a for a in alignments) + " |")
        for row in rows:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")
        return "\n".join(lines) + "\n"
    
    def render_kv_table(data, key_header='Field', value_header='Value'):
        """渲染键值对表格"""
        if not data:
            return ""
        lines = [f"| **{key_header}** | **{value_header}** |", "| :--- | :--- |"]
        for k, v in data.items():
            lines.append(f"| **{k}** | {v} |")
        return "\n".join(lines) + "\n"
    
    def section_header(title, level=2):
        return "#" * level + " " + title + "\n\n"
    
    def lineage_chain(ev):
        if ev.get('lineage'):
            return "**Lineage**: " + " → ".join(f"`{anc}`" for anc in ev['lineage']) + "\n"
        return ""
    
    def processing_chain(ev):
        if ev.get('processing_chain'):
            return "**Processing Chain**: " + " → ".join(ev['processing_chain']) + "\n"
        return ""
    
    def quality_scores(ev):
        if ev.get('quality_scores'):
            return "**Quality**: " + json.dumps(ev['quality_scores'], ensure_ascii=False) + "\n"
        return ""
    
    env.globals['render_table'] = render_table
    env.globals['render_kv_table'] = render_kv_table
    env.globals['section_header'] = section_header
    env.globals['lineage_chain'] = lineage_chain
    env.globals['processing_chain'] = processing_chain
    env.globals['quality_scores'] = quality_scores
    
    template = env.get_template("report.j2")
    
    # 提取被引用的证据
    cited_ids = set(final_output.cited_evidence)
    cited_evidence_items = [item for item in manifest.items if item.evidence_id in cited_ids]
    
    # 设置 i18n 语言
    if lang:
        set_i18n(lang)
    
    i18n = get_i18n()
    
    # 从 final_output.fields 获取结构化报告数据
    fields = final_output.fields
    
    # 构建模板所需的完整数据
    template_data = {
        "i18n": i18n,
        "ticker": ticker,
        "run_id": manifest.run_id,
        "run_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "analysis_date": getattr(final_output, 'run_time', None) or datetime.now().strftime("%Y-%m-%d"),
        "final_rating": fields.get("final_rating", "HOLD"),
        "version": "TradingAgents v2.0",
        "model_info": "nvidia/nemotron-3-ultra",
        "analysts": ", ".join([o.role_id for o in analyst_outputs]),
        "research_rounds": "3",
        "risk_rounds": "2",
        "vendors": "yfinance, FRED, StockTwits, Reddit",
        "memory_note": getattr(final_output, 'memory_note', None),
        
        # 核心结论章节
        "executive_narrative": fields.get("final_report", final_output.narrative),
        "cited_evidence": fields.get("evidence_chain_analysis", {}).get("key_chains", []),
        "risk_reward_matrix": fields.get("risk_reward_matrix", []),
        "action_plan": fields.get("action_plan", []),
        
        # 分析师视角
        "analyst_views": [
            {
                "role": o.role_id.replace("_", " ").title(),
                "role_id": o.role_id,
                "narrative": o.narrative,
                "fields": o.fields,
                "cited_evidence": o.cited_evidence,
                "render_hint": _get_render_hint(o.role_id, o.fields)
            }
            for o in analyst_outputs if o.role_id != final_output.role_id
        ],
        
        # 专门章节
        "research_section": next((o for o in analyst_outputs if o.role_id == "research_manager"), None),
        "trading_section": next((o for o in analyst_outputs if o.role_id == "trader"), None),
        "risk_section": next((o for o in analyst_outputs if o.role_id == "risk_manager"), None),
        
        # 证据链
        "evidence_chains": [
            {
                "evidence_id": ev.evidence_id,
                "evidence_type": ev.evidence_type,
                "provider": ev.provider,
                "summary": ev.summary,
                "lineage": ev.lineage,
                "processing_chain": ev.metadata.processing_chain if ev.metadata else [],
                "quality_scores": ev.metadata.quality_scores if ev.metadata else {},
                "processing_level": str(ev.metadata.processing_level) if ev.metadata else "raw",
            }
            for ev in cited_evidence_items
        ],
    }
    
    md_content = template.render(**template_data)
    
    report_path = run_dir / f"report.{lang}.md"
    report_path.write_text(md_content, encoding="utf-8")
    return report_path


def _get_render_hint(role_id: str, fields: dict) -> str | None:
    """根据角色类型返回渲染提示"""
    if role_id == "market_analyst" and "technical_indicators" in fields:
        return "technical_indicators"
    elif role_id == "fundamentals_analyst" and "financial_ratios" in fields:
        return "financial_ratios"
    elif "core_signals" in fields:
        return "core_signals"
    return None