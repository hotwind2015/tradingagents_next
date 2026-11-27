"""Alpha Vantage Fundamentals Provider.

Provides:
- fundamentals_raw: Company overview from Alpha Vantage OVERVIEW
- financials_raw: Financial statements (BALANCE_SHEET, CASH_FLOW, INCOME_STATEMENT)
- insider_raw: Insider transactions from Alpha Vantage INSIDER_TRANSACTIONS
"""

from __future__ import annotations

import logging
from typing import Any

from tradingagents.providers.alpha_vantage._common import (
    _make_api_request,
    AlphaVantageNotConfiguredError,
    AlphaVantageRateLimitError,
)
from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence
from tradingagents.utils import get_i18n

logger = logging.getLogger(__name__)


class AlphaVantageFundamentalsProvider:
    """Alpha Vantage fundamentals provider."""

    provider_id = "alpha_vantage_fundamentals"
    provides = {"fundamentals_raw", "financials_raw", "insider_raw"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        self.freq = kwargs.get("freq", "quarterly")

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        i18n = get_i18n()
        results = []

        if req.evidence_type == "fundamentals_raw":
            results.extend(self._fetch_overview(req))
        elif req.evidence_type == "financials_raw":
            results.extend(self._fetch_financial_statements(req))
        elif req.evidence_type == "insider_raw":
            results.extend(self._fetch_insider_transactions(req))

        return results

    def _fetch_overview(self, req: DataRequest) -> list[RawEvidence]:
        """Fetch company overview (OVERVIEW endpoint)."""
        i18n = get_i18n()
        symbol = req.ticker
        as_of_date = req.params.get("as_of_date")

        params = {"symbol": symbol}

        try:
            response = _make_api_request("OVERVIEW", params)
            data = self._parse_json_response(response)

            if not data or "Symbol" not in data:
                raise AlphaVantageRateLimitError(f"No overview data returned for {symbol}")

            # Generate summary
            pe = data.get("PERatio", "N/A")
            market_cap = data.get("MarketCapitalization", "N/A")
            profit_margin = data.get("ProfitMargin", "N/A")

            summary = i18n.t(
                "providers.alpha_vantage.fundamentals.fundamentals_summary",
                ticker=symbol,
                pe=pe,
                market_cap=market_cap,
                profit_margin=profit_margin,
            )

            return [RawEvidence(
                evidence_type="fundamentals_raw",
                provider=self.provider_id,
                method="alpha_vantage_overview",
                params=params,
                summary=summary,
                raw_payload={"fields": data, "raw_info": data},
            )]

        except (AlphaVantageNotConfiguredError, AlphaVantageRateLimitError):
            raise
        except Exception as e:
            logger.warning("Alpha Vantage overview fetch failed for %s: %s", symbol, e)
            raise

    def _fetch_financial_statements(self, req: DataRequest) -> list[RawEvidence]:
        """Fetch financial statements (BALANCE_SHEET, CASH_FLOW, INCOME_STATEMENT)."""
        symbol = req.ticker
        freq = req.params.get("freq", self.freq)
        as_of_date = req.params.get("as_of_date")

        statements = [
            ("BALANCE_SHEET", "balance_sheet"),
            ("CASH_FLOW", "cash_flow"),
            ("INCOME_STATEMENT", "income_statement"),
        ]

        results = []

        for function_name, statement_type in statements:
            params = {"symbol": symbol}

            try:
                response = _make_api_request(function_name, params)
                data = self._parse_json_response(response)

                # Alpha Vantage returns annual/quarterly reports
                reports_key = f"{statement_type.replace('_', '').lower()}Reports"
                if reports_key not in data:
                    reports_key = "annualReports" if freq == "annual" else "quarterlyReports"

                reports = data.get(reports_key, [])

                if not reports:
                    logger.warning("No %s reports found for %s", statement_type, symbol)
                    continue

                # Convert to CSV format
                import csv
                from io import StringIO

                if reports:
                    fieldnames = list(reports[0].keys())
                    output = StringIO()
                    writer = csv.DictWriter(output, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(reports)
                    csv_data = output.getvalue()
                else:
                    csv_data = ""

                summary = f"{statement_type.replace('_', ' ').title()} ({freq}) for {symbol}"

                results.append(RawEvidence(
                    evidence_type="financials_raw",
                    provider=self.provider_id,
                    method=f"alpha_vantage_{statement_type}",
                    params={"freq": freq, "as_of_date": as_of_date},
                    summary=summary,
                    raw_payload={
                        "statement_type": statement_type,
                        "freq": freq,
                        "csv": csv_data,
                    }
                ))

            except (AlphaVantageNotConfiguredError, AlphaVantageRateLimitError):
                raise
            except Exception as e:
                logger.warning("Alpha Vantage %s fetch failed for %s: %s", statement_type, symbol, e)
                # Continue with other statements

        return results

    def _fetch_insider_transactions(self, req: DataRequest) -> list[RawEvidence]:
        """Fetch insider transactions (INSIDER_TRANSACTIONS endpoint)."""
        symbol = req.ticker
        as_of_date = req.params.get("as_of_date")

        params = {"symbol": symbol}

        try:
            response = _make_api_request("INSIDER_TRANSACTIONS", params)
            data = self._parse_json_response(response)

            transactions = data.get("data", []) if isinstance(data, dict) else []

            if not transactions:
                summary = f"No insider transactions reported for symbol '{symbol}'"
                return [RawEvidence(
                    evidence_type="insider_raw",
                    provider=self.provider_id,
                    method="alpha_vantage_insider_transactions",
                    params=params,
                    summary=summary,
                    raw_payload={"insider_transactions": []}
                )]

            # Convert timestamps for JSON serialization
            for txn in transactions:
                for key, value in txn.items():
                    if isinstance(value, str) and "T" in value:
                        # Already ISO format
                        pass

            summary = f"Insider Transactions for {symbol}"

            return [RawEvidence(
                evidence_type="insider_raw",
                provider=self.provider_id,
                method="alpha_vantage_insider_transactions",
                params=params,
                summary=summary,
                raw_payload={"insider_transactions": transactions},
            )]

        except (AlphaVantageNotConfiguredError, AlphaVantageRateLimitError):
            raise
        except Exception as e:
            logger.warning("Alpha Vantage insider transactions fetch failed for %s: %s", symbol, e)
            raise

    def _parse_json_response(self, response: str | dict) -> dict:
        """Parse API response as JSON."""
        import json

        if isinstance(response, str):
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                return {}
        return response


AlphaVantageFundamentalsProvider = AlphaVantageFundamentalsProvider