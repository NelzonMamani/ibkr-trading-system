# File: scanner_models_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: Skeleton based strictly on STEP_8_OUTCOME_SCANNER_RESPONSIBILITIES.md

"""
SCANNER MODELS (STRUCTURED DATA CONTRACTS)
------------------------------------------

GLOBAL CONTEXT
--------------
This file defines the **data models** used by the Market Scanner.

Its purpose is to:
- standardize scanner outputs
- prevent ad-hoc dictionaries
- enforce consistency across Scanner → Strategy → Storage

NO logic belongs here.
This file is pure structure.

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_8_OUTCOME_SCANNER_RESPONSIBILITIES.md
- Global Scanner Print Contract (frozen)

STANDALONE GUARANTEE
-------------------
This file contains no external dependencies
and can be imported safely anywhere.
"""

# ================================
# 1. Imports
# ================================

from dataclasses import dataclass, field
from typing import List, Optional

# ================================
# 2. Scanner Data Models
# ================================

@dataclass
class NewsContext:
    """
    NewsContext
    -----------
    Represents all news-related scanner information for a symbol.
    """

    sentiment_score: Optional[float] = None
    news_velocity_10m: Optional[int] = None
    total_news_events: Optional[int] = None
    unique_headline_count: Optional[int] = None
    repeated_headline_count: Optional[int] = None
    unique_region_count: Optional[int] = None

    breaking_news_urls: List[str] = field(default_factory=list)
    earnings_links: List[str] = field(default_factory=list)
    sec_filing_links: List[str] = field(default_factory=list)


@dataclass
class MarketMetrics:
    """
    MarketMetrics
    -------------
    Core quantitative market metrics used by the scanner.
    """

    symbol: str
    gap_percent: Optional[float] = None
    relative_volume: Optional[float] = None
    float_shares: Optional[int] = None

    current_price: Optional[float] = None
    previous_close_price: Optional[float] = None

    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    spread: Optional[float] = None

    volume_spike: bool = False


@dataclass
class ScannerScore:
    """
    ScannerScore
    ------------
    Represents scoring and ranking information.
    """

    score: float
    rank: int
    alert_priority_level: Optional[str] = None
    scoring_rationale: Optional[str] = None


@dataclass
class ScannerResult:
    """
    ScannerResult
    -------------
    Canonical output of the Market Scanner for one symbol.
    """

    metrics: MarketMetrics
    score: ScannerScore
    news: NewsContext

    data_quality_flags: List[str] = field(default_factory=list)
    scanner_timestamp: Optional[str] = None

# ================================
# TEACHING NOTE
# ================================
# Explicit data models prevent subtle bugs and misunderstandings.
# If a value does not fit these models, the scanner logic is wrong.

# ================================
# END OF FILE
# ================================
