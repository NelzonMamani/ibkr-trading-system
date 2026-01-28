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
    last_news_timestamp: Optional[float] = None
    news_age_minutes: Optional[int] = None
    has_recent_news: bool = False
    data_quality_flags: list[str] = field(default_factory=list)


class PreMarketPrepEngine:
    """Background cache for expensive pre-market data."""

    MAX_SYMBOLS = 150
    NEWS_TTL = timedelta(hours=6)
    LEVELS_TTL = timedelta(hours=48)
    FLOAT_TTL = timedelta(days=7)
    FLAG_FLOAT_STALE = "PREP_FLOAT_STALE"
    FLAG_LEVELS_STALE = "PREP_LEVELS_STALE"
    FLAG_NEWS_STALE = "PREP_NEWS_STALE"
    FLAG_FLOAT_MISSING = "PREP_FLOAT_MISSING"
    FLAG_LEVELS_MISSING = "PREP_LEVELS_MISSING"
    FLAG_NEWS_MISSING = "PREP_NEWS_MISSING"

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
        self._refresh_cache_flags(now)

        requested = [symbol.upper() for symbol in symbols if symbol]
        limited = requested[: self.MAX_SYMBOLS]
        if not limited:
            return

        allow_news = bool(get_config("NEWS_ENABLED")) and get_run_mode() not in {
            RunMode.LIVE,
            RunMode.LIVE_READ_ONLY,
            RunMode.LIVE_MICRO,
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
        skipped_symbols: list[str] = []
        for symbol in limited:
            snapshot = self._cache.get(symbol)
            if snapshot is None:
                if len(self._cache) >= self.MAX_SYMBOLS:
                    skipped_symbols.append(symbol)
                    continue
                snapshot = PrepSnapshot(symbol=symbol)
                self._cache[symbol] = snapshot
            self._cache.move_to_end(symbol)
            self._refresh_snapshot_flags(snapshot, now)

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
                    if "PREP_LEVELS_APPROX" not in snapshot.data_quality_flags:
                        snapshot.data_quality_flags.append("PREP_LEVELS_APPROX")

            if allow_news and self._news_expired(snapshot, now):
                snapshot.news = news_lookup.get(symbol, [])
                snapshot.news_asof = now
                if snapshot.news:
                    last_ts = max(headline.published_ts for headline in snapshot.news)
                    snapshot.last_news_timestamp = last_ts
                    snapshot.news_age_minutes = int(
                        max((now.timestamp() - last_ts) / 60.0, 0.0)
                    )
                    snapshot.has_recent_news = snapshot.news_age_minutes <= int(
                        self.NEWS_TTL.total_seconds() / 60.0
                    )
                else:
                    snapshot.last_news_timestamp = None
                    snapshot.news_age_minutes = None
                    snapshot.has_recent_news = False
                if news_failure:
                    if "NEWS_STALE" not in snapshot.data_quality_flags:
                        snapshot.data_quality_flags.append("NEWS_STALE")

            self._refresh_snapshot_flags(snapshot, now)
            updated_symbols.append(symbol)

        if skipped_symbols:
            print(
                "[PREP][WARN] Extended watchlist cache full; "
                f"skipping {len(skipped_symbols)} symbols "
                f"sample={skipped_symbols[:10]}"
            )
        self._emit_update_event(updated_symbols, reason=reason)

    def get_snapshot(self, symbol: str) -> Optional[PrepSnapshot]:
        if not symbol:
            return None
        snapshot = self._cache.get(symbol.upper())
        if snapshot is not None:
            self._refresh_snapshot_flags(snapshot, datetime.now(timezone.utc))
        return snapshot

    def _refresh_cache_flags(self, now: datetime) -> None:
        for snapshot in self._cache.values():
            self._refresh_snapshot_flags(snapshot, now)

    def _refresh_snapshot_flags(self, snapshot: PrepSnapshot, now: datetime) -> None:
        float_missing = snapshot.float_asof is None
        levels_missing = snapshot.levels_asof is None
        news_missing = snapshot.news_asof is None
        if snapshot.last_news_timestamp is not None:
            age_minutes = int(max((now.timestamp() - snapshot.last_news_timestamp) / 60.0, 0.0))
            snapshot.news_age_minutes = age_minutes
            snapshot.has_recent_news = age_minutes <= int(self.NEWS_TTL.total_seconds() / 60.0)
        self._set_flag(snapshot, self.FLAG_FLOAT_STALE, bool(snapshot.float_asof and self._float_expired(snapshot, now)))
        self._set_flag(snapshot, self.FLAG_LEVELS_STALE, bool(snapshot.levels_asof and self._levels_expired(snapshot, now)))
        self._set_flag(snapshot, self.FLAG_NEWS_STALE, bool(snapshot.news_asof and self._news_expired(snapshot, now)))
        self._set_flag(snapshot, self.FLAG_FLOAT_MISSING, float_missing)
        self._set_flag(snapshot, self.FLAG_LEVELS_MISSING, levels_missing)
        self._set_flag(snapshot, self.FLAG_NEWS_MISSING, news_missing)

    @staticmethod
    def _set_flag(snapshot: PrepSnapshot, flag: str, present: bool) -> None:
        if present:
            if flag not in snapshot.data_quality_flags:
                snapshot.data_quality_flags.append(flag)
        else:
            if flag in snapshot.data_quality_flags:
                snapshot.data_quality_flags.remove(flag)

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
