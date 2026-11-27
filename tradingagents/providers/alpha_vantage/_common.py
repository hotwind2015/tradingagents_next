"""Alpha Vantage Common Utilities.

Internal module providing shared functionality for Alpha Vantage providers:
- API key retrieval from config system
- HTTP request handling with error classification
- Date/time format conversion
- Custom exception types
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

from tradingagents.config.settings import get_env_settings

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

API_BASE_URL = "https://www.alphavantage.co/query"
REQUEST_TIMEOUT = 30

# =============================================================================
# Custom Exceptions
# =============================================================================

class AlphaVantageNotConfiguredError(Exception):
    """Raised when Alpha Vantage is selected but no API key is configured.

    Inherits from ValueError so existing "vendor unavailable" handling
    and ValueError callers keep working.
    """
    pass


class AlphaVantageRateLimitError(Exception):
    """Raised when the Alpha Vantage API rate limit is exceeded."""
    pass


# =============================================================================
# API Key Retrieval
# =============================================================================

def get_api_key() -> str:
    """Retrieve the API key for Alpha Vantage from the config system.

    Uses the dynamic_env mechanism (TRADINGAGENTS_ALPHA_VANTAGE_API_KEY
    from .env or environment variable) with SecretStr support.

    Returns:
        The API key string.

    Raises:
        AlphaVantageNotConfiguredError: If no API key is configured.
    """
    settings = get_env_settings()
    api_key = settings.get_extra("alphavantage_api_key")

    if not api_key:
        raise AlphaVantageNotConfiguredError(
            "ALPHAVANTAGE_API_KEY not configured. "
            "Set TRADINGAGENTS_ALPHAVANTAGE_API_KEY in .env or environment variable."
        )
    return api_key


# =============================================================================
# Date/Time Format Conversion
# =============================================================================

def format_datetime_for_api(date_input, end_of_day: bool = False) -> str:
    """Convert various date formats to the YYYYMMDDTHHMM Alpha Vantage expects.

    A plain date means midnight, which is the start of that day. For the end of
    a window pass ``end_of_day`` so the day itself is inside it.

    Args:
        date_input: Date as string (YYYY-MM-DD, YYYY-MM-DD HH:MM) or datetime.
        end_of_day: If True and input is date-only, use 23:59 instead of 00:00.

    Returns:
        Formatted string like "20240115T0000" or "20240115T2359".

    Raises:
        ValueError: If date format is unsupported.
    """
    if isinstance(date_input, str):
        # Already in correct format (YYYYMMDDTHHMM)
        if len(date_input) == 13 and 'T' in date_input:
            return date_input
        # Try common date formats
        try:
            dt = datetime.strptime(date_input, "%Y-%m-%d")
            return dt.strftime("%Y%m%dT2359" if end_of_day else "%Y%m%dT0000")
        except ValueError:
            try:
                dt = datetime.strptime(date_input, "%Y-%m-%d %H:%M")
                return dt.strftime("%Y%m%dT%H%M")
            except ValueError:
                raise ValueError(f"Unsupported date format: {date_input}") from None
    elif isinstance(date_input, datetime):
        return date_input.strftime("%Y%m%dT%H%M")
    else:
        raise ValueError(f"Date must be string or datetime object, got {type(date_input)}")


# =============================================================================
# HTTP Request Helper
# =============================================================================

def _make_api_request(function_name: str, params: dict) -> dict | str:
    """Make an API request to Alpha Vantage and handle responses.

    Args:
        function_name: Alpha Vantage API function (e.g., "TIME_SERIES_DAILY_ADJUSTED").
        params: Query parameters (symbol, interval, etc.).

    Returns:
        Parsed JSON dict for JSON responses, raw CSV/text string for data responses.

    Raises:
        AlphaVantageRateLimitError: When API rate limit is exceeded.
        AlphaVantageNotConfiguredError: When API key is invalid or missing.
        Exception: For other vendor errors (rejected request, network issues).
    """
    import requests

    api_key = get_api_key()

    # Create a copy of params to avoid modifying the original
    api_params = params.copy()
    api_params.update({
        "function": function_name,
        "apikey": api_key,
        "source": "trading_agents",
    })

    # Handle entitlement parameter if present
    entitlement = api_params.get("entitlement")
    if not entitlement:
        api_params.pop("entitlement", None)

    try:
        response = requests.get(
            API_BASE_URL,
            params=api_params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Alpha Vantage request failed: %s", e)
        raise

    response_text = response.text

    # Error responses are JSON; data responses are usually CSV or data-keyed JSON.
    # A non-JSON body is normal data (CSV).
    try:
        response_json = json.loads(response_text)
    except json.JSONDecodeError:
        return response_text

    # Alpha Vantage reports problems via "Information" / "Note".
    # Classify so a genuine rate limit and an invalid/missing key aren't conflated.
    def scrubbed(text: str) -> str:
        # Alpha Vantage can echo the key in its notices; error text reaches logs.
        return text.replace(api_key, "***") if api_key else text

    notice = response_json.get("Information") or response_json.get("Note")
    if notice:
        notice = scrubbed(notice)
        low = notice.lower()
        if any(m in low for m in ("rate limit", "requests per day", "call frequency", "premium")):
            raise AlphaVantageRateLimitError(f"Alpha Vantage rate limit exceeded: {notice}")
        if "api key" in low or "apikey" in low:
            # Reuse the existing "not configured" error so a bad key surfaces as
            # a real, actionable failure rather than a mislabeled rate limit.
            raise AlphaVantageNotConfiguredError(f"Alpha Vantage API key invalid or missing: {notice}")

    # A call it rejects comes back as {"Error Message": ...}, for an unknown
    # symbol and for a malformed call alike.
    rejection = response_json.get("Error Message")
    if rejection:
        raise Exception(f"Alpha Vantage rejected the request: {scrubbed(rejection)}")

    return response_text


# =============================================================================
# CSV Date Range Filtering
# =============================================================================

def _filter_csv_by_date_range(csv_data: str, start_date: str, end_date: str) -> str:
    """Filter CSV data to include only rows within the specified date range.

    Args:
        csv_data: CSV string from Alpha Vantage API.
        start_date: Start date in yyyy-mm-dd format.
        end_date: End date in yyyy-mm-dd format.

    Returns:
        Filtered CSV string.
    """
    if not csv_data or csv_data.strip() == "":
        return csv_data

    import pandas as pd
    from io import StringIO

    # Deliberately unguarded: TIME_SERIES_DAILY_ADJUSTED returns the full series
    # up to today, so this trim is the only thing keeping bars after end_date out
    # of a historical run.
    df = pd.read_csv(StringIO(csv_data))

    # Assume the first column is the date column (timestamp)
    date_col = df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col])

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    filtered_df = df[(df[date_col] >= start_dt) & (df[date_col] <= end_dt)]

    return filtered_df.to_csv(index=False)