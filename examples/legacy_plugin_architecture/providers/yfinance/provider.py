from __future__ import annotations
import yfinance as yf
from datetime import datetime, timezone
from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence
from tradingagents.utils import get_i18n

class YFinanceProvider(DataProvider):
    provider_id = "yfinance"
    provides = {"market_data", "fundamentals_data", "news_data"}

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        results = []
        i18n = get_i18n()
        ticker = yf.Ticker(req.ticker)

        if req.evidence_type == "market_data":
            hist = ticker.history(period="5d")
            if not hist.empty:
                recent = hist.tail(2)
                prev_close = recent.iloc[0]['Close']
                curr_close = recent.iloc[1]['Close']
                pct_change = (curr_close - prev_close) / prev_close * 100
                results.append(RawEvidence(
                    evidence_type="market_data",
                    provider=self.provider_id,
                    method="yf_history",
                    summary=i18n.t(
                        "evidence.market_summary",
                        ticker=req.ticker,
                        close=curr_close,
                        pct_change=pct_change,
                    ),
                    raw_payload={"close": curr_close, "pct_change": pct_change}
                ))
                
        elif req.evidence_type == "fundamentals_data":
            info = ticker.info
            if info:
                pe = info.get("trailingPE", "N/A")
                mcap = info.get("marketCap", "N/A")
                profit_margin = info.get("profitMargins", "N/A")
                results.append(RawEvidence(
                    evidence_type="fundamentals_data",
                    provider=self.provider_id,
                    method="yf_info",
                    summary=i18n.t(
                        "evidence.fundamentals_summary",
                        ticker=req.ticker,
                        pe=pe,
                        market_cap=mcap,
                        profit_margin=profit_margin,
                    ),
                    raw_payload={"pe": pe, "market_cap": mcap, "profit_margin": profit_margin}
                ))
                
        elif req.evidence_type == "news_data":
            news_list = ticker.news
            if news_list:
                # 取前 5 条新闻作为摘要
                summaries = []
                for item in news_list[:5]:
                    title = item.get("title", "")
                    publisher = item.get("publisher", "")
                    summaries.append(
                        i18n.t(
                            "evidence.news_item",
                            publisher=publisher,
                            title=title,
                        )
                    )
                
                combined_summary = " | ".join(summaries)
                results.append(RawEvidence(
                    evidence_type="news_data",
                    provider=self.provider_id,
                    method="yf_news",
                    summary=i18n.t(
                        "evidence.news_summary",
                        ticker=req.ticker,
                        headlines=combined_summary,
                    ),
                    raw_payload={"news_count": len(news_list), "raw_news": news_list[:5]}
                ))
        return results