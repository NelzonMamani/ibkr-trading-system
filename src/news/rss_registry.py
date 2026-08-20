"""Compatibility exports for canonical News Intelligence source groups."""

from __future__ import annotations

from src.news.source_groups import get_source_group_urls


RSS_FAST_TRADING = list(get_source_group_urls("FAST_TRADING"))
RSS_PREP_EXTENDED = list(get_source_group_urls("PREP_EXTENDED"))
RSS_MACRO_LONG_HORIZON = list(get_source_group_urls("MACRO_LONG_HORIZON"))

RSS_REGISTRY = {
    "FAST_TRADING": RSS_FAST_TRADING,
    "PREP_EXTENDED": RSS_PREP_EXTENDED,
    "MACRO_LONG_HORIZON": RSS_MACRO_LONG_HORIZON,
}

__all__ = [
    "RSS_FAST_TRADING",
    "RSS_MACRO_LONG_HORIZON",
    "RSS_PREP_EXTENDED",
    "RSS_REGISTRY",
]
