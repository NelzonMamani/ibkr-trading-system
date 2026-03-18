from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional

from src.scanner.candidate_identity import CandidateIdentity, bridge_identity_keys
from src.scanner.session_pct_change import (
    compute_phase_aware_rvol,
    compute_scanner_rvol,
    compute_session_aligned_pct_change,
    normalize_session_label,
)


@dataclass(frozen=True)
class ResolvedReferenceBundle:
    reference_price: Optional[float]
    reference_label: str
    pct_change_resolved: Optional[float]
    gap_pct_resolved: Optional[float]
    pct_source: str
    gap_source: str
    context_status: str
    execution_ready: bool
    prep_only: bool


@dataclass(frozen=True)
class HistoricalDailyBar:
    trading_date: str
    close: Optional[float]
    volume: Optional[int]


@dataclass(frozen=True)
class CanonicalReferenceResult:
    identity_key: str
    symbol: str
    reference_price: Optional[float]
    reference_label: str
    reference_source: str
    reference_resolved: bool
    reference_asof_trading_date: Optional[str]
    avg_volume_20d: Optional[int]
    average_daily_volume_window_days: Optional[int]
    adv20_source: str
    adv20_resolved: bool
    expected_phase_volume: Optional[float]
    rvol_discovery: Optional[float]
    rvol_phase: Optional[float]
    history_lookup_key_used: Optional[str]
    reference_failure_reason: Optional[str]
    rvol_failure_reason: Optional[str]


class PersistentReferenceCache:
    def __init__(self, path: Path | str = Path("data/reference/reference_cache.json")) -> None:
        self.path = Path(path)
        self._loaded = False
        self._store: dict[str, dict[str, Any]] = {}

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        self._store = payload if isinstance(payload, dict) else {}

    def get(self, key: str, *, trading_date: str | None) -> Optional[dict[str, Any]]:
        self._load()
        payload = self._store.get(key)
        if not isinstance(payload, dict):
            return None
        if trading_date and payload.get("cache_trading_date") not in {None, trading_date}:
            return None
        return payload

    def put(self, keys: tuple[str, ...], record: dict[str, Any]) -> None:
        self._load()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for key in keys:
            self._store[key] = dict(record)
        self.path.write_text(json.dumps(self._store, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class CanonicalReferenceResolver:
    def __init__(self, cache: PersistentReferenceCache | None = None) -> None:
        self.cache = cache or PersistentReferenceCache()
        self._cycle_cache: dict[str, CanonicalReferenceResult] = {}

    def reset_cycle(self) -> None:
        self._cycle_cache.clear()

    def resolve(
        self,
        *,
        identity: CandidateIdentity,
        provider: Any,
        session_label: str,
        current_volume: Optional[int],
        intraday_avg_volume_20d: Optional[int],
        current_last_price: Optional[float],
        rth_open_price: Optional[float],
        rth_close_price: Optional[float],
        ibkr_change_pct: Optional[float],
        persisted_pct_change: Optional[float],
    ) -> CanonicalReferenceResult:
        trading_date = date.today().isoformat()
        cache_keys = bridge_identity_keys(identity)
        if identity.con_id in {None, 0}:
            provider_ns = f"provider:{getattr(provider, 'source_name', type(provider).__name__)}"
            cache_keys = tuple(f"{provider_ns}|{key}" for key in cache_keys)
        for key in cache_keys:
            hit = self._cycle_cache.get(key)
            if hit is not None:
                print(f"[REFERENCE][CACHE_HIT] symbol={identity.symbol} identity_key={identity.key} source=cycle lookup_key={key}")
                return hit
        print(f"[REFERENCE][CACHE_MISS] symbol={identity.symbol} identity_key={identity.key} source=cycle")
        if identity.con_id not in {None, 0}:
            for key in cache_keys:
                payload = self.cache.get(key, trading_date=trading_date)
                if payload is not None:
                    result = self._result_from_cache(identity, payload, session_label, current_volume, current_last_price, rth_open_price, rth_close_price, ibkr_change_pct, persisted_pct_change)
                    for alias in cache_keys:
                        self._cycle_cache[alias] = result
                    print(f"[REFERENCE][CACHE_HIT] symbol={identity.symbol} identity_key={identity.key} source=persistent lookup_key={key}")
                    print(f"[RVOL][CACHE_HIT] symbol={identity.symbol} identity_key={identity.key} source=persistent lookup_key={key}")
                    return result
            print(f"[REFERENCE][CACHE_MISS] symbol={identity.symbol} identity_key={identity.key} source=persistent")
        else:
            print(f"[REFERENCE][CACHE_MISS] symbol={identity.symbol} identity_key={identity.key} source=persistent_skipped_no_conid")

        bars = self._request_historical_daily_bars(provider, identity)
        lookup_key_used = identity.key if bars else None
        prev_close = self._last_completed_close(bars)
        avg_volume, window_days = self._average_volume(bars)
        reference_failure_reason = None if prev_close is not None else "HISTORY_UNAVAILABLE"
        adv_source = "INTRADAY_STATS" if intraday_avg_volume_20d is not None else ("IBKR_DAILY_BARS" if avg_volume is not None else "UNRESOLVED")
        resolved_avg_volume = intraday_avg_volume_20d if intraday_avg_volume_20d is not None else avg_volume
        resolved_window_days = 20 if intraday_avg_volume_20d is not None else window_days
        rvol_failure_reason = None if resolved_avg_volume is not None else "ADV20_UNAVAILABLE"
        if bars:
            print(
                f"[REFERENCE][HISTORICAL_RESULT] symbol={identity.symbol} identity_key={identity.key} found={prev_close is not None} value={prev_close} window_days={window_days}"
            )
            print(
                f"[RVOL][HISTORICAL_RESULT] symbol={identity.symbol} identity_key={identity.key} avg_volume_20d={resolved_avg_volume} window_days={resolved_window_days}"
            )
        else:
            print(f"[REFERENCE][FAIL] symbol={identity.symbol} identity_key={identity.key} reason=HISTORY_UNAVAILABLE")
            print(f"[RVOL][FAIL] symbol={identity.symbol} identity_key={identity.key} reason={rvol_failure_reason}")

        payload = {
            "identity_key": identity.key,
            "symbol": identity.symbol,
            "reference_price": prev_close,
            "reference_label": "LAST_RTH_CLOSE",
            "reference_source": "IBKR_DAILY_BARS" if prev_close is not None else "UNRESOLVED",
            "reference_resolved": prev_close is not None,
            "asof_trading_date": bars[-1].trading_date if bars else None,
            "cache_trading_date": trading_date,
            "avg_volume_20d": resolved_avg_volume,
            "average_daily_volume_window_days": resolved_window_days,
            "adv20_source": adv_source,
            "adv20_resolved": resolved_avg_volume is not None,
            "resolved_at_utc": datetime.now(timezone.utc).isoformat(),
            "aliases": list(identity.aliases),
            "history_lookup_key_used": lookup_key_used,
            "reference_failure_reason": reference_failure_reason,
            "rvol_failure_reason": rvol_failure_reason,
        }
        if (prev_close is not None or resolved_avg_volume is not None) and identity.con_id not in {None, 0}:
            self.cache.put(cache_keys, payload)
            print(f"[REFERENCE][PERSIST] symbol={identity.symbol} identity_key={identity.key} path={self.cache.path}")
        result = self._result_from_cache(identity, payload, session_label, current_volume, current_last_price, rth_open_price, rth_close_price, ibkr_change_pct, persisted_pct_change)
        for key in cache_keys:
            self._cycle_cache[key] = result
        return result

    def _request_historical_daily_bars(self, provider: Any, identity: CandidateIdentity) -> list[HistoricalDailyBar]:
        get_bars = getattr(provider, "get_daily_bars", None)
        if callable(get_bars) and _has_concrete_method(provider, "get_daily_bars"):
            print(f"[REFERENCE][HISTORICAL_REQUEST] symbol={identity.symbol} identity_key={identity.key} source=provider_daily_bars")
            bars = get_bars(identity, lookback_days=25)
            return self._normalize_bars(bars)
        prev_close = getattr(provider, "get_previous_rth_close", None)
        avg_volume = getattr(provider, "get_average_daily_volume", None)
        legacy_prev_close = getattr(provider, "get_prev_close", None)
        legacy_intraday = getattr(provider, "get_intraday_stats", None)
        synthetic: list[HistoricalDailyBar] = []
        if callable(prev_close) and _has_concrete_method(provider, "get_previous_rth_close"):
            print(f"[REFERENCE][HISTORICAL_REQUEST] symbol={identity.symbol} identity_key={identity.key} source=provider_prev_close")
            value = prev_close(identity)
        elif callable(legacy_prev_close):
            print(f"[REFERENCE][HISTORICAL_REQUEST] symbol={identity.symbol} identity_key={identity.key} source=legacy_prev_close")
            value = legacy_prev_close(identity.symbol)
        else:
            value = None
        if value is not None:
            synthetic.append(HistoricalDailyBar(trading_date=date.today().isoformat(), close=float(value), volume=None))
        if callable(avg_volume) and _has_concrete_method(provider, "get_average_daily_volume"):
            print(f"[REFERENCE][HISTORICAL_REQUEST] symbol={identity.symbol} identity_key={identity.key} source=provider_avg_volume")
            avg, window = avg_volume(identity, window=20)
        elif callable(legacy_intraday):
            print(f"[REFERENCE][HISTORICAL_REQUEST] symbol={identity.symbol} identity_key={identity.key} source=legacy_intraday_stats")
            stats = legacy_intraday(identity.symbol)
            avg = getattr(stats, "average_daily_volume_20d", None)
            window = getattr(stats, "average_daily_volume_window_days", None)
        else:
            avg, window = None, None
        if avg is not None:
            synthetic.extend(HistoricalDailyBar(trading_date=f"window-{idx}", close=None, volume=int(avg)) for idx in range(window or 20))
        return synthetic

    def _normalize_bars(self, bars: Any) -> list[HistoricalDailyBar]:
        normalized: list[HistoricalDailyBar] = []
        for bar in bars or []:
            dt = getattr(bar, "date", None) or getattr(bar, "trading_date", None) or getattr(bar, "time", None)
            normalized.append(HistoricalDailyBar(str(dt), _to_float(getattr(bar, "close", None)), _to_int(getattr(bar, "volume", None))))
        return normalized

    def _last_completed_close(self, bars: list[HistoricalDailyBar]) -> Optional[float]:
        for bar in reversed(bars):
            if bar.close is not None:
                return bar.close
        return None

    def _average_volume(self, bars: list[HistoricalDailyBar], preferred_window: int = 20) -> tuple[Optional[int], Optional[int]]:
        volumes = [bar.volume for bar in bars if bar.volume is not None]
        if not volumes:
            return None, None
        window = min(preferred_window, len(volumes))
        sample = volumes[-window:]
        return int(sum(sample) / len(sample)), window

    def _result_from_cache(self, identity: CandidateIdentity, payload: dict[str, Any], session_label: str, current_volume: Optional[int], current_last_price: Optional[float], rth_open_price: Optional[float], rth_close_price: Optional[float], ibkr_change_pct: Optional[float], persisted_pct_change: Optional[float]) -> CanonicalReferenceResult:
        pct_payload = compute_session_aligned_pct_change(
            session_label=normalize_session_label(session_label),
            cur_last=current_last_price,
            ref_close_rth=_to_float(payload.get("reference_price")),
            rth_open_price=rth_open_price,
            rth_close_price=rth_close_price,
            ibkr_change_pct=ibkr_change_pct,
            persisted_pct_change=persisted_pct_change,
        )
        avg_volume_20d = _to_int(payload.get("avg_volume_20d"))
        phase_payload = compute_phase_aware_rvol(session_label=session_label, session_volume=current_volume, avg_volume_20d=avg_volume_20d)
        rvol_discovery = compute_scanner_rvol(session_label=session_label, session_volume=current_volume, avg_volume_20d=avg_volume_20d, persisted_rvol=None)
        return CanonicalReferenceResult(
            identity_key=identity.key,
            symbol=identity.symbol,
            reference_price=_to_float(payload.get("reference_price")),
            reference_label=str(payload.get("reference_label") or "LAST_RTH_CLOSE"),
            reference_source=str(payload.get("reference_source") or "UNRESOLVED"),
            reference_resolved=bool(payload.get("reference_resolved")),
            reference_asof_trading_date=payload.get("asof_trading_date"),
            avg_volume_20d=avg_volume_20d,
            average_daily_volume_window_days=_to_int(payload.get("average_daily_volume_window_days")),
            adv20_source=str(payload.get("adv20_source") or "UNRESOLVED"),
            adv20_resolved=bool(payload.get("adv20_resolved")),
            expected_phase_volume=phase_payload.expected_phase_volume,
            rvol_discovery=rvol_discovery,
            rvol_phase=phase_payload.rvol_phase,
            history_lookup_key_used=payload.get("history_lookup_key_used"),
            reference_failure_reason=payload.get("reference_failure_reason"),
            rvol_failure_reason=payload.get("rvol_failure_reason"),
        )


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None




def _has_concrete_method(obj: Any, name: str) -> bool:
    return name in getattr(type(obj), "__dict__", {})

def _to_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def resolve_reference_bundle(*, session_label: str | None, reference_price: Optional[float], reference_label: Optional[str], pct_change: Optional[float], pct_source: Optional[str], gap_pct: Optional[float], gap_source: Optional[str]) -> ResolvedReferenceBundle:
    session = normalize_session_label(session_label or "")
    prep_only = session in {"CLOSED", "WEEKEND", "OVN", "AH"}
    context_status = "prep_context" if prep_only else "live_candidate"
    execution_ready = session in {"PRE", "RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE"}
    return ResolvedReferenceBundle(
        reference_price=reference_price,
        reference_label=reference_label or "LAST_RTH_CLOSE",
        pct_change_resolved=pct_change,
        gap_pct_resolved=gap_pct if gap_pct is not None else pct_change,
        pct_source=pct_source or ("PREP_CONTEXT" if prep_only else "LIVE_OR_IBKR"),
        gap_source=gap_source or ("SESSION_OPEN_VS_REF" if execution_ready else "PREP_CONTEXT"),
        context_status=context_status,
        execution_ready=execution_ready,
        prep_only=prep_only,
    )
