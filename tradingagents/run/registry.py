from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any


class PluginRegistry:
    def __init__(self, group: str, attr: str = "plugin_id"):
        self.group = group
        self.attr = attr
        self._plugins: dict[str, Any] = {}
        self._sources: dict[str, str] = {}
        self.warnings: list[str] = []

    def register(self, plugin_id: str, obj: Any, source: str = "manual") -> None:
        if plugin_id in self._plugins and source != "manual":
            return
        self._plugins[plugin_id] = obj
        self._sources[plugin_id] = source

    def discover(self) -> None:
        for ep in entry_points(group=self.group):
            try:
                obj = ep.load()
            except Exception as exc:  # noqa: BLE001 - 插件加载失败不应中断启动
                self.warnings.append(f"failed to load {ep.name}: {exc}")
                continue
            plugin_id = getattr(obj, self.attr, ep.name)
            self.register(plugin_id, obj, source=f"entry_point:{ep.name}")

    def get(self, plugin_id: str) -> Any:
        if plugin_id not in self._plugins:
            available = ", ".join(self.ids())
            raise KeyError(f"plugin not registered: '{plugin_id}'. Available plugins: [{available}]")
        return self._plugins[plugin_id]

    def ids(self) -> list[str]:
        return sorted(self._plugins)

    def source_of(self, plugin_id: str) -> str:
        return self._sources.get(plugin_id, "")