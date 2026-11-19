from __future__ import annotations

from tradingagents.providers.base import DataProvider, DataRequest, RawEvidence


class MockProvider(DataProvider):
    provider_id = "mock"
    provides = {"fundamentals"}

    def fetch(self, req: DataRequest) -> list[RawEvidence]:
        if req.evidence_type == "fundamentals":
            return [
                RawEvidence(
                    evidence_type="fundamentals",
                    provider=self.provider_id,
                    method="fetch",
                    summary="营收同比 +15%，净利润 +8%，现金流健康。",
                    raw_payload={"revenue_growth": 0.15, "net_profit_growth": 0.08},
                )
            ]
        return []