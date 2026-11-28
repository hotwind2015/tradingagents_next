"""Alpha Vantage Technical Indicators Provider.

Provides:
- market_indicators: Technical indicators from Alpha Vantage API
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from dateutil.relativedelta import relativedelta

from tradingagents.providers.alpha_vantage._common import (
    _make_api_request,
    AlphaVantageNotConfiguredError,
    AlphaVantageRateLimitError,
)
from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence
from tradingagents.utils import get_i18n

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Alpha Vantage indicator endpoint mapping
INDICATOR_API_MAP = {
    "close_50_sma": {"function": "SMA", "time_period": "50", "column": "SMA"},
    "close_200_sma": {"function": "SMA", "time_period": "200", "column": "SMA"},
    "close_10_ema": {"function": "EMA", "time_period": "10", "column": "EMA"},
    "macd": {"function": "MACD", "column": "MACD"},
    "macds": {"function": "MACD", "column": "MACD_Signal"},
    "macdh": {"function": "MACD", "column": "MACD_Hist"},
    "rsi": {"function": "RSI", "column": "RSI"},
    "boll": {"function": "BBANDS", "time_period": "20", "column": "Real Middle Band"},
    "boll_ub": {"function": "BBANDS", "time_period": "20", "column": "Real Upper Band"},
    "boll_lb": {"function": "BBANDS", "time_period": "20", "column": "Real Lower Band"},
    "atr": {"function": "ATR", "column": "ATR"},
    "vwma": {"function": "VWMA", "column": "VWMA"},
}

# Indicator descriptions (migrated from original alpha_vantage/indicator.py)
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
}


class AlphaVantageIndicatorProvider:
    """Alpha Vantage Technical Indicators Provider.

    provider_id = "alpha_vantage_indicators"
    provides = {"market_indicators"}
    """

    provider_id = "alpha_vantage_indicators"
    provides = {"market_indicators"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        self.default_time_period = kwargs.get("time_period", 14)
        self.default_interval = kwargs.get("interval", "daily")
        self.default_series_type = kwargs.get("series_type", "close")

    def fetch(self, req: DataRequest) -> list:
        i18n = get_i18n()
        results = []

        symbol = req.ticker
        indicators = req.params.get("indicator", list(INDICATOR_API_MAP.keys()))
        as_of_date = req.params.get("as_of_date", datetime.now().strftime("%Y-%m-%d"))
        look_back_days = req.params.get("look_back_days", 30)
        interval = req.params.get("interval", self.default_interval)
        time_period = req.params.get("time_period", self.default_time_period)
        series_type = req.params.get("series_type", self.default_series_type)

        indicator_list = indicators if isinstance(indicators, list) else [indicators]

        results = []
        for ind in indicator_list:
            if ind not in INDICATOR_API_MAP:
                logger.warning(f"Indicator {ind} not supported by Alpha Vantage, skipping")
                continue

            config = INDICATOR_API_MAP[ind]
            desc = INDICATOR_DESCRIPTIONS.get(ind, "No description available.")

            try:
                indicator_data = self._fetch_single_indicator(
                    symbol, ind, as_of_date, look_back_days, interval, time_period, series_type
                )

                if not indicator_data:
                    logger.warning(f"No data returned for indicator {ind}")
                    continue

                # Format indicator data for storage
                ind_string = "\n".join(f"{d}: {v}" for d, v in indicator_data)
                desc = INDICATOR_DESCRIPTIONS.get(ind, "No description available.")

                summary = f"{ind.upper()} values from {before.strftime('%Y-%m-%d')} to {as_of_date}"

                results.append(RawEvidence(
                    evidence_type="market_indicators",
                    provider=self.provider_id,
                    method="alpha_vantage_native",
                    params={
                        "indicator": ind,
                        "as_of_date": as_of_date,
                        "look_back_days": look_back_days,
                        "interval": interval,
                        "time_period": time_period,
                        "series_type": series_type,
                    },
                    summary=summary,
                    raw_payload={
                        "indicator": ind,
                        "values": indicator_data,
                        "as_of_date": as_of_date,
                        "look_back_days": look_back_days,
                        "description": desc,
                    }
                ))

            except Exception as e:
                logger.warning(f"Failed to fetch indicator {ind} from Alpha Vantage: {e}")
                # Return error evidence instead of failing completely
                results.append(RawEvidence(
                    evidence_type="market_indicators",
                    provider=self.provider_id,
                    method="alpha_vantage_native",
                    params={"indicator": ind, "as_of_date": as_of_date},
                    summary=f"{ind} fetch failed: {e}",
                    raw_payload={
                        "indicator": ind,
                        "error": str(e),
                        "as_of_date": as_of_date,
                    }
                ))

        return results

    def _fetch_single_indicator(
        self,
        symbol: str,
        indicator: str,
        as_of_date: str,
        look_back_days: int,
        interval: str,
        time_period: int,
        series_type: str,
    ) -> dict:
        """Fetch a single indicator from Alpha Vantage API."""
        api_config = INDICATOR_API_MAP[indicator]

        params = {
            "symbol": symbol,
            "interval": interval,
            "series_type": series_type,
            "datatype": "csv",
        }

        # Add time_period if required
        if "time_period" in api_config:
            params["time_period"] = api_config["time_period"]
        elif indicator in ("rsi", "atr", "vwma"):
            params["time_period"] = str(time_period)

        # Make API request
        response = _make_api_request(api_config["function"], params)

        # Parse CSV response
        lines = response.strip().split('\n')
        if len(lines) < 2:
            return {}

        header = [col.strip() for col in lines[0].split(',')]
        try:
            date_col_idx = header.index('time')
        except ValueError:
            logger.warning(f"'time' column not found in data for {indicator}. Available columns: {header}")
            return {}

        target_col_name = api_config["column"]
        try:
            value_col_idx = header.index(target_col_name)
        except ValueError:
            logger.warning(f"Column '{target_col_name}' not found for indicator '{indicator}'. Available columns: {header}")
            return {}

        as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
        before = as_of_dt - relativedelta(days=look_back_days)

        result_data = []
        for line in lines[1:]:
            if not line.strip():
                continue
            values = line.split(',')
            if len(values) > max(date_col_idx, value_col_idx):
                try:
                    date_str = values[date_col_idx].strip()
                    date_dt = datetime.strptime(date_str, "%Y-%m-%d")

                    if before <= date_dt <= as_of_dt:
                        value = values[value_col_idx].strip()
                        result_data.append((date_dt, value))
                except (ValueError, IndexError):
                    continue

        # Sort by date
        result_data.sort(key=lambda x: x[0])
        return {d.strftime('%Y-%m-%d'): v for d, v in result_data}


AlphaVantageIndicatorProvider = AlphaVantageIndicatorProvider