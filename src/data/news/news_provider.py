"""Compatibility exports; remove after downstream migration (W01_OWNERSHIP.md)."""
from src.news.prep_adapter import NewsItem, NewsProvider, NewsResult
from src.news.rss_registry import RSS_FAST_TRADING

__all__ = ["NewsItem", "NewsProvider", "NewsResult", "RSS_FAST_TRADING"]
