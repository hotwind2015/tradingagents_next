"""Migration plugin roles package."""

from .market_analyst import MarketAnalyst
from .news_analyst import NewsAnalyst
from .fundamentals_analyst import FundamentalsAnalyst
from .sentiment_analyst import SentimentAnalyst
from .research_manager import ResearchManager
from .trader import Trader
from .risk_manager import RiskManager
from .project_manager import ProjectManager

__all__ = [
    "MarketAnalyst", "NewsAnalyst", "FundamentalsAnalyst", "SentimentAnalyst",
    "ResearchManager", "Trader", "RiskManager", "ProjectManager"
]