# File: sentiment_analysis_engine_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: Sentiment analysis stub

"""
SENTIMENT ANALYSIS ENGINE (STUB)
--------------------------------

GLOBAL CONTEXT
--------------
This file computes a **lightweight sentiment score** from news headlines.

Sentiment is a *supporting signal* only.

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_33_OUTCOME_SENTIMENT_ANALYSIS.md

STANDALONE GUARANTEE
-------------------
This engine runs without ML dependencies.

TRADING MODE
------------
Observation only.
"""

# ================================
# 1. Imports
# ================================

from typing import List, Dict

# ================================
# 2. Sentiment Engine
# ================================

class SentimentAnalysisEngine:
    """
    SentimentAnalysisEngine
    -----------------------
    Computes aggregate sentiment from headlines.
    """

    POSITIVE_KEYWORDS = {"beats", "growth", "surge", "record", "upgrade"}
    NEGATIVE_KEYWORDS = {"miss", "decline", "drop", "lawsuit", "downgrade"}

    def compute(self, headlines: List[Dict]) -> Dict:
        """
        Compute sentiment score.
        """
        score = 0
        hits = 0

        for h in headlines:
            text = (h.get("headline_text") or "").lower()

            for kw in self.POSITIVE_KEYWORDS:
                if kw in text:
                    score += 1
                    hits += 1

            for kw in self.NEGATIVE_KEYWORDS:
                if kw in text:
                    score -= 1
                    hits += 1

        sentiment_score = score / hits if hits else 0.0

        confidence = "LOW"
        if hits >= 5:
            confidence = "HIGH"
        elif hits >= 2:
            confidence = "MEDIUM"

        return {
            "sentiment_score": round(sentiment_score, 3),
            "sentiment_confidence": confidence,
        }

# ================================
# 3. Standalone Demo
# ================================

if __name__ == "__main__":
    engine = SentimentAnalysisEngine()
    demo = [{"headline_text": "Company beats expectations"}]
    print(engine.compute(demo))

# ================================
# END OF FILE
# ================================
