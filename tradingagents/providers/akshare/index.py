"""AKShare Index/Sector/Fund Flow Provider.

Provides:
- index_raw: Index historical data (上证/深证/创业板/科创板等)
- sector_raw: Sector/industry/concept board data
- fund_flow_raw: Fund flow data (individual, sector, market)
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

logger = logging.getLogger(__name__)

# =============================================================================
# Column Mappings
# =============================================================================

INDEX_COL_MAP = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "pct_change",
    "涨跌额": "change",
}

BOARD_COL_MAP = {
    "排名": "rank",
    "板块名称": "board_name",
    "板块代码": "board_code",
    "最新价": "price",
    "涨跌幅": "pct_change",
    "总市值": "total_market_cap",
    "换手率": "turnover_rate",
    "领涨股": "leader_stock",
    "领涨股-涨跌幅": "leader_pct_change",
}

FUND_FLOW_COL_MAP = {
    "排名": "rank",
    "代码": "symbol",
    "名称": "name",
    "最新价": "price",
    "涨跌幅": "pct_change",
    "主力净流入-净额": "main_net_inflow",
    "主力净流入-净占比": "main_net_inflow_pct",
    "超大单净流入-净额": "super_large_net_inflow",
    "超大单净流入-净占比": "super_large_net_inflow_pct",
    "大单净流入-净额": "large_net_inflow",
    "大单净流入-净占比": "large_net_inflow_pct",
    "中单净流入-净额": "medium_net_inflow",
    "中单净流入-净占比": "medium_net_inflow_pct",
    "小单净流入-净额": "small_net_inflow",
    "小单净流入-净占比": "small_net_inflow_pct",
}


class AKShareIndexProvider:
    """AKShare Index/Sector/Fund Flow Provider.

    Provides:
    - index_raw: Index historical data (上证/深证/创业板/科创板等)
    - sector_raw: Sector/industry/concept board data
    - fund_flow_raw: Fund flow data (market, sector, individual)
    """

    provider_id = "akshare_index"
    provides = {"index_raw", "sector_raw", "fund_flow_raw"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        self.default_look_back_days = kwargs.get("look_back_days", 365)

    def fetch(self, req: DataRequest) -> list:
        results = []

        if req.evidence_type == "index_raw":
            results.extend(self._fetch_index(req))
        elif req.evidence_type == "sector_raw":
            results.extend(self._fetch_sector(req))
        elif req.evidence_type == "fund_flow_raw":
            results.extend(self._fetch_fund_flow(req))

        return results

    # -------------------------------------------------------------------------
    # index_raw: Index historical data
    # -------------------------------------------------------------------------
    def _fetch_index(self, req: DataRequest) -> list:
        symbol = req.params.get("symbol", "000001")  # Default: 上证指数
        period = req.params.get("period", "daily")
        start_date = req.params.get("start_date", "20240101")
        end_date = req.params.get("end_date", "20241231")

        try:
            import akshare as ak
            df = ak.index_zh_hist_em(
                symbol=symbol,
                period=req.params.get("period", "daily"),
                start_date=start_date,
                end_date=end_date
            )

            if df is None or df.empty:
                raise Exception(f"No index data for {symbol}")

            # Standardize columns
            df = df.rename(columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "振幅": "amplitude",
                "涨跌幅": "pct_change",
                "涨跌额": "change",
            })

            # Ensure date format
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

            # Numeric columns
            for col in ["open", "high", "low", "close", "volume", "amount"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # Generate summary
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            close_val = float(latest.get("close", 0))
            prev_close = float(prev.get("close", 0))
            pct_change = ((float(latest.get("close", 0)) - prev_close) / prev_close * 100) if prev_close else 0

            from tradingagents.utils import get_i18n
            i18n = get_i18n()

            summary = i18n.t(
                "providers.akshare.index.index_summary",
                index_name=symbol,
                close=close_val,
                pct_change=pct_change,
            )

            return [RawEvidence(
                evidence_type="index_raw",
                provider="akshare_index",
                method="akshare_index_hist_em",
                params={"symbol": symbol, "period": "daily", "start_date": "20240101", "end_date": "20241231"},
                summary=summary,
                raw_payload={
                    "symbol": symbol,
                    "records": len(df),
                    "data": df.to_dict(orient="records"),
                }
            )]

        except Exception as e:
            logger.warning(f"Index fetch failed for {symbol}: {e}")
            return [RawEvidence(
                evidence_type="index_raw",
                provider="akshare_index",
                method="akshare_index_failed",
                params={"symbol": symbol},
                summary=f"Index {symbol} fetch failed: {e}",
                raw_payload={"error": str(e)},
            )]

    # -------------------------------------------------------------------------
    # sector_raw: Sector/industry/concept boards
    # -------------------------------------------------------------------------
    def _fetch_sector(self, req: DataRequest) -> list:
        results = []

        # 1. Industry boards
        try:
            import akshare as ak
            df = ak.stock_board_industry_name_em()
            if not df.empty:
                df = df.rename(columns={
                    "排名": "rank",
                    "板块名称": "board_name",
                    "板块代码": "board_code",
                    "最新价": "price",
                    "涨跌幅": "pct_change",
                    "总市值": "total_market_cap",
                    "换手率": "turnover_rate",
                    "领涨股": "leader_stock",
                    "领涨股-涨跌幅": "leader_pct_change",
                })

                summary = f"Industry boards: {len(df)} boards"
                results.append(RawEvidence(
                    evidence_type="sector_raw",
                    provider="akshare_index",
                    method="akshare_industry_boards",
                    params={},
                    summary=summary,
                    raw_payload={
                        "board_type": "industry",
                        "count": len(df),
                        "boards": df.to_dict(orient="records"),
                    }
                ))
        except Exception as e:
            logger.warning(f"Industry boards fetch failed: {e}")

        # 2. Concept boards
        try:
            df = ak.stock_board_concept_name_em()
            if not df.empty:
                df = df.rename(columns={
                    "排名": "rank",
                    "板块名称": "board_name",
                    "板块代码": "board_code",
                    "最新价": "price",
                    "涨跌幅": "pct_change",
                    "总市值": "total_market_cap",
                    "换手率": "turnover_rate",
                    "领涨股": "leader_stock",
                    "领涨股-涨跌幅": "leader_pct_change",
                })

                summary = f"Concept boards: {len(df)} boards"
                results.append(RawEvidence(
                    evidence_type="sector_raw",
                    provider="akshare_index",
                    method="akshare_concept_boards",
                    params={},
                    summary=summary,
                    raw_payload={
                        "board_type": "concept",
                        "count": len(df),
                        "boards": df.to_dict(orient="records"),
                    }
                ))
        except Exception as e:
            logger.warning(f"Concept boards fetch failed: {e}")

        return results

    # -------------------------------------------------------------------------
    # fund_flow_raw: Fund flow data
    # -------------------------------------------------------------------------
    def _fetch_fund_flow(self, req: DataRequest) -> list:
        results = []

        # 1. Individual stock fund flow (同花顺)
        try:
            import akshare as ak
            symbol = req.params.get("symbol", "000001")

            # Try different time windows
            for window in ["3天排行", "5天排行", "10天排行"]:
                try:
                    df = ak.stock_fund_flow_individual_ths(symbol=window)
                    if not df.empty:
                        df = df.rename(columns={
                            "排名": "rank",
                            "代码": "symbol",
                            "名称": "name",
                            "最新价": "price",
                            "涨跌幅": "pct_change",
                            "主力净流入-净额": "main_net_inflow",
                            "主力净流入-净占比": "main_net_inflow_pct",
                            "超大单净流入-净额": "super_large_net_inflow",
                            "超大单净流入-净占比": "super_large_net_inflow_pct",
                            "大单净流入-净额": "large_net_inflow",
                            "大单净流入-净占比": "large_net_inflow_pct",
                            "中单净流入-净额": "medium_net_inflow",
                            "中单净流入-净占比": "medium_net_inflow_pct",
                            "小单净流入-净额": "small_net_inflow",
                            "小单净流入-净占比": "small_net_inflow_pct",
                        })

                        summary = f"Fund flow ({window}): {len(df)} stocks"
                        results.append(RawEvidence(
                            evidence_type="fund_flow_raw",
                            provider="akshare_index",
                            method="akshare_fund_flow_ths",
                            params={"window": window},
                            summary=summary,
                            raw_payload={
                                "window": window,
                                "count": len(df),
                                "data": df.to_dict(orient="records"),
                            }
                        ))
                        break  # Use first successful window
                except Exception as e:
                    logger.warning(f"Fund flow {window} failed: {e}")
                    continue
        except Exception as e:
            logger.warning(f"Individual fund flow failed: {e}")

        # 2. Sector fund flow (同花顺)
        try:
            df = ak.stock_fund_flow_industry_ths()
            if not df.empty:
                df = df.rename(columns={
                    "排名": "rank",
                    "板块名称": "sector_name",
                    "涨跌幅": "pct_change",
                    "主力净流入-净额": "main_net_inflow",
                    "主力净流入-净占比": "main_net_inflow_pct",
                })

                summary = f"Sector fund flow: {len(df)} sectors"
                results.append(RawEvidence(
                    evidence_type="fund_flow_raw",
                    provider="akshare_index",
                    method="akshare_sector_fund_flow",
                    params={},
                    summary=summary,
                    raw_payload={
                        "type": "industry",
                        "count": len(df),
                        "data": df.to_dict(orient="records"),
                    }
                ))
        except Exception as e:
            logger.warning(f"Sector fund flow failed: {e}")

        # 3. Concept fund flow (同花顺)
        try:
            df = ak.stock_fund_flow_concept_ths()
            if not df.empty:
                df = df.rename(columns={
                    "排名": "rank",
                    "板块名称": "concept_name",
                    "涨跌幅": "pct_change",
                    "主力净流入-净额": "main_net_inflow",
                    "主力净流入-净占比": "main_net_inflow_pct",
                })

                summary = f"Concept fund flow: {len(df)} concepts"
                results.append(RawEvidence(
                    evidence_type="fund_flow_raw",
                    provider="akshare_index",
                    method="akshare_concept_fund_flow",
                    params={},
                    summary=summary,
                    raw_payload={
                        "type": "concept",
                        "count": len(df),
                        "data": df.to_dict(orient="records"),
                    }
                ))
        except Exception as e:
            logger.warning(f"Concept fund flow failed: {e}")

        return results


AKShareIndexProvider = AKShareIndexProvider