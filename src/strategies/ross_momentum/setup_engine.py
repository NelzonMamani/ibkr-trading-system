"""Setup family classification for Ross Momentum profitability layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs


@dataclass(frozen=True)
class SetupEvaluation:
    symbol: str
    setup_family: str
    detected: bool
    rationale: str
    disqualifiers: list[str] = field(default_factory=list)
    reference_levels: dict[str, float] = field(default_factory=dict)
    structure_state: str = "UNKNOWN"
    session_phase: str = "UNKNOWN"
    quality_flags: list[str] = field(default_factory=list)


class SetupEngine:
    """Deterministic setup-family stage (price-action led)."""

    _FAMILY_PRIORITY = (
        "GAP_AND_GO",
        "PREMARKET_HIGH_BREAK",
        "OPENING_RANGE_BREAKOUT",
        "FIRST_PULLBACK",
        "MICRO_PULLBACK",
        "BULL_FLAG",
        "HOD_BREAK",
    )

    def classify(self, symbol: str, pattern_input: PatternInputs, market_context: Any, news_context: dict[str, Any] | None) -> SetupEvaluation:
        candles = pattern_input.candles or []
        levels = pattern_input.levels
        session_phase = str((news_context or {}).get("session_phase") or getattr(market_context, "session_label", "UNKNOWN")).upper()
        if len(candles) < 3:
            return SetupEvaluation(
                symbol=symbol,
                setup_family="NONE",
                detected=False,
                rationale="Insufficient candles for setup classification.",
                disqualifiers=["INSUFFICIENT_CANDLES"],
                session_phase=session_phase,
                structure_state="UNDETERMINED",
            )

        last = candles[-1]
        prev = candles[-2]
        first = candles[0]
        gap_pct = float((news_context or {}).get("gap_pct") or 0.0)
        rvol = float(getattr(market_context, "rvol", 0.0) or 0.0)
        hod = float(levels.hod or max(c.high for c in candles))
        pmh = levels.premarket_high
        price = float(getattr(market_context, "price", last.close) or last.close)

        selected = "NONE"
        rationale = "No Ross setup family active."
        disqualifiers: list[str] = []
        quality_flags: list[str] = []

        if gap_pct >= 5.0 and rvol >= 1.5 and price >= first.close:
            selected = "GAP_AND_GO"
            rationale = "Gap and go context detected with supportive participation."
        elif pmh is not None and price >= float(pmh):
            selected = "PREMARKET_HIGH_BREAK"
            rationale = "Price is attacking or above premarket high."
        elif session_phase.startswith("RTH") and price >= max(c.high for c in candles[-3:]):
            selected = "OPENING_RANGE_BREAKOUT"
            rationale = "Price is pressing opening range highs."
        elif prev.low < first.low and last.high >= prev.high:
            selected = "FIRST_PULLBACK"
            rationale = "Constructive first pullback followed by re-expansion." 
        elif prev.low >= first.low and last.high > prev.high:
            selected = "MICRO_PULLBACK"
            rationale = "Micro pullback continuation context detected."
        elif (max(c.high for c in candles[-3:]) - min(c.low for c in candles[-3:])) / max(price, 0.01) < 0.02:
            selected = "BULL_FLAG"
            rationale = "Tight consolidation continuation under resistance."
        elif price >= hod:
            selected = "HOD_BREAK"
            rationale = "Price is breaking or holding high-of-day."

        if rvol < 1.0:
            disqualifiers.append("RVOL_WEAK")
        if getattr(market_context, "spread", 0.0) and float(getattr(market_context, "spread", 0.0)) > max(0.25, price * 0.01):
            disqualifiers.append("SPREAD_TOO_WIDE")
        if selected != "NONE" and disqualifiers:
            quality_flags.append("CONDITIONAL_SETUP")

        detected = selected != "NONE"
        return SetupEvaluation(
            symbol=symbol,
            setup_family=selected,
            detected=detected,
            rationale=rationale,
            disqualifiers=disqualifiers,
            reference_levels={
                "HOD": hod,
                "PREMARKET_HIGH": float(pmh) if pmh is not None else 0.0,
            },
            structure_state="CONSTRUCTIVE" if detected else "NEUTRAL",
            session_phase=session_phase,
            quality_flags=quality_flags,
        )
