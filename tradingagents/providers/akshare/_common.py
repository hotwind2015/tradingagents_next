"""AKShare Common Utilities.

Internal module providing shared functionality for AKShare providers:
- Symbol normalization (A-share code formats)
- Date format conversion
- Column name mapping (Chinese -> English)
- Error handling and classification
- DataFrame post-processing utilities
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import pandas as pd

from tradingagents.utils import get_i18n

logger = logging.getLogger(__name__)

# =============================================================================
# Symbol Normalization
# =============================================================================

# Market prefixes for A-share
SH_PREFIXES = {"600", "601", "603", "605", "688", "689"}  # SH main board, STAR market
SZ_PREFIXES = {"000", "001", "002", "003", "300", "301"}  # SZ main board, SME, ChiNext
BJ_PREFIXES = {"430", "83", "87", "88", "92"}  # Beijing Stock Exchange

# Symbol format patterns
SYMBOL_PATTERN_SIMPLE = re.compile(r"^\d{6}$")  # 000001
SYMBOL_PATTERN_WITH_PREFIX = re.compile(r"^(sh|sz|bj)\d{6}$", re.IGNORECASE)  # sh600000
SYMBOL_PATTERN_WITH_DOT = re.compile(r"^\d{6}\.(SH|SZ|BJ)$", re.IGNORECASE)  # 600000.SH


def detect_market(symbol: str) -> str:
    """Detect market from symbol prefix.

    Returns:
        'SH' for Shanghai, 'SZ' for Shenzhen, 'BJ' for Beijing, 'UNKNOWN' otherwise.
    """
    if not symbol or not isinstance(symbol, str):
        return "UNKNOWN"

    sym = symbol.strip().upper()

    # Already has market prefix
    if sym.startswith(("SH", "SZ", "BJ")) and len(sym) >= 8:
        return sym[:2]
    if "." in sym:
        parts = sym.split(".")
        if len(parts) == 2 and parts[1] in ("SH", "SZ", "BJ"):
            return parts[1]

    # 6-digit code
    if SYMBOL_PATTERN_SIMPLE.match(sym):
        prefix = sym[:3]
        if prefix in SH_PREFIXES:
            return "SH"
        if prefix in SZ_PREFIXES:
            return "SZ"
        if prefix in BJ_PREFIXES:
            return "BJ"

    return "UNKNOWN"


def normalize_symbol(symbol: str, target_format: str = "simple") -> str:
    """Normalize symbol to target format.

    Args:
        symbol: Input symbol in any supported format.
        target_format: One of 'simple' (000001), 'prefix' (sh600000), 'dot' (600000.SH).

    Returns:
        Normalized symbol string.
    """
    if not symbol or not isinstance(symbol, str):
        return symbol

    sym = symbol.strip().upper()

    # Already in target format
    if target_format == "simple" and SYMBOL_PATTERN_SIMPLE.match(sym):
        return sym
    if target_format == "prefix" and SYMBOL_PATTERN_WITH_PREFIX.match(sym):
        return sym.lower()
    if target_format == "dot" and SYMBOL_PATTERN_WITH_DOT.match(sym):
        return sym

    # Extract 6-digit code
    code = None
    if SYMBOL_PATTERN_SIMPLE.match(sym):
        code = sym
    elif SYMBOL_PATTERN_WITH_PREFIX.match(sym):
        code = sym[2:]
    elif SYMBOL_PATTERN_WITH_DOT.match(sym):
        code = sym.split(".")[0]

    if not code:
        logger.warning(f"Cannot parse symbol: {symbol}")
        return symbol

    # Apply target format
    if target_format == "simple":
        return code
    elif target_format == "prefix":
        market = detect_market(code)
        prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(market, "")
        return f"{prefix}{code}"
    elif target_format == "dot":
        market = detect_market(code)
        suffix = {"SH": "SH", "SZ": "SZ", "BJ": "BJ"}.get(market, "")
        return f"{code}.{suffix}"

    return symbol


# =============================================================================
# Date Format Conversion
# =============================================================================

def to_akshare_date(date_input: str | datetime, format_type: str = "akshare") -> str:
    """Convert date to AKShare format (YYYYMMDD).

    Args:
        date_input: Date string (YYYY-MM-DD, YYYY/MM/DD) or datetime object.
        format_type: Target format ('akshare' for YYYYMMDD, 'standard' for YYYY-MM-DD).

    Returns:
        Formatted date string.
    """
    if isinstance(date_input, datetime):
        dt = date_input
    elif isinstance(date_input, str):
        # Try parsing common formats
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y.%m.%d"):
            try:
                dt = datetime.strptime(date_input, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"Unsupported date format: {date_input}")
    else:
        raise ValueError(f"Date must be string or datetime, got {type(date_input)}")

    if format_type == "akshare":
        return dt.strftime("%Y%m%d")
    elif format_type == "standard":
        return dt.strftime("%Y-%m-%d")
    else:
        return dt.strftime("%Y%m%d")


def parse_akshare_date(date_str: str) -> datetime:
    """Parse AKShare date string (YYYYMMDD) to datetime."""
    return datetime.strptime(date_str, "%Y%m%d")


# =============================================================================
# Column Name Mapping (Chinese -> English)
# =============================================================================

# K-line data column mapping (东财/新浪/腾讯)
KLINE_COL_MAP = {
    # 东财
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
    # 新浪
    "date": "date",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "amount": "amount",
    "outstanding_share": "outstanding_share",
    "turnover": "turnover",
    # 腾讯
    "open": "open",
    "close": "close",
    "high": "high",
    "low": "low",
    "volume": "volume",
    "turnover": "turnover",
    "amount": "amount",
}

# Real-time snapshot column mapping (东财实时行情)
SPOT_COL_MAP = {
    "序号": "index",
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
    "涨速": "price_change_speed",
    "5分钟涨跌": "change_5min",
    "60日涨跌幅": "change_60d",
    "年初至今涨跌幅": "change_ytd",
}

# Fundamental info column mapping (个股基本信息)
FUNDAMENTAL_COL_MAP = {
    "项目": "item",
    "值": "value",
}

# Financial indicators column mapping (财务分析指标)
FINANCIAL_INDICATOR_COL_MAP = {
    "项目": "item",
    "值": "value",
}

# Financial statements column mapping (财务三表)
BALANCE_SHEET_COL_MAP = {
    "报表日期": "report_date",
    "报表类型": "report_type",
    # ... 其他字段按需补充
}

PROFIT_SHEET_COL_MAP = {
    "报表日期": "report_date",
    "报表类型": "report_type",
}

CASH_FLOW_COL_MAP = {
    "报表日期": "report_date",
    "报表类型": "report_type",
}

# Holder trade column mapping (增减持)
HOLDER_TRADE_COL_MAP = {
    "序号": "index",
    "变动人": "holder_name",
    "变动股数": "change_shares",
    "变动后持股数": "hold_shares_after",
    "变动均价": "avg_price",
    "变动原因": "reason",
    "公告日期": "announce_date",
}

# News column mapping (新闻)
NEWS_COL_MAP = {
    "代码": "symbol",
    "标题": "title",
    "内容": "content",
    "发布时间": "pub_time",
    "来源": "source",
    "链接": "url",
    "摘要": "summary",
}

# Macro column mapping (宏观)
MACRO_CPI_COL_MAP = {
    "月份": "date",
    "全国-当月": "national_current",
    "全国-同比增长": "national_yoy",
    "全国-环比增长": "national_mom",
    "全国-累计": "national_ytd",
    "城市-当月": "urban_current",
    "城市-同比增长": "urban_yoy",
    "城市-环比增长": "urban_mom",
    "城市-累计": "urban_ytd",
    "农村-当月": "rural_current",
    "农村-同比增长": "rural_yoy",
    "农村-环比增长": "rural_mom",
    "农村-累计": "rural_ytd",
}

MACRO_GDP_COL_MAP = {
    "季度": "quarter",
    "国内生产总值-绝对值": "gdp_current",
    "国内生产总值-同比增长": "gdp_yoy",
    "第一产业-绝对值": "primary_current",
    "第一产业-同比增长": "primary_yoy",
    "第二产业-绝对值": "secondary_current",
    "第二产业-同比增长": "secondary_yoy",
    "第三产业-绝对值": "tertiary_current",
    "第三产业-同比增长": "tertiary_yoy",
}


# =============================================================================
# DataFrame Processing Utilities
# =============================================================================

def rename_columns(df: pd.DataFrame, col_map: dict[str, str]) -> pd.DataFrame:
    """Rename DataFrame columns using mapping dictionary.

    Only renames columns that exist in the DataFrame.
    """
    if df.empty:
        return df

    rename_dict = {k: v for k, v in col_map.items() if k in df.columns}
    if rename_dict:
        df = df.rename(columns=rename_dict)
    return df


def standardize_kline_columns(df: pd.DataFrame, source: str = "em") -> pd.DataFrame:
    """Standardize K-line DataFrame columns to English names.

    Args:
        df: Raw DataFrame from AKShare.
        source: Data source ('em', 'sina', 'tx').

    Returns:
        DataFrame with standardized English column names.
    """
    if df.empty:
        return df

    col_map = KLINE_COL_MAP.copy()
    # Add source-specific mappings if needed
    return rename_columns(df, col_map)


def standardize_spot_columns(df: pd.DataFrame, source: str = "em") -> pd.DataFrame:
    """Standardize real-time snapshot DataFrame columns."""
    if df.empty:
        return df
    return rename_columns(df, SPOT_COL_MAP)


def ensure_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Convert specified columns to numeric, coercing errors to NaN."""
    if df.empty:
        return df

    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def add_metadata(df: pd.DataFrame, symbol: str, source: str, adjust: str = "") -> pd.DataFrame:
    """Add metadata columns to DataFrame."""
    if df.empty:
        return df

    df = df.copy()
    df["symbol"] = symbol
    df["source"] = source
    if adjust:
        df["adjust"] = adjust
    return df


# =============================================================================
# Error Handling
# =============================================================================

class AKShareError(Exception):
    """Base exception for AKShare provider errors."""
    pass


class AKShareRateLimitError(AKShareError):
    """Raised when AKShare API rate limit is hit."""
    pass


class AKShareDataUnavailableError(AKShareError):
    """Raised when data is not available (delisted, suspended, etc.)."""
    pass


class AKShareNetworkError(AKShareError):
    """Raised for network-related errors."""
    pass


def classify_akshare_error(error: Exception) -> type[AKShareError]:
    """Classify AKShare exception into our custom error types."""
    error_msg = str(error).lower()

    if any(keyword in error_msg for keyword in ["rate limit", "频率限制", "too many requests", "429"]):
        return AKShareRateLimitError
    elif any(keyword in error_msg for keyword in ["not found", "不存在", "delisted", "退市", "停牌", "suspended", "no data", "无数据", "empty"]):
        return AKShareDataUnavailableError
    elif any(keyword in error_msg for keyword in ["timeout", "超时", "connection", "连接", "network", "网络", "dns", "resolve"]):
        return AKShareNetworkError

    return AKShareError


def handle_akshare_error(error: Exception, symbol: str, operation: str) -> AKShareError:
    """Wrap AKShare error with context."""
    error_type = classify_akshare_error(error)
    message = f"{operation} failed for {symbol}: {error}"
    return error_type(message)


# =============================================================================
# Data Quality Validation
# =============================================================================

def validate_kline_data(df: pd.DataFrame, symbol: str) -> list[str]:
    """Validate K-line data quality.

    Returns:
        List of warning messages (empty if all checks pass).
    """
    warnings = []

    if df.empty:
        warnings.append(f"{symbol}: Empty DataFrame")
        return warnings

    required_cols = ["date", "open", "high", "low", "close", "volume"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        warnings.append(f"{symbol}: Missing required columns: {missing}")

    # Check for NaN in critical columns
    for col in ["open", "high", "low", "close"]:
        if col in df.columns and df[col].isna().any():
            warnings.append(f"{symbol}: NaN values in {col}")

    # Check for negative prices
    for col in ["open", "high", "low", "close"]:
        if col in df.columns and (df[col] < 0).any():
            warnings.append(f"{symbol}: Negative values in {col}")

    # Check for high > low
    if all(c in df.columns for c in ["high", "low"]):
        if (df["high"] < df["low"]).any():
            warnings.append(f"{symbol}: High < Low detected")

    # Check volume non-negative
    if "volume" in df.columns and (df["volume"] < 0).any():
        warnings.append(f"{symbol}: Negative volume detected")

    return warnings


# =============================================================================
# i18n Helpers
# =============================================================================

def get_provider_i18n_key(provider_id: str, key: str) -> str:
    """Generate i18n key for provider-specific messages."""
    return f"providers.akshare.{provider_id}.{key}"


def t_provider(provider_id: str, key: str, **kwargs) -> str:
    """Translate provider-specific message using i18n."""
    i18n = get_i18n()
    key = get_provider_i18n_key(provider_id, key)
    return i18n.t(key, **kwargs)


# =============================================================================
# Provider Configuration Helpers
# =============================================================================

def get_provider_args(config: dict, provider_id: str) -> dict:
    """Extract provider_args for a specific provider from config."""
    return config.get("provider_args", {}).get(provider_id, {})


def merge_provider_args(default_args: dict, user_args: dict) -> dict:
    """Merge default provider args with user-provided args (user wins)."""
    merged = default_args.copy()
    merged.update(user_args)
    return merged


# =============================================================================
# Constants
# =============================================================================

# Default adjust modes
DEFAULT_ADJUST = "qfq"  # 前复权

# Default periods
DEFAULT_PERIOD = "daily"

# Default date range (1 year)
DEFAULT_LOOKBACK_DAYS = 365

# Supported adjust modes
ADJUST_MODES = {"": "不复权", "qfq": "前复权", "hfq": "后复权"}

# Supported periods
PERIODS = {"daily": "日线", "weekly": "周线", "monthly": "月线"}

# Data source priorities for each evidence type
PROVIDER_PRIORITIES = {
    "market_raw_kline": ["akshare_kline", "yfinance_kline", "alpha_vantage_kline"],
    "market_verified_snapshot": ["akshare_kline", "yfinance_snapshot"],
    "market_indicators": ["akshare_indicators", "yfinance_kline"],
    "fundamentals_raw": ["akshare_fundamentals", "yfinance_fundamentals", "alpha_vantage_fundamentals"],
    "financials_raw": ["akshare_fundamentals", "yfinance_fundamentals", "alpha_vantage_fundamentals"],
    "insider_raw": ["akshare_fundamentals", "yfinance_fundamentals", "alpha_vantage_fundamentals"],
    "news_raw": ["akshare_news", "yfinance_news", "alpha_vantage_news"],
    "global_news_raw": ["akshare_news", "yfinance_news", "alpha_vantage_news"],
    "macro_raw": ["akshare_macro", "fred_macro", "alpha_vantage_macro"],
}

__all__ = [
    # Symbol normalization
    "detect_market",
    "normalize_symbol",
    # Date conversion
    "to_akshare_date",
    "parse_akshare_date",
    # Column mapping
    "rename_columns",
    "standardize_kline_columns",
    "standardize_spot_columns",
    "ensure_numeric",
    "add_metadata",
    # Error handling
    "AKShareError",
    "AKShareRateLimitError",
    "AKShareDataUnavailableError",
    "AKShareNetworkError",
    "classify_akshare_error",
    "handle_akshare_error",
    # Validation
    "validate_kline_data",
    # i18n
    "get_provider_i18n_key",
    "t_provider",
    # Config helpers
    "get_provider_args",
    "merge_provider_args",
    # Constants
    "DEFAULT_ADJUST",
    "DEFAULT_PERIOD",
    "ADJUST_MODES",
    "PERIODS",
    "PROVIDER_PRIORITIES",
]