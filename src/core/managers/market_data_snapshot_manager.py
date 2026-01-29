from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Optional

from src.domain.market_snapshot import MarketSnapshot
from src.ibkr.market_data_client import MarketDataClient, MarketDataSnapshot


@dataclass(frozen=True)
class SnapshotQuality:
    symbol: str
    missing_fields: list[str]
    data_quality_flags: list[str]


class MarketDataSnapshotManager:
    """Deterministic snapshot capture with data-quality flags."""

    def __init__(
        self,
        market_data_client: MarketDataClient | None,
        *,
        max_workers: int = 5,
    ) -> None:
        self.market_data_client = market_data_client
        self.max_workers = max_workers

    def get_snapshot(self, symbol: str) -> tuple[MarketSnapshot, SnapshotQuality]:
        if self.market_data_client is None:
            snapshot = MarketSnapshot(
                symbol=symbol,
                bid=None,
                ask=None,
                last=None,
                volume=None,
                asof_utc=datetime.now(timezone.utc),
                market_data_type="UNKNOWN",
                source="SIM",
            )
            quality = SnapshotQuality(
                symbol=symbol,
                missing_fields=["last", "close", "volume"],
                data_quality_flags=["MD_UNAVAILABLE"],
            )
            self._log_quality(quality)
            return snapshot, quality
        raw = self.market_data_client.snapshot_stock(symbol)
        snapshot, quality = self._translate_snapshot(raw)
        self._log_quality(quality)
        return snapshot, quality

    def batch_snapshots(
        self,
        symbols: Iterable[str],
    ) -> tuple[dict[str, MarketSnapshot], dict[str, SnapshotQuality]]:
        resolved_symbols = [symbol for symbol in symbols if symbol]
        snapshots: dict[str, MarketSnapshot] = {}
        quality_by_symbol: dict[str, SnapshotQuality] = {}
        if not resolved_symbols:
            return snapshots, quality_by_symbol
        max_workers = min(max(self.max_workers, 1), len(resolved_symbols))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(self.get_snapshot, symbol): symbol
                for symbol in resolved_symbols
            }
            for future in as_completed(future_map):
                symbol = future_map[future]
                try:
                    snapshot, quality = future.result()
                except Exception as exc:
                    print(f"[SNAPSHOT][ERROR] symbol={symbol} error={exc}")
                    snapshot = MarketSnapshot(
                        symbol=symbol,
                        bid=None,
                        ask=None,
                        last=None,
                        volume=None,
                        asof_utc=datetime.now(timezone.utc),
                        market_data_type="UNKNOWN",
                        source="IBKR",
                    )
                    quality = SnapshotQuality(
                        symbol=symbol,
                        missing_fields=["last", "close", "volume"],
                        data_quality_flags=["SNAPSHOT_ERROR"],
                    )
                    self._log_quality(quality)
                snapshots[symbol] = snapshot
                quality_by_symbol[symbol] = quality
        return snapshots, quality_by_symbol

    @staticmethod
    def _translate_snapshot(
        raw: MarketDataSnapshot,
    ) -> tuple[MarketSnapshot, SnapshotQuality]:
        missing_fields: list[str] = []
        if raw.last is None:
            missing_fields.append("last")
        if raw.close is None:
            missing_fields.append("close")
        if raw.volume is None:
            missing_fields.append("volume")
        data_quality_flags = list(raw.data_quality_flags or [])
        snapshot_last = raw.last if raw.last is not None else raw.close
        snapshot = MarketSnapshot(
            symbol=raw.symbol,
            bid=raw.bid,
            ask=raw.ask,
            last=snapshot_last,
            volume=raw.volume,
            asof_utc=datetime.now(timezone.utc),
            market_data_type="LIVE",
            source="IBKR",
        )
        quality = SnapshotQuality(
            symbol=raw.symbol,
            missing_fields=missing_fields,
            data_quality_flags=data_quality_flags,
        )
        return snapshot, quality

    @staticmethod
    def _log_quality(quality: SnapshotQuality) -> None:
        if not quality.missing_fields and not quality.data_quality_flags:
            return
        print(
            "[SNAPSHOT][QUALITY] "
            f"symbol={quality.symbol} missing={quality.missing_fields} "
            f"flags={quality.data_quality_flags}"
        )
