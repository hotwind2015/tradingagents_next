from __future__ import annotations

from tradingagents.run.registry import PluginRegistry
from tradingagents.providers.base import DataProvider

provider_registry = PluginRegistry("tradingagents.providers", attr="provider_id")


def available_evidence_types() -> set[str]:
    types: set[str] = set()
    for pid in provider_registry.ids():
        provider = provider_registry.get(pid)
        provides = getattr(provider, "provides", set())
        types.update(provides)
    return types


__all__ = ["provider_registry", "available_evidence_types", "DataProvider"]