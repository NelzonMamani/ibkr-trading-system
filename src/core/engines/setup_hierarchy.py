from __future__ import annotations

from dataclasses import replace
from typing import Any


SUPPRESSION_REASON = "suppressed_by_setup_exclusivity"

_SUPPRESSION_RULES: dict[str, set[str]] = {
    "GAP_GO": {"MICRO_PULLBACK", "BULL_FLAG", "RANGE", "EMA_PULLBACK"},
    "OPENING_DRIVE": {"ORB", "OPENING_RANGE_BREAKOUT", "FIRST_PULLBACK", "MICRO_PULLBACK", "BULL_FLAG"},
    "PREMARKET_HIGH_BREAK": {"FIRST_PULLBACK", "MICRO_PULLBACK", "BULL_FLAG", "EMA_PULLBACK", "VWAP_PULLBACK"},
    "KEY_LEVEL_BREAK": {"MICRO_PULLBACK", "BULL_FLAG", "EMA_PULLBACK", "VWAP_PULLBACK"},
    "FIRST_PULLBACK": {"MICRO_PULLBACK", "BULL_FLAG"},
    "ABCD": {"BULL_FLAG", "RANGE"},
    "CUP_HANDLE": {"MICRO_PULLBACK", "THREE_BAR_PULLBACK"},
}

_TIER_RANK = {
    "GAP_GO": 1,
    "OPENING_DRIVE": 1,
    "PREMARKET_HIGH_BREAK": 1,
    "ORB": 2,
    "OPENING_RANGE_BREAKOUT": 2,
    "FIRST_PULLBACK": 2,
    "KEY_LEVEL_BREAK": 2,
    "MICRO_PULLBACK": 3,
    "ABCD": 3,
    "CUP_HANDLE": 3,
    "BULL_FLAG": 3,
}

_ALIASES = {
    "P_GAP_GO": "GAP_GO",
    "P_ORB": "ORB",
    "P_OPENING_DRIVE": "OPENING_DRIVE",
    "P_FIRST_PULLBACK": "FIRST_PULLBACK",
    "P_KEY_LEVEL_BREAK": "KEY_LEVEL_BREAK",
    "P_PREMKT_BREAK": "PREMARKET_HIGH_BREAK",
    "P_PREMARKET_HIGH_BREAK": "PREMARKET_HIGH_BREAK",
    "P_MICRO_PULLBACK": "MICRO_PULLBACK",
    "P_BULL_FLAG": "BULL_FLAG",
    "P_ABCD": "ABCD",
    "P_CUP_HANDLE": "CUP_HANDLE",
}


def _family_of(item: Any) -> str:
    if isinstance(item, dict):
        raw = str(item.get("setup_family_id") or item.get("setup_family") or "").upper()
    else:
        raw = str(getattr(item, "setup_family_id", "")).upper()
    return _ALIASES.get(raw, raw)


def apply_setup_hierarchy(results: list[Any], *, symbol: str | None = None) -> list[Any]:
    detected_families = {_family_of(item) for item in results if bool(getattr(item, "detected", item.get("detected") if isinstance(item, dict) else False))}
    if not detected_families:
        return list(results or [])
    dominant = sorted(detected_families, key=lambda family: (_TIER_RANK.get(family, 99), family))[0]
    suppressed_families = _SUPPRESSION_RULES.get(dominant, set())
    if not suppressed_families:
        return list(results or [])

    output: list[Any] = []
    for item in list(results or []):
        family = _family_of(item)
        should_suppress = family in suppressed_families and bool(getattr(item, "detected", item.get("detected") if isinstance(item, dict) else False))
        if not should_suppress:
            output.append(item)
            continue
        if isinstance(item, dict):
            patched = dict(item)
            patched["detected"] = False
            patched["setup_detected"] = False
            patched["rejection_reason"] = SUPPRESSION_REASON
            patched["rationale_text"] = f"Suppressed by setup hierarchy: dominant={dominant} suppressed={family}"
            output.append(patched)
        else:
            patched = replace(
                item,
                detected=False,
                rejection_reason=SUPPRESSION_REASON,
                rationale_text=f"Suppressed by setup hierarchy: dominant={dominant} suppressed={family}",
            )
            output.append(patched)
        print(
            "[ROSS][PATTERN_DROP] "
            f"symbol={symbol or 'UNKNOWN'} reason={SUPPRESSION_REASON} dominant={dominant} suppressed={family}"
        )
    return output
