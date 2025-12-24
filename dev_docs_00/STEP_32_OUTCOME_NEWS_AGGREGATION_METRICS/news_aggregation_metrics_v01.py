
# File: news_aggregation_metrics_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: News aggregation metrics engine skeleton

"""
NEWS AGGREGATION METRICS ENGINE
-------------------------------

GLOBAL CONTEXT
--------------
This file computes quantitative metrics from raw news headlines.

It converts narrative flow into measurable signals:
- velocity
- freshness
- geographic spread
- duplication

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_32_OUTCOME_NEWS_AGGREGATION_METRICS.md

STANDALONE GUARANTEE
-------------------
This engine can be tested with mock headlines.

TRADING MODE
------------
Observation only.
"""

# ================================
# 1. Imports
# ================================

from datetime import datetime, timedelta
from typing import List, Dict

# ================================
# 2. Aggregation Engine
# ================================

class NewsAggregationMetricsEngine:
    """
    NewsAggregationMetricsEngine
    ----------------------------
    Computes aggregated metrics from normalized headlines.
    """

    def compute(self, headlines: List[Dict]) -> Dict:
        """
        Compute news aggregation metrics.
        """
        now = datetime.utcnow()

        # Filter valid timestamps
        valid = []
        for h in headlines:
            try:
                ts = datetime.fromisoformat(h.get("published_timestamp"))
                valid.append((h, ts))
            except Exception:
                continue

        # Velocity windows
        velocity_1m = sum(1 for _, ts in valid if now - ts <= timedelta(minutes=1))
        velocity_5m = sum(1 for _, ts in valid if now - ts <= timedelta(minutes=5))
        velocity_10m = sum(1 for _, ts in valid if now - ts <= timedelta(minutes=10))

        # Freshness
        headline_age_minutes = None
        if valid:
            latest_ts = max(ts for _, ts in valid)
            headline_age_minutes = int((now - latest_ts).total_seconds() / 60)

        # Deduplication
        texts = [h.get("headline_text") for h, _ in valid]
        unique_texts = set(texts)

        # Regions & sources
        regions = set(h.get("region") for h, _ in valid)
        sources = set(h.get("source_name") for h, _ in valid)

        return {
            "news_velocity_1m": velocity_1m,
            "news_velocity_5m": velocity_5m,
            "news_velocity_10m": velocity_10m,
            "headline_age_minutes": headline_age_minutes,
            "unique_headline_count": len(unique_texts),
            "repeated_headline_count": len(texts) - len(unique_texts),
            "unique_region_count": len(regions),
            "unique_source_count": len(sources),
            "headlines": headlines,
        }

# ================================
# 3. Standalone Demo
# ================================

if __name__ == "__main__":
    engine = NewsAggregationMetricsEngine()

    demo_headlines = [
        {
            "headline_text": "AAPL spikes",
            "published_timestamp": datetime.utcnow().isoformat(),
            "region": "US",
            "source_name": "Demo",
        }
    ]

    print(engine.compute(demo_headlines))

# ================================
# END OF FILE
# ================================
