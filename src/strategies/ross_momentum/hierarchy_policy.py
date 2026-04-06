"""Session-aware setup hierarchy policy for Ross Momentum."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List


SESSION_TIER_MAP: Dict[str, List[List[str]]] = {
    "PRE": [
        ["GAP_GO", "PREMARKET_HIGH_BREAK", "GAP_CONTINUATION"],
        ["ORB"],
        ["FIRST_PULLBACK"],
        ["MICRO_PULLBACK"],
    ],
    "RTH_OPEN": [
        ["GAP_GO", "OPENING_DRIVE", "PREMARKET_HIGH_BREAK"],
        ["ORB", "HOD_BREAK"],
        ["FIRST_PULLBACK"],
        ["MICRO_PULLBACK"],
    ],
    "RTH_MID": [
        ["FIRST_PULLBACK", "BULL_FLAG", "ABCD"],
        ["ASCENDING_TRIANGLE", "PENNANT", "RANGE_BREAK", "FLAT_TOP_BREAKOUT"],
        ["TREND_CONTINUATION_STAIR_STEP", "STAIR_STEP", "SECOND_PULLBACK"],
        ["MICRO_PULLBACK", "THREE_BAR_PULLBACK", "EMA_PULLBACK", "VWAP_PULLBACK"],
    ],
    "RTH_LATE": [
        ["TREND_CONTINUATION_STAIR_STEP", "STAIR_STEP", "VWAP_PULLBACK"],
        ["BREAKOUT", "RANGE_BREAK"],
        ["MICRO_PULLBACK"],
    ],
}

DEFAULT_SESSION = "RTH_MID"

SETUP_NAME_ALIASES: Dict[str, str] = {
    "GAP_&_GO": "GAP_GO",
    "GAP_AND_GO": "GAP_GO",
    "PRE_MARKET_HIGH_BREAK": "PREMARKET_HIGH_BREAK",
    "PREMARKET_BREAK": "PREMARKET_HIGH_BREAK",
    "TREND_CONTINUATION_STAIR_STEP": "TREND_CONTINUATION_STAIR_STEP",
    "STAIR_STEP": "TREND_CONTINUATION_STAIR_STEP",
    "TREND_CONTINUATION": "TREND_CONTINUATION_STAIR_STEP",
    "SECOND_PULLBACK": "SECOND_PULLBACK",
    "THREE_BAR_PULLBACK": "THREE_BAR_PULLBACK",
}


def canonical_setup_name(name: str | None) -> str:
    raw = str(name or "").strip().upper()
    raw = re.sub(r"[^A-Z0-9_ ]+", " ", raw.replace("-", " ").replace("_", " "))
    canonical = "_".join(chunk for chunk in raw.split() if chunk)
    if canonical.startswith("P_"):
        canonical = canonical[2:]
    return SETUP_NAME_ALIASES.get(canonical, canonical)


def setup_identity(setup: object) -> str:
    for attr in ("setup_family_id", "pattern_name", "setup_id"):
        value = canonical_setup_name(getattr(setup, attr, None))
        if value:
            return value
    return ""


def build_detected_lookup(detected_setups: Iterable[object]) -> dict[str, object]:
    lookup: dict[str, object] = {}
    for setup in detected_setups:
        if not getattr(setup, "detected", False):
            continue
        key = setup_identity(setup)
        if not key:
            continue
        current = lookup.get(key)
        if current is None or getattr(setup, "confidence", 0.0) > getattr(current, "confidence", 0.0):
            lookup[key] = setup
    return lookup


def select_dominant_setup_details(session: str, detected_setups: list[object]) -> tuple[object | None, int | None, list[str]]:
    tiers = SESSION_TIER_MAP.get(session, SESSION_TIER_MAP[DEFAULT_SESSION])
    detected_by_name = build_detected_lookup(detected_setups)

    for tier_idx, tier in enumerate(tiers, start=1):
        tier_matches = [detected_by_name[name] for name in tier if name in detected_by_name]
        if tier_matches:
            return max(tier_matches, key=lambda setup: getattr(setup, "confidence", 0.0)), tier_idx, tier

    return None, None, []


def select_dominant_setup(session: str, detected_setups: list[object]) -> object | None:
    selected, _, _ = select_dominant_setup_details(session, detected_setups)
    return selected
