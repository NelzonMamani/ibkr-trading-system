from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta
import math
from typing import Optional

from zoneinfo import ZoneInfo

from src.config.config_resolver import get_config


_NY_TZ = ZoneInfo("America/New_York")
PHASE_VOLUME_RATIOS: dict[str, float] = {
    "PRE": 0.05,
    "RTH_OPEN": 0.40,
    "RTH_MID": 0.35,
    "RTH_LATE": 0.20,
    "AH": 0.03,
    "OVN": 0.01,
}
PHASE_VOLUME_FLOOR = 1.0


def _session_elapsed_and_full_seconds(session_label: str, now_utc: datetime | None = None) -> tuple[int, int]:
    now = (now_utc or datetime.now(timezone.utc)).astimezone(_NY_TZ)
    session = normalize_session_label(session_label)

    if session == "PRE":
        start = now.replace(hour=4, minute=0, second=0, microsecond=0)
        end = now.replace(hour=9, minute=30, second=0, microsecond=0)
    elif session in {"RTH_OPEN", "RTH_MID", "RTH_LATE", "RTH", "REG", "REGULAR"}:
        start = now.replace(hour=9, minute=30, second=0, microsecond=0)
        end = now.replace(hour=16, minute=0, second=0, microsecond=0)
    elif session == "AH":
        start = now.replace(hour=16, minute=0, second=0, microsecond=0)
        end = now.replace(hour=20, minute=0, second=0, microsecond=0)
    elif session == "OVN":
        start = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if now.time() < time(4, 0):
            start = start - timedelta(days=1)
        end = start + timedelta(hours=8)
    else:
        return 0, 0

    full = int(max((end - start).total_seconds(), 0))
    elapsed = int(min(max((now - start).total_seconds(), 0), full))
    return elapsed, full


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
    expected_volume: Optional[float] = None


@dataclass(frozen=True)
class PhaseAwareRelativeVolume:
    session_label: str
    phase_ratio: Optional[float]
    expected_phase_volume: Optional[float]
    floor_value: float
    rvol_phase: Optional[float]


@dataclass(frozen=True)
class MarketSessionContext:
    coarse: str
    phase: str
    market_time: str


_SESSION_LABEL_MAP = {
    "REG": "RTH_OPEN",
    "REGULAR": "RTH_OPEN",
    "RTH": "RTH_OPEN",
    "AFTER": "AH",
    "AFT": "AH",
    "AFTER_HOURS": "AH",
    "AH": "AH",
    "PRE": "PRE",
    "OVN": "OVN",
    "OVERNIGHT": "OVN",
    "CLOSED": "WEEKEND",
    "RTH_OPEN": "RTH_OPEN",
    "RTH_MID": "RTH_MID",
    "RTH_LATE": "RTH_LATE",
    "WEEKEND": "WEEKEND",
}


def normalize_session_label(label: str) -> str:
    if not label:
        return "NA"
    upper = label.upper()
    return _SESSION_LABEL_MAP.get(upper, upper)


def resolve_market_session_label(now: Optional[datetime] = None) -> str:
    return resolve_market_session_context(now).phase


def resolve_market_session_context(now: Optional[datetime] = None) -> MarketSessionContext:
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)
    ny_time = now_utc.astimezone(_NY_TZ)
    market_time = ny_time.isoformat()
    if ny_time.weekday() >= 5:
        return MarketSessionContext(coarse="WEEKEND", phase="WEEKEND", market_time=market_time)
    holidays = set(get_config("MARKET_HOLIDAYS"))
    half_days = set(get_config("MARKET_HALF_DAYS"))
    if ny_time.date() in holidays:
        return MarketSessionContext(coarse="WEEKEND", phase="WEEKEND", market_time=market_time)
    if ny_time.date() in half_days:
        early_close = get_config("MARKET_EARLY_CLOSE_TIME")
        if ny_time.time() >= early_close:
            return MarketSessionContext(coarse="WEEKEND", phase="WEEKEND", market_time=market_time)

    ny_clock = ny_time.time()
    if time(4, 0) <= ny_clock < time(9, 30):
        return MarketSessionContext(coarse="PRE", phase="PRE", market_time=market_time)
    if time(9, 30) <= ny_clock < time(16, 0):
        if ny_clock < time(10, 30):
            return MarketSessionContext(coarse="RTH_OPEN", phase="RTH_OPEN", market_time=market_time)
        if ny_clock < time(14, 30):
            return MarketSessionContext(coarse="RTH_MID", phase="RTH_MID", market_time=market_time)
        return MarketSessionContext(coarse="RTH_LATE", phase="RTH_LATE", market_time=market_time)
    if time(16, 0) <= ny_clock < time(20, 0):
        return MarketSessionContext(coarse="AH", phase="AH", market_time=market_time)
    return MarketSessionContext(coarse="OVN", phase="OVN", market_time=market_time)


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
    *,
    session_label: str,
    session_volume: Optional[float],
    avg_volume_20d: Optional[float],
    persisted_rvol: Optional[float] = None,
) -> Optional[float]:
    payload = compute_session_relative_volume_with_provenance(
        session_label=session_label,
        session_volume=session_volume,
        avg_volume_20d=avg_volume_20d,
        persisted_rvol=persisted_rvol,
    )
    return payload.value


def compute_phase_aware_rvol(
    *,
    session_label: str,
    session_volume: Optional[float],
    avg_volume_20d: Optional[float],
    floor_value: float = PHASE_VOLUME_FLOOR,
) -> PhaseAwareRelativeVolume:
    normalized_session = normalize_session_label(session_label)
    ratio = PHASE_VOLUME_RATIOS.get(normalized_session)
    volume = _safe_float(session_volume)
    avg_volume = _safe_float(avg_volume_20d)
    if ratio is None or volume is None or avg_volume is None:
        return PhaseAwareRelativeVolume(
            session_label=normalized_session,
            phase_ratio=ratio,
            expected_phase_volume=None,
            floor_value=float(floor_value),
            rvol_phase=None,
        )
    expected_phase_volume = avg_volume * ratio
    denominator = max(expected_phase_volume, float(floor_value))
    rvol_phase = round(volume / denominator, 2)
    return PhaseAwareRelativeVolume(
        session_label=normalized_session,
        phase_ratio=ratio,
        expected_phase_volume=round(expected_phase_volume, 2),
        floor_value=float(floor_value),
        rvol_phase=rvol_phase,
    )


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
    symbol: Optional[str] = None,
) -> SessionRelativeVolume:
    normalized_session = normalize_session_label(session_label)

    baseline = "UNSUPPORTED"
    method = "UNSUPPORTED"

    persisted_rvol_value = _safe_float(persisted_rvol)

    if normalized_session == "WEEKEND":
        return SessionRelativeVolume(
            session_label=normalized_session,
            baseline="NO_TRADING",
            method="SESSION_NORMALIZED_RVOL",
            value=0.0,
            expected_volume=0.0,
        )

    if normalized_session in {"OVN"}:
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

    elapsed_seconds, full_seconds = _session_elapsed_and_full_seconds(normalized_session)
    baseline = "LAST_RTH_CLOSE_SESSION_TIME"
    method = "SESSION_NORMALIZED_RVOL"
    expected_volume = None
    if full_seconds > 0:
        session_progress_ratio = max(elapsed_seconds, 0) / full_seconds
        expected_volume = avg_volume_20d * session_progress_ratio
        expected_volume = max(expected_volume, avg_volume_20d * 0.001)

    if expected_volume is None or expected_volume <= 0:
        return SessionRelativeVolume(
            session_label=normalized_session,
            baseline=baseline,
            method=method,
            value=None,
            expected_volume=expected_volume,
        )

    rvol = round(session_volume / expected_volume, 2)

    print(
        "[RVOL_DEBUG] "
        f"symbol={symbol or 'NA'} "
        f"session={normalized_session} "
        f"current_volume={session_volume} "
        f"expected_volume={round(expected_volume,2)} "
        f"normalized_rvol={rvol}"
    )

    return SessionRelativeVolume(
        session_label=normalized_session,
        baseline=baseline,
        method=method,
        value=rvol,
        expected_volume=expected_volume,
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

    """
    Ross scanner gap reference law:

    Percent change used for discovery must reference the previous
    RTH close across PRE / RTH / AH sessions.

    open_relative_pct_change exists only as telemetry and must never
    replace the primary scanner gap metric.
    """

    open_relative_pct_change = _pct_change(current_last, rth_open)

    if normalized_session in {"PRE", "RTH_OPEN", "RTH_MID", "RTH_LATE", "AH", "OVN"}:
        reference_price = last_rth_close
        reference_label = "LAST_RTH_CLOSE"
    elif normalized_session in {"WEEKEND"}:
        reference_price = None
        reference_label = "LAST_SESSION_REFERENCE"

    calc_pct = _pct_change(current_last, reference_price)
    if normalized_session in {"PRE", "RTH_OPEN", "RTH_MID", "RTH_LATE", "AH", "OVN"} and calc_pct is not None:
        final_pct = calc_pct
        pct_source = "CALC(SESSION_REF)"
    elif normalized_session in {"WEEKEND"} and persisted_pct is not None:
        final_pct = persisted_pct
        pct_source = "PERSISTED_LAST_SESSION"
    elif normalized_session in {"PRE", "RTH_OPEN", "RTH_MID", "RTH_LATE", "AH", "OVN"} and ibkr_pct is not None:
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
