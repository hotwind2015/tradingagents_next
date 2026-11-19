from __future__ import annotations

from tradingagents.run.registry import PluginRegistry

role_registry = PluginRegistry("tradingagents.roles", attr="role_id")

__all__ = ["role_registry"]