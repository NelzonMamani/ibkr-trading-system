from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Optional

from zoneinfo import ZoneInfo

from src.config.config_resolver import get_config


@dataclass(frozen=True)
class SessionAlignedPercentChange:
    session_label: str
    cur_last: Optional[float]
    ref_close_rth: Optional[float]
    reference_price: Optional[float]
    reference_label: str
    ibkr_change_pct: Optional[float]
    final_pct: Optional[float]
    pct_source: str


_SESSION_LABEL_MAP = {
    "REG": "RTH",
    "REGULAR": "RTH",
    "RTH": "RTH",
    "AFTER": "AH",
    "AFT": "AH",
    "AFTER_HOURS": "AH",
    "AH": "AH",
    "PRE": "PRE",
    "OVN": "OVN",
    "OVERNIGHT": "OVN",
    "CLOSED": "CLOSED",
}


def normalize_session_label(label: str) -> str:
    if not label:
        return "NA"
    upper = label.upper()
    return _SESSION_LABEL_MAP.get(upper, upper)


def resolve_market_session_label(now: Optional[datetime] = None) -> str:
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ny_time = now_utc.astimezone(ZoneInfo("America/New_York"))
    if ny_time.weekday() >= 5:
        return "CLOSED"

    h = now_utc.hour + now_utc.minute / 60.0
    windows = get_config("SCANNER_SESSION_WINDOWS_UTC")
    if windows["PRE_START"] <= h < windows["RTH_START"]:
        return "PRE"
    if windows["RTH_START"] <= h < windows["AFT_START"]:
        return "RTH"
    if windows["AFT_START"] <= h < windows["AFT_END"]:
        return "AH"
    return "OVN"


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


def _pct_change(last_price: Optional[float], reference_price: Optional[float]) -> Optional[float]:
    if last_price is None or reference_price in {None, 0}:
        return None
    return round(((last_price - reference_price) / reference_price) * 100.0, 2)


def compute_session_relative_volume(
    *,
    session_label: str,
    session_volume: Optional[float],
    avg_volume_20d: Optional[float],
) -> Optional[float]:
    normalized_session = normalize_session_label(session_label)
    if normalized_session not in {"PRE", "RTH", "AH", "OVN", "CLOSED"}:
        return None
    if session_volume is None or avg_volume_20d in {None, 0}:
        return None
    return round(session_volume / avg_volume_20d, 2)


def compute_session_aligned_pct_change(
    *,
    session_label: str,
    cur_last: Optional[float],
    ref_close_rth: Optional[float],
    rth_open_price: Optional[float],
    rth_close_price: Optional[float],
    ibkr_change_pct: Optional[float],
) -> SessionAlignedPercentChange:
    normalized_session = normalize_session_label(session_label)
    ibkr_pct = _safe_float(ibkr_change_pct)
    reference_price = None
    reference_label = "NA"
    if normalized_session in {"PRE", "OVN", "CLOSED"}:
        reference_price = ref_close_rth
        reference_label = "LAST_RTH_CLOSE"
    elif normalized_session == "RTH":
        reference_price = rth_open_price or ref_close_rth
        reference_label = "RTH_OPEN" if rth_open_price is not None else "LAST_RTH_CLOSE"
    elif normalized_session == "AH":
        reference_price = rth_close_price or ref_close_rth
        reference_label = "RTH_CLOSE" if rth_close_price is not None else "LAST_RTH_CLOSE"

    calc_pct = _pct_change(cur_last, reference_price)
    if calc_pct is not None:
        final_pct = calc_pct
        pct_source = "CALC(SESSION_REF)"
    elif ibkr_pct is not None:
        final_pct = ibkr_pct
        pct_source = "IBKR_FALLBACK"
    else:
        final_pct = None
        pct_source = "N/A"

    return SessionAlignedPercentChange(
        session_label=normalized_session,
        cur_last=cur_last,
        ref_close_rth=ref_close_rth,
        reference_price=reference_price,
        reference_label=reference_label,
        ibkr_change_pct=ibkr_pct,
        final_pct=final_pct,
        pct_source=pct_source,
    )
