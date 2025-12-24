# File: alert_priority_engine_v01.py
# Created: 2025-12-17
# Version Notes:
# - v01: Alert priority engine skeleton

"""
ALERT PRIORITY ENGINE
---------------------

GLOBAL CONTEXT
--------------
This file assigns **visual urgency levels** to scanner results.

Alerts guide trader attention only.

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_36_OUTCOME_ALERT_PRIORITY_ENGINE.md

STANDALONE GUARANTEE
-------------------
This engine can be tested independently.

TRADING MODE
------------
Observation only.
"""

# ================================
# 1. Imports
# ================================

from typing import Dict

# ================================
# 2. Alert Engine
# ================================

class AlertPriorityEngine:
    """
    AlertPriorityEngine
    -------------------
    Assigns alert priority levels.
    """

    def __init__(self,
                 threshold_high: float = 75.0,
                 threshold_watch: float = 50.0,
                 min_news_velocity: int = 3,
                 min_gap_percent: float = 5.0):
        self.threshold_high = threshold_high
        self.threshold_watch = threshold_watch
        self.min_news_velocity = min_news_velocity
        self.min_gap_percent = min_gap_percent

    def compute(self, payload: Dict) -> Dict:
        """
        Compute alert priority level.
        """
        score = payload.get("scanner_score") or 0
        velocity = payload.get("news_velocity_10m") or 0
        gap = payload.get("gap_percent") or 0
        spike = payload.get("volume_spike")

        level = "NONE"
        rationale = ""

        if (
            score >= self.threshold_high
            and spike
            and (velocity >= self.min_news_velocity or gap >= self.min_gap_percent)
        ):
            level = "🔥"
            rationale = "High momentum with volume and news/gap confirmation"

        elif score >= self.threshold_watch:
            level = "⚠️"
            rationale = "Moderate momentum — worth watching"

        return {
            "alert_priority_level": level,
            "alert_rationale": rationale,
        }

# ================================
# 3. Standalone Demo
# ================================

if __name__ == "__main__":
    engine = AlertPriorityEngine()
    demo = {
        "scanner_score": 82,
        "volume_spike": True,
        "news_velocity_10m": 4,
        "gap_percent": 6,
    }
    print(engine.compute(demo))

# ================================
# END OF FILE
# ================================
