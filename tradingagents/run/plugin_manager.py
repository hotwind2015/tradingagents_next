from __future__ import annotations
import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from typing import Any
from importlib.metadata import entry_points

logger = logging.getLogger("tradingagents.plugin_manager")

class PluginManager:
    def __init__(self):
        # 核心注册表：{ "provider": { "yfinance": <类> }, "role": {...}, "llm": {...} }
        self._registry: dict[str, dict[str, Any]] = {}
        # 来源追踪表：{ "provider": { "yfinance": "entry_point:yfinance" } }
        self._sources: dict[str, dict[str, str]] = {}
        
        # 统一提取不同插件的 ID 属性
        self._id_attr_map = {
            "provider": "provider_id",
            "role": "role_id",
            "llm": "llm_id"
        }

    def register(self, plugin_type: str, plugin_id: str, obj: Any, source: str):
        if plugin_type not in self._registry:
            self._registry[plugin_type] = {}
            self._sources[plugin_type] = {}

        # === 冲突检测与覆盖逻辑 ===
        if plugin_id in self._registry[plugin_type]:
            old_source = self._sources[plugin_type][plugin_id]
            
            if old_source.startswith("custom:") and source.startswith("custom:"):
                old_dir = old_source.split("/")[0] if "/" in old_source else old_source
                new_dir = source.split("/")[0] if "/" in source else source
                
                if old_dir == new_dir:
                    logger.warning(
                        f"‼️ [SAME-DIRECTORY CONFLICT] {plugin_type} '{plugin_id}' duplicated! "
                        f"[{source}] OVERRIDES [{old_source}]."
                    )
                else:
                    logger.warning(
                        f"⚠️ [DIRECTORY OVERRIDE] {plugin_type} '{plugin_id}' from [{source}] overrides [{old_source}]."
                    )
            else:
                logger.warning(
                    f"⚠️ [OFFICIAL OVERRIDE] User plugin {plugin_type} '{plugin_id}' from [{source}] overrides official [{old_source}]."
                )

        self._registry[plugin_type][plugin_id] = obj
        self._sources[plugin_type][plugin_id] = source
        logger.info(f"Registered {plugin_type} '{plugin_id}' from {source}")

    def discover_all(self, plugin_dirs: list[Path]):
        # 1. 加载官方内置插件 (Entry Points)
        for group, p_type in [
            ("tradingagents.providers", "provider"),
            ("tradingagents.roles", "role"),
            ("tradingagents.llms", "llm")
        ]:
            for ep in entry_points(group=group):
                try:
                    obj = ep.load()
                    id_attr = self._id_attr_map.get(p_type)
                    if not id_attr or not hasattr(obj, id_attr):
                        logger.warning(f"Official {p_type} {ep.name} missing attribute '{id_attr}', skipped.")
                        continue
                    pid = getattr(obj, id_attr)
                    self.register(p_type, pid, obj, source=f"official:{ep.name}")
                except Exception as exc:
                    logger.warning(f"Failed to load entry_point {ep.name}: {exc}")

        # 2. 扫描用户目录 (按顺序扫描，强制按文件名排序)
        for d in plugin_dirs:
            if not d.exists() or not d.is_dir():
                continue
            logger.info(f"Scanning custom plugin directory: {d}")
            for py_file in sorted(d.rglob("*.py")):  # <--- sorted 保证确定性
                if py_file.name.startswith("__"):
                    continue
                self._load_file_and_register(py_file, d)

    def _load_file_and_register(self, file_path: Path, root_dir: Path):
        try:
            module_name = f"custom_plugin_{file_path.stem}_{id(file_path)}"
            spec = importlib.util.spec_from_file_location(module_name, str(file_path))
            if spec is None or spec.loader is None:
                return
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            source_tag = f"custom:{root_dir.name}/{file_path.name}"

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if obj.__module__ != module_name:
                    continue
                
                if hasattr(obj, "plugin_type"):
                    p_type = getattr(obj, "plugin_type")
                    id_attr = self._id_attr_map.get(p_type)
                    if id_attr and hasattr(obj, id_attr):
                        p_id = getattr(obj, id_attr)
                        self.register(p_type, p_id, obj, source=source_tag)
                    else:
                        logger.warning(f"Class {obj.__name__} in {file_path.name} has type '{p_type}' but missing ID attribute '{id_attr}'.")
        except Exception as e:
            logger.warning(f"Failed to load plugin from {file_path}: {e}")

    def get(self, plugin_type: str, plugin_id: str) -> Any:
        try:
            return self._registry[plugin_type][plugin_id]
        except KeyError:
            available = list(self._registry.get(plugin_type, {}).keys())
            raise KeyError(f"Plugin '{plugin_id}' of type '{plugin_type}' not found. Available: {available}")