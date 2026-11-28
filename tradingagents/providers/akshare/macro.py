"""AKShare Macro Provider.

Provides:
- macro_raw: Macroeconomic indicators from 东财/统计局/金十
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
    t_provider,
)
from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence
from tradingagents.utils import get_i18n

logger = logging.getLogger(__name__)

# =============================================================================
# Macro Indicator Configuration
# =============================================================================

MACRO_INDICATORS = {
    "cpi": {
        "func": "macro_china_cpi",
        "name": "CPI",
        "desc": "居民消费价格指数",
        "col_map": {
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
        },
    },
    "ppi": {
        "func": "macro_china_ppi",
        "name": "PPI",
        "desc": "工业生产者出厂价格指数",
        "col_map": {
            "月份": "date",
            "指数": "index",
            "同比增长": "yoy",
            "环比增长": "mom",
        },
    },
    "gdp": {
        "func": "macro_china_gdp",
        "name": "GDP",
        "desc": "国内生产总值",
        "col_map": {
            "季度": "quarter",
            "国内生产总值-绝对值": "gdp_current",
            "国内生产总值-同比增长": "gdp_yoy",
            "第一产业-绝对值": "primary_current",
            "第一产业-同比增长": "primary_yoy",
            "第二产业-绝对值": "secondary_current",
            "第二产业-同比增长": "secondary_yoy",
            "第三产业-绝对值": "tertiary_current",
            "第三产业-同比增长": "tertiary_yoy",
        },
    },
    "pmi": {
        "func": "macro_china_pmi",
        "name": "PMI",
        "desc": "采购经理指数",
        "col_map": {
            "月份": "date",
            "制造业PMI-指数": "manufacturing_pmi",
            "制造业PMI-同比增长": "manufacturing_yoy",
            "非制造业PMI-指数": "non_manufacturing_pmi",
            "非制造业PMI-同比增长": "non_manufacturing_yoy",
        },
    },
    "money_supply": {
        "func": "macro_china_money_supply_em",
        "name": "Money Supply",
        "desc": "货币供应量",
        "col_map": {
            "月份": "date",
            "货币供应量(M2)-绝对值(亿元)": "m2_current",
            "货币供应量(M2)-同比增长": "m2_yoy",
            "货币供应量(M2)-环比增长": "m2_mom",
            "货币供应量(M1)-绝对值(亿元)": "m1_current",
            "货币供应量(M1)-同比增长": "m1_yoy",
            "货币供应量(M1)-环比增长": "m1_mom",
            "流通中现金(M0)-绝对值(亿元)": "m0_current",
            "流通中现金(M0)-同比增长": "m0_yoy",
            "流通中现金(M0)-环比增长": "m0_mom",
        },
    },
    "fx_gold": {
        "func": "macro_china_fx_gold_em",
        "name": "FX & Gold",
        "desc": "外汇黄金储备",
        "col_map": {
            "月份": "date",
            "外汇储备-绝对值(亿美元)": "fx_reserves",
            "外汇储备-同比增长": "fx_yoy",
            "外汇储备-环比增长": "fx_mom",
            "黄金储备-绝对值(吨)": "gold_reserves",
            "黄金储备-同比增长": "gold_yoy",
            "黄金储备-环比增长": "gold_mom",
        },
    },
    "gdp_yearly": {
        "func": "macro_china_gdp_yearly",
        "name": "GDP Yearly",
        "desc": "年度GDP",
        "col_map": {
            "日期": "date",
            "国内生产总值-绝对值": "gdp_current",
            "国内生产总值-同比增长": "gdp_yoy",
        },
    },
    "cpi_monthly": {
        "func": "macro_china_cpi_monthly",
        "name": "CPI Monthly",
        "desc": "月度CPI",
        "col_map": {},
    },
    "cpi_yearly": {
        "func": "macro_china_cpi_yearly",
        "name": "CPI Yearly",
        "desc": "年度CPI",
        "col_map": {},
    },
    "ppi_monthly": {
        "func": "macro_china_ppi_monthly",
        "name": "PPI Monthly",
        "desc": "月度PPI",
        "col_map": {},
    },
    "ppi_yearly": {
        "func": "macro_china_ppi_yearly",
        "name": "PPI Yearly",
        "desc": "年度PPI",
        "col_map": {},
    },
    "interest_rate": {
        "func": "macro_china_interest_rate",
        "name": "Interest Rate",
        "desc": "利率",
        "col_map": {},
    },
    "fx_reserves": {
        "func": "macro_china_fx_reserves",
        "name": "FX Reserves",
        "desc": "外汇储备",
        "col_map": {},
    },
    "trade_balance": {
        "func": "macro_china_trade_balance",
        "name": "Trade Balance",
        "desc": "贸易差额",
        "col_map": {},
    },
    "industrial_value_added": {
        "func": "macro_china_industrial_value_added",
        "name": "Industrial Value Added",
        "desc": "工业增加值",
        "col_map": {},
    },
    "retail_sales": {
        "func": "macro_china_retail_sales",
        "name": "Retail Sales",
        "desc": "社会消费品零售总额",
        "col_map": {},
    },
    "fixed_asset_investment": {
        "func": "macro_china_fixed_asset_investment",
        "name": "Fixed Asset Investment",
        "desc": "固定资产投资",
        "col_map": {},
    },
    "new_financial_credit": {
        "func": "macro_china_new_financial_credit",
        "name": "New Financial Credit",
        "desc": "社会融资规模增量",
        "col_map": {},
    },
    "social_financing": {
        "func": "macro_china_social_financing",
        "name": "Social Financing",
        "desc": "社会融资规模",
        "col_map": {},
    },
}


class AKShareMacroProvider:
    """AKShare Macro Provider.

    Provides:
    - macro_raw: Macroeconomic indicators from 东财/统计局/金十
    """

    provider_id = "akshare_macro"
    provides = {"macro_raw"}
    plugin_type = "provider"

    def __init__(self, **kwargs):
        self.default_lookback_days = kwargs.get("look_back_days", 365)
        self.indicators = kwargs.get("indicators", list(MACRO_INDICATORS.keys()))

    def fetch(self, req: DataRequest) -> list:
        i18n = get_i18n()
        results = []

        # Get requested indicators
        requested = req.params.get("indicator", self.indicators)
        if isinstance(requested, str):
            requested = [requested]

        as_of_date = req.params.get("as_of_date", "20241231")
        look_back_days = req.params.get("look_back_days", self.default_lookback_days)

        for indicator in requested:
            if indicator not in MACRO_INDICATORS:
                logger.warning(f"Unknown macro indicator: {indicator}")
                continue

            config = MACRO_INDICATORS[indicator]
            func_name = config["func"]

            try:
                import akshare as ak
                func = getattr(ak, func_name)
                df = func()

                if df is None or df.empty:
                    raise Exception(f"No data returned for {indicator}")

                # Standardize columns
                col_map = config.get("col_map", {})
                if col_map:
                    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

                # Generate summary
                summary = f"{config['name']} ({config['desc']}) - Latest data as of {as_of_date}"

                results.append(RawEvidence(
                    evidence_type="macro_raw",
                    provider=self.provider_id,
                    method=f"akshare_{func_name}",
                    params={"indicator": indicator, "as_of_date": as_of_date, "look_back_days": look_back_days},
                    summary=summary,
                    raw_payload={
                        "indicator": indicator,
                        "name": config["name"],
                        "description": config["desc"],
                        "data": df.to_dict(orient="records"),
                        "as_of_date": as_of_date,
                        "look_back_days": look_back_days,
                    }
                ))

            except Exception as e:
                logger.warning(f"Failed to fetch macro indicator {indicator}: {e}")
                results.append(RawEvidence(
                    evidence_type="macro_raw",
                    provider=self.provider_id,
                    method=f"akshare_{func_name}",
                    params={"indicator": indicator, "as_of_date": as_of_date},
                    summary=f"{MACRO_INDICATORS[indicator]['name']} fetch failed: {e}",
                    raw_payload={
                        "indicator": indicator,
                        "error": str(e),
                        "as_of_date": as_of_date,
                    }
                ))

        return results


AKShareMacroProvider = AKShareMacroProvider