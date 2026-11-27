"""Alpha Vantage K-line Provider (Free Tier).

Provides:
- market_raw_kline: Raw OHLCV data from Alpha Vantage TIME_SERIES_DAILY

Note: Free tier only supports TIME_SERIES_DAILY endpoint.
Technical indicators (SMA, EMA, MACD, RSI, etc.) require premium subscription.
For market_indicators, DataRouter will fall back to yfinance_kline.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd
from dateutil.relativedelta import relativedelta

from tradingagents.providers.alpha_vantage._common import (
    _filter_csv_by_date_range,
    _make_api_request,
    AlphaVantageNotConfiguredError,
    AlphaVantageRateLimitError,
)
from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence
from tradingagents.utils import get_i18n

logger = logging.getLogger(__name__)


class AlphaVantageKlineProvider:
    """Alpha Vantage K-line provider (free tier only supports TIME_SERIES_DAILY)."""

    provider_id = "alpha_vantage_kline"
    provides = {"market_raw_kline"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        """Initialize with provider_args from recipe (only used for raw kline)."""
        # Accept but ignore indicator-specific args since free tier doesn't support them
        self.default_look_back_days = kwargs.get("look_back_days", 30)

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        i18n = get_i18n()
        results = []

        if req.evidence_type == "market_raw_kline":
            results.extend(self._fetch_raw_kline(req))
        # market_indicators not supported on free tier - let DataRouter fall back to yfinance

        return results

    # -------------------------------------------------------------------------
    # market_raw_kline: TIME_SERIES_DAILY
    # -------------------------------------------------------------------------
    def _fetch_raw_kline(self, req: DataRequest) -> list[RawEvidence]:
        """Fetch raw OHLCV data from Alpha Vantage."""
        i18n = get_i18n()
        symbol = req.ticker
        start_date = req.params.get("start_date", (datetime.now() - relativedelta(years=1)).strftime("%Y-%m-%d"))
        end_date = req.params.get("end_date", datetime.now().strftime("%Y-%m-%d"))

        # Choose outputsize based on whether the requested range is within the latest 100 days
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        today = datetime.now()
        days_from_today_to_start = (today - start_dt).days
        outputsize = "compact" if days_from_today_to_start < 100 else "full"

        params = {
            "symbol": symbol,
            "outputsize": outputsize,
            "datatype": "csv",
        }

        try:
            # Use TIME_SERIES_DAILY for free tier (TIME_SERIES_DAILY_ADJUSTED is premium)
            response = _make_api_request("TIME_SERIES_DAILY", params)
            csv_data = _filter_csv_by_date_range(response, start_date, end_date)

            if not csv_data or csv_data.strip() == "":
                raise AlphaVantageRateLimitError(f"No data returned for {symbol}")

            # Parse CSV to get summary info
            df = pd.read_csv(pd.io.common.StringIO(csv_data))
            date_col = df.columns[0]
            df[date_col] = pd.to_datetime(df[date_col])

            latest_row = df.iloc[-1]
            prev_row = df.iloc[-2] if len(df) > 1 else latest_row

            # TIME_SERIES_DAILY returns 'close' column (not 'adjusted_close')
            close_val = float(latest_row.get("close", 0))
            prev_close = float(prev_row.get("close", 0))
            pct_change = ((close_val - prev_close) / prev_close * 100) if prev_close else 0.0

            # Generate summary using i18n
            summary = i18n.t(
                "providers.alpha_vantage.kline.market_summary",
                ticker=req.ticker,
                close=close_val,
                pct_change=pct_change,
            )

            return [RawEvidence(
                evidence_type="market_raw_kline",
                provider=self.provider_id,
                method="alpha_vantage_daily",
                params={"start_date": start_date, "end_date": end_date, "outputsize": outputsize},
                summary=summary,
                raw_payload={
                    "csv": csv_data,
                    "records": len(df),
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )]

        except (AlphaVantageNotConfiguredError, AlphaVantageRateLimitError):
            raise
        except Exception as e:
            logger.warning("Alpha Vantage raw kline fetch failed for %s: %s", symbol, e)
            raise


AlphaVantageKlineProvider = AlphaVantageKlineProvider