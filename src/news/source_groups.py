from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


SourceGroupId = Literal[
    "FAST_TRADING",
    "PREP_EXTENDED",
    "MACRO_LONG_HORIZON",
    "VERIFIED_RSS_LEGACY",
]


@dataclass(frozen=True)
class NewsSourceGroup:
    """Strategy-neutral description of an ordered source group."""

    group_id: SourceGroupId
    urls: tuple[str, ...] = ()
    purpose: str = ""
    runtime_scope: str = ""
    ordering_significant: bool = True
    active_runtime_group: bool = True
    catalogue_path: str | None = None
    compatibility_exports: tuple[str, ...] = ()


FAST_TRADING_URLS: tuple[str, ...] = (
    "https://www.benzinga.com/feed",
    "https://www.globenewswire.com/RssFeed?Category=Finance",
    "https://www.reuters.com/markets/rss",
    "https://www.marketwatch.com/rss/topstories",
    "https://feeds.businessinsider.com/custom/all",
    "https://seekingalpha.com/feed",
    "http://rss.cnn.com/rss/edition_business.rss",
)

PREP_EXTENDED_URLS: tuple[str, ...] = (
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "https://fortune.com/rss",
    "https://www.forbes.com/business/feed2",
    "https://www.forbes.com/finance/feed2",
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://www.bbc.com/news/business/rss.xml",
    "https://feeds.skynews.com/feeds/rss/world.xml",
    "https://www.france24.com/en/rss",
    "https://markets.businessinsider.com/rss",
    "https://www.investing.com/rss/news.rss",
    "https://www.marketbeat.com/feed",
    "https://techcrunch.com/rss",
    "https://venturebeat.com/feed",
)

MACRO_LONG_HORIZON_URLS: tuple[str, ...] = (
    "https://www.federalreserve.gov/feeds/press_all.xml",
    "https://www.bankofcanada.ca/feed",
    "https://www.bis.org/doclist/rss_all_categories.rss",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml",
    "https://www.economist.com/finance-and-economics/rss.xml",
    "https://www.economist.com/the-world-this-week/rss.xml",
)


NEWS_SOURCE_GROUPS: dict[SourceGroupId, NewsSourceGroup] = {
    "FAST_TRADING": NewsSourceGroup(
        group_id="FAST_TRADING",
        urls=FAST_TRADING_URLS,
        purpose="Fast bounded trading-time RSS group used by current scanner/news paths.",
        runtime_scope="active_scanner_and_prep_compatibility",
        compatibility_exports=("RSS_FAST_TRADING",),
    ),
    "PREP_EXTENDED": NewsSourceGroup(
        group_id="PREP_EXTENDED",
        urls=PREP_EXTENDED_URLS,
        purpose="Extended/preparation RSS group used by bounded unresolved-symbol fallback.",
        runtime_scope="prep_and_active_unresolved_fallback",
        compatibility_exports=("RSS_PREP_EXTENDED",),
    ),
    "MACRO_LONG_HORIZON": NewsSourceGroup(
        group_id="MACRO_LONG_HORIZON",
        urls=MACRO_LONG_HORIZON_URLS,
        purpose="Macro and long-horizon RSS group available for non-Ross future consumers.",
        runtime_scope="long_horizon_metadata",
        compatibility_exports=("RSS_MACRO_LONG_HORIZON",),
    ),
    "VERIFIED_RSS_LEGACY": NewsSourceGroup(
        group_id="VERIFIED_RSS_LEGACY",
        purpose="Historical verified RSS catalogue consumed by legacy scanner/news_engine code.",
        runtime_scope="legacy_metadata_only",
        active_runtime_group=False,
        catalogue_path="verified_rss.txt",
    ),
}


def get_source_group(group_id: SourceGroupId) -> NewsSourceGroup:
    return NEWS_SOURCE_GROUPS[group_id]


def get_source_group_urls(group_id: SourceGroupId) -> tuple[str, ...]:
    return get_source_group(group_id).urls


def list_source_groups(*, include_legacy: bool = True) -> tuple[NewsSourceGroup, ...]:
    groups = tuple(NEWS_SOURCE_GROUPS.values())
    if include_legacy:
        return groups
    return tuple(group for group in groups if group.active_runtime_group)


__all__ = [
    "FAST_TRADING_URLS",
    "MACRO_LONG_HORIZON_URLS",
    "NEWS_SOURCE_GROUPS",
    "NewsSourceGroup",
    "PREP_EXTENDED_URLS",
    "SourceGroupId",
    "get_source_group",
    "get_source_group_urls",
    "list_source_groups",
]
