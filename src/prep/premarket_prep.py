from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence

from src.config.config_resolver import get_config
from src.config.runtime_config import RunMode, get_run_mode
from src.core.event_collector import EventCollector
from src.news.news_fetcher import Headline, fetch_headlines_for_symbols
from src.news.verified_sources import load_verified_rss_sources
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


@dataclass
class PrepSnapshot:
    symbol: str
    float_shares: Optional[int] = None
    float_asof: Optional[datetime] = None
    levels: PrepLevels = field(default_factory=PrepLevels)
    levels_asof: Optional[datetime] = None
    news: list[Headline] = field(default_factory=list)
    news_asof: Optional[datetime] = None
    data_quality_flags: list[str] = field(default_factory=list)


class PreMarketPrepEngine:
    """Background cache for expensive pre-market data."""

    MAX_SYMBOLS = 150
    NEWS_TTL = timedelta(hours=6)
    LEVELS_TTL = timedelta(hours=48)
    FLOAT_TTL = timedelta(days=7)

    def __init__(self, event_collector: EventCollector | None = None) -> None:
        self._cache: OrderedDict[str, PrepSnapshot] = OrderedDict()
        self._event_collector = event_collector
        self._last_full_reset: Optional[str] = None

    def update_from_universe(
        self,
        symbols: Sequence[str],
        *,
        last_price_by_symbol: Optional[dict[str, Optional[float]]] = None,
        float_by_symbol: Optional[dict[str, Optional[int]]] = None,
        prior_close_by_symbol: Optional[dict[str, Optional[float]]] = None,
        gap_pct_by_symbol: Optional[dict[str, Optional[float]]] = None,
        reason: str = "SCANNER_UNIVERSE",
    ) -> None:
        now = datetime.now(timezone.utc)
        self._full_reset_if_friday(now)
        self._cleanup_expired(now)

        requested = [symbol.upper() for symbol in symbols if symbol]
        limited = requested[: self.MAX_SYMBOLS]
        if not limited:
            return

        allow_news = bool(get_config("NEWS_ENABLED")) and get_run_mode() not in {
            RunMode.LIVE,
            RunMode.LIVE_READ_ONLY,
            RunMode.LIVE_MICRO,
            RunMode.LIVE_ONE_SHARE,
            RunMode.PAPER,
        }
        news_lookup: dict[str, list[Headline]] = {}
        news_failure: Optional[str] = None
        if allow_news:
            try:
                sources = load_verified_rss_sources()
                news_lookup, summary = fetch_headlines_for_symbols(
                    limited,
                    sources,
                    lookback_hours=float(get_config("NEWS_LOOKBACK_HOURS")),
                    request_timeout_s=float(get_config("NEWS_REQUEST_TIMEOUT_S")),
                )
                if summary.reason:
                    news_failure = summary.reason
            except Exception as exc:  # pragma: no cover - network dependent
                news_failure = str(exc)

        updated_symbols: list[str] = []
        for symbol in limited:
            snapshot = self._cache.get(symbol)
            if snapshot is None:
                snapshot = PrepSnapshot(symbol=symbol)
                self._cache[symbol] = snapshot
            self._cache.move_to_end(symbol)

            last_price = (last_price_by_symbol or {}).get(symbol)
            float_value = (float_by_symbol or {}).get(symbol)
            prior_close = (prior_close_by_symbol or {}).get(symbol)
            gap_pct = (gap_pct_by_symbol or {}).get(symbol)

            if float_value is not None and self._float_expired(snapshot, now):
                snapshot.float_shares = float_value
                snapshot.float_asof = now

            if self._levels_expired(snapshot, now):
                snapshot.levels = PrepLevels(
                    ema50=last_price,
                    ema200=last_price,
                    vwap_anchor=last_price,
                    prior_close=prior_close,
                    gap_pct=gap_pct,
                )
                snapshot.levels_asof = now
                if last_price is None:
                    snapshot.data_quality_flags.append("PREP_LEVELS_APPROX")

            if allow_news and self._news_expired(snapshot, now):
                snapshot.news = news_lookup.get(symbol, [])
                snapshot.news_asof = now
                if news_failure:
                    snapshot.data_quality_flags.append("NEWS_STALE")

            updated_symbols.append(symbol)

        self._evict_excess()
        self._emit_update_event(updated_symbols, reason=reason)

    def get_snapshot(self, symbol: str) -> Optional[PrepSnapshot]:
        if not symbol:
            return None
        return self._cache.get(symbol.upper())

    def _cleanup_expired(self, now: datetime) -> None:
        for symbol, snapshot in list(self._cache.items()):
            if (
                self._float_expired(snapshot, now)
                and self._levels_expired(snapshot, now)
                and self._news_expired(snapshot, now)
            ):
                self._cache.pop(symbol, None)

    def _float_expired(self, snapshot: PrepSnapshot, now: datetime) -> bool:
        if snapshot.float_asof is None:
            return True
        return (now - snapshot.float_asof) > self.FLOAT_TTL

    def _levels_expired(self, snapshot: PrepSnapshot, now: datetime) -> bool:
        if snapshot.levels_asof is None:
            return True
        return (now - snapshot.levels_asof) > self.LEVELS_TTL

    def _news_expired(self, snapshot: PrepSnapshot, now: datetime) -> bool:
        if snapshot.news_asof is None:
            return True
        return (now - snapshot.news_asof) > self.NEWS_TTL

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
        if self._event_collector:
            self._event_collector.emit(
                event_type="PREP_RESET",
                source="PreMarketPrep",
                payload={"reset_date": key, "reason": "FRIDAY_RESET"},
            )

    def _emit_update_event(self, symbols: list[str], *, reason: str) -> None:
        if not self._event_collector:
            return
        payload = {
            "symbols": symbols,
            "count": len(symbols),
            "reason": reason,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        self._event_collector.emit(
            event_type="PREP_UPDATED",
            source="PreMarketPrep",
            payload=payload,
        )
        self._event_collector.emit(
            event_type="PREP_CACHE_UPDATED",
            source="PreMarketPrep",
            payload=payload,
        )
