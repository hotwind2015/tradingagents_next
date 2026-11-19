from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml
from omegaconf import OmegaConf

from tradingagents.config.loader import flatten, load_effective_config
from tradingagents.config.settings import explicit_env_overrides, get_env_settings
from tradingagents.config.snapshot import write_snapshot
from tradingagents.evidence.store import EvidenceStore
from tradingagents.evidence.view import EvidenceView
from tradingagents.llm import OpenAICompatibleClient
from tradingagents.logging import setup_logging
from tradingagents.models.config import EffectiveConfig, ProvenanceField
from tradingagents.models.evidence import Citation, EvidenceManifest
from tradingagents.models.graph import EdgeIR, GraphIR, NodeIR
from tradingagents.models.recipe import Recipe
from tradingagents.prompt.persistence import PromptPersister
from tradingagents.prompt.renderer import PromptRenderer
from tradingagents.report.renderer import render_report
from tradingagents.run.context import RunContext

# 引入重构后的组件
from tradingagents.run.data_router import DataFetchError, DataRouter
from tradingagents.run.plugin_manager import PluginManager
from tradingagents.run.state_manager import StateManager
from tradingagents.utils import get_i18n, set_i18n

logger = logging.getLogger("tradingagents.orchestrator")


class DynamicGraphExecutor:
    """基于 consumes/produces 依赖的自动执行器"""
    def __init__(self, ir: GraphIR, initial_state: dict):
        self.ir = ir
        self.state = initial_state
        self.node_fns = {}

    def add_node(self, node_id: str, fn: Callable):
        self.node_fns[node_id] = fn

    def execute(self):
        executed = set()
        while len(executed) < len(self.ir.nodes):
            progressed = False
            for node in self.ir.nodes:
                if node.id in executed:
                    continue
                
                incoming = [e.src for e in self.ir.edges if e.dst == node.id]
                if all(src in executed for src in incoming):
                    if node.id not in self.node_fns:
                        raise ValueError(f"No function for node {node.id}")
                    self.state = self.node_fns[node.id](self.state)
                    executed.add(node.id)
                    progressed = True
            
            if not progressed:
                missing = [n.id for n in self.ir.nodes if n.id not in executed]
                raise RuntimeError(f"Graph stalled. Unresolved dependencies for nodes: {missing}")

        return self.state


class Orchestrator:
    def __init__(
        self,
        recipe: Recipe,
        ticker: str,
        cli_overrides: dict,
        config_path: Path | None = None,
        template_dir: Path = Path("templates"),
        resume_run_id: str | None = None,
        cli_plugin_dirs: list[str] | None = None,
    ):
        self.recipe = recipe
        self.ticker = ticker
        self.cli_overrides = cli_overrides
        self.config_path = config_path
        self.template_dir = template_dir
        self.cli_plugin_dirs = cli_plugin_dirs or []

        env = get_env_settings()
        if resume_run_id:
            self.run_id = resume_run_id
        else:
            self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + str(uuid.uuid4())[:6]
        self.run_dir = env.runs_dir / self.run_id

    def run(self) -> Path:
        # === 新增：OmegaConf 深度合并 ===
        def _read_yaml(path):
            if path and Path(path).exists():
                return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
            return {}

        def unflatten(dictionary):
            result = dict()
            for key, value in dictionary.items():
                parts = key.split(".")
                d = result
                for part in parts[:-1]:
                    if part not in d:
                        d[part] = dict()
                    d = d[part]
                d[parts[-1]] = value
            return result

        recipe_dict = self.recipe.model_dump()
        default_dict = _read_yaml(get_env_settings().default_config)
        user_dict = _read_yaml(self.config_path)
        cli_dict = unflatten(self.cli_overrides)

        # 合并优先级：default < recipe < user < cli
        merged_dict = OmegaConf.to_container(
            OmegaConf.merge(default_dict, recipe_dict, user_dict, cli_dict),
            resolve=True
        )
        self.recipe = Recipe.model_validate(merged_dict)

        # 生成带来源追踪的 EffectiveConfig
        merged_fields = {}
        for source_name, d in [("default", default_dict), ("recipe", recipe_dict), ("user_config", user_dict), ("cli", cli_dict)]:
            flat_d = flatten(d)
            for k, v in flat_d.items():
                merged_fields[k] = ProvenanceField(value=v, source=source_name)
        
        effective_cfg = EffectiveConfig(
            fields=merged_fields,
            recipe_id=self.recipe.id,
            recipe_version=self.recipe.version,
            evidence_schema=self.recipe.evidence_schema
        )
        # ================================
        
        final_lang = effective_cfg.get("output.lang") or get_env_settings().lang
        set_i18n(final_lang)
        i18n = get_i18n()
        
        logger = setup_logging(self.run_dir, get_env_settings().log_level)
        logger.info(i18n.t("run_start", run_id=self.run_id, ticker=self.ticker))
        write_snapshot(effective_cfg, self.run_dir / "effective_config.yaml",recipe_data=self.recipe.model_dump())

        ctx = RunContext(run_id=self.run_id, run_dir=self.run_dir, recipe=self.recipe, lang=final_lang)
        # llm = OpenAICompatibleClient()
        renderer = PromptRenderer(self.template_dir)
        persister = PromptPersister(self.run_dir, strategy=self.recipe.prompt_persistence)
        store = EvidenceStore(self.run_dir, self.run_id, self.recipe.id, self.recipe.version)
        state_mgr = StateManager(self.run_dir)

        lang_name_map = {"zh-CN": "Simplified Chinese (简体中文)", "en-US": "English"}
        output_language = lang_name_map.get(final_lang, "English")

        # === 插件目录解析与统一加载 ===
        if self.cli_plugin_dirs:
            final_plugin_dirs = self.cli_plugin_dirs
        elif self.recipe.plugin_dirs:
            final_plugin_dirs = self.recipe.plugin_dirs
        else:
            final_plugin_dirs = []  # <--- 默认空列表，白名单模式

        # 2. 收集模板搜索路径
        template_search_paths = [self.template_dir] # 首先是主框架的 templates/
        
        # 假设用户把模板放在了 plugin_dir/templates/ 下
        for p_dir in final_plugin_dirs:
            custom_tpl_dir = Path(p_dir) / "templates"
            if custom_tpl_dir.exists():
                logger.info(f"Added custom template path: {custom_tpl_dir}")
                template_search_paths.append(custom_tpl_dir)

        # 3. 实例化渲染器
        renderer = PromptRenderer(template_search_paths)
            
        logger.info(f"Resolved plugin dirs: {final_plugin_dirs}")
        
        plugin_manager = PluginManager()
        if final_plugin_dirs:
            logger.info(f"Resolved plugin dirs: {final_plugin_dirs}")
            plugin_manager.discover_all([Path(d) for d in final_plugin_dirs])
        else:
            logger.info("No custom plugin dirs specified. Running in pure mode.")
            plugin_manager.discover_all([]) # 内部只加载官方内置

        llm_provider_id = self.recipe.models.provider
        try:
            # 改用 plugin_manager.get
            llm_cls = plugin_manager.get("llm", llm_provider_id)
            llm = llm_cls()
            logger.info(f"Initialized LLM provider: {llm_provider_id}")
        except KeyError:
            logger.error(f"LLM provider '{llm_provider_id}' not found. Please check your recipe or plugins.")
            raise
        # =====================
        # === 解析 Team 实际配置 ===
        actual_analysts = []
        for role_id in self.recipe.team.analysts:
            if role_id not in self.recipe.roles:
                raise ValueError(f"Role ID '{role_id}' not found in roles pool.")
            actual_analysts.append(self.recipe.roles[role_id])
            
        pm_id = self.recipe.team.project_manager
        if pm_id not in self.recipe.roles:
            raise ValueError(f"PM Role ID '{pm_id}' not found in roles pool.")
        actual_pm = self.recipe.roles[pm_id]
        
        # 校验合并后的配置
        from tradingagents.recipe.validator import validate_recipe
        val_res = validate_recipe(self.recipe)
        if not val_res.ok:
            logger.error(f"Recipe validation failed after merge: {val_res.errors}")
            raise ValueError("Recipe validation failed.")        
        # 3. 数据层：判断是否断点续跑，还是新拉取数据
        if not store.manifest_path.exists():
            logger.info(i18n.t("fetch_evidence"))
            router = DataRouter(plugin_manager, store)
            
            required_evidence = set()
            for role in actual_analysts:
                required_evidence.update(role.consumes)
                
            for ev_type in required_evidence:
                chain = self.recipe.data.provider_chain.get(ev_type, ["yfinance"])
                try:
                    router.fetch_and_store(self.ticker, ev_type, chain)
                except DataFetchError as e:
                    logger.error(f"Data fetch aborted: {e}")
                    logger.error("分析中止。请检查网络后使用 --resume 重新尝试。")
                    raise
        else:
            logger.info("Found existing evidence_manifest, loading from disk...")
            store.manifest = EvidenceManifest.model_validate_json(store.manifest_path.read_text(encoding="utf-8"))

        evidence_view = EvidenceView(store.manifest.items)

        # 4. 编排层：构建 DAG 依赖图
        nodes, edges = [], []
        produced_map: dict[str, list[str]] = {}  
        
        all_roles = actual_analysts + [actual_pm]
        for role in all_roles:
            nodes.append(NodeIR(id=role.plugin, kind="project_manager" if role.plugin == self.recipe.team.project_manager else "analyst"))
            for out in role.produces:
                produced_map.setdefault(out, []).append(role.plugin)

        for consumer in all_roles:
            for req in consumer.consumes:
                if req in produced_map:
                    for producer_id in produced_map[req]:
                        edges.append(EdgeIR(src=producer_id, dst=consumer.plugin))

        unique_edges = []
        for e in edges:
            if e.src != e.dst and e not in unique_edges:
                unique_edges.append(e)

        ir = GraphIR(nodes=nodes, edges=unique_edges, entry="start", terminals=[actual_pm.plugin])

        # 5. 执行层：绑定执行函数
        state = {"role_outputs": [], "final_report": None}
        executor = DynamicGraphExecutor(ir, state)

        def make_analyst_fn(role_spec):
            def inner(s):
                # 注意这里的 StateManager 缓存 key，用 plugin 名
                cached_output = state_mgr.load_output(role_spec.plugin)
                if cached_output:
                    logger.info(f"Skipping {role_spec.plugin}: Loaded from cache.")
                    s["role_outputs"].append(cached_output)
                    return s
                
                role_cls = plugin_manager.get("role", role_spec.plugin)
                role = role_cls()
                logger.info(i18n.t("run_analyst", role_id=role.role_id))
                
                prompt_ctx = role.prepare_context(evidence_view, ctx)
                prompt_ctx["output_language"] = output_language
                prompt_ctx["ticker"] = self.ticker
                
                try:
                    renderer.validate_variables(role.template, set(prompt_ctx.keys()))
                except Exception as e:
                    logger.error(f"Template validation failed for {role.role_id}: {e}")
                    raise
                
                prompt_text = renderer.render(role.template, prompt_ctx)
                persister.save(role.role_id, 1, prompt_text, {"template": role.template})
                
                model_cfg = self.recipe.models.quick if role_spec.model_tier == "quick" else self.recipe.models.deep
                raw_res = llm.invoke(prompt_text, model_cfg)
                out = role.parse_output(raw_res)
                
                state_mgr.save_output(role_spec.plugin, out)
                s["role_outputs"].append(out)
                return s
            return inner

        def run_pm_fn(s):
            pm_spec = self.recipe.team.project_manager
            
            cached_output = state_mgr.load_output(pm_spec.plugin)
            if cached_output:
                logger.info(f"Skipping {pm_spec.plugin}: Loaded from cache.")
                s["final_report"] = cached_output
                return s
                
            role_cls = plugin_manager.get("role",pm_spec.plugin)
            role = role_cls()
            logger.info(i18n.t("run_pm"))
            
            prompt_ctx = role.prepare_context(s["role_outputs"], evidence_view, ctx)
            prompt_ctx["output_language"] = output_language
            prompt_ctx["ticker"] = self.ticker
            
            try:
                renderer.validate_variables(role.template, set(prompt_ctx.keys()))
            except Exception as e:
                logger.error(f"Template validation failed for PM: {e}")
                raise
                
            prompt_text = renderer.render(role.template, prompt_ctx)
            persister.save(role.role_id, 1, prompt_text, {"template": role.template})
            
            raw_res = llm.invoke(prompt_text, self.recipe.models.deep)
            out = role.parse_output(raw_res)
            
            state_mgr.save_output(pm_spec.plugin, out)
            s["final_report"] = out
            return s

        for role in actual_analysts:
            executor.add_node(role.plugin, make_analyst_fn(role))
        executor.add_node(actual_pm.plugin, run_pm_fn)

        # 6. 执行图
        final_state = executor.execute()

        # 7. 收尾层：幻觉清理与报告生成
        report = final_state["final_report"]
        if report and report.cited_evidence:
            valid_ids = {item.evidence_id for item in store.manifest.items}
            valid_citations = [cid for cid in report.cited_evidence if cid in valid_ids]
            
            if len(valid_citations) < len(report.cited_evidence):
                fake_ids = set(report.cited_evidence) - set(valid_citations)
                logger.warning(i18n.t("hallucinated_citations", fake_ids=str(fake_ids)))
                report.cited_evidence = valid_citations
                
            for ev_id in valid_citations:
                store.manifest.citations.append(Citation(evidence_id=ev_id, section="conclusion"))
            store._flush_manifest()
            
        report_path = render_report(
            final_output=report,
            analyst_outputs=final_state["role_outputs"],
            manifest=store.manifest,
            run_dir=self.run_dir,
            ticker=self.ticker,
            lang=final_lang
        )
        
        store.verify_integrity()
        logger.info(i18n.t("run_complete", path=str(report_path)))
        
        return report_path