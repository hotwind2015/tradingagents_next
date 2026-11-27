"""YFinance News Provider.

Provides:
- news_raw: Company-specific news from Yahoo Finance
- global_news_raw: Global macroeconomic news from Yahoo Finance Search
"""

from __future__ import annotations

import contextlib
import logging
import re
from datetime import UTC, datetime
from typing import Any

import yfinance as yf
from dateutil.relativedelta import relativedelta

from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence
from tradingagents.utils import get_i18n

logger = logging.getLogger(__name__)

# =============================================================================
# Inlined from original tradingagents.dataflows.symbols
# =============================================================================

_FOREX_CURRENCIES = frozenset({
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD",
    "CNY", "CNH", "HKD", "SGD", "SEK", "NOK", "DKK", "PLN",
    "MXN", "ZAR", "TRY", "INR", "KRW", "BRL", "RUB", "THB",
})

_CRYPTO_BASES = frozenset({
    "BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH", "DOT", "AVAX", "LINK"
})

_ALIASES = {
    "XAUUSD": "GC=F", "XAU": "GC=F", "GOLD": "GC=F",
    "XAGUSD": "SI=F", "XAG": "SI=F", "SILVER": "SI=F",
    "XPTUSD": "PL=F", "XPDUSD": "PA=F",
    "WTICOUSD": "CL=F", "USOIL": "CL=F", "WTI": "CL=F",
    "BCOUSD": "BZ=F", "UKOIL": "BZ=F", "BRENT": "BZ=F",
    "NATGAS": "NG=F", "XNGUSD": "NG=F",
    "COPPER": "HG=F", "XCUUSD": "HG=F",
    "SPX500": "^GSPC", "US500": "^GSPC", "SPX": "^GSPC",
    "NAS100": "^NDX", "US100": "^NDX", "USTEC": "^NDX",
    "US30": "^DJI", "DJI30": "^DJI", "WS30": "^DJI",
    "GER40": "^GDAXI", "GER30": "^GDAXI", "DE40": "^GDAXI",
    "UK100": "^FTSE", "JP225": "^N225", "JPN225": "^N225",
    "FRA40": "^FCHI", "EU50": "^STOXX50E", "HK50": "^HSI",
}

_HK_CODE = re.compile(r"^(\d{1,5})\.HK$")
_SHANGHAI_SH = re.compile(r"^(\d{6})\.SH$")

_CRYPTO_QUOTES = ("USDT", "USDC", "USD")


def _crypto_base(raw: str) -> str | None:
    if not isinstance(raw, str):
        return None
    compact = raw.strip().upper().rstrip("+").replace("-", "")
    for quote in _CRYPTO_QUOTES:
        if compact.endswith(quote):
            base = compact[: -len(quote)]
            return base if base in _CRYPTO_BASES else None
    return None


def _normalize_crypto(s: str) -> str | None:
    base = _crypto_base(s)
    return f"{base}-USD" if base else None


def normalize_symbol(raw: str) -> str:
    """Map a user/broker symbol to its canonical Yahoo Finance symbol."""
    if not isinstance(raw, str) or not raw.strip():
        return raw

    s = raw.strip().upper()
    s = s.rstrip("+")

    crypto = _normalize_crypto(s)
    if s in _ALIASES:
        canonical = _ALIASES[s]
    elif crypto is not None:
        canonical = crypto
    elif len(s) == 6 and s[:3] in _FOREX_CURRENCIES and s[3:] in _FOREX_CURRENCIES:
        canonical = f"{s}=X"
    elif hk := _HK_CODE.match(s):
        canonical = f"{int(hk.group(1)):04d}.HK"
    elif sh := _SHANGHAI_SH.match(s):
        canonical = f"{sh.group(1)}.SS"
    else:
        canonical = s

    if canonical != raw.strip().upper():
        logger.info("Resolved symbol %r to Yahoo symbol %r", raw, canonical)
    return canonical


# =============================================================================
# Inlined from original tradingagents.dataflows.errors
# =============================================================================

class VendorError(Exception):
    """Base for any condition where a vendor could not return usable data."""
    pass


class VendorUnavailableError(VendorError):
    """A vendor could not answer: it throttled or failed the request."""
    pass


# =============================================================================
# News extraction utilities
# =============================================================================

def _extract_article_data(article: dict) -> dict:
    """Extract article data from yfinance news format (handles nested 'content' structure).
    Returns pub_date as ISO string for JSON serialization.
    """
    content = article.get("content")
    if isinstance(content, dict):
        url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        pub_date_str = content.get("pubDate") or ""
        pub_date = None
        if pub_date_str:
            with contextlib.suppress(ValueError, AttributeError):
                pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))

        return {
            "title": content.get("title") or "No title",
            "summary": content.get("summary") or "",
            "publisher": (content.get("provider") or {}).get("displayName") or "Unknown",
            "link": url_obj.get("url") or "",
            "pub_date": pub_date.isoformat() if pub_date else None,
        }
    # Fallback for flat structure
    pub_date = None
    ts = article.get("providerPublishTime")
    if ts:
        with contextlib.suppress(ValueError, OSError, TypeError):
            pub_date = datetime.fromtimestamp(ts, tz=UTC)
    return {
        "title": article.get("title") or "No title",
        "summary": article.get("summary") or "",
        "publisher": article.get("publisher") or "Unknown",
        "link": article.get("link") or "",
        "pub_date": pub_date.isoformat() if pub_date else None,
    }


def _search_news(canonical: str, limit: int) -> tuple[list, bool]:
    """Yahoo search's articles tagged with canonical, and whether it knows the symbol."""
    search = _yf_retry(lambda: yf.Search(canonical, news_count=limit))
    if search is None:
        return [], False
    tagged = [
        a for a in (search.news or [])
        if canonical in (t.upper() for t in a.get("relatedTickers") or [])
    ]
    knows = any((q.get("symbol") or "").upper() == canonical for q in search.quotes or [])
    return tagged, knows or bool(search.news)


def _format_articles(articles: list[dict]) -> str:
    out = ""
    for data in articles:
        out += f"### {data['title']} (source: {data['publisher']})\n"
        if data["summary"]:
            out += f"{data['summary']}\n"
        if data["link"]:
            out += f"Link: {data['link']}\n"
        out += "\n"
    return out


def _yf_retry(func, max_retries=3):
    import time
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)


def _in_window(pub_date_str, start_dt, end_dt):
    """Check if publication date is within window."""
    if not pub_date_str:
        return False
    try:
        pub_date = datetime.fromisoformat(pub_date_str)
        if pub_date.tzinfo is not None:
            pub_date = pub_date.replace(tzinfo=None)
        return start_dt <= pub_date <= end_dt
    except (ValueError, TypeError):
        return False


class YFinanceNewsProvider:
    """Yahoo Finance news provider."""
    
    provider_id = "yfinance_news"
    provides = {"news_raw", "global_news_raw"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        self.article_limit = kwargs.get("article_limit", 20)
        self.global_lookback_days = kwargs.get("global_lookback_days", 7)
        self.global_article_limit = kwargs.get("global_article_limit", 20)
        self.global_queries = kwargs.get("global_queries", [
            "stock market", "federal reserve", "inflation", "earnings", "economy"
        ])

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        i18n = get_i18n()
        results = []
        canonical = normalize_symbol(req.ticker)
        
        if req.evidence_type == "news_raw":
            # Company-specific news
            resolved = "" if canonical == req.ticker.upper() else f" (resolved to {canonical})"
            subject = f"news for {req.ticker}{resolved}"
            
            feed = _yf_retry(lambda: yf.Ticker(canonical).get_news(count=self.article_limit)) or []
            articles = [_extract_article_data(a) for a in feed]
            
            if not feed:
                found, answered = _search_news(canonical, self.article_limit)
                if not answered:
                    raise VendorUnavailableError(f"Yahoo Finance returned no news response for {canonical}")
                if not found:
                    raise VendorUnavailableError(f"Yahoo Finance has no news articles tagged {canonical}")
                articles = [_extract_article_data(a) for a in found]
            
            start_date = req.params.get("start_date", (datetime.now() - relativedelta(days=7)).strftime("%Y-%m-%d"))
            end_date = req.params.get("end_date", datetime.now().strftime("%Y-%m-%d"))
            
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            
            in_range = [a for a in articles if _in_window(a["pub_date"], start_dt, end_dt)]
            
            if in_range:
                summary = i18n.t(
                    "providers.yfinance.news.news_summary",
                    ticker=req.ticker,
                    headlines=_format_articles(in_range),
                    count=len(in_range),
                )
            else:
                if not feed:
                    summary = f"<Yahoo Finance news unavailable for {start_date}..{end_date}: Yahoo search returns only a sample of recent articles about {canonical}, so this is not an absence of {subject}>"
                else:
                    summary = f"No news found for {req.ticker}{resolved} between {start_date} and {end_date}"
            
            results.append(RawEvidence(
                evidence_type="news_raw",
                provider=self.provider_id,
                method="yf_news",
                params={"start_date": start_date, "end_date": end_date, "canonical": canonical},
                summary=summary,
                raw_payload={
                    "articles": in_range if in_range else articles,
                    "canonical": canonical,
                    "resolved": resolved,
                }
            ))
            
        elif req.evidence_type == "global_news_raw":
            # Global/macro news via Yahoo Search
            as_of_date = req.params.get("as_of_date", datetime.now().strftime("%Y-%m-%d"))
            look_back_days = req.params.get("look_back_days", self.global_lookback_days)
            limit = req.params.get("limit", self.global_article_limit)
            
            curr_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
            start_dt = curr_dt - relativedelta(days=look_back_days)
            start_date = start_dt.strftime("%Y-%m-%d")
            
            in_window_news = []
            seen_titles = set()
            
            for query in self.global_queries:
                found = _yf_retry(lambda q=query: yf.Search(
                    query=q,
                    news_count=limit,
                    enable_fuzzy_query=True,
                ).news)
                
                for article in found or []:
                    data = _extract_article_data(article)
                    if not _in_window(data["pub_date"], start_dt, curr_dt):
                        continue
                    if data["title"] and data["title"] not in seen_titles:
                        seen_titles.add(data["title"])
                        in_window_news.append(data)
                
                if len(in_window_news) >= limit:
                    break
            
            news_str = _format_articles(in_window_news[:limit])
            
            if not news_str:
                summary = f"No global news found between {start_date} and {as_of_date}"
            else:
                summary = i18n.t(
                    "providers.yfinance.news.global_news_summary",
                    headlines=news_str,
                    start_date=start_date,
                    end_date=as_of_date,
                    count = len(in_window_news)
                )
            
            results.append(RawEvidence(
                evidence_type="global_news_raw",
                provider=self.provider_id,
                method="yf_global_news",
                params={"as_of_date": as_of_date, "look_back_days": look_back_days, "limit": limit},
                summary=summary,
                raw_payload={
                    "articles": in_window_news[:limit],
                    "queries": self.global_queries,
                }
            ))
        
        return results


YFinanceNewsProvider = YFinanceNewsProvider