from __future__ import annotations

import logging
from datetime import datetime, timezone

from tradingagents.evidence.store import EvidenceStore
from tradingagents.models.evidence import EvidenceItem
from tradingagents.providers.base import DataRequest
from tradingagents.run.plugin_manager import PluginManager
from tradingagents.utils import get_i18n

logger = logging.getLogger("tradingagents.data")

class DataFetchError(Exception):
    """所有备用数据源均获取失败"""
    pass

class DataRouter:
    def __init__(self, plugin_manager: PluginManager, store: EvidenceStore, provider_args: dict[str, dict[str, Any]] | None = None):
        self.plugin_manager = plugin_manager
        self.store = store
        self.provider_args = provider_args or {}

    def fetch_and_store(self, ticker: str, ev_type: str, provider_chain: list[str]):
        i18n = get_i18n()
        for provider_id in provider_chain:
            try:
                provider_obj = self.plugin_manager.get("provider", provider_id)
                # 透传 provider_args 给 provider 实例化
                args = self.provider_args.get(provider_id, {})
                provider = provider_obj(**args) if args else (provider_obj() if isinstance(provider_obj, type) else provider_obj)
                
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
                        logger.info(
                            i18n.t(
                                "run.fetched_evidence",
                                ev_id=item.evidence_id,
                                summary=item.summary,
                            )
                        )
                    return  # 成功获取就退出尝试链
            except Exception as e:
                logger.warning(
                    i18n.t(
                        "run.provider_failed",
                        provider_id=provider_id,
                        evidence_type=ev_type,
                        error=e,
                    )
                )
        
        # 如果循环结束还没 return，说明全挂了。直接抛异常！
        error_message = i18n.t("errors.data_fetch_failed", evidence_type=ev_type)
        logger.error(error_message)
        raise DataFetchError(error_message)