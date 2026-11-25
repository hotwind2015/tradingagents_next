"""YFinance Verified Market Snapshot Provider.

Provides deterministic ground-truth snapshot for market data verification.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import pandas as pd
import yfinance as yf
from dateutil.relativedelta import relativedelta
from stockstats import wrap

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


class NoMarketDataError(VendorError):
    """A vendor returned no usable rows for a symbol (empty result or stale data)."""

    def __init__(self, symbol: str, canonical: str | None = None, detail: str = ""):
        self.symbol = symbol
        self.canonical = canonical or symbol
        self.detail = detail
        msg = f"No market data for {symbol!r}"
        if canonical and canonical != symbol:
            msg += f" (queried as {canonical!r})"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


# =============================================================================
# Fixed indicator set for consistent snapshot shape
# =============================================================================

DEFAULT_SNAPSHOT_INDICATORS: tuple[str, ...] = (
    "close_10_ema", "close_50_sma", "close_200_sma",
    "rsi", "boll", "boll_ub", "boll_lb",
    "macd", "macds", "macdh", "atr",
)


def _fmt(value) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _yf_retry(func, max_retries=3):
    import time
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)


def _load_ohlcv(symbol: str, as_of_date: str, fill_gaps: bool = True) -> pd.DataFrame:
    """Fetch OHLCV data with caching, filtered to prevent look-ahead bias."""
    canonical = normalize_symbol(symbol)
    # Parse as naive datetime (no timezone)
    as_of_dt = pd.to_datetime(as_of_date).normalize()
    
    # Download 5 years of data
    now = pd.Timestamp.today().tz_localize(None)  # Make naive
    start_date = now - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = (now + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    
    data = _yf_retry(lambda: yf.Ticker(canonical).history(
        start=start_str,
        end=end_str,
        auto_adjust=True,
        actions=False,
    ))
    if data is None or data.empty or "Close" not in data.columns:
        raise NoMarketDataError(symbol, canonical, "price rows")
    
    data = data.reset_index()
    data.columns = [c.capitalize() for c in data.columns]
    
    # Normalize dates - strip timezone to make naive for comparison
    if data["Date"].dt.tz is not None:
        data["Date"] = data["Date"].dt.tz_localize(None)
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"])
    data = data[data["Date"] <= as_of_dt].sort_values("Date")
    
    if data.empty:
        raise NoMarketDataError(symbol, canonical, f"no price rows on or before {as_of_date}")
    
    if fill_gaps:
        price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
        data = data.dropna(subset=["Close"]).copy()
        data[price_cols] = data[price_cols].ffill().bfill()
    
    return data


class YFinanceSnapshotProvider:
    """Yahoo Finance verified market snapshot provider."""
    
    provider_id = "yfinance_snapshot"
    provides = {"market_verified_snapshot"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        # Accept provider_args from recipe
        self.default_look_back_days = kwargs.get("look_back_days", 30)
        self.default_indicators = kwargs.get("indicators", DEFAULT_SNAPSHOT_INDICATORS)

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        i18n = get_i18n()
        results = []
        
        symbol = req.ticker
        as_of_date = req.params.get("as_of_date", datetime.now().strftime("%Y-%m-%d"))
        look_back_days = req.params.get("look_back_days", 30)
        indicators = req.params.get("indicators", DEFAULT_SNAPSHOT_INDICATORS)
        
        try:
            df = _load_ohlcv(symbol, as_of_date, fill_gaps=False)
            stock_df = wrap(df.copy())

            selected = tuple(indicators) if indicators else self.default_indicators
            indicator_values: dict[str, str] = {}
            for name in selected:
                try:
                    stock_df[name]
                    indicator_values[name] = _fmt(stock_df.iloc[-1][name])
                except Exception as exc:
                    indicator_values[name] = f"N/A ({type(exc).__name__})"

            latest = df.iloc[-1]
            latest_date = _fmt(latest["Date"])
            window = max(1, min(int(look_back_days), 30))
            recent = df.tail(window)

            lines = [
                f"## Verified market data snapshot for {symbol.upper()}",
                "",
                f"- Requested analysis date: {as_of_date}",
                f"- Latest trading row used: {latest_date}",
                "- Rows after the requested analysis date are excluded before verification.",
                "",
                "### Latest verified OHLCV row",
                "",
                "| Field | Value |",
                "|---|---:|",
            ]
            for field in ("Open", "High", "Low", "Close", "Volume"):
                lines.append(f"| {field} | {_fmt(latest.get(field))} |")

            lines += ["", "### Verified technical indicators (latest row)", "",
                      "| Indicator | Value |", "|---|---:|"]
            for name, value in indicator_values.items():
                lines.append(f"| {name} | {value} |")

            lines += ["", f"### Recent verified closes (last {len(recent)} rows)", "",
                      "| Date | Close |", "|---|---:|"]
            for _, row in recent.iterrows():
                lines.append(f"| {_fmt(row['Date'])} | {_fmt(row.get('Close'))} |")

            lines += [
                "",
                "Use this snapshot as the source of truth for exact OHLCV, price-level, "
                "and indicator-value claims. If another tool output conflicts with it, "
                "flag the discrepancy rather than inventing a reconciled number. Do not "
                "claim historical validation, support/resistance bounces, or exact "
                "percentage moves unless directly supported by tool output with concrete "
                "dates and prices.",
            ]
            
            snapshot_text = "\n".join(lines)
            
            summary = f"Verified snapshot for {symbol} as of {as_of_date} (latest row: {latest_date})"
            
            results.append(RawEvidence(
                evidence_type="market_verified_snapshot",
                provider=self.provider_id,
                method="verified_snapshot",
                params={"as_of_date": as_of_date, "look_back_days": look_back_days, "indicators": list(selected)},
                summary=summary,
                raw_payload={
                    "snapshot": snapshot_text,
                    "latest_date": latest_date,
                    "indicators": indicator_values,
                    "recent_closes": {_fmt(row['Date']): _fmt(row.get('Close')) for _, row in recent.iterrows()},
                }
            ))
            
        except Exception as e:
            logger.error(f"Failed to build verified snapshot for {symbol}: {e}")
            raise
        
        return results


YFinanceSnapshotProvider = YFinanceSnapshotProvider