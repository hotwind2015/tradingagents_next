from __future__ import annotations

import json  # <--- 新增
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from tradingagents.models.evidence import EvidenceManifest
from tradingagents.roles.base import RoleOutput
from tradingagents.utils import get_i18n


def render_report(
    final_output: RoleOutput,
    analyst_outputs: list[RoleOutput],
    manifest: EvidenceManifest,
    run_dir: Path,
    ticker: str,
    lang: str = "zh-CN"
) -> Path:
    env = Environment(loader=FileSystemLoader("templates"))
    
    # === 新增：自定义过滤器，保证中文正常显示并缩进 ===
    def tojson_unicode(obj):
        return json.dumps(obj, ensure_ascii=False, indent=2)
        
    env.filters['tojson_unicode'] = tojson_unicode
    # ==================================================
    
    template = env.get_template("report.j2")
    
    cited_ids = set(final_output.cited_evidence)
    cited_evidence_items = [item for item in manifest.items if item.evidence_id in cited_ids]
    
    i18n = get_i18n()
    
    md_content = template.render(
        i18n=i18n.data,
        ticker=ticker,
        run_id=manifest.run_id,
        run_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        final_report=final_output.model_dump(),
        analyst_outputs=[o.model_dump() for o in analyst_outputs if o.role_id != final_output.role_id],
        evidence_items=[item.model_dump() for item in cited_evidence_items]
    )
    
    report_path = run_dir / f"report.{lang}.md"
    report_path.write_text(md_content, encoding="utf-8")
    return report_path