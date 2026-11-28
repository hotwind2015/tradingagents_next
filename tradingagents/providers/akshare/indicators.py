"""AKShare Technical Indicators Provider.

Provides:
- market_indicators: Technical indicators computed locally from kline data

This provider computes indicators locally using stockstats/pandas-ta
based on kline data from other providers (akshare_kline, yfinance_kline, etc.)
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import pandas as pd

from tradingagents.providers.akshare._common import (
    ensure_numeric,
    get_provider_i18n_key,
    t_provider,
)
from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence
from tradingagents.utils import get_i18n

logger = logging.getLogger(__name__)

# =============================================================================
# Indicator Configuration
# =============================================================================

# Supported indicators and their parameters
INDICATOR_CONFIG = {
    # Trend indicators
    "close_50_sma": {"func": "sma", "window": 50, "col": "close"},
    "close_200_sma": {"func": "sma", "window": 200, "col": "close"},
    "close_10_ema": {"func": "ema", "window": 10, "col": "close"},
    "close_20_ema": {"func": "ema", "window": 20, "col": "close"},
    "close_50_ema": {"func": "ema", "window": 50, "col": "close"},

    # Momentum indicators
    "rsi": {"func": "rsi", "window": 14, "col": "close"},
    "rsi_6": {"func": "rsi", "window": 6, "col": "close"},
    "rsi_24": {"func": "rsi", "window": 24, "col": "close"},

    # MACD
    "macd": {"func": "macd", "fast": 12, "slow": 26, "signal": 9, "col": "close"},
    "macds": {"func": "macd_signal", "fast": 12, "slow": 26, "signal": 9, "col": "close"},
    "macdh": {"func": "macd_hist", "fast": 12, "slow": 26, "signal": 9, "col": "close"},

    # Bollinger Bands
    "boll": {"func": "boll_mid", "window": 20, "std": 2, "col": "close"},
    "boll_ub": {"func": "boll_upper", "window": 20, "std": 2, "col": "close"},
    "boll_lb": {"func": "boll_lower", "window": 20, "std": 2, "col": "close"},

    # Volatility
    "atr": {"func": "atr", "window": 14, "col": None},  # Uses high, low, close
    "atr_14": {"func": "atr", "window": 14, "col": None},

    # Volume indicators
    "vwma": {"func": "vwma", "window": 20, "col": "close"},  # Volume-weighted MA
    "mfi": {"func": "mfi", "window": 14, "col": None},  # Money Flow Index

    # Other
    "cci": {"func": "cci", "window": 20, "col": None},  # Commodity Channel Index
    "adx": {"func": "adx", "window": 14, "col": None},  # Average Directional Index
}

# Indicator descriptions for summaries
INDICATOR_DESCRIPTIONS = {
    "close_50_sma": "50 SMA: Medium-term trend indicator. Usage: Identify trend direction and dynamic support/resistance.",
    "close_200_sma": "200 SMA: Long-term trend benchmark. Usage: Confirm overall trend and golden/death cross setups.",
    "close_10_ema": "10 EMA: Responsive short-term average. Usage: Capture quick momentum shifts.",
    "close_20_ema": "20 EMA: Short-term trend indicator. Usage: Trend confirmation and dynamic support/resistance.",
    "close_50_ema": "50 EMA: Medium-term EMA. Usage: Smoother trend tracking than SMA.",
    "rsi": "RSI: Momentum oscillator. Usage: 70/30 overbought/oversold, divergence signals.",
    "rsi_6": "RSI(6): Fast RSI for short-term momentum.",
    "rsi_24": "RSI(24): Slower RSI for trend confirmation.",
    "macd": "MACD: Trend-following momentum. Usage: Crossovers, divergence, histogram.",
    "macds": "MACD Signal: Smoothed MACD line. Usage: Crossover signals.",
    "macdh": "MACD Histogram: MACD - Signal. Usage: Momentum strength visualization.",
    "boll": "Bollinger Middle: 20 SMA basis. Usage: Trend basis for bands.",
    "boll_ub": "Bollinger Upper: +2 std dev. Usage: Overbought/breakout signals.",
    "boll_lb": "Bollinger Lower: -2 std dev. Usage: Oversold/bounce signals.",
    "atr": "ATR: Average True Range. Usage: Volatility measure, stop-loss setting.",
    "vwma": "VWMA: Volume-weighted MA. Usage: Volume-confirmed trend.",
    "mfi": "MFI: Money Flow Index. Usage: Volume-weighted RSI, divergence.",
    "cci": "CCI: Commodity Channel Index. Usage: Cyclical turns, overbought/oversold.",
    "adx": "ADX: Average Directional Index. Usage: Trend strength (not direction).",
}


class AKShareIndicatorsProvider:
    """AKShare Technical Indicators Provider.

    Computes technical indicators locally from kline data.
    Does not fetch from external API - computes locally using stockstats.

    provider_id = "akshare_indicators"
    provides = {"market_indicators"}
    """

    provider_id = "akshare_indicators"
    provides = {"market_indicators"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        self.default_look_back_days = kwargs.get("look_back_days", 30)
        self.default_indicators = kwargs.get("indicators", list(INDICATOR_CONFIG.keys()))

    def fetch(self, req: DataRequest) -> list:
        """Fetch/compute technical indicators from kline data.

        This provider computes indicators locally using stockstats
        based on kline data from other providers (akshare_kline, yfinance_kline, etc.)
        """
        symbol = req.ticker
        indicators = req.params.get("indicator", self.default_indicators)
        as_of_date = req.params.get("as_of_date", "auto")
        look_back_days = req.params.get("look_back_days", self.default_look_back_days)

        # Get kline data from params or fetch from akshare_kline provider
        kline_df = self._get_kline_data(req)

        indicator_list = indicators if isinstance(indicators, list) else [indicators]

        results = []
        for ind in indicator_list:
            if ind not in INDICATOR_CONFIG:
                logger.warning(f"Indicator {ind} not supported, skipping")
                continue

            config = INDICATOR_CONFIG[ind]
            desc = INDICATOR_DESCRIPTIONS.get(ind, "No description available.")

            # Compute the actual indicator values
            indicator_values = self._compute_indicator(ind, kline_df, look_back_days)

            # Prepare the actual indicator data for storage
            indicator_data = self._format_indicator_data(ind, indicator_values)

            results.append(RawEvidence(
                evidence_type="market_indicators",
                provider=self.provider_id,
                method="local_computation",
                params={
                    "indicator": ind,
                    "as_of_date": as_of_date,
                    "look_back_days": look_back_days,
                    "config": config,
                },
                summary=f"{ind} values computed locally (last {look_back_days} days)",
                raw_payload={
                    "indicator": ind,
                    "config": config,
                    "description": desc,
                    "as_of_date": as_of_date,
                    "look_back_days": look_back_days,
                    "values": indicator_data,  # Store actual computed values
                }
            )
        )
        return results

    def _get_kline_data(self, req: DataRequest) -> pd.DataFrame:
        """Get kline data for indicator computation."""
        # Try to get kline data from request params first
        kline_data = req.params.get("kline_data")
        if kline_data is not None:
            return pd.DataFrame(kline_data)

        # Otherwise, fetch from akshare_kline provider
        try:
            from tradingagents.providers.akshare.kline import AKShareKlineProvider
            kline_provider = AKShareKlineProvider(
                look_back_days=req.params.get("look_back_days", self.default_look_back_days),
                adjust=req.params.get("adjust", "qfq")
            )
            from tradingagents.providers.base import DataRequest
            from datetime import datetime
            
            kline_req = DataRequest(
                evidence_type="market_raw_kline",
                ticker=req.ticker,
                params={
                    "start_date": req.params.get("start_date", (datetime.now() - timedelta(days=self.default_look_back_days)).strftime("%Y-%m-%d")),
                    "end_date": req.params.get("end_date", datetime.now().strftime("%Y-%m-%d")),
                    "adjust": "qfq",
                    "period": "daily"
                },
                as_of=datetime.now().date()
            )
            results = kline_provider.fetch(kline_req)
            if results:
                # Get the raw payload from the first result
                raw_payload = results[0].raw_payload
                if "sample" in raw_payload:
                    return pd.DataFrame(raw_payload["sample"])
        except Exception as e:
            logger.warning(f"Failed to fetch kline data for indicators: {e}")

        return pd.DataFrame()

    def _compute_indicator(self, indicator: str, df: pd.DataFrame, look_back_days: int) -> pd.Series:
        """Compute a single indicator from kline data."""
        if df.empty:
            return pd.Series(dtype=float)

        # Use the existing compute function
        indicator_dict = compute_indicators_from_kline(df, [indicator])
        if indicator in indicator_dict:
            return indicator_dict[indicator]
        return pd.Series(dtype=float)

    def _format_indicator_data(self, indicator: str, values: pd.Series) -> dict:
        """Format indicator values for JSON storage as a mapping (date -> value)."""
        if values.empty:
            return {}

        # Convert Series to mapping {date -> value}
        data = {}
        for date, value in values.items():
            if pd.notna(value):
                date_str = date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date)
                data[date_str] = float(value)
        return data


# For backward compatibility and actual computation in context
def compute_indicators_from_kline(df: pd.DataFrame, indicators: list[str]) -> dict[str, pd.Series]:
    """Compute technical indicators from kline DataFrame.

    Args:
        df: K-line DataFrame with columns [date, open, high, low, close, volume]
        indicators: List of indicator names to compute

    Returns:
        Dictionary mapping indicator name to pandas Series
    """
    try:
        import stockstats
    except ImportError:
        logger.warning("stockstats not installed, cannot compute indicators")
        return {}

    if df.empty:
        return {}

    # Ensure required columns
    required = ["open", "high", "low", "close", "volume"]
    for col in required:
        if col not in df.columns:
            logger.warning(f"Missing required column: {col}")
            return {}

    # Create stockstats wrapper
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()

    stock = stockstats.StockDataFrame.retype(df)

    results = {}
    for ind in indicators:
        if ind not in INDICATOR_CONFIG:
            continue

        config = INDICATOR_CONFIG[ind]
        func_name = config["func"]

        try:
            if func_name == "sma":
                window = config["window"]
                col = config["col"]
                results[ind] = stock[f"close_{window}_sma"]

            elif func_name == "ema":
                window = config["window"]
                col = config["col"]
                results[ind] = stock[f"close_{window}_ema"]

            elif func_name == "rsi":
                window = config.get("window", 14)
                results[ind] = stock[f"rsi_{window}"]

            elif func_name == "macd":
                results["macd"] = stock["macd"]
                results["macds"] = stock["macds"]
                results["macdh"] = stock["macdh"]

            elif func_name == "macd_signal":
                results[ind] = stock["macds"]

            elif func_name == "macd_hist":
                results[ind] = stock["macdh"]

            elif func_name in ("boll_mid", "boll_upper", "boll_lower"):
                window = config.get("window", 20)
                std = config.get("std", 2)
                if func_name == "boll_mid":
                    results[ind] = stock[f"boll_{window}"]
                elif func_name == "boll_upper":
                    results[ind] = stock[f"boll_ub_{window}"]
                elif func_name == "boll_lower":
                    results[ind] = stock[f"boll_lb_{window}"]

            elif func_name == "atr":
                window = config.get("window", 14)
                results[ind] = stock[f"atr_{window}"]

            elif func_name == "vwma":
                window = config.get("window", 20)
                results[ind] = stock[f"vwma_{window}"]

            elif func_name == "mfi":
                window = config.get("window", 14)
                results[ind] = stock[f"mfi_{window}"]

            elif func_name == "cci":
                window = config.get("window", 20)
                results[ind] = stock[f"cci_{window}"]

            elif func_name == "adx":
                window = config.get("window", 14)
                results[ind] = stock[f"adx_{window}"]

        except Exception as e:
            logger.warning(f"Failed to compute indicator {ind}: {e}")

    return results


# Module exports
AKShareIndicatorsProvider = AKShareIndicatorsProvider