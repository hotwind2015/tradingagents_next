from __future__ import annotations
import yfinance as yf
from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence

class YFinanceProvider(DataProvider):
    provider_id = "yfinance"
    provides = {"market_data", "fundamentals_data"}

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        results = []
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
                    summary=f"{req.ticker} 最新收盘: {curr_close:.2f}, 两日涨跌幅: {pct_change:.2f}%",
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
                    summary=f"{req.ticker} 市盈率: {pe}, 市值: {mcap}, 利润率: {profit_margin}",
                    raw_payload={"pe": pe, "market_cap": mcap, "profit_margin": profit_margin}
                ))
        return results