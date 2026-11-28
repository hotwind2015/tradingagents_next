from __future__ import annotations

import inspect
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
from tradingagents.run.analyst_context import AnalystContext
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
        ticker: str,
        cli_overrides: dict,
        config_path: Path | None = None,
        template_dir: Path = Path("templates"),
        resume_run_id: str | None = None,
        cli_plugin_dirs: list[str] | None = None,
    ):
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

        default_dict = _read_yaml(get_env_settings().default_config)
        user_dict = _read_yaml(self.config_path)
        cli_dict = unflatten(self.cli_overrides)

        # 合并优先级：default < recipe < user < cli
        merged_dict = OmegaConf.to_container(
            OmegaConf.merge(default_dict, user_dict, cli_dict),
            resolve=True
        )
        self.recipe = Recipe.model_validate(merged_dict)

        # 生成带来源追踪的 EffectiveConfig
        merged_fields = {}
        for source_name, d in [("default", default_dict), ("user_config", user_dict), ("cli", cli_dict)]:
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
        logger.info(i18n.t("run.started", run_id=self.run_id, ticker=self.ticker))
        write_snapshot(effective_cfg, self.run_dir / "effective_config.yaml", recipe_data=self.recipe.model_dump())

        ctx = RunContext(run_id=self.run_id, run_dir=self.run_dir, recipe=self.recipe, lang=final_lang)
        renderer = PromptRenderer(self.template_dir)
        persister = PromptPersister(self.run_dir, strategy=self.recipe.prompt_persistence)
        store = EvidenceStore(self.run_dir, self.run_id, self.recipe.id, self.recipe.version)
        state_mgr = StateManager(self.run_dir)

        lang_name_map = {
            "zh-CN": i18n.t("languages.zh_cn"),
            "en-US": i18n.t("languages.en_us"),
        }
        output_language = lang_name_map.get(final_lang, i18n.t("languages.en_us"))

        # === 插件目录解析与统一加载 ===
        if self.cli_plugin_dirs:
            final_plugin_dirs = self.cli_plugin_dirs
        else:
            final_plugin_dirs = []  # <--- 默认空列表，白名单模式

        # 2. 收集模板搜索路径 - 插件模板优先（与 report renderer 保持一致）
        template_search_paths = []
        
        # 先添加插件模板目录（优先级高）
        for p_dir in final_plugin_dirs:
            custom_tpl_dir = Path(p_dir) / "templates"
            if custom_tpl_dir.exists():
                logger.info(
                    i18n.t("run.plugin_template_added", template_dir=custom_tpl_dir)
                )
                template_search_paths.append(custom_tpl_dir)
        
        # 最后添加主框架模板目录（兜底）
        template_search_paths.append(self.template_dir)

        # 3. 实例化渲染器
        renderer = PromptRenderer(template_search_paths)
            
        logger.info(
            i18n.t("run.plugin_dirs_resolved", plugin_dirs=final_plugin_dirs)
        )
        
        plugin_manager = PluginManager()
        if final_plugin_dirs:
            plugin_manager.discover_all([Path(d) for d in final_plugin_dirs])
        else:
            logger.info(i18n.t("run.no_custom_plugins"))
            plugin_manager.discover_all([]) # 内部只加载官方内置

        llm_provider_id = self.recipe.models.provider
        try:
            # 改用 plugin_manager.get
            llm_cls = plugin_manager.get("llm", llm_provider_id)
            # 透传 provider_args 给 LLM 客户端
            llm_provider_args = self.recipe.models.provider_args.get(llm_provider_id, {})
            llm = llm_cls(**llm_provider_args) if llm_provider_args else llm_cls()
            logger.info(
                i18n.t("run.llm_initialized", provider_id=llm_provider_id)
            )
        except KeyError:
            logger.error(
                i18n.t("run.llm_provider_not_found", provider_id=llm_provider_id)
            )
            raise
        # =====================
        # === 解析 Team 实际配置 ===
        actual_analysts = []
        for role_id in self.recipe.team.analysts:
            if role_id not in self.recipe.roles:
                raise ValueError(i18n.t("run.analyst_role_not_found", role_id=role_id))
            actual_analysts.append(self.recipe.roles[role_id])
            
        pm_id = self.recipe.team.project_manager
        if pm_id not in self.recipe.roles:
            raise ValueError(i18n.t("run.manager_role_not_found", role_id=pm_id))
        actual_pm = self.recipe.roles[pm_id]
        
        # 校验合并后的配置
        from tradingagents.recipe.validator import validate_recipe
        val_res = validate_recipe(self.recipe)
        if not val_res.ok:
            error_message = i18n.t(
                "run.recipe_validation_failed", errors=val_res.errors
            )
            logger.error(error_message)
            raise ValueError(error_message)
        # 3. 数据层：判断是否断点续跑，还是新拉取数据
        if not store.manifest_path.exists():
            logger.info(i18n.t("run.fetching_evidence"))
            # 透传 provider_args 给 DataRouter
            router = DataRouter(plugin_manager, store, self.recipe.data.provider_args)
            
            # Collect all evidence types produced by roles in the team
            produced_by_roles = set()
            all_roles = actual_analysts + [actual_pm]
            for role in all_roles:
                produced_by_roles.update(role.produces)
            
            # Only fetch evidence types that are NOT produced by any role (i.e., provider evidence types)
            required_evidence = set()
            for role in actual_analysts:
                for t in role.consumes:
                    if t not in produced_by_roles:
                        required_evidence.add(t)
                
            # 读取处理层级配置（默认 RAW）
            processing_level = getattr(self.recipe.data, 'default_processing_level', 'raw')
            type_levels = getattr(self.recipe.data, 'processing_level', {})
            
            for ev_type in required_evidence:
                chain = self.recipe.data.provider_chain.get(ev_type, ["yfinance"])
                level = type_levels.get(ev_type, processing_level)
                try:
                    router.fetch_and_store(self.ticker, ev_type, chain, level)
                except DataFetchError as e:
                    logger.error(i18n.t("run.data_fetch_aborted", error=e))
                    logger.error(i18n.t("run.analysis_aborted"))
                    raise
        else:
            logger.info(i18n.t("run.evidence_manifest_loaded"))
            store.manifest = EvidenceManifest.model_validate_json(store.manifest_path.read_text(encoding="utf-8"))

        # 传递 raw_dir 给 EvidenceView 以支持 get_raw()
        evidence_view = EvidenceView(store.manifest.items, store._raw_dir)

        # 4. 编排层：构建 DAG 依赖图
        nodes, edges = [], []
        produced_map: dict[str, list[str]] = {}  
        
        all_roles = actual_analysts + [actual_pm]
        
        # 如果 project_manager 的 consumes 为空，默认消费所有 analyst 的输出
        pm_role = next((r for r in all_roles if r.role_id == self.recipe.team.project_manager), None)
        if pm_role and not pm_role.consumes:
            # 默认消费所有 analyst 的 produces
            all_analyst_produces = set()
            for analyst in actual_analysts:
                all_analyst_produces.update(analyst.produces)
            pm_role.consumes = list(all_analyst_produces)
            logger.info(f"ProjectManager 默认消费所有分析师输出: {pm_role.consumes}")
        
        for role in all_roles:
            nodes.append(NodeIR(id=role.role_id, kind="project_manager" if role.role_id == self.recipe.team.project_manager else "analyst"))
            for out in role.produces:
                produced_map.setdefault(out, []).append(role.role_id)

        for consumer in all_roles:
            for req in consumer.consumes:
                if req in produced_map:
                    for producer_id in produced_map[req]:
                        edges.append(EdgeIR(src=producer_id, dst=consumer.role_id))

        unique_edges = []
        for e in edges:
            if e.src != e.dst and e not in unique_edges:
                unique_edges.append(e)

        ir = GraphIR(nodes=nodes, edges=unique_edges, entry="start", terminals=[actual_pm.role_id])

        # 5. 执行层：绑定执行函数
        state = {"role_outputs": [], "final_report": None}
        executor = DynamicGraphExecutor(ir, state)

        # 创建基础上下文（共享 prior_outputs 引用）
        base_ctx = AnalystContext(
            run_id=self.run_id,
            run_dir=self.run_dir,
            ticker=self.ticker,
            lang=final_lang,
            recipe=self.recipe,
            evidence=evidence_view,
            shared_state={},  # 可预置：如共享 HTTP 客户端、缓存等
        )
        
        # 角色实例缓存（支持 configure + 复用）
        role_instances: dict[str, object] = {}

        def _call_prepare_context(role_obj, role_ctx: AnalystContext) -> dict:
            """自动适配新/旧 prepare_context 签名"""
            sig = inspect.signature(role_obj.prepare_context)
            params = list(sig.parameters.keys())
            
            if len(params) == 1 and params[0] in ("ctx", "context"):
                # 新签名：单一 AnalystContext
                return role_obj.prepare_context(role_ctx)
            elif len(params) == 2:
                # 旧签名：(evidence, run_ctx) - 向后兼容
                return role_obj.prepare_context(role_ctx.evidence, RunContext(
                    run_id=role_ctx.run_id, run_dir=role_ctx.run_dir,
                    recipe=role_ctx.recipe, lang=role_ctx.lang
                ))
            elif len(params) == 3:
                # PM 旧签名：(outputs, evidence, run_ctx) - 向后兼容
                return role_obj.prepare_context(
                    [o for o in role_ctx.prior_outputs.values()],
                    role_ctx.evidence,
                    RunContext(
                        run_id=role_ctx.run_id, run_dir=role_ctx.run_dir,
                        recipe=role_ctx.recipe, lang=role_ctx.lang
                    )
                )
            else:
                raise TypeError(f"Unsupported prepare_context signature: {sig}")

        def make_analyst_fn(role_spec):
            def inner(s):
                # 缓存检查
                cached_output = state_mgr.load_output(role_spec.role_id)
                if cached_output:
                    logger.info(
                        i18n.t(
                            "run.cached_role_output", role_id=role_spec.role_id
                        )
                    )
                    s["role_outputs"].append(cached_output)
                    # 关键：更新 base_ctx.prior_outputs
                    base_ctx.prior_outputs[role_spec.role_id] = cached_output
                    return s
                
                # 获取/创建角色实例
                if role_spec.role_id not in role_instances:
                    role_cls = plugin_manager.get("role", role_spec.role_id)
                    role = role_cls()
                    # 透传 args 给角色
                    if hasattr(role, "configure"):
                        role.configure(role_spec.args)
                    role_instances[role_spec.role_id] = role
                else:
                    role = role_instances[role_spec.role_id]
                
                logger.info(i18n.t("run.analyst_started", role_id=role.role_id))
                
                # 构建该角色的专属上下文（含上游输出）
                role_ctx = AnalystContext(
                    run_id=base_ctx.run_id,
                    run_dir=base_ctx.run_dir,
                    ticker=base_ctx.ticker,
                    lang=base_ctx.lang,
                    recipe=base_ctx.recipe,
                    evidence=base_ctx.evidence,
                    prior_outputs=dict(base_ctx.prior_outputs),  # 拷贝当前已完成的上游输出
                    shared_state=base_ctx.shared_state,
                    role_args=role_spec.args,
                    model_tier=role_spec.model_tier,
                    model_config=self.recipe.models.quick if role_spec.model_tier == "quick" else self.recipe.models.deep,
                    consumes=role_spec.consumes,
                )
                
                # 统一调用：单一 context 参数
                prompt_ctx = _call_prepare_context(role, role_ctx)
                prompt_ctx["output_language"] = output_language
                prompt_ctx["ticker"] = self.ticker
                
                # 模板验证
                try:
                    renderer.validate_variables(role.template, set(prompt_ctx.keys()))
                except Exception as e:
                    logger.error(
                        i18n.t(
                            "run.template_validation_failed",
                            role_id=role.role_id,
                            error=e,
                        )
                    )
                    raise
                
                # 渲染提示词（用于持久化）
                prompt_text = renderer.render(role.template, prompt_ctx)
                persister.save(role.role_id, 1, prompt_text, {"template": role.template})
                
                # 注入 renderer 和 llm 到 shared_state，由角色内部 analyze() 使用
                role_ctx.shared_state = {
                    **base_ctx.shared_state,
                    "prompt_renderer": renderer,
                    "llm_client": llm,
                }
                
                # 统一调用 analyze()，角色内部完成 render -> llm -> parse
                out = role.analyze(role_ctx)
                
                state_mgr.save_output(role_spec.role_id, out)
                
                # 关键：写入共享上下文，供下游角色使用
                base_ctx.prior_outputs[role_spec.role_id] = out
                s["role_outputs"].append(out)
                return s
            return inner

        def run_pm_fn(s):
            pm_spec = actual_pm
            
            cached_output = state_mgr.load_output(pm_spec.role_id)
            if cached_output:
                logger.info(
                    i18n.t("run.cached_manager_output", role_id=pm_spec.role_id)
                )
                s["final_report"] = cached_output
                return s
                
            role_cls = plugin_manager.get("role", pm_spec.role_id)
            role = role_cls()
            if hasattr(role, "configure"):
                role.configure({})  # PM 通常无 args
            
            logger.info(i18n.t("run.manager_started"))
            
            # PM 拿到全量 prior_outputs
            pm_ctx = AnalystContext(
                run_id=base_ctx.run_id,
                run_dir=base_ctx.run_dir,
                ticker=base_ctx.ticker,
                lang=base_ctx.lang,
                recipe=base_ctx.recipe,
                evidence=base_ctx.evidence,
                prior_outputs=base_ctx.prior_outputs,  # 全部分析师输出
                shared_state=base_ctx.shared_state,
                role_args={},
                model_tier="deep",
                model_config=self.recipe.models.deep,
            )
            
            prompt_ctx = _call_prepare_context(role, pm_ctx)
            prompt_ctx["output_language"] = output_language
            prompt_ctx["ticker"] = self.ticker
            
            try:
                renderer.validate_variables(role.template, set(prompt_ctx.keys()))
            except Exception as e:
                logger.error(
                    i18n.t(
                        "run.template_validation_failed",
                        role_id=role.role_id,
                        error=e,
                    )
                )
                raise
            
            # 渲染提示词（用于持久化）
            prompt_text = renderer.render(role.template, prompt_ctx)
            persister.save(role.role_id, 1, prompt_text, {"template": role.template})
            
            # 注入 renderer 和 llm 到 shared_state
            pm_ctx.shared_state = {
                **base_ctx.shared_state,
                "prompt_renderer": renderer,
                "llm_client": llm,
            }
            
            # 统一调用 analyze()
            out = role.analyze(pm_ctx)
            
            state_mgr.save_output(pm_spec.role_id, out)
            s["final_report"] = out
            return s

        for role in actual_analysts:
            executor.add_node(role.role_id, make_analyst_fn(role))
        executor.add_node(actual_pm.role_id, run_pm_fn)

        # 6. 执行图
        final_state = executor.execute()

        # 7. 收尾层：幻觉清理与报告生成
        report = final_state["final_report"]
        if report and report.cited_evidence:
            valid_ids = {item.evidence_id for item in store.manifest.items}
            valid_citations = [cid for cid in report.cited_evidence if cid in valid_ids]
            
            if len(valid_citations) < len(report.cited_evidence):
                fake_ids = set(report.cited_evidence) - set(valid_citations)
                logger.warning(
                    i18n.t(
                        "run.hallucinated_citations", fake_ids=str(fake_ids)
                    )
                )
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
        logger.info(i18n.t("run.completed", path=str(report_path)))
        
        return report_path