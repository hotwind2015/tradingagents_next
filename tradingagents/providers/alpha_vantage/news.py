"""Alpha Vantage News Provider.

Provides:
- news_raw: Company-specific news from Alpha Vantage NEWS_SENTIMENT
- global_news_raw: Global macroeconomic news from Alpha Vantage NEWS_SENTIMENT
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from tradingagents.providers.alpha_vantage._common import (
    _make_api_request,
    format_datetime_for_api,
    AlphaVantageNotConfiguredError,
    AlphaVantageRateLimitError,
)
from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence
from tradingagents.utils import get_i18n

logger = logging.getLogger(__name__)


class AlphaVantageNewsProvider:
    """Alpha Vantage news provider (NEWS_SENTIMENT endpoint)."""

    provider_id = "alpha_vantage_news"
    provides = {"news_raw", "global_news_raw"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        self.article_limit = kwargs.get("article_limit", 20)
        self.global_lookback_days = kwargs.get("global_lookback_days", 7)
        self.global_article_limit = kwargs.get("global_article_limit", 20)
        # Default topics for global news
        self.global_topics = kwargs.get("global_topics", "financial_markets,economy_macro,economy_monetary")

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        i18n = get_i18n()
        results = []

        if req.evidence_type == "news_raw":
            results.extend(self._fetch_company_news(req))
        elif req.evidence_type == "global_news_raw":
            results.extend(self._fetch_global_news(req))

        return results

    def _fetch_company_news(self, req: DataRequest) -> list[RawEvidence]:
        """Fetch company-specific news."""
        i18n = get_i18n()
        symbol = req.ticker
        start_date = req.params.get("start_date", (datetime.now().strftime("%Y-%m-%d")))
        end_date = req.params.get("end_date", datetime.now().strftime("%Y-%m-%d"))
        limit = req.params.get("limit", self.article_limit)

        params = {
            "tickers": symbol,
            "time_from": format_datetime_for_api(start_date),
            "time_to": format_datetime_for_api(end_date, end_of_day=True),
            "limit": str(limit),
        }

        try:
            response = _make_api_request("NEWS_SENTIMENT", params)
            articles = self._parse_news_response(response, symbol)

            if not articles:
                summary = f"No news found for {symbol} between {start_date} and {end_date}"
            else:
                headlines = "\n".join(f"- {a['title']} ({a['publisher']})" for a in articles[:5])
                summary = i18n.t(
                    "providers.alpha_vantage.news.news_summary",
                    ticker=symbol,
                    headlines=headlines,
                    count=len(articles),
                )

            return [RawEvidence(
                evidence_type="news_raw",
                provider=self.provider_id,
                method="alpha_vantage_news_sentiment",
                params={"start_date": start_date, "end_date": end_date, "limit": limit},
                summary=summary,
                raw_payload={"articles": articles, "symbol": symbol},
            )]

        except (AlphaVantageNotConfiguredError, AlphaVantageRateLimitError):
            raise
        except Exception as e:
            logger.warning("Alpha Vantage company news fetch failed for %s: %s", symbol, e)
            raise

    def _fetch_global_news(self, req: DataRequest) -> list[RawEvidence]:
        """Fetch global/macro news."""
        i18n = get_i18n()
        as_of_date = req.params.get("as_of_date", datetime.now().strftime("%Y-%m-%d"))
        look_back_days = req.params.get("look_back_days", self.global_lookback_days)
        limit = req.params.get("limit", self.global_article_limit)
        topics = req.params.get("topics", self.global_topics)

        from datetime import timedelta
        curr_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
        start_dt = curr_dt - timedelta(days=look_back_days)
        start_date = start_dt.strftime("%Y-%m-%d")

        params = {
            "topics": topics,
            "time_from": format_datetime_for_api(start_date),
            "time_to": format_datetime_for_api(as_of_date, end_of_day=True),
            "limit": str(limit),
        }

        try:
            response = _make_api_request("NEWS_SENTIMENT", params)
            articles = self._parse_news_response(response, "GLOBAL")

            if not articles:
                summary = f"No global news found between {start_date} and {as_of_date}"
            else:
                headlines = "\n".join(f"- {a['title']} ({a['publisher']})" for a in articles[:5])
                summary = i18n.t(
                    "providers.alpha_vantage.news.global_news_summary",
                    headlines=headlines,
                    start_date=start_date,
                    end_date=as_of_date,
                    count=len(articles),
                )

            return [RawEvidence(
                evidence_type="global_news_raw",
                provider=self.provider_id,
                method="alpha_vantage_global_news",
                params={"as_of_date": as_of_date, "look_back_days": look_back_days, "limit": limit, "topics": topics},
                summary=summary,
                raw_payload={"articles": articles, "topics": topics},
            )]

        except (AlphaVantageNotConfiguredError, AlphaVantageRateLimitError):
            raise
        except Exception as e:
            logger.warning("Alpha Vantage global news fetch failed: %s", e)
            raise

    def _parse_news_response(self, response: str | dict, symbol: str) -> list[dict]:
        """Parse NEWS_SENTIMENT API response into article list."""
        import json

        if isinstance(response, str):
            try:
                data = json.loads(response)
            except json.JSONDecodeError:
                logger.warning("Failed to parse NEWS_SENTIMENT response as JSON")
                return []
        else:
            data = response

        # Response structure: {"feed": [...], ...}
        feed = data.get("feed", [])
        articles = []

        for item in feed:
            article = {
                "title": item.get("title", "No title"),
                "summary": item.get("summary", ""),
                "publisher": item.get("source", "Unknown"),
                "url": item.get("url", ""),
                "pub_date": item.get("time_published", ""),
                "ticker_sentiment": item.get("ticker_sentiment", []),
            }
            # Filter for relevant ticker if provided
            if symbol != "GLOBAL":
                relevant = any(
                    ts.get("ticker") == symbol
                    for ts in article["ticker_sentiment"]
                )
                if not relevant:
                    continue
            articles.append(article)

        return articles


AlphaVantageNewsProvider = AlphaVantageNewsProvider