from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional

from src.runtime.async_runtime_bootstrap import safe_import_ib_insync

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
    qualified_identity: CandidateIdentity
    reference_price: Optional[float]
    reference_label: str
    reference_source: str
    reference_quality_tier: str
    reference_resolved: bool
    continuity_usable_reference: bool
    qualification_usable_reference: bool
    execution_usable_reference: bool
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
    reference_degraded: bool
    reference_synthetic: bool


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
    REFERENCE_QUALITY_BY_SOURCE = {
        "IBKR_DAILY_BARS": "PRIMARY",
        "CACHED_CLOSE_FALLBACK": "SECONDARY",
        "PROVIDER_PREV_CLOSE_FALLBACK": "SECONDARY",
        "QUOTE_CLOSE_FALLBACK": "SECONDARY",
        "SCANNER_PCT_SYNTHETIC_FALLBACK": "DEGRADED_SYNTHETIC",
        "SNAPSHOT_LAST_PRICE_FALLBACK": "WEAK",
        "UNRESOLVED": "NONE",
    }

    def _contract_from_identity(self, identity: CandidateIdentity):
        _, Stock, Contract = safe_import_ib_insync()
        exchange = identity.exchange or "SMART"
        currency = identity.currency or "USD"
        symbol = identity.symbol or identity.local_symbol or identity.trading_class or ""
        contract = Stock(symbol, exchange, currency) if identity.sec_type in {None, "", "STK"} else Contract()
        if not hasattr(contract, "symbol"):
            contract.symbol = symbol
        contract.secType = identity.sec_type or getattr(contract, "secType", None) or "STK"
        contract.exchange = exchange
        contract.currency = currency
        if identity.con_id not in {None, 0}:
            contract.conId = int(identity.con_id)
        if identity.primary_exchange:
            contract.primaryExchange = identity.primary_exchange
        if identity.trading_class:
            contract.tradingClass = identity.trading_class
        if identity.local_symbol:
            contract.localSymbol = identity.local_symbol
        return contract

    def _qualify_history_identity(self, provider: Any, identity: CandidateIdentity) -> tuple[CandidateIdentity, bool]:
        qualify_contracts = getattr(provider, "qualifyContracts", None)
        if not callable(qualify_contracts):
            if getattr(provider, "source_name", "") != "IBKR":
                return identity, True
            print(
                f"[REFERENCE][QUALIFY_FAIL] symbol={identity.symbol} identity_key={identity.key} reason=QUALIFY_METHOD_UNAVAILABLE"
            )
            return identity, False

        contract = self._contract_from_identity(identity)
        try:
            qualified = qualify_contracts(contract)
        except Exception as exc:
            print(
                f"[REFERENCE][QUALIFY_FAIL] symbol={identity.symbol} identity_key={identity.key} reason=QUALIFY_EXCEPTION error={exc}"
            )
            return identity, False

        if not qualified or getattr(qualified[0], "conId", None) in (None, 0):
            print(
                f"[REFERENCE][QUALIFY_FAIL] symbol={identity.symbol} identity_key={identity.key} reason=INVALID_CONTRACT"
            )
            return identity, False

        contract = qualified[0]
        primary_exchange = getattr(contract, "primaryExchange", None)
        print(
            f"[REFERENCE][QUALIFIED] symbol={identity.symbol} identity_key={identity.key} conId={getattr(contract, 'conId', None)} "
            f"primaryExchange={primary_exchange} exchange={getattr(contract, 'exchange', None)}"
        )
        if primary_exchange in {None, "", "SMART"}:
            print(
                f"[REFERENCE][QUALIFIED_DEGRADED] symbol={identity.symbol} identity_key={identity.key} "
                f"conId={getattr(contract, 'conId', None)} exchange={getattr(contract, 'exchange', None)} "
                f"primaryExchange={primary_exchange} action=USE_QUALIFIED_CONTRACT_ANYWAY"
            )

        return CandidateIdentity.from_contract(contract, fallback_symbol=identity.symbol), True

    def __init__(self, cache: PersistentReferenceCache | None = None) -> None:
        self.cache = cache or PersistentReferenceCache()
        self._cycle_cache: dict[str, CanonicalReferenceResult] = {}
        self._last_resolution_trace: dict[str, dict[str, Any]] = {}

    def reset_cycle(self) -> None:
        self._cycle_cache.clear()
        self._last_resolution_trace.clear()

    def get_last_resolution_trace(self, identity_key: str) -> dict[str, Any]:
        return dict(self._last_resolution_trace.get(identity_key, {}))

    def _cache_keys(self, identity: CandidateIdentity, provider: Any) -> tuple[str, ...]:
        if identity.con_id not in {None, 0}:
            return (identity.key,)
        provider_ns = f"provider:{getattr(provider, 'source_name', type(provider).__name__)}"
        return tuple(f"{provider_ns}|{key}" for key in bridge_identity_keys(identity))

    def _verify_cache_hit(self, *, identity: CandidateIdentity, lookup_key: str, result_identity_key: str, source: str) -> None:
        if identity.con_id not in {None, 0} and lookup_key != identity.key:
            raise AssertionError(
                f"ConId-backed identity resolved through non-conId {source} cache key: "
                f"identity_key={identity.key} lookup_key={lookup_key}"
            )
        if identity.con_id not in {None, 0} and result_identity_key != identity.key:
            raise AssertionError(
                f"ConId-backed identity reused another instrument's {source} cache entry: "
                f"identity_key={identity.key} cached_identity_key={result_identity_key}"
            )

    def _history_contract_fields(self, identity: CandidateIdentity) -> str:
        return (
            f"symbol={identity.symbol} conId={identity.con_id} secType={identity.sec_type} "
            f"exchange={identity.exchange} primaryExchange={identity.primary_exchange} "
            f"localSymbol={identity.local_symbol} tradingClass={identity.trading_class} currency={identity.currency}"
        )

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
        cache_keys = self._cache_keys(identity, provider)
        for key in cache_keys:
            hit = self._cycle_cache.get(key)
            if hit is not None:
                self._verify_cache_hit(identity=identity, lookup_key=key, result_identity_key=hit.identity_key, source="cycle")
                print(f"[REFERENCE][CACHE_HIT] symbol={identity.symbol} identity_key={identity.key} source=cycle lookup_key={key}")
                return hit
        print(f"[REFERENCE][CACHE_MISS] symbol={identity.symbol} identity_key={identity.key} source=cycle")
        if identity.con_id not in {None, 0}:
            for key in cache_keys:
                payload = self.cache.get(key, trading_date=trading_date)
                if payload is not None:
                    cached_identity_key = str(payload.get("identity_key") or "")
                    self._verify_cache_hit(identity=identity, lookup_key=key, result_identity_key=cached_identity_key, source="persistent")
                    payload = dict(payload)
                    if _to_float(payload.get("reference_price")) is not None:
                        payload["reference_source"] = "CACHED_CLOSE_FALLBACK"
                    result = self._result_from_cache(identity, payload, session_label, current_volume, current_last_price, rth_open_price, rth_close_price, ibkr_change_pct, persisted_pct_change)
                    for alias in cache_keys:
                        self._cycle_cache[alias] = result
                        self._last_resolution_trace[alias] = {
                            "identity_key": identity.key,
                            "symbol": identity.symbol,
                            "cache_source": "persistent",
                            "qualified_identity": {
                                "conId": result.qualified_identity.con_id,
                                "secType": result.qualified_identity.sec_type,
                                "exchange": result.qualified_identity.exchange,
                                "primaryExchange": result.qualified_identity.primary_exchange,
                                "tradingClass": result.qualified_identity.trading_class,
                                "localSymbol": result.qualified_identity.local_symbol,
                                "currency": result.qualified_identity.currency,
                            },
                            "history_attempts": [],
                            "selected_reference_source": result.reference_source,
                            "selected_reference_price": result.reference_price,
                            "selected_adv20_source": result.adv20_source,
                            "selected_adv20": result.avg_volume_20d,
                        }
                    print(f"[REFERENCE][CACHE_HIT] symbol={identity.symbol} identity_key={identity.key} source=persistent lookup_key={key}")
                    print(f"[RVOL][CACHE_HIT] symbol={identity.symbol} identity_key={identity.key} source=persistent lookup_key={key}")
                    return result
            print(f"[REFERENCE][CACHE_MISS] symbol={identity.symbol} identity_key={identity.key} source=persistent")
        else:
            print(f"[REFERENCE][CACHE_MISS] symbol={identity.symbol} identity_key={identity.key} source=persistent_skipped_no_conid")

        debug_trace = bool(getattr(provider, "debug_reference_trace", False))
        history_identity, qualified_ok = self._qualify_history_identity(provider, identity)
        history_trace: dict[str, Any] = {
            "identity_key": identity.key,
            "symbol": identity.symbol,
            "qualified_ok": qualified_ok,
            "history_identity_key": history_identity.key,
            "qualified_identity": {
                "conId": history_identity.con_id,
                "secType": history_identity.sec_type,
                "exchange": history_identity.exchange,
                "primaryExchange": history_identity.primary_exchange,
                "tradingClass": history_identity.trading_class,
                "localSymbol": history_identity.local_symbol,
                "currency": history_identity.currency,
            },
            "history_attempts": [],
        }
        bars = self._request_historical_daily_bars(provider, history_identity, session_label=session_label, trace=history_trace) if qualified_ok else []
        prev_close = self._last_completed_close(bars)
        snapshot_reference = None
        reference_source = "UNRESOLVED"
        if prev_close is not None:
            reference_source = "IBKR_DAILY_BARS"
        elif (provider_prev_close := self._provider_prev_close_fallback(provider, history_identity)) is not None:
            prev_close = provider_prev_close
            reference_source = "PROVIDER_PREV_CLOSE_FALLBACK"
        elif (quote_close := self._quote_close_fallback(provider, identity)) is not None:
            prev_close = quote_close
            reference_source = "QUOTE_CLOSE_FALLBACK"
        elif normalize_session_label(session_label) in {"RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE"} and (
            synthetic_reference := self._scanner_pct_synthetic_fallback(current_last_price=current_last_price, ibkr_change_pct=ibkr_change_pct)
        ) is not None:
            prev_close = synthetic_reference
            reference_source = "SCANNER_PCT_SYNTHETIC_FALLBACK"
        elif (snapshot_reference := self._snapshot_reference_fallback(session_label=session_label, rth_close_price=rth_close_price, current_last_price=current_last_price)) is not None:
            prev_close = snapshot_reference
            reference_source = "SNAPSHOT_LAST_PRICE_FALLBACK"
        avg_volume, window_days = self._average_volume(bars)
        provider_avg_volume, provider_window = self._provider_adv20_fallback(provider, history_identity)
        reference_failure_reason = None
        if reference_source != "IBKR_DAILY_BARS":
            reference_failure_reason = "HISTORY_UNAVAILABLE" if qualified_ok else "QUALIFY_FAILED"
        adv_source = "INTRADAY_STATS" if intraday_avg_volume_20d is not None else ("IBKR_DAILY_BARS" if avg_volume is not None else ("PROVIDER_ADV20_FALLBACK" if provider_avg_volume is not None else "UNAVAILABLE"))
        resolved_avg_volume = intraday_avg_volume_20d if intraday_avg_volume_20d is not None else (avg_volume if avg_volume is not None else provider_avg_volume)
        resolved_window_days = 20 if intraday_avg_volume_20d is not None else (window_days if window_days is not None else provider_window)
        rvol_failure_reason = None if resolved_avg_volume is not None else "ADV20_UNAVAILABLE"
        if debug_trace:
            print(
                "[REFERENCE][TRACE] "
                f"symbol={identity.symbol} session={normalize_session_label(session_label)} "
                f"qualified_ok={qualified_ok} history_identity={history_identity.key} "
                f"last={current_last_price} volume={current_volume} intraday_adv20={intraday_avg_volume_20d} "
                f"rth_open={rth_open_price} rth_close={rth_close_price} ibkr_change_pct={ibkr_change_pct} "
                f"selected_reference_source={reference_source} selected_reference={prev_close} "
                f"selected_adv20_source={adv_source} selected_adv20={resolved_avg_volume}"
            )
        if bars:
            print(
                f"[REFERENCE][HISTORICAL_RESULT] symbol={identity.symbol} identity_key={identity.key} "
                f"bar_count={len(bars)} first_bar_date={bars[0].trading_date} last_bar_date={bars[-1].trading_date} "
                f"found={prev_close is not None} value={prev_close} window_days={window_days} selected_source={reference_source}"
            )
            print(
                f"[RVOL][HISTORICAL_RESULT] symbol={identity.symbol} identity_key={identity.key} avg_volume_20d={resolved_avg_volume} window_days={resolved_window_days}"
            )
        else:
            print(
                f"[REFERENCE][FAIL] symbol={identity.symbol} identity_key={identity.key} reason=HISTORY_UNAVAILABLE_ZERO_BARS selected_source={reference_source}"
            )
            print(f"[RVOL][FAIL] symbol={identity.symbol} identity_key={identity.key} reason={rvol_failure_reason}")

        payload = {
            "identity_key": identity.key,
            "symbol": identity.symbol,
            "reference_price": prev_close,
            "reference_label": "LAST_RTH_CLOSE",
            "reference_source": reference_source,
            "reference_resolved": prev_close is not None,
            "asof_trading_date": bars[-1].trading_date if bars else None,
            "cache_trading_date": trading_date,
            "avg_volume_20d": resolved_avg_volume,
            "average_daily_volume_window_days": resolved_window_days,
            "adv20_source": adv_source,
            "adv20_resolved": resolved_avg_volume is not None,
            "resolved_at_utc": datetime.now(timezone.utc).isoformat(),
            "aliases": [] if identity.con_id not in {None, 0} else list(identity.aliases),
            "history_lookup_key_used": history_identity.key if bars else None,
            "reference_failure_reason": reference_failure_reason,
            "rvol_failure_reason": rvol_failure_reason,
            "reference_degraded": reference_source in {"CACHED_CLOSE_FALLBACK", "PROVIDER_PREV_CLOSE_FALLBACK", "QUOTE_CLOSE_FALLBACK", "SCANNER_PCT_SYNTHETIC_FALLBACK", "SNAPSHOT_LAST_PRICE_FALLBACK"},
            "reference_synthetic": reference_source == "SCANNER_PCT_SYNTHETIC_FALLBACK",
        }
        history_trace.update(
            {
                "selected_reference_source": reference_source,
                "selected_reference_price": prev_close,
                "selected_adv20_source": adv_source,
                "selected_adv20": resolved_avg_volume,
                "reference_failure_reason": reference_failure_reason,
                "rvol_failure_reason": rvol_failure_reason,
            }
        )
        if (prev_close is not None or resolved_avg_volume is not None) and identity.con_id not in {None, 0}:
            self.cache.put(cache_keys, payload)
            print(f"[REFERENCE][PERSIST] symbol={identity.symbol} identity_key={identity.key} path={self.cache.path} keys={cache_keys}")
        result = self._result_from_cache(history_identity if qualified_ok else identity, payload, session_label, current_volume, current_last_price, rth_open_price, rth_close_price, ibkr_change_pct, persisted_pct_change)
        for key in cache_keys:
            self._cycle_cache[key] = result
            self._last_resolution_trace[key] = dict(history_trace)
        return result

    def _snapshot_reference_fallback(self, *, session_label: str, rth_close_price: Optional[float], current_last_price: Optional[float]) -> Optional[float]:
        if normalize_session_label(session_label) != "PRE":
            return None
        if rth_close_price is not None:
            print(f"[REFERENCE][SNAPSHOT_FALLBACK] session=PRE source=last_close_tick value={rth_close_price}")
            return float(rth_close_price)
        if current_last_price is not None:
            print(f"[REFERENCE][SNAPSHOT_FALLBACK] session=PRE source=last value={current_last_price}")
            return float(current_last_price)
        return None

    def _request_historical_daily_bars(self, provider: Any, identity: CandidateIdentity, *, session_label: str, trace: dict[str, Any] | None = None) -> list[HistoricalDailyBar]:
        get_bars = getattr(provider, "get_daily_bars", None)
        if callable(get_bars) and _has_concrete_method(provider, "get_daily_bars"):
            print(
                f"[REFERENCE][HISTORICAL_REQUEST] identity_key={identity.key} source=provider_daily_bars "
                f"{self._history_contract_fields(identity)}"
            )
            primary_kwargs = {"lookback_days": 25}
            print(
                f"[REFERENCE][HISTORICAL_REQUEST_PARAMS] identity_key={identity.key} attempt=primary "
                f"useRTH=True endDateTime='' durationStr=25 D"
            )
            bars = self._normalize_bars(get_bars(identity, **primary_kwargs))
            if trace is not None:
                trace.setdefault("history_attempts", []).append(
                    {
                        "attempt": "primary",
                        "params": {"useRTH": True, "endDateTime": "", "durationStr": "25 D"},
                        "raw_bar_count": len(bars),
                    }
                )
            print(
                f"[REFERENCE][HISTORICAL_ATTEMPT_RESULT] identity_key={identity.key} attempt=primary "
                f"raw_bar_count={len(bars)} normalized_bar_count={len(bars)}"
            )
            if not bars and normalize_session_label(session_label) in {"RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE"}:
                explicit_end = f"{date.today().strftime('%Y%m%d')} 09:29:59 US/Eastern"
                print(
                    f"[REFERENCE][HISTORICAL_RETRY] identity_key={identity.key} reason=ZERO_BARS_RTH_PRIMARY "
                    f"retry_useRTH=False endDateTime='{explicit_end}'"
                )
                try:
                    bars = self._normalize_bars(get_bars(identity, lookback_days=25, use_rth=False, end_datetime=explicit_end))
                except TypeError:
                    print(
                        f"[REFERENCE][HISTORICAL_RETRY_UNSUPPORTED] identity_key={identity.key} "
                        "provider_signature_missing_use_rth_or_end_datetime=True"
                    )
                    bars = []
                if trace is not None:
                    trace.setdefault("history_attempts", []).append(
                        {
                            "attempt": "retry_useRTH_false",
                            "params": {"useRTH": False, "endDateTime": explicit_end, "durationStr": "25 D"},
                            "raw_bar_count": len(bars),
                        }
                    )
                print(
                    f"[REFERENCE][HISTORICAL_ATTEMPT_RESULT] identity_key={identity.key} attempt=retry_useRTH_false "
                    f"raw_bar_count={len(bars)} normalized_bar_count={len(bars)}"
                )
            if bars:
                print(
                    f"[REFERENCE][HISTORICAL_RESPONSE] identity_key={identity.key} bar_count={len(bars)} "
                    f"first_bar_date={bars[0].trading_date} last_bar_date={bars[-1].trading_date}"
                )
            else:
                print(
                    f"[REFERENCE][HISTORICAL_RESPONSE] identity_key={identity.key} bar_count=0 "
                    f"fail_reason=ZERO_BARS_RETURNED"
                )
                print(
                    f"[REFERENCE][ZERO_BARS_DEBUG] symbol={identity.symbol} conId={identity.con_id} exchange={identity.exchange} "
                    f"primaryExchange={identity.primary_exchange} tradingClass={identity.trading_class} localSymbol={identity.local_symbol}"
                )
            return bars
        prev_close = getattr(provider, "get_previous_rth_close", None)
        avg_volume = getattr(provider, "get_average_daily_volume", None)
        legacy_prev_close = getattr(provider, "get_prev_close", None)
        legacy_intraday = getattr(provider, "get_intraday_stats", None)
        synthetic: list[HistoricalDailyBar] = []
        if callable(prev_close) and _has_concrete_method(provider, "get_previous_rth_close"):
            print(
                f"[REFERENCE][HISTORICAL_REQUEST] identity_key={identity.key} source=provider_prev_close "
                f"{self._history_contract_fields(identity)}"
            )
            value = prev_close(identity)
        elif callable(legacy_prev_close):
            print(
                f"[REFERENCE][HISTORICAL_REQUEST] identity_key={identity.key} source=legacy_prev_close "
                f"{self._history_contract_fields(identity)}"
            )
            value = legacy_prev_close(identity.symbol)
        else:
            value = None
        if value is not None:
            synthetic.append(HistoricalDailyBar(trading_date=date.today().isoformat(), close=float(value), volume=None))
        if callable(avg_volume) and _has_concrete_method(provider, "get_average_daily_volume"):
            print(
                f"[REFERENCE][HISTORICAL_REQUEST] identity_key={identity.key} source=provider_avg_volume "
                f"{self._history_contract_fields(identity)}"
            )
            avg, window = avg_volume(identity, window=20)
        elif callable(legacy_intraday):
            print(
                f"[REFERENCE][HISTORICAL_REQUEST] identity_key={identity.key} source=legacy_intraday_stats "
                f"{self._history_contract_fields(identity)}"
            )
            stats = legacy_intraday(identity.symbol)
            avg = getattr(stats, "average_daily_volume_20d", None)
            window = getattr(stats, "average_daily_volume_window_days", None)
        else:
            avg, window = None, None
        if avg is not None:
            synthetic.extend(HistoricalDailyBar(trading_date=f"window-{idx}", close=None, volume=int(avg)) for idx in range(window or 20))
        if synthetic:
            print(
                f"[REFERENCE][HISTORICAL_RESPONSE] identity_key={identity.key} bar_count={len(synthetic)} "
                f"first_bar_date={synthetic[0].trading_date} last_bar_date={synthetic[-1].trading_date}"
            )
        else:
            print(
                f"[REFERENCE][HISTORICAL_RESPONSE] identity_key={identity.key} bar_count=0 fail_reason=NO_HISTORY_METHODS"
            )
        return synthetic

    def _provider_prev_close_fallback(self, provider: Any, identity: CandidateIdentity) -> Optional[float]:
        prev_close = getattr(provider, "get_previous_rth_close", None)
        if callable(prev_close):
            value = prev_close(identity)
            if value is not None:
                return float(value)
        legacy_prev_close = getattr(provider, "get_prev_close", None)
        if callable(legacy_prev_close):
            value = legacy_prev_close(identity.symbol)
            if value is not None:
                return float(value)
        return None

    def _quote_close_fallback(self, provider: Any, identity: CandidateIdentity) -> Optional[float]:
        get_quote = getattr(provider, "get_quote", None)
        if not callable(get_quote):
            return None
        try:
            quote = get_quote(identity.symbol)
        except Exception:
            return None
        value = _to_float(getattr(quote, "close", None))
        if value is not None:
            print(f"[REFERENCE][QUOTE_CLOSE_FALLBACK] symbol={identity.symbol} identity_key={identity.key} value={value}")
        return value

    def _provider_adv20_fallback(self, provider: Any, identity: CandidateIdentity) -> tuple[Optional[int], Optional[int]]:
        avg_volume = getattr(provider, "get_average_daily_volume", None)
        if callable(avg_volume):
            try:
                resolved = avg_volume(identity, window=20)
            except Exception:
                return None, None
            if not isinstance(resolved, tuple) or len(resolved) != 2:
                return None, None
            avg, window = resolved
            return _to_int(avg), _to_int(window)
        return None, None

    def _scanner_pct_synthetic_fallback(self, *, current_last_price: Optional[float], ibkr_change_pct: Optional[float]) -> Optional[float]:
        price = _to_float(current_last_price)
        pct = _to_float(ibkr_change_pct)
        if price is None or pct is None or pct <= -100:
            return None
        base = price / (1.0 + (pct / 100.0))
        return round(base, 4) if base > 0 else None

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
        reference_source = str(payload.get("reference_source") or "UNRESOLVED")
        reference_quality_tier = self.REFERENCE_QUALITY_BY_SOURCE.get(reference_source, "NONE")
        continuity_usable_reference = reference_source != "UNRESOLVED"
        qualification_usable_reference = reference_source in {"IBKR_DAILY_BARS", "CACHED_CLOSE_FALLBACK"}
        if reference_source in {"PROVIDER_PREV_CLOSE_FALLBACK", "QUOTE_CLOSE_FALLBACK"}:
            qualification_usable_reference = True
        execution_usable_reference = reference_source in {"IBKR_DAILY_BARS", "CACHED_CLOSE_FALLBACK", "PROVIDER_PREV_CLOSE_FALLBACK", "QUOTE_CLOSE_FALLBACK"}
        return CanonicalReferenceResult(
            identity_key=identity.key,
            symbol=identity.symbol,
            qualified_identity=identity,
            reference_price=_to_float(payload.get("reference_price")),
            reference_label=str(payload.get("reference_label") or "LAST_RTH_CLOSE"),
            reference_source=reference_source,
            reference_quality_tier=reference_quality_tier,
            reference_resolved=bool(payload.get("reference_resolved")),
            continuity_usable_reference=continuity_usable_reference,
            qualification_usable_reference=qualification_usable_reference,
            execution_usable_reference=execution_usable_reference,
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
            reference_degraded=bool(payload.get("reference_degraded")),
            reference_synthetic=bool(payload.get("reference_synthetic")),
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
