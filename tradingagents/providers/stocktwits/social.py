"""StockTwits Social Sentiment Provider.

Provides:
- sentiment_social_stocktwits: StockTwits messages for a ticker
"""

from __future__ import annotations

import contextlib
import html
import json
import logging
from datetime import datetime
from typing import Any
from urllib.request import Request, urlopen

from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence
from tradingagents.utils import get_i18n

logger = logging.getLogger(__name__)

_API = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"


def _created_at(message) -> datetime | None:
    raw = message.get("created_at")
    if not raw:
        return None
    with contextlib.suppress(ValueError, TypeError):
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return None


def _within_window(messages, start_date, end_date):
    if not (start_date and end_date):
        return messages
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    return [m for m in messages if _in_window(_created_at(m), start_dt, end_dt)]


def _created_at(message) -> datetime | None:
    raw = message.get("created_at")
    if not raw:
        return None
    with contextlib.suppress(ValueError, TypeError):
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return None


def _in_window(created, start_dt, end_dt):
    if created is None:
        return False
    return start_dt <= created <= end_dt


def _body(message) -> str:
    return html.unescape(message.get("body") or "")


def _stocktwits_symbol(ticker: str) -> str:
    """Map a crypto pair to StockTwits' <BASE>.X convention."""
    base = crypto_base(ticker)
    return f"{base}.X" if base else ticker.strip().upper()


def crypto_base(ticker: str) -> str | None:
    if not isinstance(ticker, str):
        return None
    compact = ticker.strip().upper().rstrip("+").replace("-", "")
    for quote in ("USDT", "USDC", "USD"):
        if compact.endswith(quote):
            base = compact[: -len(quote)]
            return base if base in {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "BCH", "DOT", "AVAX", "LINK"} else None
    return None


class StockTwitsSocialProvider:
    """StockTwits social sentiment provider."""
    
    provider_id = "stocktwits_social"
    provides = {"sentiment_social_stocktwits"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        self.limit = kwargs.get("limit", 30)
        self.timeout = kwargs.get("timeout", 10.0)

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        i18n = get_i18n()
        results = []
        ticker = req.ticker
        
        st_symbol = _stocktwits_symbol(ticker)
        url = _API.format(ticker=st_symbol)
        req_obj = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
        
        start_date = req.params.get("start_date")
        end_date = req.params.get("end_date")
        
        try:
            with urlopen(req_obj, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("StockTwits fetch failed for %s: %s", ticker, exc)
            return [RawEvidence(
                evidence_type="sentiment_social_stocktwits",
                provider=self.provider_id,
                method="stocktwits_api",
                params=req.params,
                summary=f"<stocktwits unavailable: {type(exc).__name__}>",
                raw_payload={"error": str(exc)}
            )]
        
        fetched = data.get("messages", []) if isinstance(data, dict) else []
        messages = _within_window(fetched, start_date, end_date)
        
        if not messages:
            if start_date and end_date:
                return [RawEvidence(
                    evidence_type="sentiment_social_stocktwits",
                    provider=self.provider_id,
                    method="stocktwits_api",
                    params=req.params,
                    summary=f"<no StockTwits messages for ${ticker.upper()} within {start_date}..{end_date}>",
                    raw_payload={"messages": []}
                )]
            return [RawEvidence(
                evidence_type="sentiment_social_stocktwits",
                provider=self.provider_id,
                method="stocktwits_api",
                params=req.params,
                summary=f"<no StockTwits messages found for ${ticker.upper()}>",
                raw_payload={"messages": []}
            )]
        
        # Apply screening if available
        screen = req.params.get("screen")
        note = ""
        if screen:
            keep, note = screen([_body(m) for m in messages])
            messages = [m for m, kept in zip(messages, keep, strict=True) if kept]
        
        lines = []
        bullish = bearish = unlabeled = 0
        for m in messages[:self.limit]:
            created = m.get("created_at", "")
            user = (m.get("user") or {}).get("username", "?")
            entities = m.get("entities") or {}
            sentiment_obj = entities.get("sentiment") or {}
            sentiment = sentiment_obj.get("basic") if isinstance(sentiment_obj, dict) else None
            body = _body(m).replace("\n", " ").strip()
            if len(body) > 280:
                body = body[:280] + "…"
            
            if sentiment == "Bullish":
                bullish += 1
                tag = "Bullish"
            elif sentiment == "Bearish":
                bearish += 1
                tag = "Bearish"
            else:
                unlabeled += 1
                tag = "no-label"
            lines.append(f"[{created} · @{user} · {tag}] {body}")
        
        total = bullish + bearish + unlabeled
        bull_pct = round(100 * bullish / total) if total else 0
        bear_pct = round(100 * bearish / total) if total else 0
        summary = (
            f"Bullish: {bullish} ({bull_pct}%) · "
            f"Bearish: {bearish} ({bear_pct}%) · "
            f"Unlabeled: {unlabeled} · "
            f"Total: {total} most-recent messages"
        )
        
        content = (f"{note}\n\n" if note else "") + summary + "\n\n" + "\n".join(lines)
        
        return [RawEvidence(
            evidence_type="sentiment_social_stocktwits",
            provider=self.provider_id,
            method="stocktwits_api",
            params={"limit": self.limit},
            summary=f"StockTwits messages for ${ticker.upper()}: {bullish} bullish, {bearish} bearish, {unlabeled} unlabeled",
            raw_payload={
                "content": content,
                "bullish": bullish,
                "bearish": bearish,
                "unlabeled": unlabeled,
                "total": total,
                "bullish_pct": bull_pct,
                "bearish_pct": bear_pct,
            }
        )]


StockTwitsSocialProvider = StockTwitsSocialProvider