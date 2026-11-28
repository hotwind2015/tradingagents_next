"""AKShare K-line and Snapshot Provider.

Provides:
- market_raw_kline: Raw OHLCV data from AKShare (东财/新浪/腾讯)
- market_verified_snapshot: Verified market snapshot from real-time data
"""

from __future__ import annotations

import logging
import os

# Disable tqdm progress bars from akshare
os.environ.setdefault("TQDM_DISABLE", "1")

import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from tradingagents.providers.alpha_vantage._common import (
    AlphaVantageNotConfiguredError,
    AlphaVantageRateLimitError,
)
from tradingagents.providers.akshare._common import (
    AKShareDataUnavailableError,
    AKShareNetworkError,
    AKShareRateLimitError,
    add_metadata,
    classify_akshare_error,
    ensure_numeric,
    get_provider_i18n_key,
    handle_akshare_error,
    standardize_kline_columns,
    standardize_spot_columns,
    to_akshare_date,
    t_provider,
    validate_kline_data,
)
from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence
from tradingagents.utils import get_i18n

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Data source priorities for kline
KLINE_SOURCES = ["em", "sina", "tx"]
SNAPSHOT_SOURCES = ["em", "sina"]

# Default parameters
DEFAULT_LOOKBACK_DAYS = 365
DEFAULT_ADJUST = "qfq"  # 前复权

# Column name mappings for different sources
COL_MAP_EM = {
    "日期": "date",
    "股票代码": "symbol",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "pct_change",
    "涨跌额": "change",
    "换手率": "turnover_rate",
}

COL_MAP_SINA = {
    "date": "date",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "amount": "amount",
}

COL_MAP_TX = {
    "date": "date",
    "open": "open",
    "close": "close",
    "high": "high",
    "low": "low",
    "volume": "volume",
    "turnover": "turnover",
    "amount": "amount",
}

SNAPSHOT_COL_MAP_EM = {
    "代码": "symbol",
    "名称": "name",
    "最新价": "price",
    "涨跌幅": "pct_change",
    "涨跌额": "change",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "最高": "high",
    "最低": "low",
    "今开": "open",
    "昨收": "prev_close",
    "量比": "volume_ratio",
    "换手率": "turnover_rate",
    "市盈率-动态": "pe_ttm",
    "市净率": "pb",
    "总市值": "total_market_cap",
    "流通市值": "circulating_market_cap",
}


class AKShareKlineProvider:
    """AKShare K-line and Snapshot Provider.

    provider_id = "akshare_kline"
    provides = {"market_raw_kline", "market_verified_snapshot"}
    """

    provider_id = "akshare_kline"
    provides = {"market_raw_kline", "market_verified_snapshot"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        """Initialize with provider_args from recipe.

        Args:
            look_back_days: Days to look back for kline data (default: 365)
            adjust: Adjustment mode - "qfq" (前复权), "hfq" (后复权), "" (不复权)
            sources: List of data sources to try in order (default: ["em", "sina", "tx"])
        """
        self.default_look_back_days = kwargs.get("look_back_days", 365)
        self.default_adjust = kwargs.get("adjust", "qfq")
        self.sources = kwargs.get("sources", KLINE_SOURCES)
        self.snapshot_sources = kwargs.get("snapshot_sources", SNAPSHOT_SOURCES)

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        i18n = get_i18n()
        results = []

        if req.evidence_type == "market_raw_kline":
            results.extend(self._fetch_raw_kline(req))
        elif req.evidence_type == "market_verified_snapshot":
            results.extend(self._fetch_verified_snapshot(req))

        return results

    # -------------------------------------------------------------------------
    # market_raw_kline: Historical OHLCV data
    # -------------------------------------------------------------------------
    def _fetch_raw_kline(self, req: DataRequest) -> list[RawEvidence]:
        """Fetch raw OHLCV data from AKShare."""
        symbol = req.ticker
        start_date = req.params.get("start_date", (datetime.now() - timedelta(days=self.default_look_back_days)).strftime("%Y-%m-%d"))
        end_date = req.params.get("end_date", datetime.now().strftime("%Y-%m-%d"))
        adjust = req.params.get("adjust", self.default_adjust)
        period = req.params.get("period", "daily")

        # Try each source in priority order
        last_error = None
        for source in self.sources:
            try:
                df = self._fetch_kline_from_source(source, symbol, period, start_date, end_date, adjust)
                if df is not None and not df.empty:
                    # Standardize columns first
                    df = self._standardize_kline_columns(df, source)

                    # Validate data quality after standardization
                    warnings = validate_kline_data(df, symbol)
                    for w in warnings:
                        logger.warning(w)

                    # Generate summary
                    summary = self._generate_kline_summary(symbol, df, source)

                    return [RawEvidence(
                        evidence_type="market_raw_kline",
                        provider=self.provider_id,
                        method=f"akshare_{source}_kline",
                        params={"source": source, "period": period, "adjust": adjust, "start_date": start_date, "end_date": end_date},
                        summary=summary,
                        raw_payload=self._df_to_raw_payload(df, source)
                    )]

            except Exception as e:
                last_error = handle_akshare_error(e, symbol, f"fetch kline from {source}")
                logger.warning(f"Source {source} failed for {symbol}: {e}")
                continue

        # All sources failed
        if last_error:
            raise last_error
        raise AKShareDataUnavailableError(f"No data available for {symbol} from any source")

    def _fetch_kline_from_source(self, source: str, symbol: str, period: str,
                                  start_date: str, end_date: str, adjust: str) -> pd.DataFrame | None:
        """Fetch kline data from specific source."""
        import akshare as ak

        ak_symbol = self._format_symbol_for_source(source, symbol)

        if source == "em":
            return ak.stock_zh_a_hist_em(
                symbol=ak_symbol,
                period=period,
                start_date=to_akshare_date(start_date),
                end_date=to_akshare_date(end_date),
                adjust=adjust
            )
        elif source == "sina":
            return ak.stock_zh_a_hist_sina(
                symbol=ak_symbol,
                period=period,
                start_date=to_akshare_date(start_date),
                end_date=to_akshare_date(end_date),
                adjust=adjust
            )
        elif source == "tx":
            return ak.stock_zh_a_hist_tx(
                symbol=ak_symbol,
                start_date=to_akshare_date(start_date),
                end_date=to_akshare_date(end_date),
                adjust=adjust
            )
        return None

    def _format_symbol_for_source(self, source: str, symbol: str) -> str:
        """Format symbol for specific data source."""
        if source == "em":
            # 东财使用不带前缀的6位代码
            return symbol.split(".")[0] if "." in symbol else symbol
        elif source == "sina":
            # 新浪使用 sz/sh 前缀
            market = "sh" if symbol.startswith(("6", "688")) else "sz"
            code = symbol.split(".")[0] if "." in symbol else symbol
            return f"{market}{code}"
        elif source == "tx":
            # 腾讯使用 sz/sh 前缀
            market = "sz" if symbol.startswith(("0", "3")) else "sh"
            code = symbol.split(".")[0] if "." in symbol else symbol
            return f"{market}{code}"
        return symbol

    def _standardize_kline_columns(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        """Standardize column names to English."""
        col_maps = {
            "em": {
                "日期": "date",
                "股票代码": "symbol",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "振幅": "amplitude",
                "涨跌幅": "pct_change",
                "涨跌额": "change",
                "换手率": "turnover_rate",
            },
            "sina": {
                "date": "date",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
                "amount": "amount",
            },
            "tx": {
                "date": "date",
                "open": "open",
                "close": "close",
                "high": "high",
                "low": "low",
                "volume": "volume",
                "turnover": "turnover",
                "amount": "amount",
            },
        }
        col_map = col_maps.get(source, {})
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        # Ensure date column is standardized
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

        # Ensure numeric columns
        numeric_cols = ["open", "high", "low", "close", "volume", "amount"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    def _generate_kline_summary(self, symbol: str, df: pd.DataFrame, source: str) -> str:
        """Generate human-readable summary for kline data."""
        i18n = get_i18n()
        if df.empty:
            return f"No kline data for {symbol} from {source}"

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        close_val = float(latest.get("close", 0))
        prev_close = float(prev.get("close", 0))
        pct_change = ((close_val - prev_close) / prev_close * 100) if prev_close else 0.0

        return i18n.t(
            "providers.akshare.kline.market_summary",
            ticker=symbol,
            close=close_val,
            pct_change=pct_change,
        )

    def _df_to_raw_payload(self, df: pd.DataFrame, source: str) -> dict:
        """Convert DataFrame to raw payload for storage."""
        return {
            "source": source,
            "records": len(df),
            "date_range": {
                "start": df["date"].iloc[0] if "date" in df.columns and not df.empty else None,
                "end": df["date"].iloc[-1] if "date" in df.columns and not df.empty else None,
            },
            "columns": list(df.columns),
            "sample": df.head(5).to_dict(orient="records") if not df.empty else [],
        }

    # -------------------------------------------------------------------------
    # market_verified_snapshot: Real-time verified snapshot
    # -------------------------------------------------------------------------
    def _fetch_verified_snapshot(self, req: DataRequest) -> list[RawEvidence]:
        """Fetch verified market snapshot from real-time data."""
        symbol = req.ticker
        as_of_date = req.params.get("as_of_date", datetime.now().strftime("%Y-%m-%d"))

        for source in self.snapshot_sources:
            try:
                df = self._fetch_snapshot_from_source(source, symbol)
                if df is not None and not df.empty:
                    snapshot_data = self._extract_snapshot_data(df, symbol)
                    if snapshot_data:
                        summary = f"Verified snapshot for {symbol} as of {as_of_date}"
                        return [RawEvidence(
                            evidence_type="market_verified_snapshot",
                            provider=self.provider_id,
                            method=f"akshare_{source}_snapshot",
                            params={"as_of_date": as_of_date, "source": source},
                            summary=summary,
                            raw_payload=snapshot_data
                        )]
            except Exception as e:
                logger.warning(f"Snapshot source {source} failed for {symbol}: {e}")
                continue

        raise AKShareDataUnavailableError(f"No snapshot data available for {symbol}")

    def _fetch_snapshot_from_source(self, source: str, symbol: str) -> pd.DataFrame | None:
        """Fetch snapshot from specific source."""
        import akshare as ak

        if source == "em":
            # Get full market snapshot and filter for our symbol
            df = ak.stock_zh_a_spot_em()
            code = symbol.split(".")[0] if "." in symbol else symbol
            return df[df["代码"] == code] if not df.empty else None
        elif source == "sina":
            df = ak.stock_zh_a_spot_sina()
            code = symbol.split(".")[0] if "." in symbol else symbol
            market = "sh" if symbol.startswith(("6", "688")) else "sz"
            full_code = f"{market}{symbol.split('.')[0]}"
            return df[df["代码"] == full_code] if not df.empty else None
        return None

    def _extract_snapshot_data(self, df: pd.DataFrame, symbol: str) -> dict:
        """Extract snapshot data from DataFrame."""
        if df.empty:
            return {}

        row = df.iloc[0]
        data = {}

        # Map Chinese column names to English
        col_map = {
            "代码": "symbol",
            "名称": "name",
            "最新价": "price",
            "涨跌幅": "pct_change",
            "涨跌额": "change",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude",
            "最高": "high",
            "最低": "low",
            "今开": "open",
            "昨收": "prev_close",
            "量比": "volume_ratio",
            "换手率": "turnover_rate",
            "市盈率-动态": "pe_ttm",
            "市净率": "pb",
            "总市值": "total_market_cap",
            "流通市值": "circulating_market_cap",
        }

        for cn, en in col_map.items():
            if cn in row.index:
                data[en] = row[cn]

        data["symbol"] = symbol
        return data


AKShareKlineProvider = AKShareKlineProvider