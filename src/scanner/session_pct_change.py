from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional


@dataclass(frozen=True)
class SessionAlignedPercentChange:
    session_label: str
    cur_last: Optional[float]
    ref_close_rth: Optional[float]
    ibkr_change_pct: Optional[float]
    final_pct: Optional[float]
    pct_source: str


_SESSION_LABEL_MAP = {
    "REG": "RTH",
    "REGULAR": "RTH",
    "RTH": "RTH",
    "AFTER": "AH",
    "AFTER_HOURS": "AH",
    "AH": "AH",
    "PRE": "PRE",
    "OVN": "PRE",
    "OVERNIGHT": "PRE",
}


def normalize_session_label(label: str) -> str:
    if not label:
        return "NA"
    upper = label.upper()
    return _SESSION_LABEL_MAP.get(upper, upper)


def _safe_float(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric) or not math.isfinite(numeric):
        return None
    return numeric


def _pct_change(last_price: Optional[float], ref_close: Optional[float]) -> Optional[float]:
    if last_price is None or ref_close in {None, 0}:
        return None
    return round(((last_price - ref_close) / ref_close) * 100.0, 2)


def compute_session_aligned_pct_change(
    *,
    session_label: str,
    cur_last: Optional[float],
    ref_close_rth: Optional[float],
    ibkr_change_pct: Optional[float],
) -> SessionAlignedPercentChange:
    normalized_session = normalize_session_label(session_label)
    ibkr_pct = _safe_float(ibkr_change_pct)
    calc_gap_pct = _pct_change(cur_last, ref_close_rth)

    if ibkr_pct is not None:
        final_pct = ibkr_pct
        pct_source = "IBKR"
    else:
        final_pct = calc_gap_pct
        pct_source = "CALC(GAP_PCT)" if final_pct is not None else "N/A"

    return SessionAlignedPercentChange(
        session_label=normalized_session,
        cur_last=cur_last,
        ref_close_rth=ref_close_rth,
        ibkr_change_pct=ibkr_pct,
        final_pct=final_pct,
        pct_source=pct_source,
    )
