from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta
import math
import hashlib
import json
import os
from datetime import date
from urllib.parse import urlparse
from typing import Optional

from zoneinfo import ZoneInfo

from src.config.config_resolver import get_config
from src.core.time.calendar_session import resolve_calendar_session


_NY_TZ = ZoneInfo("America/New_York")
_PRE_START = time(4, 0)
_RTH_OPEN = time(9, 30)
_OPENING_END = time(10, 30)
_RTH_CLOSE = time(16, 0)
PHASE_VOLUME_RATIOS: dict[str, float] = {
    "PRE": 0.05,
    "RTH_OPEN": 0.40,
    "RTH_MID": 0.35,
    "RTH_LATE": 0.20,
    "AH": 0.03,
    "OVN": 0.05,
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
    source: str
    market_time: str


@dataclass(frozen=True)
class SessionResolutionDiagnostics:
    utc_time: str
    ny_time: str
    resolved_session: str
    canonical_session: str
    reference_trading_date: str
    previous_valid_market_session_date: str
    reason: str
    override_source: str


_SESSION_LABEL_MAP = {
    "REG": "RTH_OPEN",
    "REGULAR": "RTH_OPEN",
    "RTH": "RTH_OPEN",
    "POWER_HOUR": "RTH_LATE",
    "LATE": "RTH_LATE",
    "AFTER": "AH",
    "AFT": "AH",
    "AFTER_HOURS": "AH",
    "AH": "AH",
    "PRE": "PRE",
    "OVN": "OVN",
    "OVERNIGHT": "OVN",
    "CLOSED": "OVN",
    "RTH_OPEN": "RTH_OPEN",
    "RTH_MID": "RTH_MID",
    "RTH_LATE": "RTH_LATE",
    "WEEKEND": "WEEKEND",
    "MIDDAY": "RTH_MID",
}

_CANONICAL_SESSION_MAP = {
    "PRE": "PRE",
    "RTH_OPEN": "RTH_OPEN",
    "RTH_MID": "RTH_MID",
    "RTH_LATE": "RTH_LATE",
    "AH": "AH",
    "OVN": "PRE",
    "WEEKEND": "PRE",
    "MIDDAY": "RTH_MID",
    "CLOSED": "PRE",
}


def normalize_session_label(label: str) -> str:
    if not label:
        return "OVN"
    upper = label.upper()
    return _SESSION_LABEL_MAP.get(upper, upper)


def resolve_market_session_label(now: Optional[datetime] = None) -> str:
    return resolve_market_session_context(now).phase


def resolve_market_session_context(
    now: Optional[datetime] = None,
    *,
    override_phase: Optional[str] = None,
    override_source: Optional[str] = None,
) -> MarketSessionContext:
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)
    ny_time = now_utc.astimezone(_NY_TZ)
    market_time = ny_time.isoformat()
    run_mode = str(get_config("RUN_MODE_EFFECTIVE") or get_config("RUN_MODE") or "LIVE").upper()

    raw_override = str(override_phase or "").strip()
    normalized_override = normalize_session_label(raw_override) if raw_override else ""
    if normalized_override:
        source = "CONTEXT_OVERRIDE"
        if normalized_override in {"RTH_OPEN", "RTH_MID", "RTH_LATE", "RTH"}:
            context = MarketSessionContext(
                coarse="RTH",
                phase=normalized_override if normalized_override != "RTH" else "RTH_OPEN",
                source=source,
                market_time=market_time,
            )
        else:
            context = MarketSessionContext(
                coarse=normalized_override,
                phase=normalized_override,
                source=source,
                market_time=market_time,
            )
    elif ny_time.weekday() >= 5:
        context = MarketSessionContext(coarse="WEEKEND", phase="WEEKEND", source="TIME", market_time=market_time)
    else:
        holidays = set(get_config("MARKET_HOLIDAYS"))
        half_days = set(get_config("MARKET_HALF_DAYS"))
        if ny_time.date() in holidays:
            context = MarketSessionContext(coarse="CLOSED", phase="CLOSED", source="TIME", market_time=market_time)
        elif ny_time.date() in half_days and ny_time.time() >= get_config("MARKET_EARLY_CLOSE_TIME"):
            context = MarketSessionContext(coarse="CLOSED", phase="CLOSED", source="TIME", market_time=market_time)
        else:
            ny_clock = ny_time.time()
            if _PRE_START <= ny_clock < _RTH_OPEN:
                context = MarketSessionContext(coarse="PRE", phase="PRE", source="TIME", market_time=market_time)
            elif _RTH_OPEN <= ny_clock < _RTH_CLOSE:
                if ny_clock < _OPENING_END:
                    context = MarketSessionContext(coarse="RTH", phase="RTH_OPEN", source="TIME", market_time=market_time)
                elif ny_clock < time(14, 30):
                    context = MarketSessionContext(coarse="RTH", phase="RTH_MID", source="TIME", market_time=market_time)
                else:
                    context = MarketSessionContext(coarse="RTH", phase="RTH_LATE", source="TIME", market_time=market_time)
            elif time(16, 0) <= ny_clock < time(20, 0):
                context = MarketSessionContext(coarse="AH", phase="AH", source="TIME", market_time=market_time)
            elif time(20, 0) <= ny_clock or ny_clock < time(4, 0):
                context = MarketSessionContext(coarse="OVN", phase="OVN", source="TIME", market_time=market_time)
            else:
                context = MarketSessionContext(coarse="CLOSED", phase="CLOSED", source="TIME", market_time=market_time)

    print(
        "[SESSION][TIME] "
        f"utc={now_utc.isoformat()} "
        f"ny={ny_time.isoformat()} "
        f"run_mode={run_mode} "
        f"phase={context.phase} "
        f"coarse={context.coarse} "
        f"source={override_source or context.source}"
    )
    return context


def canonical_session_label(label: str) -> str:
    return resolve_canonical_session(label)


def resolve_canonical_session(label: str) -> str:
    normalized = normalize_session_label(label)
    return _CANONICAL_SESSION_MAP.get(normalized, normalized or "PRE")


def previous_valid_trading_day(now: Optional[datetime] = None) -> datetime.date:
    now_utc = now or datetime.now(timezone.utc)
    ny_time = now_utc.astimezone(_NY_TZ)
    holidays = set(get_config("MARKET_HOLIDAYS"))
    cursor = ny_time.date() - timedelta(days=1)
    while cursor.weekday() >= 5 or cursor in holidays:
        cursor -= timedelta(days=1)
    return cursor


@dataclass(frozen=True)
class CoveredOpeningWindow:
    """Explicit reviewed schedule declaration, not a live calendar verifier."""
    target_session: str
    previous_session: str
    pre_start: datetime
    current_open: datetime
    opening_end: datetime
    current_close: datetime
    previous_close: datetime
    phase: str
    provenance: tuple[tuple[str, str], ...]
    covered_days: tuple[tuple[str, str, str, str, str, str], ...]
    fingerprint: str

    def snapshot(self) -> dict:
        return {key: value.isoformat() if isinstance(value, datetime) else value
                for key, value in self.__dict__.items()}


def covered_opening_window(now: datetime, *, override_phase=None) -> CoveredOpeningWindow | None:
    """Fail closed on missing coverage, conflicts, overrides or actual phase.

    The finite explicit date map supplies completeness; weekdays alone never do.
    Existing holiday/half-day facts and scanner phase semantics remain shared.
    """
    if now.tzinfo is None or now.utcoffset() is None or override_phase:
        return None
    if any(os.getenv(key, "").strip() for key in ("FORCE_SESSION", "SESSION_OVERRIDE", "MARKET_SESSION_OVERRIDE")):
        return None
    if get_config("SESSION_PHASE_OVERRIDE"):
        return None
    raw = get_config("MARKET_SESSION_COVERAGE")
    holidays = frozenset(get_config("MARKET_HOLIDAYS"))
    half_days = frozenset(get_config("MARKET_HALF_DAYS"))
    early_close = get_config("MARKET_EARLY_CLOSE_TIME")
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate schedule field")
            result[key] = value
        return result
    try:
        receipt = json.loads(raw, object_pairs_hook=unique_object)
        if set(receipt) != {"schema", "authority", "source_url", "version", "review_reference", "days"}:
            return None
        if receipt["schema"] != "market.session_coverage.v1" or receipt["authority"] not in {"NYSE", "NASDAQ"}:
            return None
        if any(not isinstance(receipt[k], str) or not receipt[k].strip()
               for k in ("source_url", "version", "review_reference")):
            return None
        source = urlparse(receipt["source_url"])
        host = "nyse.com" if receipt["authority"] == "NYSE" else "nasdaq.com"
        if source.scheme != "https" or source.hostname not in {host, "www." + host}:
            return None
        days = receipt["days"]
        if not isinstance(days, dict) or not days:
            return None
        parsed = {date.fromisoformat(key): row for key, row in days.items()}
        if any(day.isoformat() not in days for day in parsed):
            return None
        today = now.astimezone(_NY_TZ).date()
        prior = max(day for day, row in parsed.items() if day < today and row.get("status") == "OPEN")
        if previous_valid_trading_day(now) != prior:
            return None
        facts = []
        cursor = prior
        while cursor <= today:
            row = parsed[cursor]  # Every intervening date must be explicitly covered.
            closed = cursor.weekday() >= 5 or cursor in holidays
            if cursor in holidays and cursor in half_days:
                return None
            if closed:
                if row.get("status") != "CLOSED" or set(row) - {"status", "reason"}:
                    return None
                if row.get("reason", "weekend" if cursor.weekday() >= 5 else "holiday") != ("weekend" if cursor.weekday() >= 5 else "holiday"):
                    return None
                facts.append((cursor.isoformat(), "CLOSED", "", "", "", ""))
            else:
                close = early_close if cursor in half_days else _RTH_CLOSE
                if close.second or close.microsecond or close.tzinfo is not None:
                    return None  # Unsupported precision is unknown, never rounded.
                end = min(_OPENING_END, close)
                expected = {"status": "OPEN", "pre_start": _PRE_START.strftime("%H:%M"), "rth_open": _RTH_OPEN.strftime("%H:%M"),
                            "rth_close": close.strftime("%H:%M"), "opening_end": end.strftime("%H:%M")}
                if row != expected or not (_PRE_START < _RTH_OPEN < close <= _RTH_CLOSE):
                    return None
                facts.append((cursor.isoformat(), "OPEN", expected["pre_start"], expected["rth_open"], expected["opening_end"], expected["rth_close"]))
            cursor += timedelta(days=1)
        if parsed[today].get("status") != "OPEN":
            return None
        phase = resolve_market_session_context(now).phase
        if phase not in {"PRE", "RTH_OPEN"}:
            return None
        def utc(day, clock):
            return datetime.combine(day, time.fromisoformat(clock), _NY_TZ).astimezone(timezone.utc)
        row = parsed[today]
        boundaries = dict(pre_start=utc(today, row["pre_start"]), current_open=utc(today, row["rth_open"]),
                          opening_end=utc(today, row["opening_end"]), current_close=utc(today, row["rth_close"]),
                          previous_close=utc(prior, parsed[prior]["rth_close"]))
        if not boundaries["pre_start"] <= now < min(boundaries["opening_end"], boundaries["current_close"]):
            return None
        # Dynamic configuration must not change during this authority read.
        if (get_config("SESSION_PHASE_OVERRIDE") or any(os.getenv(key, "").strip() for key in ("FORCE_SESSION", "SESSION_OVERRIDE", "MARKET_SESSION_OVERRIDE"))
                or raw != get_config("MARKET_SESSION_COVERAGE") or holidays != frozenset(get_config("MARKET_HOLIDAYS"))
                or half_days != frozenset(get_config("MARKET_HALF_DAYS")) or early_close != get_config("MARKET_EARLY_CLOSE_TIME")):
            return None
        provenance = tuple((key, receipt[key]) for key in ("schema", "authority", "source_url", "version", "review_reference"))
        identity = dict(target_session=today.isoformat(), previous_session=prior.isoformat(), phase=phase,
                        provenance=provenance, covered_days=tuple(facts),
                        **{key: value.isoformat() for key, value in boundaries.items()})
        fingerprint = hashlib.sha256(json.dumps({key: value for key, value in identity.items() if key != "phase"}, sort_keys=True).encode()).hexdigest()
        return CoveredOpeningWindow(today.isoformat(), prior.isoformat(), **boundaries, phase=phase,
                                    provenance=provenance, covered_days=tuple(facts), fingerprint=fingerprint)
    except (TypeError, ValueError, KeyError, AttributeError):
        return None


def reference_trading_day(now: Optional[datetime] = None) -> datetime.date:
    now_utc = now or datetime.now(timezone.utc)
    ny_time = now_utc.astimezone(_NY_TZ)
    holidays = set(get_config("MARKET_HOLIDAYS"))
    if ny_time.weekday() >= 5 or ny_time.date() in holidays:
        return previous_valid_trading_day(now_utc)
    return ny_time.date()


def resolve_session_diagnostics(now: Optional[datetime] = None, forced_session_label: Optional[str] = None, forced_session_source: Optional[str] = None) -> SessionResolutionDiagnostics:
    now_utc = now or datetime.now(timezone.utc)
    session_ctx = resolve_market_session_context(now_utc)
    resolved = normalize_session_label(forced_session_label or session_ctx.phase)
    canonical = canonical_session_label(resolved)
    calendar_session = resolve_calendar_session(now_utc)
    if canonical not in {"PRE", "RTH_OPEN", "RTH_MID", "RTH_LATE", "AH"}:
        canonical = "PRE" if calendar_session in {"WEEKEND", "OVN"} else canonical
    ref_day = reference_trading_day(now_utc)
    prev_day = previous_valid_trading_day(now_utc)
    if forced_session_label:
        normalized_source = str(forced_session_source or "PARAMETER").upper()
        if normalized_source in {"FORCE_SESSION", "SESSION_OVERRIDE", "MARKET_SESSION_OVERRIDE", "ENV", "ENV_VAR", "ENV_OVERRIDE"}:
            reason = "ENV_OVERRIDE"
        elif normalized_source in {"CONFIG", "CONFIG_OVERRIDE"}:
            reason = "CONFIG_OVERRIDE"
        elif normalized_source in {"TEST", "TEST_OVERRIDE", "PYTEST"}:
            reason = "TEST_OVERRIDE"
        elif normalized_source in {"PARAMETER", "PARAM"}:
            reason = "PARAMETER_OVERRIDE"
        else:
            reason = normalized_source
        override_source = normalized_source
    else:
        reason = "MARKET_CLOCK"
        override_source = "NONE"
    return SessionResolutionDiagnostics(
        utc_time=now_utc.astimezone(timezone.utc).isoformat(),
        ny_time=now_utc.astimezone(_NY_TZ).isoformat(),
        resolved_session=resolved,
        canonical_session=canonical,
        reference_trading_date=ref_day.isoformat(),
        previous_valid_market_session_date=prev_day.isoformat(),
        reason=reason,
        override_source=override_source,
    )


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
    session_volume: Optional[float] = None,
    avg_volume_20d: Optional[float] = None,
    *,
    session_label: Optional[str] = None,
    persisted_rvol: Optional[float] = None,
) -> Optional[float]:
    if session_label is None:
        volume = _safe_float(session_volume)
        avg_volume = _safe_float(avg_volume_20d)
        if volume is None or avg_volume in {None, 0}:
            return None
        return round(volume / avg_volume, 2)

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
    ratio_source = normalized_session
    if ratio is None and normalized_session in {"OVN", "WEEKEND"}:
        ratio = PHASE_VOLUME_RATIOS.get("PRE")
        ratio_source = "PREP_PRE_BASELINE"
    volume = _safe_float(session_volume)
    avg_volume = _safe_float(avg_volume_20d)
    if ratio is None or volume is None or avg_volume is None:
        print(
            "[RVOL][PHASE_FALLBACK] "
            f"session={normalized_session} ratio_source={ratio_source} avg_volume_20d={avg_volume} session_volume={volume} "
            "reason=INSUFFICIENT_INPUT"
        )
        return PhaseAwareRelativeVolume(
            session_label=normalized_session,
            phase_ratio=ratio,
            expected_phase_volume=None,
            floor_value=float(floor_value),
            rvol_phase=None,
        )
    expected_phase_volume = avg_volume * ratio
    if ratio_source != normalized_session:
        print(
            "[RVOL][PHASE_FALLBACK] "
            f"session={normalized_session} ratio_source={ratio_source} avg_volume_20d={avg_volume} expected_phase_volume={round(expected_phase_volume, 2)}"
        )
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

    if normalized_session in {"OVN", "WEEKEND"}:
        if persisted_rvol_value is not None:
            print(
                "[RVOL] "
                f"session={normalized_session} baseline=LAST_SESSION_REFERENCE method=PERSISTED_RVOL value={persisted_rvol_value}"
            )
            return SessionRelativeVolume(
                session_label=normalized_session,
                baseline="LAST_SESSION_REFERENCE",
                method="PERSISTED_RVOL",
                value=persisted_rvol_value,
            )
        if avg_volume_20d not in {None, 0} and session_volume is not None:
            prep_payload = compute_phase_aware_rvol(
                session_label=normalized_session,
                session_volume=session_volume,
                avg_volume_20d=avg_volume_20d,
            )
            if prep_payload.rvol_phase is not None:
                print(
                    "[RVOL] "
                    f"session={normalized_session} baseline=PREP_PREMARKET_EXPECTED_VOLUME method=PREP_PHASE_FALLBACK value={prep_payload.rvol_phase} expected_volume={prep_payload.expected_phase_volume}"
                )
                return SessionRelativeVolume(
                    session_label=normalized_session,
                    baseline="PREP_PREMARKET_EXPECTED_VOLUME",
                    method="PREP_PHASE_FALLBACK",
                    value=prep_payload.rvol_phase,
                    expected_volume=prep_payload.expected_phase_volume,
                )
        print(
            "[RVOL] "
            f"session={normalized_session} baseline=LAST_SESSION_REFERENCE method=PERSISTED_RVOL_UNAVAILABLE value=None"
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

    if normalized_session in {"PRE", "RTH_OPEN", "RTH_MID", "RTH_LATE", "AH", "OVN", "WEEKEND"}:
        reference_price = last_rth_close
        reference_label = "LAST_RTH_CLOSE"

    calc_pct = _pct_change(current_last, reference_price)
    if calc_pct is not None:
        final_pct = calc_pct
        pct_source = "CALC(SESSION_REF)"
        if normalized_session in {"WEEKEND", "OVN"}:
            print(f"[PCT][FALLBACK_USED] session={normalized_session} source=IBKR_PREV_CLOSE")
    elif normalized_session == "WEEKEND" and persisted_pct is not None:
        final_pct = persisted_pct
        pct_source = "PERSISTED_LAST_SESSION"
    elif ibkr_pct is not None:
        # Fallback only when session-aligned reference values are unavailable.
        final_pct = ibkr_pct
        pct_source = "IBKR_FALLBACK"
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
