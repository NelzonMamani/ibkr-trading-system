from __future__ import annotations

from typing import Iterable


_FLAG_TO_CAUSE = {
    "MISSING_PRICE": "missing_price",
    "MISSING_LAST": "missing_price",
    "DROP_MISSING_PRICE": "missing_price",
    "INCOMPLETE_BID_ASK": "missing_bid_ask",
    "DROP_MISSING_BID_ASK": "missing_bid_ask",
    "NEGATIVE_SPREAD": "invalid_bid_ask",
    "DROP_SPREAD": "invalid_spread",
    "DROP_MISSING_SPREAD": "invalid_spread",
    "STALE_SNAPSHOT": "stale_quote",
    "MISSING_VOLUME": "invalid_volume",
    "DROP_MISSING_VOLUME": "invalid_volume",
    "DROP_VOLUME": "invalid_volume",
    "MISSING_REF_CLOSE_RTH": "invalid_reference",
    "MISSING_REFERENCE": "invalid_reference",
    "MISSING_SESSION": "unresolved_session_fields",
}


def data_quality_blocking_causes(flags: Iterable[str]) -> list[str]:
    causes: list[str] = []
    for raw_flag in flags:
        key = str(raw_flag or "").strip().upper()
        cause = _FLAG_TO_CAUSE.get(key)
        if cause and cause not in causes:
            causes.append(cause)
    return causes

