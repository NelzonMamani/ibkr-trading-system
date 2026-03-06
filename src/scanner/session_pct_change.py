from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
import math
from typing import Optional

from zoneinfo import ZoneInfo

from src.config.config_resolver import get_config


def _estimate_session_progress(session_label: str, now_utc: datetime | None = None) -> float:
    """
    Estimate how far we are into the RTH session.
    Returns a float between 0.01 and 1.0.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    session = normalize_session_label(session_label)

    if session != "RTH":
        return 0.0

    # Market open 09:30 ET, close 16:00 ET
    # Convert UTC to approximate ET offset
    # (simple approximation is sufficient for RVOL scaling)
    market_open_utc = time(hour=14, minute=30)
    minutes_since_open = (
        (now_utc.hour * 60 + now_utc.minute)
        - (market_open_utc.hour * 60 + market_open_utc.minute)
    )

    total_session_minutes = 390

    progress = max(0.01, min(minutes_since_open / total_session_minutes, 1.0))

    return progress


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
    open_relative_pct_change: Optional[float] = None


@dataclass(frozen=True)
class SessionRelativeVolume:
    session_label: str
    baseline: str
    method: str
    value: Optional[float]


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
    holidays = set(get_config("MARKET_HOLIDAYS"))
    half_days = set(get_config("MARKET_HALF_DAYS"))
    if ny_time.date() in holidays:
        return "CLOSED"
    if ny_time.date() in half_days:
        early_close = get_config("MARKET_EARLY_CLOSE_TIME")
        if ny_time.time() >= early_close:
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


def compute_scanner_rvol(
    session_volume: Optional[float],
    avg_volume_20d: Optional[float],
) -> Optional[float]:
    if session_volume is None or avg_volume_20d in (None, 0):
        return None

    return round(session_volume / avg_volume_20d, 2)


def compute_session_relative_volume(
    *,
    session_label: str,
    session_volume: Optional[float],
    avg_volume_20d: Optional[float],
) -> Optional[float]:
    payload = compute_session_relative_volume_with_provenance(
        session_label=session_label,
        session_volume=session_volume,
        avg_volume_20d=avg_volume_20d,
    )
    return payload.value


def compute_session_relative_volume_with_provenance(
    *,
    session_label: str,
    session_volume: Optional[float],
    avg_volume_20d: Optional[float],
    persisted_rvol: Optional[float] = None,
) -> SessionRelativeVolume:
    normalized_session = normalize_session_label(session_label)

    baseline = "UNSUPPORTED"
    method = "UNSUPPORTED"

    persisted_rvol_value = _safe_float(persisted_rvol)

    if normalized_session in {"OVN", "CLOSED"}:
        if persisted_rvol_value is not None:
            print(
                "[RVOL] "
                f"session={normalized_session} baseline=LAST_SESSION_REFERENCE "
                f"method=PERSISTED_RVOL value={persisted_rvol_value}"
            )
            return SessionRelativeVolume(
                session_label=normalized_session,
                baseline="LAST_SESSION_REFERENCE",
                method="PERSISTED_RVOL",
                value=persisted_rvol_value,
            )
        print(
            "[RVOL] "
            f"session={normalized_session} baseline=LAST_SESSION_REFERENCE "
            "method=PERSISTED_RVOL value=None"
        )
        return SessionRelativeVolume(
            session_label=normalized_session,
            baseline="LAST_SESSION_REFERENCE",
            method="PERSISTED_RVOL_UNAVAILABLE",
            value=None,
        )

    if avg_volume_20d in {None, 0} or session_volume is None:
        return SessionRelativeVolume(
            session_label=normalized_session,
            baseline="NO_DATA",
            method="UNAVAILABLE",
            value=None,
        )

    expected_volume = None

    if normalized_session == "PRE":
        baseline = "PREMARKET_EXPECTED"
        method = "SESSION_NORMALIZED_RVOL"
        expected_volume = avg_volume_20d * 0.02

    elif normalized_session == "RTH":
        progress = _estimate_session_progress(normalized_session)
        baseline = "RTH_TIME_NORMALIZED"
        method = "SESSION_NORMALIZED_RVOL"
        expected_volume = avg_volume_20d * progress

    elif normalized_session == "AH":
        baseline = "AFTER_HOURS_EXPECTED"
        method = "SESSION_NORMALIZED_RVOL"
        expected_volume = avg_volume_20d * 0.01

    if expected_volume is None or expected_volume <= 0:
        return SessionRelativeVolume(
            session_label=normalized_session,
            baseline=baseline,
            method=method,
            value=None,
        )

    rvol = round(session_volume / expected_volume, 2)

    print(
        "[RVOL_DEBUG] "
        f"session={normalized_session} "
        f"current_volume={session_volume} "
        f"expected_volume={round(expected_volume,2)} "
        f"rvol={rvol}"
    )

    return SessionRelativeVolume(
        session_label=normalized_session,
        baseline=baseline,
        method=method,
        value=rvol,
    )


def compute_session_aligned_pct_change(
    *,
    session_label: str,
    cur_last: Optional[float],
    ref_close_rth: Optional[float],
    rth_open_price: Optional[float],
    rth_close_price: Optional[float],
    ibkr_change_pct: Optional[float],
    persisted_pct_change: Optional[float] = None,
) -> SessionAlignedPercentChange:
    normalized_session = normalize_session_label(session_label)
    ibkr_pct = _safe_float(ibkr_change_pct)
    persisted_pct = _safe_float(persisted_pct_change)
    rth_open = _safe_float(rth_open_price)
    current_last = _safe_float(cur_last)
    last_rth_close = _safe_float(ref_close_rth)
    reference_price = None
    reference_label = "NA"

    open_relative_pct_change = _pct_change(current_last, rth_open)

    if normalized_session in {"PRE", "RTH", "AH"}:
        reference_price = last_rth_close
        reference_label = "LAST_RTH_CLOSE"
    elif normalized_session in {"OVN", "CLOSED", "WEEKEND"}:
        reference_price = None
        reference_label = "LAST_SESSION_REFERENCE"

    calc_pct = _pct_change(current_last, reference_price)
    if normalized_session in {"PRE", "RTH", "AH"} and calc_pct is not None:
        final_pct = calc_pct
        pct_source = "CALC(SESSION_REF)"
    elif normalized_session in {"OVN", "CLOSED", "WEEKEND"} and persisted_pct is not None:
        final_pct = persisted_pct
        pct_source = "PERSISTED_LAST_SESSION"
    elif normalized_session in {"PRE", "RTH", "AH"} and ibkr_pct is not None:
        # Fallback only when in-session reference values are unavailable.
        final_pct = ibkr_pct
        pct_source = "IBKR_FALLBACK"
    elif ibkr_pct is not None:
        final_pct = ibkr_pct
        pct_source = "IBKR_FALLBACK_CLOSED"
    else:
        final_pct = None
        pct_source = "N/A"

    return SessionAlignedPercentChange(
        session_label=normalized_session,
        cur_last=current_last,
        ref_close_rth=last_rth_close,
        reference_price=reference_price,
        reference_label=reference_label,
        ibkr_change_pct=ibkr_pct,
        final_pct=final_pct,
        pct_source=pct_source,
        open_relative_pct_change=open_relative_pct_change,
    )
