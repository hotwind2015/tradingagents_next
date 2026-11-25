"""YFinance K-line and Technical Indicators Provider.

Provides:
- market_raw_kline: Raw OHLCV data from Yahoo Finance
- market_indicators: Technical indicators computed via stockstats
"""

from __future__ import annotations

import logging
import re
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
# Indicator descriptions (migrated from original market_analyst.py)
# =============================================================================

INDICATOR_DESCRIPTIONS = {
    "close_50_sma": (
        "50 SMA: A medium-term trend indicator. "
        "Usage: Identify trend direction and serve as dynamic support/resistance. "
        "Tips: It lags price; combine with faster indicators for timely signals."
    ),
    "close_200_sma": (
        "200 SMA: A long-term trend benchmark. "
        "Usage: Confirm overall market trend and identify golden/death cross setups. "
        "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
    ),
    "close_10_ema": (
        "10 EMA: A responsive short-term average. "
        "Usage: Capture quick shifts in momentum and potential entry points. "
        "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
    ),
    "macd": (
        "MACD: Computes momentum via differences of EMAs. "
        "Usage: Look for crossovers and divergence as signals of trend changes. "
        "Tips: Confirm with other indicators in low-volatility or sideways markets."
    ),
    "macds": (
        "MACD Signal: An EMA smoothing of the MACD line. "
        "Usage: Use crossovers with the MACD line to trigger trades. "
        "Tips: Should be part of a broader strategy to avoid false positives."
    ),
    "macdh": (
        "MACD Histogram: Shows the gap between the MACD line and its signal. "
        "Usage: Visualize momentum strength and spot divergence early. "
        "Tips: Can be volatile; complement with additional filters in fast-moving markets."
    ),
    "rsi": (
        "RSI: Measures momentum to flag overbought/oversold conditions. "
        "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
        "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
    ),
    "boll": (
        "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
        "Usage: Acts as a dynamic benchmark for price movement. "
        "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
    ),
    "boll_ub": (
        "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
        "Usage: Signals potential overbought conditions and breakout zones. "
        "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
    ),
    "boll_lb": (
        "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
        "Usage: Indicates potential oversold conditions. "
        "Tips: Use additional analysis to avoid false reversal signals."
    ),
    "atr": (
        "ATR: Averages true range to measure volatility. "
        "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
        "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
    ),
    "vwma": (
        "VWMA: A moving average weighted by volume. "
        "Usage: Confirm trends by integrating price action with volume data. "
        "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
    ),
    "mfi": (
        "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure. "
        "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends or reversals. "
        "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate potential reversals."
    ),
}


def _yf_retry(func, max_retries=3):
    """Retry yfinance calls on transient failures."""
    import time
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)


def _raise_for_empty(symbol, canonical, what):
    raise NoMarketDataError(symbol, canonical, f"no {what}")


def _assert_ohlcv_not_stale(data, as_of_date, symbol, canonical, max_stale_days=10):
    if data is None or data.empty:
        return
    requested = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(requested):
        return
    requested = requested.normalize()
    dates = data.index if isinstance(data.index, pd.DatetimeIndex) else pd.to_datetime(data.get("Date", pd.Series()), errors="coerce").dropna()
    if dates.empty:
        return
    latest = dates.max().normalize()
    stale_days = (requested - latest).days
    if stale_days > max_stale_days:
        raise NoMarketDataError(
            symbol,
            canonical,
            f"latest row is {latest.date()}, {stale_days} days before the requested {requested.date()} (stale)",
        )


class YFinanceKlineProvider:
    """Yahoo Finance K-line and indicators provider."""
    
    provider_id = "yfinance_kline"
    provides = {"market_raw_kline", "market_indicators"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        # Accept provider_args from recipe (e.g., indicator list, look_back_days)
        self.default_indicators = kwargs.get("indicator", [
            "rsi", "macd", "close_50_sma", "close_200_sma", "close_10_ema",
            "boll", "boll_ub", "boll_lb", "atr", "vwma", "mfi"
        ])
        self.default_look_back_days = kwargs.get("look_back_days", 30)

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        i18n = get_i18n()
        results = []
        canonical = normalize_symbol(req.ticker)
        
        if req.evidence_type == "market_raw_kline":
            # Fetch raw OHLCV data
            start_date = req.params.get("start_date", (datetime.now() - relativedelta(years=1)).strftime("%Y-%m-%d"))
            end_date = req.params.get("end_date", datetime.now().strftime("%Y-%m-%d"))
            
            # yfinance treats end as EXCLUSIVE
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            end_inclusive = (end_dt + relativedelta(days=1)).strftime("%Y-%m-%d")
            
            data = _yf_retry(lambda: yf.Ticker(canonical).history(start=start_date, end=end_inclusive))
            
            if data is None or data.empty:
                _raise_for_empty(req.ticker, canonical, f"rows between {start_date} and {end_date}")
            
            if data.index.tz is not None:
                data.index = data.index.tz_localize(None)
            
            _assert_ohlcv_not_stale(data, end_date, req.ticker, canonical)
            
            for col in ("Open", "High", "Low", "Close", "Adj Close"):
                if col in data.columns:
                    data[col] = data[col].map(self._price_text, na_action="ignore")
            
            csv_string = data.to_csv()
            label = canonical if canonical == req.ticker.upper() else f"{canonical} (from {req.ticker})"
            header = f"# Stock data for {label} from {start_date} to {end_date}\n"
            header += f"# Total records: {len(data)}\n\n"
            
            summary = i18n.t(
                "providers.yfinance.kline.market_summary",
                ticker=req.ticker,
                close=float(data['Close'].iloc[-1]),
                pct_change=((float(data['Close'].iloc[-1]) - float(data['Close'].iloc[-2])) / float(data['Close'].iloc[-2]) * 100) if len(data) > 1 else 0.0,
            )
            
            results.append(RawEvidence(
                evidence_type="market_raw_kline",
                provider=self.provider_id,
                method="yf_history",
                params={"start_date": start_date, "end_date": end_date},
                summary=summary,
                raw_payload={
                    "csv": header + csv_string,
                    "records": len(data),
                    "start_date": start_date,
                    "end_date": end_date,
                }
            ))
            
        elif req.evidence_type == "market_indicators":
            # Fetch technical indicators
            indicator = req.params.get("indicator", self.default_indicators)
            as_of_date = req.params.get("as_of_date", datetime.now().strftime("%Y-%m-%d"))
            look_back_days = req.params.get("look_back_days", self.default_look_back_days)
            
            # Support multiple indicators
            indicators = indicator if isinstance(indicator, list) else [indicator]
            
            for ind in indicators:
                try:
                    indicator_data = self._get_stock_stats_bulk(req.ticker, ind, as_of_date)
                    
                    end_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
                    before = end_dt - relativedelta(days=look_back_days)
                    
                    current_dt = end_dt
                    date_values = []
                    
                    while current_dt >= before:
                        date_str = current_dt.strftime('%Y-%m-%d')
                        if date_str in indicator_data:
                            indicator_value = indicator_data[date_str]
                        else:
                            indicator_value = "N/A: Not a trading day (weekend or holiday)"
                        date_values.append((date_str, indicator_value))
                        current_dt = current_dt - relativedelta(days=1)
                    
                    ind_string = "\n".join(f"{d}: {v}" for d, v in date_values)
                    
                    desc = INDICATOR_DESCRIPTIONS.get(ind, "No description available.")
                    
                    results.append(RawEvidence(
                        evidence_type="market_indicators",
                        provider=self.provider_id,
                        method="stockstats",
                        params={"indicator": ind, "as_of_date": as_of_date, "look_back_days": look_back_days},
                        summary=f"{ind} values from {before.strftime('%Y-%m-%d')} to {as_of_date}",
                        raw_payload={
                            "indicator": ind,
                            "values": {d: v for d, v in date_values},
                            "as_of_date": as_of_date,
                            "look_back_days": look_back_days,
                            "description": desc,
                        }
                    ))
                except Exception as e:
                    logger.warning(f"Failed to fetch indicator {ind}: {e}")
                    # Continue with other indicators
        
        return results

    def _get_stock_stats_bulk(self, symbol: str, indicator: str, as_of_date: str) -> dict:
        """Optimized bulk calculation of stock stats indicators."""
        data = self._load_ohlcv(symbol, as_of_date)
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

        df[indicator]  # This triggers stockstats to calculate the indicator

        result_dict = {}
        for _, row in df.iterrows():
            date_str = row["Date"]
            indicator_value = row[indicator]
            if pd.isna(indicator_value):
                result_dict[date_str] = "N/A"
            else:
                result_dict[date_str] = str(indicator_value)
        return result_dict

    def _load_ohlcv(self, symbol: str, as_of_date: str) -> pd.DataFrame:
        """Load OHLCV data with caching (simplified version)."""
        canonical = normalize_symbol(symbol)
        data = _yf_retry(lambda: yf.Ticker(canonical).history(period="5y", auto_adjust=True, actions=False))
        if data is None or data.empty:
            _raise_for_empty(symbol, canonical, "price rows")
        data = data.reset_index()
        data.columns = [c.capitalize() for c in data.columns]
        return data

    def _price_text(self, value) -> str:
        if pd.isna(value):
            return ""
        return f"{value:.2f}"


def _yf_retry(func, max_retries=3):
    """Retry yfinance calls on transient failures."""
    import time
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)


def _raise_for_empty(symbol, canonical, what):
    raise NoMarketDataError(symbol, canonical, f"no {what}")


def _assert_ohlcv_not_stale(data, as_of_date, symbol, canonical, max_stale_days=10):
    if data is None or data.empty:
        return
    requested = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(requested):
        return
    requested = requested.normalize()
    dates = data.index if isinstance(data.index, pd.DatetimeIndex) else pd.to_datetime(data.get("Date", pd.Series()), errors="coerce").dropna()
    if dates.empty:
        return
    latest = dates.max().normalize()
    stale_days = (requested - latest).days
    if stale_days > max_stale_days:
        raise NoMarketDataError(
            symbol,
            canonical,
            f"latest row is {latest.date()}, {stale_days} days before the requested {requested.date()} (stale)",
        )


YFinanceKlineProvider = YFinanceKlineProvider