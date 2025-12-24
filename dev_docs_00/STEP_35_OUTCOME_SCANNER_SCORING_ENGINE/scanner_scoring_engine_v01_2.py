# File: scanner_scoring_engine_v01.py
# Created: 2025-12-17
# Version Notes:
# - v01: Scanner scoring engine skeleton

"""
SCANNER SCORING ENGINE
---------------------

GLOBAL CONTEXT
--------------
This file computes a **composite scanner score** used to rank symbols
for trader attention.

The score does NOT imply an entry.

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_35_OUTCOME_SCANNER_SCORING_ENGINE.md

STANDALONE GUARANTEE
-------------------
This engine can be tested with mock scanner payloads.

TRADING MODE
------------
Observation only.
"""

# ================================
# 1. Imports
# ================================

from typing import Dict

# ================================
# 2. Scoring Engine
# ================================

class ScannerScoringEngine:
    """
    ScannerScoringEngine
    --------------------
    Computes composite scanner score.
    """

    def compute(self, payload: Dict) -> Dict:
        """
        Compute scanner score and rationale.
        """
        score = 0.0
        rationale = []

        # --- Momentum ---
        gap = payload.get("gap_percent") or 0
        rvol = payload.get("relative_volume") or 0

        score += min(gap * 2, 30)
        score += min(rvol * 5, 30)

        if payload.get("volume_spike"):
            score += 10
            rationale.append("Volume spike detected")

        # --- News Awareness ---
        velocity = payload.get("news_velocity_10m") or 0
        regions = payload.get("unique_region_count") or 0

        score += min(velocity * 2, 10)
        score += min(regions * 2, 10)

        # --- Sentiment ---
        sentiment = payload.get("sentiment_score")
        if sentiment is not None:
            score += sentiment * 5

        # --- Penalties ---
        if payload.get("liquidity_risk_flag"):
            score -= 15
            rationale.append("Liquidity risk")

        if payload.get("volatility_risk_flag"):
            score -= 10
            rationale.append("Volatility risk")

        # Clamp
        score = max(0, min(100, score))

        return {
            "scanner_score": round(score, 2),
            "scoring_rationale": ", ".join(rationale) or "Composite momentum score",
        }

# ================================
# 3. Standalone Demo
# ================================

if __name__ == "__main__":
    engine = ScannerScoringEngine()
    demo_payload = {
        "gap_percent": 12,
        "relative_volume": 5,
        "volume_spike": True,
        "news_velocity_10m": 4,
        "unique_region_count": 3,
        "sentiment_score": 0.6,
    }
    print(engine.compute(demo_payload))

# ================================
# END OF FILE
# ================================
