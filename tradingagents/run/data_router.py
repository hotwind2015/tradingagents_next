from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from tradingagents.evidence.store import EvidenceStore
from tradingagents.models.evidence import EvidenceItem, EvidenceMetadata, ProcessingLevel
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

    def fetch_and_store(self, ticker: str, ev_type: str, provider_chain: list[str], processing_level: str = ProcessingLevel.RAW):
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
                        # 组装元数据
                        metadata = EvidenceMetadata(
                            source_provider=raw_ev.provider,
                            source_method=raw_ev.method,
                            fetched_at=datetime.now(timezone.utc),
                            processing_level=processing_level,
                            processing_chain=["fetch"],
                            quality_scores=self._assess_quality(raw_ev.raw_payload, ev_type),
                        )
                        
                        # 基因链：根据当前 manifest 中的同类型证据构建 lineage
                        lineage = self._build_lineage(ev_type)
                        
                        item = EvidenceItem(
                            evidence_id=f"ev-{len(self.store.manifest.items)+1:04d}",
                            evidence_type=raw_ev.evidence_type,
                            provider=raw_ev.provider,
                            method=raw_ev.method,
                            summary=raw_ev.summary,
                            raw_ref=f"raw/ev-{len(self.store.manifest.items)+1:04d}.json",
                            fetched_at=datetime.now(timezone.utc),
                            metadata=metadata,
                            lineage=lineage,
                        )
                        self.store.append(item, raw_ev.raw_payload)
                        logger.info(
                            i18n.t(
                                "run.fetched_evidence",
                                ev_id=item.evidence_id,
                                summary=item.summary,
                                provider=item.provider
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

    def _assess_quality(self, payload: dict[str, Any], ev_type: str) -> dict[str, float]:
        """简单的质量评估，返回 0-1 评分"""
        scores = {}
        if not payload:
            return {"completeness": 0.0, "freshness": 0.0}
        # 简单启发式：字段数量、关键字段存在性
        scores["completeness"] = min(len(payload) / 5.0, 1.0)  # 假设 5 个字段为完整
        scores["freshness"] = 1.0  # 刚获取，默认最新
        return scores

    def _build_lineage(self, ev_type: str) -> list[str]:
        """构建基因链：收集 manifest 中同类型的已有证据 ID 作为祖先"""
        return [
            item.evidence_id 
            for item in self.store.manifest.items 
            if item.evidence_type == ev_type
        ]