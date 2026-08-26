from __future__ import annotations

import ast
from src.config.config_resolver import set_config_overrides
from pathlib import Path

from src.data.news import news_provider
from src.news import rss_registry
from src.news.source_groups import (
    NEWS_SOURCE_GROUPS,
    get_source_group,
    get_source_group_urls,
    list_source_groups,
)
from src.scanner import scanner_runner


SOURCE_GROUPS_MODULE = Path("src/news/source_groups.py")
DOC_PATH = Path("docs/architecture/NEWS_INTELLIGENCE_CONTRACT.md")

EXPECTED_FAST_TRADING = (
    "https://www.benzinga.com/feed",
    "https://www.globenewswire.com/RssFeed?Category=Finance",
    "https://www.globenewswire.com/RssFeed/industry/9000-Technology/feedTitle/GlobeNewswire%20-%20Industry%20News%20on%20Technology",
    "https://www.reuters.com/markets/rss",
    "https://www.marketwatch.com/rss/topstories",
    "https://feeds.businessinsider.com/custom/all",
    "https://seekingalpha.com/feed",
    "http://rss.cnn.com/rss/edition_business.rss",
)

EXPECTED_PREP_EXTENDED = (
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

EXPECTED_MACRO_LONG_HORIZON = (
    "https://www.federalreserve.gov/feeds/press_all.xml",
    "https://www.bankofcanada.ca/feed",
    "https://www.bis.org/doclist/rss_all_categories.rss",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml",
    "https://www.economist.com/finance-and-economics/rss.xml",
    "https://www.economist.com/the-world-this-week/rss.xml",
)


def test_pr1065_active_source_group_memberships_and_order_are_unchanged() -> None:
    assert get_source_group_urls("FAST_TRADING") == EXPECTED_FAST_TRADING
    assert get_source_group_urls("PREP_EXTENDED") == EXPECTED_PREP_EXTENDED
    assert get_source_group_urls("MACRO_LONG_HORIZON") == EXPECTED_MACRO_LONG_HORIZON

    assert rss_registry.RSS_FAST_TRADING == list(EXPECTED_FAST_TRADING)
    assert rss_registry.RSS_PREP_EXTENDED == list(EXPECTED_PREP_EXTENDED)
    assert rss_registry.RSS_MACRO_LONG_HORIZON == list(EXPECTED_MACRO_LONG_HORIZON)
    assert rss_registry.RSS_REGISTRY == {
        "FAST_TRADING": list(EXPECTED_FAST_TRADING),
        "PREP_EXTENDED": list(EXPECTED_PREP_EXTENDED),
        "MACRO_LONG_HORIZON": list(EXPECTED_MACRO_LONG_HORIZON),
    }


def test_pr1065_existing_runtime_imports_receive_compatibility_lists() -> None:
    assert scanner_runner.RSS_FAST_TRADING == list(EXPECTED_FAST_TRADING)
    assert scanner_runner.RSS_PREP_EXTENDED == list(EXPECTED_PREP_EXTENDED)
    assert news_provider.RSS_FAST_TRADING == list(EXPECTED_FAST_TRADING)


def test_pr1065_scanner_runtime_selects_same_ordered_fast_and_extended_sources(monkeypatch, tmp_path) -> None:
    set_config_overrides({"NEWS_CACHE_FILE": str(tmp_path / "news_cache.json")})
    captured: dict[str, list[str]] = {}

    def fake_fast(symbols, sources, **kwargs):
        captured["fast"] = list(sources)
        return {symbol: [] for symbol in symbols}, scanner_runner.RssFailureSummary(
            total_sources=len(sources),
            failure_count=0,
            failures_by_domain={},
            reason=None,
            tier_source_counts={"fast": len(sources)},
        )

    def fake_extended(symbols, sources, **kwargs):
        captured["extended"] = list(sources)
        return {symbol: [] for symbol in symbols}, scanner_runner.RssFailureSummary(
            total_sources=len(sources),
            failure_count=0,
            failures_by_domain={},
            reason=None,
            tier_source_counts={"extended": len(sources)},
        )

    monkeypatch.setattr(scanner_runner, "fetch_fast_headlines_for_symbols", fake_fast)
    monkeypatch.setattr(scanner_runner, "fetch_headlines_for_symbols", fake_extended)

    _news_by_symbol, diagnostics = scanner_runner._enrich_news_context(["PR65A"], "IBKR")

    assert captured["fast"] == list(EXPECTED_FAST_TRADING)
    assert captured["extended"] == list(EXPECTED_PREP_EXTENDED)
    assert diagnostics.tier_source_counts == {
        "fast": len(EXPECTED_FAST_TRADING),
        "extended": len(EXPECTED_PREP_EXTENDED),
    }


def test_pr1065_legacy_verified_rss_catalogue_is_metadata_only() -> None:
    legacy = get_source_group("VERIFIED_RSS_LEGACY")

    assert legacy.urls == ()
    assert legacy.active_runtime_group is False
    assert legacy.catalogue_path == "verified_rss.txt"
    assert "VERIFIED_RSS_LEGACY" in NEWS_SOURCE_GROUPS
    assert "VERIFIED_RSS_LEGACY" not in {group.group_id for group in list_source_groups(include_legacy=False)}


def test_pr1065_source_group_module_is_strategy_neutral() -> None:
    tree = ast.parse(SOURCE_GROUPS_MODULE.read_text(encoding="utf-8"))
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    assert all("src.strategies.ross_momentum" not in module for module in imported_modules)
    assert all("strategies.ross_momentum" not in module for module in imported_modules)


def test_pr1065_architecture_document_records_source_group_boundary_and_safety() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "src/news/source_groups.py" in text
    assert "src/news/rss_registry.py" in text
    assert "VERIFIED_RSS_LEGACY" in text
    assert "active Ross scanner path" in text
    for required in (
        "SOURCE LISTS AND ORDER UNCHANGED",
        "NO ROSS THRESHOLD CHANGE",
        "NO CATALYST BYPASS",
        "NO PAPER",
        "NO LIVE",
        "ZERO BROKER ORDER MUTATIONS",
        "PAPER_READY=NO",
        "PAPER_READINESS_GATE=FAIL",
    ):
        assert required in text
