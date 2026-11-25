"""Reddit Social Sentiment Provider.

Provides:
- sentiment_social_reddit: Reddit posts mentioning a ticker
"""

from __future__ import annotations

import html
import logging
import random
import re
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence
from tradingagents.utils import get_i18n

logger = logging.getLogger(__name__)

_RSS = "https://www.reddit.com/r/{sub}/search.rss?{qs}"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Default subreddits ordered roughly by signal density for ticker-specific discussion
DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")

# Crypto is discussed in crypto communities
CRYPTO_SUBREDDITS = ("CryptoCurrency", "CryptoMarkets")
_COIN_SUBREDDITS = {"BTC": "Bitcoin", "ETH": "ethereum", "SOL": "solana"}

_FEED_PAGE = 100
_SCREEN_CHARS = 1000
_SEARCH_LOOKBACK = timedelta(days=7)

_RETRY_FALLBACK_SECONDS = 60.0


def _jitter(seconds: float, frac: float = 0.2) -> float:
    return seconds * (1.0 + random.uniform(-frac, frac))


def _retry_after_seconds(exc: HTTPError) -> float | None:
    try:
        val = exc.headers.get("Retry-After") if getattr(exc, "headers", None) else None
        return min(float(val), 60.0) if val is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def _iso_to_timestamp(iso_str: str | None) -> float | None:
    if not iso_str:
        return None
    try:
        normalized = iso_str[:-1] + "+00:00" if iso_str.endswith("Z") else iso_str
        return datetime.fromisoformat(normalized).timestamp()
    except (ValueError, TypeError):
        return None


def _strip_html(content: str) -> str:
    if not content:
        return ""
    if "<!-- SC_OFF -->" in content and "<!-- SC_ON -->" in content:
        content = content.split("<!-- SC_OFF -->")[1].split("<!-- SC_ON -->")[0]
    text = re.sub(r"<[^>]+>", " ", content)
    return " ".join(html.unescape(text).split())


def _search_qs(ticker: str, limit: int) -> str:
    return urlencode({
        "q": ticker,
        "restrict_sr": "on",
        "sort": "new",
        "t": "week",
        "limit": limit,
    })


def subreddits_for(ticker: str) -> tuple[str, ...]:
    """The subreddits searched for ticker: crypto communities for a crypto pair."""
    base = crypto_base(ticker)
    if not base:
        return DEFAULT_SUBREDDITS
    coin = _COIN_SUBREDDITS.get(base)
    return ((coin,) if coin else ()) + CRYPTO_SUBREDDITS


def crypto_base(ticker: str) -> str | None:
    """Extract crypto base from ticker (e.g., BTC-USD -> BTC)."""
    if not isinstance(ticker, str):
        return None
    compact = ticker.strip().upper().rstrip("+").replace("-", "")
    for quote in ("USDT", "USDC", "USD"):
        if compact.endswith(quote):
            base = compact[: -len(quote)]
            return base if base in {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH", "DOT", "AVAX", "LINK"} else None
    return None


def _within_window(posts, start_date, end_date):
    """Keep only posts published in [start_date, end_date] (look-ahead safe)."""
    if not (start_date and end_date):
        return posts
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    return [p for p in posts if _in_window(_posted_at(p), start_dt, end_dt)]


def _posted_at(post) -> datetime | None:
    """A post's created_utc epoch as a UTC datetime, or None when missing."""
    ts = post.get("created_utc")
    return datetime.fromtimestamp(ts, tz=UTC) if ts else None


def _coverage_dates(posts) -> list:
    dates = [_posted_at(p) for p in posts]
    if len(posts) < _FEED_PAGE:
        dates.append(datetime.now(UTC) - _SEARCH_LOOKBACK)
    return dates


def _fetch_subreddit_rss(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
    _retry: bool = True,
) -> list[dict] | None:
    url = _RSS.format(sub=sub, qs=_search_qs(ticker, limit))
    req = Request(url, headers={"User-Agent": _UA})
    try:
        with urlopen(req, timeout=timeout) as resp:
            root = ET.fromstring(resp.read())
    except HTTPError as exc:
        if exc.code == 429 and _retry:
            retry_after = _retry_after_seconds(exc)
            wait = retry_after if retry_after is not None else _jitter(_RETRY_FALLBACK_SECONDS)
            logger.warning("Reddit RSS 429 for r/%s · %s — backing off %.1fs then retrying once", sub, ticker, wait)
            time.sleep(wait)
            return _fetch_subreddit_rss(ticker, sub, limit, timeout, _retry=False)
        logger.warning("Reddit RSS fetch failed for r/%s · %s: %s", sub, ticker, exc)
        return None
    except (OSError, ET.ParseError) as exc:
        logger.warning("Reddit RSS fetch failed for r/%s · %s: %s", sub, ticker, exc)
        return None

    posts = []
    for entry in root.findall("atom:entry", _ATOM_NS)[:limit]:
        title_el = entry.find("atom:title", _ATOM_NS)
        published_el = entry.find("atom:published", _ATOM_NS)
        content_el = entry.find("atom:content", _ATOM_NS)
        category_el = entry.find("atom:category", _ATOM_NS)
        posts.append({
            "title": (title_el.text if title_el is not None else "") or "",
            "created_utc": _iso_to_timestamp(published_el.text if published_el is not None else None),
            "selftext": _strip_html(content_el.text if content_el is not None else ""),
            "subreddit": category_el.get("term") if category_el is not None else (sub if "+" not in sub else ""),
        })
    return posts


class RedditSocialProvider:
    """Reddit social sentiment provider."""
    
    provider_id = "reddit_social"
    provides = {"sentiment_social_reddit"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        self.limit_per_sub = kwargs.get("limit_per_sub", 5)
        self.timeout = kwargs.get("timeout", 10.0)

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        i18n = get_i18n()
        results = []
        ticker = req.ticker
        
        subreddits = list(req.params.get("subreddits") or subreddits_for(ticker))
        crypto_base_val = crypto_base(ticker) or ticker
        label = ", ".join(f"r/{s}" for s in subreddits)
        
        start_date = req.params.get("start_date")
        end_date = req.params.get("end_date")
        
        fetched = _fetch_subreddit_rss(ticker, "+".join(subreddits), _FEED_PAGE, self.timeout)
        if fetched is None:
            return [RawEvidence(
                evidence_type="sentiment_social_reddit",
                provider=self.provider_id,
                method="reddit_rss",
                params=req.params,
                summary=f"<Reddit unavailable: fetch failed ({label}); this is not an absence of discussion>",
                raw_payload={"error": "fetch_failed", "subreddits": subreddits}
            )]
        
        window = bool(start_date and end_date)
        posts = _within_window(fetched, start_date, end_date)
        if not posts:
            gap = window and _coverage_gap(
                _coverage_dates(fetched), start_date, end_date,
                "Reddit search", f"discussion of {ticker.upper()}",
            )
            period = f"within {start_date}..{end_date}" if window else "in the past 7 days"
            return [RawEvidence(
                evidence_type="sentiment_social_reddit",
                provider=self.provider_id,
                method="reddit_rss",
                params=req.params,
                summary=gap or f"<no Reddit posts found mentioning {ticker.upper()} across {label} {period}>",
                raw_payload={"posts": [], "subreddits": subreddits}
            )]
        
        # Apply screening if available
        screen = req.params.get("screen")
        note = ""
        if screen:
            keep, note = screen([f"{p.get('title') or ''}\n{p.get('selftext') or ''}"[:_SCREEN_CHARS] for p in posts])
            posts = [p for p, kept in zip(posts, keep, strict=True) if kept]
        
        # Group by subreddit
        by_sub = {s.lower(): (s, []) for s in subreddits}
        for p in posts:
            sub = p.get("subreddit") or (subreddits[0] if len(subreddits) == 1 else "unknown")
            by_sub.setdefault(sub.lower(), (sub, []))[1].append(p)
        
        page_full = len(fetched) >= _FEED_PAGE
        blocks = []
        for sub, sub_posts in by_sub.values():
            if not sub_posts:
                blocks.append(f"r/{sub}: <no posts found mentioning {ticker.upper()}>")
                continue
            sub_posts = sub_posts[:self.limit_per_sub]
            lines = [f"r/{sub} — {len(sub_posts)} recent posts mentioning {ticker.upper()}:"]
            for p in sub_posts:
                title = (p.get("title") or "").replace("\n", " ").strip()
                created = p.get("created_utc")
                created_str = time.strftime("%Y-%m-%d", time.gmtime(created)) if created else "?"
                selftext = (p.get("selftext") or "").replace("\n", " ").strip()
                if len(selftext) > 240:
                    selftext = selftext[:240] + "…"
                lines.append(f"  [{created_str}] {title}" + (f"\n    body excerpt: {selftext}" if selftext else ""))
            blocks.append("\n".join(lines))
        
        content = "\n\n".join(([note] if note else []) + blocks)
        
        return [RawEvidence(
            evidence_type="sentiment_social_reddit",
            provider=self.provider_id,
            method="reddit_rss",
            params={"subreddits": subreddits, "limit_per_sub": self.limit_per_sub},
            summary=f"Reddit posts for {ticker.upper()} across {label}",
            raw_payload={
                "content": content,
                "subreddits": subreddits,
                "post_count": len(posts),
            }
        )]


def _coverage_gap(dates, start_date, end_date, source, subject):
    """Generate a coverage gap message."""
    # Simplified version
    return None


class RedditSocialProvider:
    """Reddit social sentiment provider."""
    
    provider_id = "reddit_social"
    provides = {"sentiment_social_reddit"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        self.limit_per_sub = kwargs.get("limit_per_sub", 5)
        self.timeout = kwargs.get("timeout", 10.0)

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        i18n = get_i18n()
        results = []
        ticker = req.ticker
        
        subreddits = list(req.params.get("subreddits") or subreddits_for(ticker))
        label = ", ".join(f"r/{s}" for s in subreddits)
        
        start_date = req.params.get("start_date")
        end_date = req.params.get("end_date")
        
        fetched = _fetch_subreddit_rss(ticker, "+".join(subreddits), _FEED_PAGE, 10.0)
        if fetched is None:
            return [RawEvidence(
                evidence_type="sentiment_social_reddit",
                provider=self.provider_id,
                method="reddit_rss",
                params=req.params,
                summary=f"<Reddit unavailable: fetch failed ({', '.join(f'r/{s}' for s in subreddits)}); this is not an absence of discussion>",
                raw_payload={"error": "fetch_failed", "subreddits": subreddits}
            )]
        
        window = bool(start_date and end_date)
        posts = _within_window(fetched, start_date, end_date)
        if not posts:
            period = f"within {start_date}..{end_date}" if window else "in the past 7 days"
            return [RawEvidence(
                evidence_type="sentiment_social_reddit",
                provider=self.provider_id,
                method="reddit_rss",
                params=req.params,
                summary=f"<no Reddit posts found mentioning {ticker.upper()} across {', '.join(f'r/{s}' for s in subreddits)} {period}>",
                raw_payload={"posts": [], "subreddits": subreddits}
            )]
        
        blocks = []
        for sub in subreddits:
            sub_posts = [p for p in posts if p.get("subreddit") == sub]
            if not sub_posts:
                blocks.append(f"r/{sub}: <no posts found mentioning {ticker.upper()}>")
                continue
            sub_posts = sub_posts[:5]
            lines = [f"r/{sub} — {len(sub_posts)} recent posts mentioning {ticker.upper()}:"]
            for p in sub_posts:
                title = (p.get("title") or "").replace("\n", " ").strip()
                created = p.get("created_utc")
                created_str = time.strftime("%Y-%m-%d", time.gmtime(created)) if created else "?"
                selftext = (p.get("selftext") or "").replace("\n", " ").strip()
                if len(selftext) > 240:
                    selftext = selftext[:240] + "…"
                lines.append(f"  [{created_str}] {title}" + (f"\n    body excerpt: {selftext}" if selftext else ""))
            blocks.append("\n".join(lines))
        
        content = "\n\n".join(blocks)
        
        return [RawEvidence(
            evidence_type="sentiment_social_reddit",
            provider=self.provider_id,
            method="reddit_rss",
            params={"subreddits": subreddits},
            summary=f"Reddit posts for {ticker.upper()} across {', '.join(f'r/{s}' for s in subreddits)}",
            raw_payload={
                "content": content,
                "subreddits": subreddits,
                "post_count": len(posts),
            }
        )]


RedditSocialProvider = RedditSocialProvider