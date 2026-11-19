from __future__ import annotations

import logging
from datetime import datetime, timezone

from tradingagents.evidence.store import EvidenceStore
from tradingagents.models.evidence import EvidenceItem
from tradingagents.providers.base import DataRequest
from tradingagents.run.plugin_manager import PluginManager

logger = logging.getLogger("tradingagents.data")

class DataFetchError(Exception):
    """所有备用数据源均获取失败"""
    pass

class DataRouter:
    def __init__(self, plugin_manager: PluginManager, store: EvidenceStore):
        self.plugin_manager = plugin_manager
        self.store = store

    def fetch_and_store(self, ticker: str, ev_type: str, provider_chain: list[str]):
        for provider_id in provider_chain:
            try:
                provider_obj = self.plugin_manager.get("provider", provider_id)
                provider = provider_obj() if isinstance(provider_obj, type) else provider_obj
                
                req = DataRequest(evidence_type=ev_type, ticker=ticker, as_of=datetime.now().date())
                raw_evs = provider.fetch(req)
                
                if raw_evs:
                    for raw_ev in raw_evs:
                        item = EvidenceItem(
                            evidence_id=f"ev-{len(self.store.manifest.items)+1:04d}",
                            evidence_type=raw_ev.evidence_type,
                            provider=raw_ev.provider,
                            method=raw_ev.method,
                            summary=raw_ev.summary,
                            raw_ref=f"raw/ev-{len(self.store.manifest.items)+1:04d}.json",
                            fetched_at=datetime.now(timezone.utc)
                        )
                        self.store.append(item, raw_ev.raw_payload)
                        logger.info(f"Fetched {item.evidence_id} via {provider_id}")
                    return  # 成功获取就退出尝试链
            except Exception as e:
                logger.warning(f"Provider {provider_id} failed for {ev_type}: {e}. Trying next...")
        
        # 如果循环结束还没 return，说明全挂了。直接抛异常！
        logger.error(f"All providers in chain failed for {ev_type}.")
        raise DataFetchError(f"无法获取必需的数据类型: {ev_type}，网络可能受限或 API 限流。")