"""Reporter - 报告生成器抽象层

BaseReporter: 通用模板编排器，读取 reporter.yaml 按序拼装章节
ReporterFactory: 从模板目录加载配置，实例化 Reporter
"""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any
from dataclasses import dataclass

from tradingagents.report.generator import ReportGenerator, ReportBundle
from tradingagents.utils import get_i18n, set_i18n
from tradingagents.report.extractor import EvidenceChainExtractor
from tradingagents.roles.base import RoleOutput
# 避免循环导入：ReporterFactory 在文件末尾定义，project_manager.py 导入时会触发循环
# 解决方案：在 project_manager.py 中使用 TYPE_CHECKING 或延迟导入


@dataclass
class ReportContext:
    """报告渲染上下文"""
    ticker: str
    run_time: str
    i18n: Any
    sections: list[dict]           # 章节定义列表
    pm_decision: RoleOutput        # PM 决策输出
    analyst_outputs: dict          # 分析师输出 {role_id: RoleOutput}
    evidence_data: dict            # 证据数据
    config: dict                   # Reporter 完整配置


class BaseReporter:
    """通用报告生成器 - 读取 reporter.yaml 按序拼装章节"""
    
    def __init__(self, generator: ReportGenerator, config: dict):
        self.generator = generator
        self.config = config
        self.template_dir = config.get("template_dir", "report/shared/professional")
        self.main_template = config.get("main_template", "report.md.j2")
        self.sections = config.get("sections", [])
        self.output_formats = config.get("output_formats", ["md", "html"])
        self.custom_config = config.get("custom_config", {})
    
    def generate_report(
        self,
        ctx,
        pm_decision: RoleOutput,
        output_formats: list[str] = None,
        lang: str = None
    ) -> ReportBundle:
        """生成多格式报告"""
        # 1. 解析参数（优先级：方法参数 > config > 默认值）
        output_formats = output_formats or self.output_formats
        lang = lang or self.config.get("lang", getattr(ctx, 'lang', 'zh-CN'))
        
        # 2. 设置语言
        if lang:
            set_i18n(lang)
        
        # 3. 构建上下文
        context = self._build_context(ctx, pm_decision, lang)
        
        # 4. 渲染主模板（主模板内部 include 各 section）
        main_template_path = f"{self.template_dir}/{self.main_template}"
        bundle = self.generator.generate_from_context(
            context=context,
            template_path=main_template_path,
            output_formats=output_formats,
            lang=lang
        )
        
        # 5. 文件落盘（原子写入，返回生成文件列表）
        generated_files = self._save(bundle, ctx, lang)
        
        # 将生成的文件信息加入 bundle metadata
        bundle.metadata["generated_files"] = [str(f) for f in generated_files]
        bundle.metadata["output_formats"] = output_formats
        
        return bundle
    
    def _build_context(self, ctx, pm_decision: RoleOutput, lang: str) -> dict:
        """构建模板渲染上下文"""
        # 提取证据数据
        evidence_data = self._extract_evidence(ctx)
        
        # 从 PM 决策中提取编译好的章节数据
        pm_fields = pm_decision.fields if hasattr(pm_decision, 'fields') else {}
        compiled_sections = pm_fields.get("compiled_sections", {})
        
        # 如果 PM 没有预编译章节，从 analyst_outputs 和 evidence_data 现场编译
        if not compiled_sections:
            compiled_sections = self._compile_sections(evidence_data, ctx.prior_outputs)
        
        # 构建 header 信息
        header_info = self._build_header(ctx, pm_decision)
        
        return {
            "ticker": ctx.ticker,
            "run_time": getattr(ctx, 'run_time', None) or 
                       __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "i18n": get_i18n(),
            "sections": self.sections,
            "pm_decision": pm_decision,
            "analyst_outputs": ctx.prior_outputs,
            "evidence_data": evidence_data,
            "compiled_sections": compiled_sections,
            "config": self.config,
            "custom_config": self.custom_config,
            **header_info,  # 展开 header 字段
        }
    
    def _extract_evidence(self, ctx) -> dict:
        """从证据链提取结构化数据"""
        extractor = EvidenceChainExtractor(ctx.evidence)
        all_cited_ids = set()
        for output in ctx.prior_outputs.values():
            if hasattr(output, 'cited_evidence'):
                all_cited_ids.update(output.cited_evidence)
        
        return {
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
    
    def _compile_sections(self, evidence_data: dict, analyst_outputs: dict) -> dict:
        """从 analyst_outputs 和 evidence_data 编译章节数据（兜底方案）"""
        # 这里可以复用 PM 的编译逻辑，简化版
        return {
            "executive_summary": {
                "rating": "HOLD",
                "narrative": "综合分析报告",
                "risk_reward_matrix": [],
                "action_plan": [],
            },
            "analyst_views": [],
            "technical_analysis": {},
            "fundamental_analysis": {},
            "sentiment_analysis": {},
            "news_macro": {},
            "risk_reward": {},
            "action_plan": [],
        }
    
    def _build_header(self, ctx, pm_decision: RoleOutput) -> dict:
        """构建报告头部信息"""
        i18n = get_i18n()
        analyst_names = []
        for role_id, output in ctx.prior_outputs.items():
            if role_id != "project_manager":
                analyst_names.append(output.role_id)
        
        return {
            "title": i18n.t("report.title", default="AI Investment Analysis Report"),
            "version": "TradingAgents v1.0",
            "model_info": "NVIDIA Nemotron 3 Ultra",
            "analysts": ", ".join(analyst_names),
            "research_rounds": 3,
            "risk_rounds": 3,
        }
    
    def _save(self, bundle: ReportBundle, ctx, lang: str) -> list[Path]:
        """文件落盘 - 原子写入，返回生成的文件路径列表供审计/清理
        
        Returns:
            list[Path]: 成功生成的文件路径列表
        """
        from pathlib import Path
        import tempfile
        import os
        
        run_dir = getattr(ctx, 'run_dir', None)
        if not run_dir:
            run_dir = Path.cwd() / "runs" / getattr(ctx, 'run_id', 'unknown')
        
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成文件名后缀：基于 template_dir 或自定义 output_suffix
        template_dir = self.config.get("template_dir", "report/shared/professional")
        # 从 template_dir 提取标识符，如 "report/us/professional" -> "us-professional"
        suffix = template_dir.replace("report/", "").replace("/", "-")
        custom_suffix = self.config.get("output_suffix")
        if custom_suffix:
            suffix = custom_suffix
        
        base_name = f"complete_report.{lang}"
        if suffix:
            base_name = f"complete_report.{suffix}.{lang}"
        
        generated_files = []
        
        def _atomic_write(target_path: Path, content: str | bytes, is_binary: bool = False):
            """原子写入：先写临时文件，再重命名"""
            mode = 'wb' if is_binary else 'w'
            encoding = None if is_binary else 'utf-8'
            
            # 在同一目录下创建临时文件，保证同文件系统
            with tempfile.NamedTemporaryFile(
                mode=mode, 
                encoding=encoding,
                dir=run_dir, 
                delete=False,
                prefix=f".tmp_{target_path.stem}_",
                suffix=target_path.suffix
            ) as tmp:
                tmp.write(content)
                tmp_path = Path(tmp.name)
            
            # 原子重命名（同文件系统下保证原子性）
            try:
                tmp_path.replace(target_path)
            except Exception:
                # 失败时清理临时文件
                tmp_path.unlink(missing_ok=True)
                raise
        
        try:
            if bundle.markdown:
                md_path = run_dir / f"{base_name}.md"
                _atomic_write(md_path, bundle.markdown)
                generated_files.append(md_path)
            
            if bundle.html:
                html_path = run_dir / f"{base_name}.html"
                _atomic_write(html_path, bundle.html)
                generated_files.append(html_path)
            
            if bundle.pdf:
                pdf_path = run_dir / f"{base_name}.pdf"
                _atomic_write(pdf_path, bundle.pdf, is_binary=True)
                generated_files.append(pdf_path)
                
        except Exception as e:
            # 失败时清理已生成的文件
            for f in generated_files:
                f.unlink(missing_ok=True)
            raise
        
        return generated_files


class ReporterFactory:
    """Reporter 工厂 - 从模板目录加载配置"""
    
    # 预设名称 -> 模板目录映射
    PRESET_DIRS = {
        "us-professional": "report/us/professional",
        "cn-professional": "report/cn/professional",
        "shared-professional": "report/shared/professional",
    }
    
    # 默认配置
    DEFAULT_CONFIG = {
        "template_dir": "report/shared/professional",
        "main_template": "report.md.j2",
        "output_formats": ["md", "html"],
        "sections": [],
        "custom_config": {},
    }
    
    @classmethod
    def create(cls, spec: dict | str, generator: ReportGenerator) -> BaseReporter:
        """
        创建 Reporter 实例
        
        spec 支持：
        - 字符串预设名: "us-professional"
        - 字典: {"preset": "us-professional", "overrides": {...}}
        - 字典: {"template_dir": "report/custom/my_style", "overrides": {...}}
        - 字典: {"class": "pkg.module.CustomReporter", "config": {...}}
        """
        if isinstance(spec, str):
            spec = {"preset": spec}
        
        # 1. 预设模式
        if "preset" in spec:
            preset_name = spec["preset"]
            if preset_name not in cls.PRESET_DIRS:
                raise ValueError(f"Unknown reporter preset: {preset_name}. Available: {list(cls.PRESET_DIRS.keys())}")
            template_dir = cls.PRESET_DIRS[preset_name]
            config = cls._load_reporter_config(template_dir)
            config = cls._deep_merge(config, spec.get("overrides", {}))
            return BaseReporter(generator, config)
        
        # 2. 显式模板目录
        if "template_dir" in spec:
            template_dir = spec["template_dir"]
            config = cls._load_reporter_config(template_dir)
            config = cls._deep_merge(config, spec.get("overrides", {}))
            return BaseReporter(generator, config)
        
        # 3. 自定义类（高级用法）
        if "class" in spec:
            cls_path = spec["class"]
            module_path, class_name = cls_path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            reporter_cls = getattr(module, class_name)
            return reporter_cls(generator, spec.get("config", {}))
        
        raise ValueError(f"Invalid reporter spec: {spec}. Must contain 'preset', 'template_dir', or 'class'")
    
    @classmethod
    def _load_reporter_config(cls, template_dir: str) -> dict:
        """读取模板目录下的 reporter.yaml，合并默认值
        
        在模板搜索路径中查找 reporter.yaml
        """
        import glob
        search_dirs = ["templates", "plugins/*/templates"]
        config_path = None
        
        for d in search_dirs:
            for path in glob.glob(str(Path(d) / template_dir / "reporter.yaml")):
                config_path = Path(path)
                if config_path.exists():
                    with open(config_path, encoding="utf-8") as f:
                        return cls._deep_merge(cls.DEFAULT_CONFIG, yaml.safe_load(f) or {})
        
        # 未找到，返回默认配置
        return cls.DEFAULT_CONFIG.copy()
    
    @classmethod
    def _deep_merge(cls, base: dict, override: dict) -> dict:
        """深度合并字典"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = cls._deep_merge(result[key], value)
            else:
                result[key] = value
        return result