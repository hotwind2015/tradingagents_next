"""AKShare Fundamentals Provider.

Provides:
- fundamentals_raw: Company overview and key metrics (东财个股信息)
- financials_raw: Financial statements (Balance Sheet, Income Statement, Cash Flow)
- insider_raw: Insider/major holder transactions (东财/同花顺)
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from tradingagents.providers.akshare._common import (
    classify_akshare_error,
    get_provider_i18n_key,
    handle_akshare_error,
    rename_columns,
    to_akshare_date,
    t_provider,
)
from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence
from tradingagents.utils import get_i18n
import io
from datetime import datetime

logger = logging.getLogger(__name__)

# =============================================================================
# Column Mapping
# =============================================================================

# 个股基本信息 (stock_individual_info_em)
INDIVIDUAL_INFO_COL_MAP = {
    "项目": "item",
    "值": "value",
}

# 财务分析指标
FINANCIAL_INDICATOR_COL_MAP = {
    "项目": "item",
    "值": "value",
}

# 资产负债表
BALANCE_SHEET_COL_MAP = {
    "报表日期": "report_date",
    "报表类型": "report_type",
    # 常用字段
    "货币资金": "cash_and_equivalents",
    "应收账款": "accounts_receivable",
    "存货": "inventory",
    "固定资产": "fixed_assets",
    "总资产": "total_assets",
    "应付账款": "accounts_payable",
    "短期借款": "short_term_borrowings",
    "长期借款": "long_term_borrowings",
    "股东权益合计": "total_equity",
}

# 利润表
PROFIT_SHEET_COL_MAP = {
    "报表日期": "report_date",
    "营业收入": "revenue",
    "营业成本": "cost_of_revenue",
    "营业利润": "operating_profit",
    "净利润": "net_income",
    "基本每股收益": "basic_eps",
    "稀释每股收益": "diluted_eps",
}

# 现金流量表
CASH_FLOW_COL_MAP = {
    "报表日期": "report_date",
    "经营活动产生的现金流量净额": "operating_cash_flow",
    "投资活动产生的现金流量净额": "investing_cash_flow",
    "筹资活动产生的现金流量净额": "financing_cash_flow",
    "自由现金流": "free_cash_flow",
}

# 增减持
HOLDER_TRADE_COL_MAP = {
    "序号": "index",
    "变动人": "holder_name",
    "变动股数": "change_shares",
    "变动后持股数": "hold_shares_after",
    "变动均价": "avg_price",
    "变动原因": "reason",
    "公告日期": "announce_date",
}

SHAREHOLDER_CHANGE_COL_MAP = {
    "变动日期": "change_date",
    "变动人": "holder_name",
    "变动股数": "change_shares",
    "变动后持股数": "hold_shares_after",
    "变动均价": "avg_price",
    "变动原因": "reason",
    "公告日期": "announce_date",
}


class AKShareFundamentalsProvider:
    """AKShare Fundamentals Provider.

    Provides:
    - fundamentals_raw: Company overview (东财个股信息)
    - financials_raw: Financial statements (Balance Sheet, Income Statement, Cash Flow)
    - insider_raw: Insider/major holder transactions (东财/同花顺)
    """

    provider_id = "akshare_fundamentals"
    provides = {"fundamentals_raw", "financials_raw", "insider_raw"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        self.freq = "quarterly"  # quarterly or annual

    def _serialize_records(self, records: list) -> list:
        """Convert datetime/date objects in records to ISO format strings for JSON serialization."""
        serialized = []
        for record in records:
            serialized_record = {}
            for key, value in record.items():
                if isinstance(value, (pd.Timestamp, datetime)):
                    serialized_record[key] = value.isoformat()
                elif hasattr(value, 'isoformat'):  # Handles date objects too
                    serialized_record[key] = value.isoformat()
                else:
                    serialized_record[key] = value
            serialized.append(serialized_record)
        return serialized

    def fetch(self, req: DataRequest) -> list:
        results = []

        if req.evidence_type == "fundamentals_raw":
            results.extend(self._fetch_overview(req))
        elif req.evidence_type == "financials_raw":
            results.extend(self._fetch_financial_statements(req))
        elif req.evidence_type == "insider_raw":
            results.extend(self._fetch_insider_transactions(req))

        return results

    # -------------------------------------------------------------------------
    # fundamentals_raw: Company overview
    # -------------------------------------------------------------------------
    def _fetch_overview(self, req: DataRequest) -> list:
        symbol = req.ticker

        try:
            import akshare as ak
            df = ak.stock_individual_info_em(symbol=symbol)

            if df.empty:
                raise Exception(f"No overview data for {symbol}")

            # Standardize columns
            df = df.rename(columns={"项目": "item", "值": "value"})

            # Extract key metrics for summary
            data_dict = dict(zip(df["item"], df["value"]))
            pe = data_dict.get("市盈率", "N/A")
            market_cap = data_dict.get("总市值", "N/A")
            profit_margin = data_dict.get("利润率", "N/A")

            from tradingagents.utils import get_i18n
            i18n = get_i18n()

            summary = i18n.t(
                "providers.akshare.fundamentals.fundamentals_summary",
                ticker=req.ticker,
                pe=pe,
                market_cap=market_cap,
                profit_margin=profit_margin,
            )

            return [RawEvidence(
                evidence_type="fundamentals_raw",
                provider=self.provider_id,
                method="akshare_individual_info_em",
                params={},
                summary=summary,
                raw_payload={
                    "fields": data_dict,
                    "raw_info": df.to_dict(orient="records"),
                }
            )]

        except Exception as e:
            logger.warning(f"Overview fetch failed for {symbol}: {e}")
            raise

    # -------------------------------------------------------------------------
    # financials_raw: Financial statements (3 tables)
    # -------------------------------------------------------------------------
    def _fetch_financial_statements(self, req: DataRequest) -> list:
        symbol = req.ticker
        freq = req.params.get("freq", "quarterly")

        results = []
        statements = [
            ("BALANCE_SHEET", "balance_sheet", "资产负债表", BALANCE_SHEET_COL_MAP),
            ("PROFIT_SHEET", "income_statement", "利润表", PROFIT_SHEET_COL_MAP),
            ("CASH_FLOW", "cash_flow", "现金流量表", CASH_FLOW_COL_MAP),
        ]

        for func_name, stmt_type, display_name, col_map in statements:
            try:
                import akshare as ak

                if func_name == "BALANCE_SHEET":
                    df = ak.stock_balance_sheet_by_report_em(symbol=req.ticker)
                elif func_name == "PROFIT_SHEET":
                    df = ak.stock_profit_sheet_by_report_em(symbol=req.ticker)
                elif func_name == "CASH_FLOW":
                    df = ak.stock_cash_flow_sheet_by_report_em(symbol=req.ticker)
                else:
                    continue

                if df is None or df.empty:
                    logger.warning(f"No {stmt_type} data for {req.ticker}")
                    continue

                # Standardize column names
                df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

                # Convert to CSV
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False)
                csv_data = csv_buffer.getvalue()

                summary = f"{display_name} ({freq}) for {req.ticker}"

                results.append(RawEvidence(
                    evidence_type="financials_raw",
                    provider=self.provider_id,
                    method=f"akshare_{func_name.lower()}",
                    params={"freq": freq, "stmt_type": stmt_type},
                    summary=summary,
                    raw_payload={
                        "statement_type": stmt_type,
                        "freq": freq,
                        "csv": csv_data,
                    }
                ))

            except Exception as e:
                logger.warning(f"Failed to fetch {stmt_type} for {req.ticker}: {e}")
                results.append(RawEvidence(
                    evidence_type="financials_raw",
                    provider=self.provider_id,
                    method=f"akshare_{func_name.lower()}",
                    params={"freq": freq, "stmt_type": stmt_type},
                    summary=f"{display_name} fetch failed: {e}",
                    raw_payload={"error": str(e), "statement_type": stmt_type},
                ))

        return results

    # -------------------------------------------------------------------------
    # insider_raw: Insider/major holder transactions
    # -------------------------------------------------------------------------
    def _fetch_insider_transactions(self, req: DataRequest) -> list:
        symbol = req.ticker

        results = []

        # 1. 东财大股东/高管持股
        try:
            import akshare as ak
            df = ak.stock_main_stock_holder(symbol=req.ticker)
            if not df.empty:
                df = df.rename(columns={
                    "序号": "index",
                    "股东名称": "holder_name",
                    "持股数量": "hold_shares",
                    "持股比例": "hold_ratio",
                    "股份性质": "share_nature",
                })

                summary = f"Major holders for {req.ticker}"
                results.append(RawEvidence(
                    evidence_type="insider_raw",
                    provider=self.provider_id,
                    method="akshare_main_stock_holder",
                    params={},
                    summary=summary,
                    raw_payload={
                        "holder_type": "major_holders",
                        "holders": self._serialize_records(df.to_dict(orient="records")),
                    }
                ))
        except Exception as e:
            logger.warning(f"Major holders fetch failed for {symbol}: {e}")

        # 2. 同花顺股东变动
        try:
            df = ak.stock_shareholder_change_ths(symbol=req.ticker)
            if not df.empty:
                df = df.rename(columns={
                    "变动日期": "change_date",
                    "变动人": "holder_name",
                    "变动股数": "change_shares",
                    "变动均价": "avg_price",
                    "变动原因": "reason",
                })

                summary = f"Shareholder changes for {req.ticker}"
                results.append(RawEvidence(
                    evidence_type="insider_raw",
                    provider=self.provider_id,
                    method="akshare_shareholder_change_ths",
                    params={},
                    summary=summary,
                    raw_payload={
                        "holder_type": "shareholder_changes",
                        "transactions": self._serialize_records(df.to_dict(orient="records")),
                    }
                ))
        except Exception as e:
            logger.warning(f"Shareholder changes fetch failed for {symbol}: {e}")

        if not results:
            # Return empty evidence if all failed
            return [RawEvidence(
                evidence_type="insider_raw",
                provider=self.provider_id,
                method="akshare_insider",
                params={},
                summary=f"No insider data available for {req.ticker}",
                raw_payload={"insider_transactions": []},
            )]

        return results


AKShareFundamentalsProvider = AKShareFundamentalsProvider