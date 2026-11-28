"""ReportGenerator - 纯渲染引擎

职责：
- Jinja2 模板渲染
- 表格渲染（通过 TableRenderer）
- 多格式输出 (md, html, pdf, json)
- 无业务逻辑，无数据编译
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from abc import ABC, abstractmethod

from jinja2 import Environment, FileSystemLoader

from tradingagents.utils import get_i18n, set_i18n
from .table_renderer import TableRenderer


@dataclass
class ReportBundle:
    """多格式报告输出包"""
    markdown: str = ""
    html: str = ""
    pdf: bytes = b""
    json: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class TemplateEngine(ABC):
    """模板引擎抽象基类 - 为 Phase 2+ 外部框架预留"""
    
    @abstractmethod
    def render(self, template: str, context: dict) -> str:
        pass
    
    @abstractmethod
    def render_pdf(self, template: str, context: dict) -> bytes:
        pass


class Jinja2Engine(TemplateEngine):
    """Jinja2 引擎 - 当前主力"""
    
    def __init__(self, template_dirs: list[str] = None):
        self.dirs = template_dirs or ["templates", "plugins/*/templates"]
        self.env = Environment(
            loader=FileSystemLoader(self.dirs),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._register_filters()
        self._register_globals()
    
    def _register_filters(self):
        """注册自定义过滤器"""
        import json
        import markdown
        self.env.filters["tojson_unicode"] = lambda obj: json.dumps(obj, ensure_ascii=False)
        self.env.filters["tojson_pretty"] = lambda obj, indent=2: json.dumps(obj, ensure_ascii=False, indent=indent)
        # Markdown 转 HTML 过滤器
        self.env.filters["markdown_to_html"] = lambda text: markdown.markdown(text, extensions=['tables', 'fenced_code']) if text else ""
    
    def _register_globals(self):
        """注册全局函数（模板宏）"""
        tables = TableRenderer(get_i18n())
        self.env.globals.update({
            "render_kv_table": tables.render_kv_table,
            "render_list_table": tables.render_list_table,
            "render_technical_indicators": tables.render_technical_indicators,
            "render_key_levels": tables.render_key_levels,
            "render_signals": tables.render_signals,
            "render_financial_ratios": tables.render_financial_ratios,
            "render_growth_metrics": tables.render_growth_metrics,
            "render_valuation": tables.render_valuation,
            "render_profitability": tables.render_profitability,
            "render_balance_sheet": tables.render_balance_sheet,
            "render_cash_flow": tables.render_cash_flow,
            "render_insider": tables.render_insider,
            "render_sentiment": tables.render_sentiment,
            "render_platform_breakdown": tables.render_platform_breakdown,
            "render_news": tables.render_news,
            "render_risk_reward": tables.render_risk_reward,
            "render_action_plan": tables.render_action_plan,
            "render_bull_bear": tables.render_bull_bear,
            "render_macro": tables.render_macro,
            "render_industry": tables.render_industry,
            "render_company": tables.render_company,
            "render_strategies": tables.render_strategies,
            "render_key_points": tables.render_key_points,
            "render_financials": tables.render_financials,
            "render_risk_factors": tables.render_risk_factors,
            "render_catalysts": tables.render_catalysts,
            "render_evidence_appendix": tables.render_evidence_appendix,
            "render_evidence_chain": tables.render_evidence_chain,
            "render_data_suggestions": tables.render_data_suggestions,
        })
    
    def render(self, template: str, context: dict) -> str:
        return self.env.get_template(template).render(**context)
    
    def render_pdf(self, template: str, context: dict) -> bytes:
        html = self.render(template, context)
        try:
            import weasyprint
            return weasyprint.HTML(string=html).write_pdf()
        except ImportError:
            raise RuntimeError("WeasyPrint not installed. Run: pip install weasyprint")


class ReportGenerator:
    """纯渲染引擎 - 无业务逻辑，无数据编译
    
    输入: 完整的模板上下文字典
    输出: ReportBundle
    """
    
    def __init__(
        self,
        template_engine: TemplateEngine = None,
        table_renderer: TableRenderer = None,
        i18n = None,
    ):
        self.engine = template_engine or Jinja2Engine()
        self.tables = table_renderer or TableRenderer(i18n or get_i18n())
        self.i18n = i18n or get_i18n()
    
    def generate_from_context(
        self,
        context: dict,
        template_path: str,
        output_formats: list[str] = None,
        lang: str = "zh-CN",
    ) -> ReportBundle:
        """从预构建的上下文直接渲染指定模板
        
        Args:
            context: 完整的模板上下文字典
            template_path: 相对于搜索目录的模板路径 (如 "report/us/professional/report.md.j2")
            output_formats: 输出格式列表
            lang: 语言
        """
        output_formats = output_formats or ["md", "html"]
        
        if lang:
            set_i18n(lang)
            self.i18n = get_i18n()
            self.tables.i18n = self.i18n
        
        bundle = ReportBundle()
        bundle.metadata = {
            "ticker": context.get("ticker", ""),
            "lang": lang,
            "generated_at": context.get("run_time", ""),
            "formats": output_formats,
        }
        
        for fmt in output_formats:
            if fmt == "md":
                bundle.markdown = self.engine.render(template_path, context)
            elif fmt == "html":
                bundle.html = self.engine.render(template_path, context)
            elif fmt == "pdf":
                bundle.pdf = self.engine.render_pdf(template_path, context)
            elif fmt == "json":
                bundle.json = json.loads(self.engine.render(template_path, context))
        
        return bundle