"""Evidence Chain Extractor - 从证据链中提取结构化数据供报告编译使用"""

from __future__ import annotations

from typing import Any
from tradingagents.evidence.view import EvidenceView


class EvidenceChainExtractor:
    """从证据链中提取结构化数据供报告编译使用"""
    
    def __init__(self, evidence_view: EvidenceView):
        self.evidence_view = evidence_view
    
    def _get_raw(self, ev_id: str) -> dict | None:
        """获取原始数据"""
        return self.evidence_view.get_raw(ev_id)
    
    def get_cited_evidence_items(self, evidence_type: str | set[str]) -> list:
        """按类型获取证据项"""
        if isinstance(evidence_type, str):
            evidence_type = {evidence_type}
        
        items = []
        for ev in self.evidence_view.for_types(evidence_type):
            items.append(ev)
        return items
    
    def get_cited_evidence_items_by_ids(self, cited_ids: set[str]) -> list:
        """获取被引用的证据项"""
        items = []
        for ev_id in cited_ids:
            ev = self.evidence_view.get(ev_id)
            if ev:
                items.append(ev)
        return items
    
    def get_technical_indicators(self, cited_ids: set[str]) -> dict:
        """提取技术指标数据"""
        indicators = {}
        for ev in self.evidence_view.for_types({"market_indicators"}):
            raw = self._get_raw(ev.evidence_id)
            if raw and raw.get("values"):
                indicator_name = raw.get("indicator", "")
                indicators[indicator_name] = raw["values"]
        return indicators
    
    def get_financial_statements(self, cited_ids: set[str]) -> dict:
        """获取财务报表"""
        statements = {}
        for ev in self.evidence_view.for_types({"financials_raw"}):
            raw = self._get_raw(ev.evidence_id)
            if raw:
                stmt_type = raw.get("statement_type", "unknown")
                statements[stmt_type] = raw.get("csv", "")
        return statements
    
    def get_fundamentals_overview(self, cited_ids: set[str]) -> dict:
        """获取基本面概览"""
        for ev in self.evidence_view.for_types({"fundamentals_raw"}):
            raw = self._get_raw(ev.evidence_id)
            if raw:
                return raw.get("fields", {})
        return {}
    
    def get_insider_transactions(self, cited_ids: set[str]) -> list:
        """获取内部人交易"""
        for ev in self.evidence_view.for_types({"insider_raw"}):
            raw = self._get_raw(ev.evidence_id)
            if raw:
                return raw.get("insider_transactions", [])
        return []
    
    def get_news_timeline(self, cited_ids: set[str]) -> list:
        """获取新闻时间线"""
        articles = []
        for ev in self.evidence_view.for_types({"news_raw", "global_news_raw"}):
            raw = self._get_raw(ev.evidence_id)
            if raw and raw.get("articles"):
                articles.extend(raw["articles"])
        return articles
    
    def get_sentiment_data(self, cited_ids: set[str]) -> dict:
        """获取情绪数据"""
        for ev in self.evidence_view.for_types({"sentiment_social_stocktwits", "sentiment_social_reddit"}):
            raw = self._get_raw(ev.evidence_id)
            if raw:
                return raw
        return {}
    
    def get_macro_indicators(self, cited_ids: set[str]) -> dict:
        """获取宏观指标"""
        for ev in self.evidence_view.for_types({"macro_raw"}):
            raw = self._get_raw(ev.evidence_id)
            if raw:
                return raw
        return {}
    
    def get_evidence_chains(self, cited_ids: set[str]) -> list[dict]:
        """获取完整证据链信息"""
        chains = []
        for ev_id in cited_ids:
            ev = self.evidence_view.get(ev_id)
            if ev:
                chains.append({
                    "evidence_id": ev.evidence_id,
                    "evidence_type": ev.evidence_type,
                    "provider": ev.provider,
                    "lineage": ev.lineage,
                    "processing_chain": ev.metadata.processing_chain if ev.metadata else [],
                    "quality_scores": ev.metadata.quality_scores if ev.metadata else {},
                    "processing_level": ev.metadata.processing_level if ev.metadata else "raw",
                })
        return chains
    
    def get_all_cited_ids(self, cited_ids: set[str]) -> set[str]:
        """获取所有被引用的证据ID"""
        return cited_ids
    
    def get_evidence_by_type(self, evidence_type: str) -> list:
        """按类型获取证据"""
        items = []
        for ev in self.evidence_view.for_types({evidence_type}):
            items.append(ev)
        return items
    
    def get_all_cited_ids_from_outputs(self, prior_outputs: dict) -> set[str]:
        """从所有分析师输出中收集引用的证据ID"""
        cited_ids = set()
        for output in prior_outputs.values():
            if hasattr(output, 'cited_evidence'):
                cited_ids.update(output.cited_evidence)
        return cited_ids


# 便捷函数
def create_evidence_extractor(evidence_view) -> 'EvidenceChainExtractor':
    """创建证据链提取器"""
    return EvidenceChainExtractor(evidence_view)