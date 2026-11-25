"""FRED (Federal Reserve Economic Data) Macro Provider.

Provides:
- macro_raw: Macroeconomic time series from FRED API
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Iterable

import pytz

from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence
from tradingagents.utils import get_i18n
from tradingagents.config.settings import get_env_settings

logger = logging.getLogger(__name__)

FRED_API_BASE = "https://api.stlouisfed.org/fred"
FRED_TZ = pytz.timezone("America/Chicago")
REQUEST_TIMEOUT = 30
DEFAULT_LOOKBACK_DAYS = 365
MAX_ROWS = 40

# Curated human-friendly aliases -> FRED series IDs
MACRO_SERIES = {
    "fed_funds_rate": "FEDFUNDS",
    "federal_funds_rate": "FEDFUNDS",
    "fed_funds": "FEDFUNDS",
    "2y_treasury": "DGS2",
    "10y_treasury": "DGS10",
    "30y_treasury": "DGS30",
    "10y_2y_spread": "T10Y2Y",
    "yield_curve": "T10Y2Y",
    "cpi": "CPIAUCSL",
    "core_cpi": "CPILFESL",
    "pce": "PCEPI",
    "core_pce": "PCEPILFE",
    "inflation_expectations": "T10YIE",
    "real_gdp": "GDPC1",
    "gdp": "GDP",
    "industrial_production": "INDPRO",
    "unemployment_rate": "UNRATE",
    "unemployment": "UNRATE",
    "nonfarm_payrolls": "PAYEMS",
    "payrolls": "PAYEMS",
    "initial_claims": "ICSA",
    "m2": "M2SL",
    "money_supply": "M2SL",
    "vix": "VIXCLS",
    "dollar_index": "DTWEXBGS",
    "consumer_sentiment": "UMCSENT",
    "housing_starts": "HOUST",
    "retail_sales": "RSAFS",
    "ecb_deposit_rate": "ECBDFR",
    "ecb_main_refi_rate": "ECBMRRFR",
    "euro_hicp": "CP0000EZ19M086NEST",
    "euro_core_hicp": "00XEFDEZ19M086NEST",
    "euro_real_gdp": "CLVMNACSCAB1GQEA19",
    "germany_10y": "IRLTLT01DEM156N",
    "france_10y": "IRLTLT01FRM156N",
    "eur_usd": "DEXUSEU",
}


class FredNotConfiguredError(Exception):
    """Raised when FRED is selected but no API key is configured."""
    pass


def _get_api_key() -> str:
    # 优先从配置系统获取，回退到环境变量
    settings = get_env_settings()
    api_key = None
    
    # 使用 get_extra 方法自动处理 SecretStr
    api_key = settings.get_extra("fred_api_key")
    
    if not api_key:
        api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise FredNotConfiguredError(
            "FRED_API_KEY not configured. Set TRADINGAGENTS_FRED_API_KEY in .env "
            "or FRED_API_KEY environment variable. Get a free key at "
            "https://fred.stlouisfed.org/docs/api/api_key.html."
        )
    return api_key


def _resolve_series_id(indicator: str) -> str:
    key = indicator.strip().lower().replace(" ", "_").replace("-", "_")
    if key in MACRO_SERIES:
        return MACRO_SERIES[key]
    candidate = indicator.strip().upper()
    if not candidate or len(candidate) > 30 or any(c.isspace() for c in candidate):
        raise ValueError(
            f"'{indicator}' is not a known macro alias or a valid FRED series ID. "
            f"Use an alias (e.g. 'cpi', 'unemployment', '10y_treasury') or a raw "
            f"FRED series ID (e.g. 'CPIAUCSL')."
        )
    return candidate


def _fred_today() -> str:
    return datetime.now(FRED_TZ).strftime("%Y-%m-%d")


def _request(path: str, params: dict) -> dict:
    import requests
    api_key = _get_api_key()
    response = requests.get(
        f"{FRED_API_BASE}/{path}",
        params={**params, "api_key": api_key, "file_type": "json"},
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code == 400:
        try:
            message = response.json().get("error_message", response.text)
        except ValueError:
            message = response.text
        raise ValueError(f"FRED request failed: {message}")
    return response.json()


class FredMacroProvider:
    """FRED macroeconomic data provider."""
    
    provider_id = "fred_macro"
    provides = {"macro_raw"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        self.default_lookback_days = kwargs.get("look_back_days", DEFAULT_LOOKBACK_DAYS)
        # indicator can be a single string or list of strings
        self.indicators = kwargs.get("indicator", ["cpi", "unemployment", "fed_funds_rate", "10y_treasury", "yield_curve", "vix", "dollar_index"])

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        i18n = get_i18n()
        results = []
        
        as_of_date = req.params.get("as_of_date", datetime.now().strftime("%Y-%m-%d"))
        look_back_days = req.params.get("look_back_days", self.default_lookback_days)
        
        indicators = self.indicators if isinstance(self.indicators, list) else [self.indicators]
        
        for ind in indicators:
            try:
                report = self._fetch_macro_data(ind, as_of_date, look_back_days)
                
                results.append(RawEvidence(
                    evidence_type="macro_raw",
                    provider=self.provider_id,
                    method="fred_api",
                    params={"indicator": ind, "as_of_date": as_of_date, "look_back_days": look_back_days},
                    summary=f"FRED {ind} from {as_of_date} (lookback: {look_back_days}d)",
                    raw_payload={
                        "indicator": ind,
                        "report": report,
                        "as_of_date": as_of_date,
                        "look_back_days": look_back_days,
                    }
                ))
            except Exception as e:
                logger.warning(f"Failed to fetch macro {ind}: {e}")
                # Return error as payload instead of failing
                results.append(RawEvidence(
                    evidence_type="macro_raw",
                    provider=self.provider_id,
                    method="fred_api",
                    params={"indicator": ind, "as_of_date": as_of_date, "look_back_days": look_back_days},
                    summary=f"FRED {ind} fetch failed: {e}",
                    raw_payload={
                        "indicator": ind,
                        "error": str(e),
                        "as_of_date": as_of_date,
                        "look_back_days": look_back_days,
                    }
                ))
        
        return results

    def _fetch_macro_data(self, indicator: str, as_of_date: str, look_back_days: int) -> str:
        if look_back_days is None:
            look_back_days = DEFAULT_LOOKBACK_DAYS

        end_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
        start_date = (end_dt - timedelta(days=look_back_days)).strftime("%Y-%m-%d")

        # Pin the data vintage
        pit = min(as_of_date, _fred_today())
        realtime = {"realtime_start": pit, "realtime_end": pit}

        try:
            series_id = _resolve_series_id(indicator)
        except ValueError as e:
            return f"FRED: {e}"

        meta = _request("series", {"series_id": series_id, **realtime}).get("seriess") or []
        if not meta:
            return f"FRED series '{series_id}' not found."
        info = meta[0]
        title = info.get("title", series_id)
        units = info.get("units_short") or info.get("units", "")
        frequency = info.get("frequency", "")
        seasonal = info.get("seasonal_adjustment_short", "")

        observations = _request(
            "series/observations",
            {
                "series_id": series_id,
                "observation_start": start_date,
                "observation_end": as_of_date,
                "sort_order": "asc",
                **realtime,
            },
        ).get("observations", [])

        points = [
            (o["date"], o["value"])
            for o in observations
            if o.get("value") not in (".", None, "")
        ]

        header = (
            f"## FRED: {title} ({series_id})\n"
            f"- Units: {units}\n"
            f"- Frequency: {frequency}"
            f"{f' ({seasonal})' if seasonal else ''}\n"
            f"- Window: {start_date} to {as_of_date}\n"
        )

        if not points:
            return header + (
                f"\nNo observations for {series_id} in this window at the {pit} "
                f"vintage. The series may report less frequently than the window "
                f"(try a longer look_back_days), or have no vintage published by "
                f"then (unpublished as of {pit}, or before ALFRED coverage begins)."
            )

        first_date, first_val = points[0]
        last_date, last_val = points[-1]
        try:
            delta = float(last_val) - float(first_val)
            base = float(first_val)
            pct = f" ({delta / base * 100:+.2f}%)" if base != 0 else ""
            summary = (
                f"\n**Latest:** {last_val} ({last_date}) | "
                f"**Change from {first_date} to {last_date}:** {delta:+.2f}{pct}, "
                f"from {first_val}\n"
            )
        except ValueError:
            summary = f"\n**Latest:** {last_val} ({last_date})\n"

        shown = points
        note = ""
        if len(points) > MAX_ROWS:
            shown = points[-MAX_ROWS:]
            note = f"\n_(showing the most recent {MAX_ROWS} of {len(points)} observations)_\n"

        table = (
            "\n| Date | Value |\n| --- | --- |\n"
            + "\n".join(f"| {d} | {v} |" for d, v in shown)
            + "\n"
        )

        return header + summary + note + table


FredMacroProvider = FredMacroProvider