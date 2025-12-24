# File: scanner_print_contract_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: Frozen scanner print contract constants + lightweight validation helpers

"""
SCANNER PRINT CONTRACT (FROZEN FIELDS)
-------------------------------------

GLOBAL CONTEXT
--------------
This file encodes the **frozen scanner print contract** as:
- ordered field names
- brief descriptions
- lightweight validation helpers

This ensures the printed output remains stable across refactors.

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_26_OUTCOME_SCANNER_PRINT_CONTRACT.md

STANDALONE GUARANTEE
-------------------
This file contains no external dependencies.

TRADING MODE
------------
None — contract only.
"""

# ================================
# 1. Contract Fields (Ordered)
# ================================

SCANNER_PRINT_FIELDS_ORDERED = [
    # SECTION A — Core Identification
    "symbol",
    "alert_priority_level",

    # SECTION B — Price & Liquidity Context
    "current_price",
    "previous_close_price",
    "gap_percent",
    "bid_price",
    "ask_price",
    "spread",
    "float_shares",
    "relative_volume",
    "volume_spike",

    # SECTION C — Momentum & Ranking
    "scanner_score",
    "scanner_rank",
    "scoring_rationale",

    # SECTION D — News & Catalyst Context
    "news_velocity_10m",
    "headline_age_minutes",
    "total_news_events",
    "unique_headline_count",
    "repeated_headline_count",
    "unique_region_count",
    "sentiment_score",
    "breaking_news_urls",
    "earnings_links",
    "sec_filing_links",

    # SECTION E — Structural Context
    "corporate_actions_detected",
    "sector",
    "industry",
    "subcategory",

    # SECTION F — Strategy Context (Scanner-Level Only)
    "trend_direction",
    "trend_strength",
    "signal_bias",

    # SECTION G — Risk Pre-Checks
    "liquidity_risk_flag",
    "volatility_risk_flag",
    "max_position_size_hint",
]

# ================================
# 2. Field Descriptions (Brief)
# ================================

SCANNER_PRINT_FIELD_DESCRIPTIONS = {
    "symbol": "Ticker symbol being scanned.",
    "alert_priority_level": "Visual urgency indicator: 🔥 / ⚠️ / NONE.",

    "current_price": "Latest traded price.",
    "previous_close_price": "Prior session close price.",
    "gap_percent": "% gap from prior close.",
    "bid_price": "Best bid price.",
    "ask_price": "Best ask price.",
    "spread": "Ask minus bid (liquidity quality proxy).",
    "float_shares": "Public float size (supply).",
    "relative_volume": "RVOL vs baseline.",
    "volume_spike": "Boolean: unusual volume detected.",

    "scanner_score": "Composite scanner score.",
    "scanner_rank": "Rank relative to other candidates.",
    "scoring_rationale": "Human explanation for score.",

    "news_velocity_10m": "Count of news/events in last 10 minutes.",
    "headline_age_minutes": "Age (minutes) of most recent headline.",
    "total_news_events": "Total accumulated news/events count.",
    "unique_headline_count": "Count of unique headlines.",
    "repeated_headline_count": "Count of repeated headlines.",
    "unique_region_count": "Count of distinct regions/countries across sources.",
    "sentiment_score": "Aggregate sentiment score if available (else None).",
    "breaking_news_urls": "List of clickable breaking-news URLs.",
    "earnings_links": "List of earnings-related URLs.",
    "sec_filing_links": "List of SEC filing URLs.",

    "corporate_actions_detected": "Splits/halts/offerings etc. detected for the symbol.",
    "sector": "Sector classification.",
    "industry": "Industry classification.",
    "subcategory": "More granular classification.",

    "trend_direction": "UP / DOWN / SIDEWAYS (scanner-level context).",
    "trend_strength": "Numeric or qualitative strength measure.",
    "signal_bias": "Pre-strategy bias: LONG / SHORT / NEUTRAL.",

    "liquidity_risk_flag": "True if spread/volume suggests liquidity risk.",
    "volatility_risk_flag": "True if volatility is extreme.",
    "max_position_size_hint": "Scanner-level hint only (risk engine decides final size).",
}

# ================================
# 3. Lightweight Validation Helpers
# ================================

def validate_scanner_print_payload(payload: dict) -> list[str]:
    """
    Validate that a scanner result payload contains all contract fields.

    Returns
    -------
    list[str]
        List of missing field names (empty if valid).

    TEACHING NOTE:
    This is a *contract validator*, not a type validator.
    We only ensure that the system prints consistent fields.
    """
    return [f for f in SCANNER_PRINT_FIELDS_ORDERED if f not in payload]

# ================================
# 4. Standalone Demo
# ================================

if __name__ == "__main__":
    demo_payload = {"symbol": "DEMO"}
    missing_fields = validate_scanner_print_payload(demo_payload)
    print("Missing fields:", missing_fields)

# ================================
# END OF FILE
# ================================
