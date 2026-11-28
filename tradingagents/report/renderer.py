from __future__ import annotations

"""Report Renderer - 兼容层，调用专业报告生成器"""

from pathlib import Path
from tradingagents.evidence.view import EvidenceView
from tradingagents.models.evidence import EvidenceManifest
from tradingagents.roles.base import RoleOutput
from .generator import ReportGenerator
from .extractor import EvidenceChainExtractor


def render_report(
    final_output: RoleOutput,
    analyst_outputs: list[RoleOutput],
    manifest: EvidenceManifest,
    run_dir: Path,
    ticker: str,
    lang: str = "zh-CN",
    settings: dict | None = None,
) -> Path:
    """兼容旧接口：使用新的 ReportGenerator 生成报告"""
    
    # 构建模拟的 AnalystContext
    class MockContext:
        def __init__(self):
            self.ticker = ticker
            self.evidence = EvidenceView(manifest.items, run_dir / "raw")
            self.prior_outputs = {o.role_id: o for o in analyst_outputs}
            self.run_dir = run_dir
            self.run_id = run_dir.name
            self.lang = lang
    
    ctx = MockContext()
    
    # 使用默认配置生成报告
    rg = ReportGenerator()
    bundle = rg.generate_from_context(
        context={
            "ticker": ticker,
            "run_time": __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "i18n": get_i18n(),
            "sections": [],  # 旧接口不使用 sections
            "pm_decision": final_output,
            "analyst_outputs": ctx.prior_outputs,
            "evidence_data": {},  # 旧接口直接用 manifest
            "config": {},
            "custom_config": {},
        },
        template_path="report.md.j2",  # 兜底模板
        output_formats=["md", "html"],
        lang=lang
    )
    
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = None
    if bundle.markdown:
        md_path = run_dir / f"complete_report.{lang}.md"
        md_path.write_text(bundle.markdown, encoding="utf-8")
        report_path = md_path
    if bundle.html:
        html_path = run_dir / f"complete_report.{lang}.html"
        html_path.write_text(bundle.html, encoding="utf-8")
    if bundle.pdf:
        pdf_path = run_dir / f"complete_report.{lang}.pdf"
        pdf_path.write_bytes(bundle.pdf)
    
    return report_path


# 需要导入 get_i18n
from tradingagents.utils import get_i18n

__all__ = ["render_report"]