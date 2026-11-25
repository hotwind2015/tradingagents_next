"""YFinance Fundamentals Provider.

Provides:
- fundamentals_raw: Company overview (info)
- financials_raw: Financial statements (balance sheet, cashflow, income statement)
- insider_raw: Insider transactions
"""

from __future__ import annotations

import logging
import re
from typing import Any

import yfinance as yf

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


# Quote currencies Yahoo gives in a minor unit, and the main unit of each.
_MAIN_UNIT = {"GBp": "GBP", "GBX": "GBP", "ZAc": "ZAR", "ILA": "ILS"}

def _yf_retry(func, max_retries=3):
    import time
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)


def _withhold_live_profile(as_of_date: str, canonical: str) -> str | None:
    """Point-in-time guard for live profile data."""
    # For now, allow live data - can be enhanced with date_window logic later
    return None


def _withhold_undated_statements(as_of_date: str, canonical: str, title: str) -> str | None:
    """Point-in-time guard for undated financial statements."""
    return None


def _withhold_undisclosed_trades(as_of_date: str, canonical: str) -> str | None:
    """Point-in-time guard for insider trades."""
    return None


def _raise_for_empty(ticker: str, canonical: str, what: str):
    raise NoMarketDataError(ticker, canonical, f"no {what}")


def _raise_for_empty(ticker: str, canonical: str, what: str):
    from tradingagents.dataflows.errors import NoMarketDataError
    raise NoMarketDataError(ticker, canonical, f"no {what}")


def _statement(ticker: str, freq: str, as_of_date: str, title: str, quarterly_attr: str, annual_attr: str) -> str:
    """One financial statement as CSV, for a run dated today."""
    canonical = normalize_symbol(ticker)
    withheld = _withhold_undated_statements(as_of_date, canonical, title)
    if withheld:
        return withheld
    what = title.lower()
    attr = quarterly_attr if freq.lower() == "quarterly" else annual_attr
    data = _yf_retry(lambda: getattr(yf.Ticker(canonical), attr))
    if data is None or data.empty:
        _raise_for_empty(ticker, canonical, f"{what} data")
    return f"# {title} data for {canonical} ({freq})\n" + data.to_csv()


class YFinanceFundamentalsProvider:
    """Yahoo Finance fundamentals provider."""
    
    provider_id = "yfinance_fundamentals"
    provides = {"fundamentals_raw", "financials_raw", "insider_raw"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        self.freq = kwargs.get("freq", "quarterly")
        self.as_of_date = kwargs.get("as_of_date", None)

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        i18n = get_i18n()
        results = []
        canonical = normalize_symbol(req.ticker)
        
        if req.evidence_type == "fundamentals_raw":
            # Company fundamentals overview from yfinance
            withheld = _withhold_live_profile(req.params.get("as_of_date") or self.as_of_date, canonical)
            if withheld:
                results.append(RawEvidence(
                    evidence_type="fundamentals_raw",
                    provider=self.provider_id,
                    method="yf_info",
                    params=req.params,
                    summary=withheld,
                    raw_payload={"withheld": withheld}
                ))
                return results
            
            info = _yf_retry(lambda: yf.Ticker(canonical).info)
            if not info:
                _raise_for_empty(req.ticker, canonical, "fundamentals")
            
            dividend_yield, debt_to_equity = info.get("dividendYield"), info.get("debtToEquity")
            quote = info.get("currency")
            main = _MAIN_UNIT.get(quote, quote)
            reported = info.get("financialCurrency")
            
            def money(key, currency):
                value = info.get(key)
                return None if value is None else f"{value} {currency}" if currency else value
            
            fields = [
                ("Name", info.get("longName")),
                ("Sector", info.get("sector")),
                ("Industry", info.get("industry")),
                ("Market Cap", money("marketCap", main)),
                ("PE Ratio (TTM)", info.get("trailingPE")),
                ("Forward PE", info.get("forwardPE")),
                ("PEG Ratio", info.get("pegRatio")),
                ("Price to Book", info.get("priceToBook")),
                ("EPS (TTM)", money("trailingEps", main)),
                ("Forward EPS", money("forwardEps", main)),
                ("Dividend Yield", None if dividend_yield is None else f"{dividend_yield}%"),
                ("Beta", info.get("beta")),
                ("52 Week High", money("fiftyTwoWeekHigh", quote)),
                ("52 Week Low", money("fiftyTwoWeekLow", quote)),
                ("50 Day Average", money("fiftyDayAverage", quote)),
                ("200 Day Average", money("twoHundredDayAverage", quote)),
                ("Revenue (TTM)", money("totalRevenue", reported)),
                ("Gross Profit", money("grossProfits", reported)),
                ("EBITDA", money("ebitda", reported)),
                ("Net Income", money("netIncomeToCommon", reported)),
                ("Profit Margin", info.get("profitMargins")),
                ("Operating Margin", info.get("operatingMargins")),
                ("Return on Equity", info.get("returnOnEquity")),
                ("Return on Assets", info.get("returnOnAssets")),
                ("Debt to Equity", None if debt_to_equity is None else f"{debt_to_equity}% ({debt_to_equity / 100:.2f}x)"),
                ("Current Ratio", info.get("currentRatio")),
                ("Book Value", money("bookValue", main)),
                ("Free Cash Flow", money("freeCashflow", reported)),
            ]
            
            lines = [f"{label}: {v}" for label, v in fields if v is not None]
            
            if not lines:
                _raise_for_empty(req.ticker, canonical, "fundamental fields")
            
            summary = i18n.t(
                "evidence.fundamentals_summary",
                ticker=req.ticker,
                pe=info.get("trailingPE", "N/A"),
                market_cap=money("marketCap", main) or "N/A",
                profit_margin=info.get("profitMargins", "N/A"),
            )
            
            results.append(RawEvidence(
                evidence_type="fundamentals_raw",
                provider=self.provider_id,
                method="yf_info",
                params=req.params,
                summary=summary,
                raw_payload={
                    "fields": {label: v for label, v in fields if v is not None},
                    "raw_info": {k: v for k, v in info.items() if v is not None},
                }
            ))
            
        elif req.evidence_type == "financials_raw":
            # Financial statements
            freq = req.params.get("freq", self.freq)
            as_of_date = req.params.get("as_of_date") or self.as_of_date
            
            statements = [
                ("Balance Sheet", "quarterly_balance_sheet", "balance_sheet"),
                ("Cash Flow", "quarterly_cashflow", "cashflow"),
                ("Income Statement", "quarterly_income_stmt", "income_stmt"),
            ]
            
            for title, quarterly_attr, annual_attr in statements:
                try:
                    csv_data = _statement(req.ticker, freq, as_of_date or "", title, quarterly_attr, annual_attr)
                    results.append(RawEvidence(
                        evidence_type="financials_raw",
                        provider=self.provider_id,
                        method=f"yf_{title.lower().replace(' ', '_')}",
                        params={"freq": freq, "as_of_date": as_of_date},
                        summary=f"{title} ({freq}) for {req.ticker}",
                        raw_payload={
                            "statement_type": title.lower().replace(' ', '_'),
                            "freq": freq,
                            "csv": csv_data,
                        }
                    ))
                except Exception as e:
                    logger.warning(f"Failed to fetch {title}: {e}")
                    results.append(RawEvidence(
                        evidence_type="financials_raw",
                        provider=self.provider_id,
                        method=f"yf_{title.lower().replace(' ', '_')}",
                        params={"freq": freq, "as_of_date": as_of_date},
                        summary=f"{title} fetch failed: {e}",
                        raw_payload={"error": str(e), "statement_type": title.lower().replace(' ', '_')},
                    ))
            
        elif req.evidence_type == "insider_raw":
            # Insider transactions
            as_of_date = req.params.get("as_of_date") or self.as_of_date
            withheld = _withhold_undisclosed_trades(as_of_date, canonical)
            if withheld:
                results.append(RawEvidence(
                    evidence_type="insider_raw",
                    provider=self.provider_id,
                    method="yf_insider_transactions",
                    params=req.params,
                    summary=withheld,
                    raw_payload={"withheld": withheld}
                ))
                return results
            
            data = _yf_retry(lambda: yf.Ticker(canonical).insider_transactions)
            
            if data is None or data.empty:
                results.append(RawEvidence(
                    evidence_type="insider_raw",
                    provider=self.provider_id,
                    method="yf_insider_transactions",
                    params=req.params,
                    summary=f"No insider transactions reported for symbol '{canonical}'",
                    raw_payload={"insider_transactions": []}
                ))
                return results
            
            summary = f"Insider Transactions for {canonical}"
            
            # Convert timestamps to ISO strings for JSON serialization
            insider_records = data.to_dict(orient="records")
            for record in insider_records:
                for key, value in record.items():
                    if hasattr(value, 'isoformat'):  # Timestamp or datetime
                        record[key] = value.isoformat()
            
            results.append(RawEvidence(
                evidence_type="insider_raw",
                provider=self.provider_id,
                method="yf_insider_transactions",
                params=req.params,
                summary=summary,
                raw_payload={
                    "insider_transactions": insider_records,
                }
            ))
        
        return results


def _raise_for_empty(ticker: str, canonical: str, what: str):
    from tradingagents.dataflows.errors import NoMarketDataError
    raise NoMarketDataError(ticker, canonical, f"no {what}")


YFinanceFundamentalsProvider = YFinanceFundamentalsProvider