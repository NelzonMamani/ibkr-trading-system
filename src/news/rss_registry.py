"""
rss_registry.py

Authoritative RSS registry for the entire system.

Rules:
- NO RSS URLs hardcoded anywhere else
- Scanner uses FAST_TRADING only
- Prep engines may use PREP_EXTENDED
- Long-horizon strategies may use MACRO_LONG_HORIZON
"""

# ============================================================
# FAST / LIVE TRADING RSS (Ross Momentum – cheap boolean news)
# ============================================================
# Purpose:
# - Detect catalyst presence (news=True / False)
# - Stop searching on first hit
# - NO sentiment, NO scoring, NO storage

RSS_FAST_TRADING = [
    # Ross core sources (MANDATORY)
    "https://www.benzinga.com/feed",
    "https://www.globenewswire.com/RssFeed?Category=Finance",

    # High-signal market news
    "https://www.reuters.com/markets/rss",
    "https://www.marketwatch.com/rss/topstories",
    "https://feeds.businessinsider.com/custom/all",
    "https://seekingalpha.com/feed",

    # One mainstream business outlet only
    "http://rss.cnn.com/rss/edition_business.rss",
]

# ============================================================
# PREPARATION / WEEKEND / RESEARCH RSS
# ============================================================
# Purpose:
# - Enrichment
# - Reports
# - Context
# - NOT used in live scan path

RSS_PREP_EXTENDED = [
    # Financial press
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "https://fortune.com/rss",
    "https://www.forbes.com/business/feed2",
    "https://www.forbes.com/finance/feed2",

    # Global business news
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://www.bbc.com/news/business/rss.xml",
    "https://feeds.skynews.com/feeds/rss/world.xml",
    "https://www.france24.com/en/rss",

    # Market / investing
    "https://markets.businessinsider.com/rss",
    "https://www.investing.com/rss/news.rss",
    "https://www.marketbeat.com/feed",

    # Tech & growth (for momentum context)
    "https://techcrunch.com/rss",
    "https://venturebeat.com/feed",
]

# ============================================================
# MACRO / LONG-HORIZON / BUFFETT-STYLE RSS
# ============================================================
# Purpose:
# - Rates
# - Policy
# - Macro regime
# - Earnings cycles

RSS_MACRO_LONG_HORIZON = [
    # Central banks & institutions
    "https://www.federalreserve.gov/feeds/press_all.xml",
    "https://www.bankofcanada.ca/feed",
    "https://www.bis.org/doclist/rss_all_categories.rss",

    # Macro economics
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml",
    "https://www.economist.com/finance-and-economics/rss.xml",
    "https://www.economist.com/the-world-this-week/rss.xml",
]

# ============================================================
# REGISTRY (single import point)
# ============================================================

RSS_REGISTRY = {
    "FAST_TRADING": RSS_FAST_TRADING,
    "PREP_EXTENDED": RSS_PREP_EXTENDED,
    "MACRO_LONG_HORIZON": RSS_MACRO_LONG_HORIZON,
}
