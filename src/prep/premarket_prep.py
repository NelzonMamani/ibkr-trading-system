from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from src.config.config_resolver import get_config
from src.core.event_collector import EventCollector
from src.data.news.news_provider import NewsProvider
from src.utils.time_utils import to_ny_time


@dataclass
class PrepLevels:
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    vwap_anchor: Optional[float] = None
    prior_high: Optional[float] = None
    prior_low: Optional[float] = None
    prior_close: Optional[float] = None
    gap_pct: Optional[float] = None
    premarket_high: Optional[float] = None
    premarket_low: Optional[float] = None
    prior_day_high: Optional[float] = None
    prior_day_low: Optional[float] = None
    multi_day_high: Optional[float] = None
    multi_day_low: Optional[float] = None


@dataclass
class PrepSnapshot:
    symbol: str
    float_shares: Optional[int] = None
    float_asof: Optional[datetime] = None
    levels: PrepLevels = field(default_factory=PrepLevels)
    levels_asof: Optional[datetime] = None
    news_context: list[dict] = field(default_factory=list)
    news_asof: Optional[datetime] = None
    data_quality_flags: list[str] = field(default_factory=list)
    persisted_pct_change: Optional[float] = None
    persisted_rvol: Optional[float] = None
    persisted_volume: Optional[float] = None
    persisted_reference_label: Optional[str] = None
    persisted_session_label: Optional[str] = None
    persisted_asof: Optional[datetime] = None
    watchlist_member: bool = False
    focus_member: bool = False
    last_refresh_reasons: list[str] = field(default_factory=list)
    context_status: str = "newly_confirmed"
    last_transition_reason: Optional[str] = None
    live_confirmed_fields: list[str] = field(default_factory=list)
    context_only_fields: list[str] = field(default_factory=list)


class PreMarketPrepEngine:
    MAX_SYMBOLS = 150
    NEWS_TTL = timedelta(hours=6)
    LEVELS_TTL = timedelta(hours=48)
    FLOAT_TTL = timedelta(days=7)

    def __init__(self, event_collector: EventCollector | None = None) -> None:
        self._cache: OrderedDict[str, PrepSnapshot] = OrderedDict()
        self._event_collector = event_collector
        self._last_full_reset: Optional[str] = None
        self._last_session_label: Optional[str] = None
        self._news_provider = NewsProvider()

    def update_from_universe(
        self,
        symbols: Sequence[str],
        *,
        last_price_by_symbol: Optional[dict[str, Optional[float]]] = None,
        float_by_symbol: Optional[dict[str, Optional[int]]] = None,
        prior_close_by_symbol: Optional[dict[str, Optional[float]]] = None,
        gap_pct_by_symbol: Optional[dict[str, Optional[float]]] = None,
        persisted_pct_change_by_symbol: Optional[dict[str, Optional[float]]] = None,
        persisted_rvol_by_symbol: Optional[dict[str, Optional[float]]] = None,
        persisted_volume_by_symbol: Optional[dict[str, Optional[float]]] = None,
        persisted_reference_label_by_symbol: Optional[dict[str, Optional[str]]] = None,
        persisted_session_label_by_symbol: Optional[dict[str, Optional[str]]] = None,
        watchlist_symbols: Optional[set[str]] = None,
        focus_symbols: Optional[set[str]] = None,
        session_label: Optional[str] = None,
        reason: str = "SCANNER_UNIVERSE",
    ) -> None:
        now = datetime.now(timezone.utc)
        self._full_reset_if_friday(now)
        self._cleanup_expired(now)

        if session_label and self._last_session_label != session_label:
            print(f"[PREP][SESSION_TRANSITION] from={self._last_session_label} to={session_label}")
            self._last_session_label = session_label

        requested = [symbol.upper() for symbol in symbols if symbol]
        requested_was_empty = not bool(requested)
        existing = list(self._cache.keys())
        if not requested:
            requested = existing
        merged = list(dict.fromkeys(requested + existing))[: self.MAX_SYMBOLS]
        if not merged:
            return

        news_lookup = self._news_provider.get_news_batch(merged)
        updated_symbols: list[str] = []

        for symbol in merged:
            snapshot = self._cache.get(symbol) or PrepSnapshot(symbol=symbol)
            self._cache[symbol] = snapshot
            self._cache.move_to_end(symbol)

            last_price = (last_price_by_symbol or {}).get(symbol)
            float_value = (float_by_symbol or {}).get(symbol)
            prior_close = (prior_close_by_symbol or {}).get(symbol)
            gap_pct = (gap_pct_by_symbol or {}).get(symbol)
            persisted_pct_change = (persisted_pct_change_by_symbol or {}).get(symbol)
            persisted_rvol = (persisted_rvol_by_symbol or {}).get(symbol)
            persisted_volume = (persisted_volume_by_symbol or {}).get(symbol)
            persisted_reference_label = (persisted_reference_label_by_symbol or {}).get(symbol)
            persisted_session_label = (persisted_session_label_by_symbol or {}).get(symbol)

            refresh_reasons = [reason]
            snapshot.last_transition_reason = reason
            if float_value is not None:
                snapshot.float_shares = float_value
                snapshot.float_asof = now
                refresh_reasons.append("FLOAT_REFRESH")
            elif snapshot.float_shares is None:
                snapshot.data_quality_flags.append("MISSING_FLOAT")

            if self._levels_expired(snapshot, now) or last_price is not None or prior_close is not None:
                snapshot.levels = PrepLevels(
                    ema50=last_price,
                    ema200=last_price,
                    vwap_anchor=last_price,
                    prior_close=prior_close,
                    gap_pct=gap_pct,
                    premarket_high=snapshot.levels.premarket_high,
                    premarket_low=snapshot.levels.premarket_low,
                    prior_day_high=snapshot.levels.prior_day_high,
                    prior_day_low=snapshot.levels.prior_day_low,
                    multi_day_high=snapshot.levels.multi_day_high,
                    multi_day_low=snapshot.levels.multi_day_low,
                )
                snapshot.levels_asof = now
                refresh_reasons.append("LEVELS_REFRESH")
                if last_price is None:
                    snapshot.data_quality_flags.append("PREP_CONTEXT_ONLY")

            news_result = news_lookup.get(symbol)
            if news_result is not None:
                snapshot.news_context = list(news_result.news_context)
                snapshot.news_asof = now
                refresh_reasons.append("NEWS_REFRESH")
                if any(item.get("freshness") == "stale" for item in snapshot.news_context):
                    snapshot.data_quality_flags.append("STALE_NEWS")

            if persisted_pct_change is not None or persisted_rvol is not None or persisted_volume is not None:
                snapshot.persisted_pct_change = persisted_pct_change
                snapshot.persisted_rvol = persisted_rvol
                snapshot.persisted_volume = persisted_volume
                snapshot.persisted_reference_label = persisted_reference_label
                snapshot.persisted_session_label = persisted_session_label
                snapshot.persisted_asof = now
                refresh_reasons.append("REFERENCE_REFRESH")

            snapshot.watchlist_member = symbol in (watchlist_symbols or set()) if watchlist_symbols is not None else snapshot.watchlist_member
            snapshot.focus_member = symbol in (focus_symbols or set()) if focus_symbols is not None else snapshot.focus_member

            if requested_was_empty or symbol not in requested:
                snapshot.context_status = "retained_context"
                print(f"[PREP][WATCHLIST_RETAIN] symbol={symbol} status=retained_context")
            elif last_price is None:
                snapshot.context_status = "degraded_data"
                print(f"[PREP][CONTEXT_DEGRADED] symbol={symbol}")
            else:
                snapshot.context_status = "newly_confirmed"
                print(f"[PREP][CONTEXT_REFRESH] symbol={symbol}")

            snapshot.last_refresh_reasons = sorted(set(snapshot.last_refresh_reasons + refresh_reasons))
            updated_symbols.append(symbol)

        self._evict_excess()
        self._emit_update_event(updated_symbols, reason=reason)

    def get_snapshot(self, symbol: str) -> Optional[PrepSnapshot]:
        return self._cache.get((symbol or "").upper())

    def hydrate_from_artifact(self, symbols: Sequence[dict]) -> int:
        now = datetime.now(timezone.utc)
        restored = 0
        for entry in symbols:
            symbol = str(entry.get("symbol") or "").upper()
            if not symbol:
                continue
            snapshot = PrepSnapshot(symbol=symbol)
            float_value = entry.get("float") or entry.get("float_shares")
            try:
                snapshot.float_shares = int(float_value) if float_value is not None else None
            except (TypeError, ValueError):
                snapshot.float_shares = None
            snapshot.float_asof = _parse_datetime(entry.get("float_asof")) or now
            snapshot.levels = PrepLevels(
                prior_high=entry.get("premarket_high"),
                prior_low=entry.get("premarket_low"),
                prior_close=entry.get("prior_close"),
                gap_pct=entry.get("gap") or entry.get("gap_context"),
                premarket_high=entry.get("premarket_high"),
                premarket_low=entry.get("premarket_low"),
                prior_day_high=entry.get("prior_day_high"),
                prior_day_low=entry.get("prior_day_low"),
                multi_day_high=entry.get("multi_day_high"),
                multi_day_low=entry.get("multi_day_low"),
            )
            snapshot.levels_asof = _parse_datetime(entry.get("levels_asof")) or now
            snapshot.news_context = list(entry.get("news_context") or [])
            snapshot.news_asof = _parse_datetime(entry.get("news_asof")) or now
            snapshot.persisted_pct_change = entry.get("persisted_pct_change") or entry.get("pct_change_context")
            snapshot.persisted_rvol = entry.get("persisted_rvol") or entry.get("scanner_rvol")
            snapshot.persisted_volume = entry.get("persisted_volume") or entry.get("volume")
            snapshot.persisted_reference_label = entry.get("persisted_reference_label") or entry.get("reference_label")
            snapshot.persisted_session_label = entry.get("persisted_session_label") or entry.get("session_label")
            snapshot.persisted_asof = _parse_datetime(entry.get("persisted_asof")) or now
            snapshot.watchlist_member = bool(entry.get("watchlist_member"))
            snapshot.focus_member = bool(entry.get("focus_member"))
            snapshot.last_refresh_reasons = list(entry.get("last_refresh_reasons") or [])
            snapshot.context_status = str(entry.get("context_status") or "retained_context")
            snapshot.last_transition_reason = entry.get("last_transition_reason")
            snapshot.live_confirmed_fields = list(entry.get("live_confirmed_fields") or [])
            snapshot.context_only_fields = list(entry.get("context_only_fields") or [])
            snapshot.data_quality_flags = list(entry.get("data_quality_flags") or [])
            self._cache[symbol] = snapshot
            restored += 1
        self._evict_excess()
        return restored

    def build_artifact_payload(self, symbols: Sequence[str]) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for symbol in symbols:
            snapshot = self.get_snapshot(symbol)
            if snapshot is None:
                rows.append(
                    {
                        "symbol": symbol,
                        "news_context": [],
                        "last_refresh_reasons": [],
                        "terminal_state": "NOT_READY_DATA_WEAK",
                        "terminal_reason": "no_prep_snapshot",
                    }
                )
                continue
            float_age_days = (
                (datetime.now(timezone.utc) - snapshot.float_asof).days
                if snapshot.float_asof is not None
                else None
            )
            float_age_bucket = (
                "UNKNOWN"
                if float_age_days is None
                else "FRESH_0_7D"
                if float_age_days <= 7
                else "STALE_8_30D"
                if float_age_days <= 30
                else "OLD_GT_30D"
            )
            float_class = _float_classification(snapshot.float_shares)
            float_state = _float_state(snapshot.float_shares, snapshot.float_asof)
            fresh_news = [item for item in snapshot.news_context if item.get("freshness") == "fresh"]
            stale_news = [item for item in snapshot.news_context if item.get("freshness") != "fresh"]
            top_news = snapshot.news_context[0] if snapshot.news_context else {}
            catalyst_present = bool(fresh_news)
            catalyst_confidence = 0.85 if catalyst_present else 0.0
            catalyst_type = (
                str(top_news.get("catalyst_tag") or "unknown").lower().replace(" ", "_")
                if snapshot.news_context
                else "unknown"
            )
            has_levels = snapshot.levels.premarket_high is not None and snapshot.levels.premarket_low is not None
            premarket_range_pct = None
            if (
                has_levels
                and snapshot.levels.premarket_low
                and snapshot.levels.premarket_low > 0
                and snapshot.levels.premarket_high is not None
            ):
                premarket_range_pct = round(
                    ((snapshot.levels.premarket_high - snapshot.levels.premarket_low) / snapshot.levels.premarket_low) * 100.0,
                    4,
                )
            pct_change_quality = min(max(float(snapshot.persisted_pct_change or 0.0) / 15.0, 0.0), 1.0)
            rvol_quality = min(max(float(snapshot.persisted_rvol or 0.0) / 4.0, 0.0), 1.0)
            float_quality = {
                "ROSS_SWEET_SPOT": 1.0,
                "LOW_FLOAT": 0.85,
                "MID_FLOAT": 0.55,
                "HIGH_FLOAT": 0.30,
                "UNKNOWN_FLOAT": 0.0,
            }.get(float_class, 0.0)
            catalyst_quality = catalyst_confidence
            structure_quality = 0.8 if has_levels else 0.2
            stale_penalty = 0.3 if stale_news and not fresh_news else 0.0
            missing_penalty = 0.4 if float_class == "UNKNOWN_FLOAT" else 0.0
            score_raw = (
                0.22 * pct_change_quality
                + 0.20 * rvol_quality
                + 0.20 * float_quality
                + 0.20 * catalyst_quality
                + 0.18 * structure_quality
                - stale_penalty
                - missing_penalty
            )
            premarket_quality_score = round(max(0.0, min(score_raw, 1.0)) * 100.0, 2)
            if not catalyst_present:
                terminal_state = "NOT_READY_NO_CATALYST"
                terminal_reason = "no_credible_catalyst_found"
            elif float_class == "UNKNOWN_FLOAT":
                terminal_state = "NOT_READY_FLOAT_UNKNOWN"
                terminal_reason = "float_unknown"
            elif premarket_quality_score >= 75:
                terminal_state = "READY_HIGH_QUALITY"
                terminal_reason = "high_quality_premarket_packet"
            elif premarket_quality_score >= 50:
                terminal_state = "READY_MEDIUM_QUALITY"
                terminal_reason = "adequate_quality_premarket_packet"
            else:
                terminal_state = "READY_LOW_QUALITY"
                terminal_reason = "low_rank_but_usable"
            rows.append(
                {
                    "symbol": symbol,
                    "last_known_price": snapshot.levels.vwap_anchor,
                    "prior_close": snapshot.levels.prior_close,
                    "session_reference_price": snapshot.levels.prior_close,
                    "pct_change_context": snapshot.persisted_pct_change,
                    "gap_context": snapshot.levels.gap_pct,
                    "float": snapshot.float_shares,
                    "float_shares": snapshot.float_shares,
                    "float_millions": round(snapshot.float_shares / 1_000_000.0, 4) if snapshot.float_shares else None,
                    "float_source": "prep_cache" if snapshot.float_shares is not None else "missing",
                    "float_classification": float_class,
                    "float_state": float_state,
                    "float_cache_hit": snapshot.float_shares is not None,
                    "float_asof": snapshot.float_asof.isoformat() if snapshot.float_asof else None,
                    "float_age_days": float_age_days,
                    "float_age_bucket": float_age_bucket,
                    "float_confidence": 1.0 if float_state == "FLOAT_CONFIRMED" else 0.6 if float_state == "FLOAT_ESTIMATED" else 0.0,
                    "news_context": snapshot.news_context,
                    "news_count": len(snapshot.news_context),
                    "fresh_news_count": sum(1 for item in snapshot.news_context if item.get("freshness") == "fresh"),
                    "stale_news_count": sum(1 for item in snapshot.news_context if item.get("freshness") != "fresh"),
                    "top_news_title": snapshot.news_context[0].get("title") if snapshot.news_context else None,
                    "top_news_catalyst_tag": snapshot.news_context[0].get("catalyst_tag") if snapshot.news_context else None,
                    "news_asof": snapshot.news_asof.isoformat() if snapshot.news_asof else None,
                    "catalyst_packet": {
                        "has_news": bool(snapshot.news_context),
                        "catalyst_present": catalyst_present,
                        "catalyst_type": catalyst_type,
                        "catalyst_title": top_news.get("title"),
                        "catalyst_source_count": len({str(item.get('source') or '').lower() for item in snapshot.news_context if item.get("source")}),
                        "catalyst_source_quality": "multi_source" if len(snapshot.news_context) >= 2 else "single_source" if snapshot.news_context else "none",
                        "catalyst_confidence": catalyst_confidence,
                        "stale_news_flag": bool(stale_news and not fresh_news),
                        "no_news_reason": None if snapshot.news_context else "no_credible_catalyst_found",
                    },
                    "premarket_high": snapshot.levels.premarket_high,
                    "premarket_low": snapshot.levels.premarket_low,
                    "premarket_structure_packet": {
                        "premarket_high": snapshot.levels.premarket_high,
                        "premarket_low": snapshot.levels.premarket_low,
                        "premarket_range_pct": premarket_range_pct,
                        "premarket_volume": snapshot.persisted_volume,
                        "gap_classification": "VALID_ROSS_GAP" if (snapshot.levels.gap_pct or 0) >= 5 else "SMALL_GAP" if (snapshot.levels.gap_pct or 0) > 0 else "NO_GAP",
                        "extension_state": "EXTENDED" if (snapshot.levels.gap_pct or 0) >= 20 else "NORMAL",
                        "clean_breakout_candidate": bool(has_levels and catalyst_present),
                        "crowded_or_extended": bool((snapshot.levels.gap_pct or 0) >= 20),
                        "spread_quality": "UNKNOWN",
                        "liquidity_quality": "GOOD" if (snapshot.persisted_volume or 0) >= 100_000 else "WEAK",
                    },
                    "prior_day_high": snapshot.levels.prior_day_high,
                    "prior_day_low": snapshot.levels.prior_day_low,
                    "multi_day_high": snapshot.levels.multi_day_high,
                    "multi_day_low": snapshot.levels.multi_day_low,
                    "volume": snapshot.persisted_volume,
                    "scanner_rvol": snapshot.persisted_rvol,
                    "persisted_pct_change": snapshot.persisted_pct_change,
                    "persisted_rvol": snapshot.persisted_rvol,
                    "persisted_volume": snapshot.persisted_volume,
                    "persisted_reference_label": snapshot.persisted_reference_label,
                    "persisted_session_label": snapshot.persisted_session_label,
                    "persisted_asof": snapshot.persisted_asof.isoformat() if snapshot.persisted_asof else None,
                    "data_quality_flags": sorted(set(snapshot.data_quality_flags)),
                    "watchlist_member": snapshot.watchlist_member,
                    "focus_member": snapshot.focus_member,
                    "context_status": snapshot.context_status,
                    "last_refresh_reasons": snapshot.last_refresh_reasons,
                    "last_transition_reason": snapshot.last_transition_reason,
                    "live_confirmed_fields": snapshot.live_confirmed_fields,
                    "context_only_fields": snapshot.context_only_fields,
                    "premarket_quality_score": premarket_quality_score,
                    "score_breakdown": {
                        "pct_change_quality": round(pct_change_quality * 100.0, 2),
                        "rvol_quality": round(rvol_quality * 100.0, 2),
                        "float_quality": round(float_quality * 100.0, 2),
                        "catalyst_quality": round(catalyst_quality * 100.0, 2),
                        "structure_quality": round(structure_quality * 100.0, 2),
                        "stale_penalty": round(stale_penalty * 100.0, 2),
                        "missing_penalty": round(missing_penalty * 100.0, 2),
                    },
                    "terminal_state": terminal_state,
                    "terminal_reason": terminal_reason,
                }
            )
        rows = sorted(rows, key=lambda row: (-float(row.get("premarket_quality_score") or 0.0), row.get("symbol") or ""))
        for idx, row in enumerate(rows, start=1):
            row["watchlist_rank"] = idx
            row["focus_status"] = "IN_FOCUS_CANDIDATE" if idx <= 5 and str(row.get("terminal_state", "")).startswith("READY_") else "WATCHLIST_ONLY"
        return {"timestamp": now, "symbols": rows}

    def _cleanup_expired(self, now: datetime) -> None:
        for symbol, snapshot in list(self._cache.items()):
            if self._float_expired(snapshot, now) and self._levels_expired(snapshot, now) and self._news_expired(snapshot, now):
                self._cache.pop(symbol, None)

    def _float_expired(self, snapshot: PrepSnapshot, now: datetime) -> bool:
        return snapshot.float_asof is None or (now - snapshot.float_asof) > self.FLOAT_TTL

    def _levels_expired(self, snapshot: PrepSnapshot, now: datetime) -> bool:
        return snapshot.levels_asof is None or (now - snapshot.levels_asof) > self.LEVELS_TTL

    def _news_expired(self, snapshot: PrepSnapshot, now: datetime) -> bool:
        return snapshot.news_asof is None or (now - snapshot.news_asof) > self.NEWS_TTL

    def _evict_excess(self) -> None:
        while len(self._cache) > self.MAX_SYMBOLS:
            self._cache.popitem(last=False)

    def _full_reset_if_friday(self, now: datetime) -> None:
        ny_time = to_ny_time(now)
        if ny_time.weekday() != 4 or ny_time.hour < 18:
            return
        key = ny_time.date().isoformat()
        if self._last_full_reset == key:
            return
        self._cache.clear()
        self._last_full_reset = key

    def _emit_update_event(self, symbols: list[str], *, reason: str) -> None:
        if not self._event_collector:
            return
        payload = {"symbols": symbols, "count": len(symbols), "reason": reason, "timestamp_utc": datetime.now(timezone.utc).isoformat()}
        self._event_collector.emit(event_type="PREP_UPDATED", source="PreMarketPrep", payload=payload)
        self._event_collector.emit(event_type="PREP_CACHE_UPDATED", source="PreMarketPrep", payload=payload)


def _parse_datetime(raw: object) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _float_classification(float_shares: Optional[int]) -> str:
    if float_shares is None or float_shares <= 0:
        return "UNKNOWN_FLOAT"
    if float_shares < 10_000_000:
        return "LOW_FLOAT"
    if float_shares <= 20_000_000:
        return "ROSS_SWEET_SPOT"
    if float_shares <= 50_000_000:
        return "MID_FLOAT"
    return "HIGH_FLOAT"


def _float_state(float_shares: Optional[int], float_asof: Optional[datetime]) -> str:
    if float_shares is None or float_shares <= 0:
        return "FLOAT_UNKNOWN"
    if float_asof is None:
        return "FLOAT_ESTIMATED"
    age_days = (datetime.now(timezone.utc) - float_asof).days
    if age_days <= 7:
        return "FLOAT_CONFIRMED"
    return "FLOAT_ESTIMATED"
