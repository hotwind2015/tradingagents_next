"""AKShare News Provider.

Provides:
- news_raw: Company-specific news from 东财/财新
- global_news_raw: Global/macro news from 东财/财联社/新浪/富途
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from tradingagents.providers.akshare._common import (
    classify_akshare_error,
    get_provider_i18n_key,
    handle_akshare_error,
    to_akshare_date,
    t_provider,
)
from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence
from tradingagents.utils import get_i18n

logger = logging.getLogger(__name__)

# =============================================================================
# Column Mapping
# =============================================================================

# 东财个股新闻
NEWS_EM_COL_MAP = {
    "代码": "symbol",
    "标题": "title",
    "内容": "content",
    "发布时间": "pub_time",
    "来源": "source",
    "链接": "url",
    "摘要": "summary",
}

# 财新新闻
NEWS_CX_COL_MAP = {
    "标题": "title",
    "内容": "content",
    "发布时间": "pub_time",
    "来源": "source",
    "链接": "url",
}

# 全球财经新闻 (东财)
GLOBAL_NEWS_EM_COL_MAP = {
    "标题": "title",
    "内容": "content",
    "发布时间": "pub_time",
    "来源": "source",
    "链接": "url",
}

# 财联社全球新闻
GLOBAL_NEWS_CLS_COL_MAP = {
    "标题": "title",
    "内容": "content",
    "发布时间": "pub_time",
    "链接": "url",
}

# 新浪全球新闻
GLOBAL_NEWS_SINA_COL_MAP = {
    "标题": "title",
    "内容": "content",
    "发布时间": "pub_time",
    "链接": "url",
}


class AKShareNewsProvider:
    """AKShare News Provider.

    Provides:
    - news_raw: Company-specific news from 东财/财新
    - global_news_raw: Global/macro news from 东财/财联社/新浪/富途
    """

    provider_id = "akshare_news"
    provides = {"news_raw", "global_news_raw"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        self.article_limit = kwargs.get("article_limit", 20)
        self.global_lookback_days = kwargs.get("global_lookback_days", 7)
        self.global_article_limit = kwargs.get("global_article_limit", 20)
        self.global_topics = kwargs.get("global_topics", "financial_markets,economy_macro,economy_monetary")

    def fetch(self, req: DataRequest) -> list:
        results = []

        if req.evidence_type == "news_raw":
            results.extend(self._fetch_company_news(req))
        elif req.evidence_type == "global_news_raw":
            results.extend(self._fetch_global_news(req))

        return results

    def _serialize_articles(self, articles: list) -> list:
        """Convert datetime/date objects in articles to ISO format strings for JSON serialization."""
        serialized = []
        for article in articles:
            serialized_article = {}
            for key, value in article.items():
                if isinstance(value, (pd.Timestamp, datetime)):
                    serialized_article[key] = value.isoformat()
                elif hasattr(value, 'isoformat'):  # Handles date objects too
                    serialized_article[key] = value.isoformat()
                else:
                    serialized_article[key] = value
            serialized.append(serialized_article)
        return serialized

    # -------------------------------------------------------------------------
    # news_raw: Company-specific news
    # -------------------------------------------------------------------------
    def _fetch_company_news(self, req: DataRequest) -> list:
        symbol = req.ticker
        start_date = req.params.get("start_date", (datetime.now().strftime("%Y-%m-%d")))
        end_date = req.params.get("end_date", datetime.now().strftime("%Y-%m-%d"))
        limit = req.params.get("limit", self.article_limit)

        # 1. 东财新闻
        try:
            import akshare as ak
            df = ak.stock_news_em(symbol=req.ticker)
            
            articles = []
            headlines = ""
            
            if not df.empty:
                df = df.rename(columns={
                    "代码": "symbol",
                    "新闻标题": "title",
                    "新闻内容": "content",
                    "发布时间": "pub_time",
                    "文章来源": "source",
                    "新闻链接": "url",
                    "摘要": "summary",
                })
                df = df.head(limit)

                articles = self._serialize_articles(df.to_dict(orient="records"))
                headlines = "\n".join(f"- {a.get('title', '')} ({a.get('source', '')})" for a in articles[:5])
            else:
                articles = []
                headlines = ""

            from tradingagents.utils import get_i18n
            i18n = get_i18n()

            summary = i18n.t(
                "providers.akshare.news.news_summary",
                ticker=req.ticker,
                headlines=headlines,
                count=len(articles),
            )

            return [RawEvidence(
                evidence_type="news_raw",
                provider=self.provider_id,
                method="akshare_news_em",
                params={"start_date": start_date, "end_date": end_date, "limit": limit},
                summary=summary,
                raw_payload={"articles": articles, "symbol": req.ticker},
            )]
        except Exception as e:
            logger.warning(f"东财新闻获取失败 {symbol}: {e}")

        # 2. 财新新闻 (备选)
        try:
            import akshare as ak
            df = ak.stock_news_main_cx()
            if not df.empty:
                df = df.rename(columns={
                    "标题": "title",
                    "内容": "content",
                    "发布时间": "pub_time",
                    "来源": "source",
                    "链接": "url",
                })
                df = df.head(limit)

                articles = self._serialize_articles(df.to_dict(orient="records"))
                headlines = "\n".join(f"- {a.get('title', '')} ({a.get('source', '')})" for a in articles[:5])

                from tradingagents.utils import get_i18n
                i18n = get_i18n()

                summary = i18n.t(
                    "providers.akshare.news.news_summary",
                    ticker=req.ticker,
                    headlines=headlines,
                    count=len(articles),
                )

                return [RawEvidence(
                    evidence_type="news_raw",
                    provider=self.provider_id,
                    method="akshare_news_cx",
                    params={"limit": limit},
                    summary=summary,
                    raw_payload={"articles": articles, "symbol": req.ticker},
                )]
        except Exception as e:
            logger.warning(f"财新新闻获取失败 {symbol}: {e}")

        # If all failed, return empty evidence
        return [RawEvidence(
            evidence_type="news_raw",
            provider=self.provider_id,
            method="akshare_news_failed",
            params={"symbol": req.ticker},
            summary=f"No news data available for {req.ticker}",
            raw_payload={"articles": []},
        )]

    # -------------------------------------------------------------------------
    # global_news_raw: Global/macro news
    # -------------------------------------------------------------------------
    def _fetch_global_news(self, req: DataRequest) -> list:
        as_of_date = req.params.get("as_of_date", "20241231")
        look_back_days = req.params.get("look_back_days", self.global_lookback_days)
        limit = req.params.get("limit", self.global_article_limit)
        topics = req.params.get("topics", self.global_topics)

        from datetime import datetime, timedelta

        curr_dt = datetime.strptime(as_of_date, "%Y%m%d")
        start_dt = curr_dt - timedelta(days=look_back_days)
        start_date = start_dt.strftime("%Y%m%d")

        all_articles = []
        sources_tried = []

        # 1. 东财全球新闻
        try:
            import akshare as ak
            df = ak.stock_news_global_em()
            if not df.empty:
                df = df.rename(columns={
                    "标题": "title",
                    "内容": "content",
                    "发布时间": "pub_time",
                    "来源": "source",
                    "链接": "url",
                })
                df = df.head(limit)
                all_articles.extend(df.to_dict(orient="records"))
                sources_tried.append("东财")
        except Exception as e:
            logger.warning(f"东财全球新闻获取失败: {e}")

        # 2. 财联社
        try:
            import akshare as ak
            df = ak.stock_news_global_cls()
            if not df.empty:
                df = df.rename(columns={
                    "标题": "title",
                    "内容": "content",
                    "发布时间": "pub_time",
                    "来源": "source",
                    "链接": "url",
                })
                df = df.head(limit)
                all_articles.extend(df.to_dict(orient="records"))
                sources_tried.append("财联社")
        except Exception as e:
            logger.warning(f"财联社全球新闻获取失败: {e}")

        # 3. 新浪全球新闻
        try:
            import akshare as ak
            df = ak.stock_news_global_sina()
            if not df.empty:
                df = df.rename(columns={
                    "发布时间": "pub_time",
                    "链接": "url",
                })
                df = df.head(limit)
                all_articles.extend(df.to_dict(orient="records"))
                sources_tried.append("新浪")
        except Exception as e:
            logger.warning(f"新浪全球新闻获取失败: {e}")

        # 4. 富途 (如果可用)
        try:
            import akshare as ak
            df = ak.stock_news_global_futu()
            if not df.empty:
                df = df.rename(columns={
                    "标题": "title",
                    "内容": "content",
                    "发布时间": "pub_time",
                    "链接": "url",
                })
                df = df.head(limit)
                all_articles.extend(df.to_dict(orient="records"))
                sources_tried.append("富途")
        except Exception as e:
            logger.warning(f"富途全球新闻获取失败: {e}")

        # Filter by date range if possible
        if all_articles:
            filtered = []
            for a in all_articles:
                pub_time = a.get("pub_time") or a.get("发布时间")
                if pub_time:
                    try:
                        pub_dt = pd.to_datetime(pub_time)
                        if start_dt <= pub_dt <= pd.Timestamp(as_of_date):
                            filtered.append(a)
                    except:
                        filtered.append(a)  # Keep if date parsing fails
                else:
                    filtered.append(a)
            all_articles = filtered[:limit]

        # Convert datetime objects to strings for JSON serialization
        all_articles = self._serialize_articles(all_articles)

        if not all_articles:
            return [RawEvidence(
                evidence_type="global_news_raw",
                provider=self.provider_id,
                method="akshare_global_news_failed",
                params={"as_of_date": as_of_date, "topics": topics},
                summary=f"No global news found between {start_date} and {as_of_date}",
                raw_payload={"articles": [], "sources_tried": sources_tried},
            )]

        # Format output
        headlines = "\n".join(f"- {a.get('title', '')} ({a.get('source', 'Unknown')})" for a in all_articles[:5])

        from tradingagents.utils import get_i18n
        i18n = get_i18n()

        summary = i18n.t(
            "providers.akshare.news.global_news_summary",
            headlines=headlines,
            start_date=start_date.replace("-", "") if "-" in start_date else start_date,
            end_date=as_of_date.replace("-", "") if "-" in as_of_date else as_of_date,
            count=len(all_articles),
        )

        return [RawEvidence(
            evidence_type="global_news_raw",
            provider=self.provider_id,
            method="akshare_global_news",
            params={"as_of_date": as_of_date, "look_back_days": look_back_days, "limit": limit, "topics": topics},
            summary=summary,
            raw_payload={
                "articles": all_articles,
                "sources": sources_tried,
            },
        )]


AKShareNewsProvider = AKShareNewsProvider