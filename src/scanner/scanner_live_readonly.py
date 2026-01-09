from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import List, Optional

from src.core.event_collector import EventCollector
from src.ibkr.market_data_client import MarketDataClient
from src.models.data_models import ScannerCandidate
from src.scanner.providers.mock_provider import MockScannerProvider


DEFAULT_SCAN_SYMBOLS = ["AAPL", "TSLA", "NVDA", "AMD", "SPY"]


@dataclass(frozen=True)
class LiveReadOnlyScannerConfig:
    symbols: List[str]
    max_symbols_per_cycle: int


def _get_scanner_symbols() -> List[str]:
    raw = (os.getenv("SCANNER_SYMBOLS") or os.getenv("IBKR_SCAN_SYMBOLS") or "").strip()
    if not raw:
        return []
    return [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no"}


def _current_market_session() -> str:
    now = datetime.now(timezone.utc)
    h = now.hour + now.minute / 60.0
    if 12.0 <= h < 14.0:
        return "PRE"
    if 14.0 <= h < 21.5:
        return "RTH"
    if 21.5 <= h < 23.0:
        return "AFT"
    return "OVN"


class LiveReadOnlyScanner:
    """Scanner that uses live IBKR read-only market data snapshots."""

    def __init__(
        self,
        market_data_client: MarketDataClient,
        event_collector: Optional[EventCollector] = None,
        config: Optional[LiveReadOnlyScannerConfig] = None,
    ) -> None:
        resolved_symbols = _get_scanner_symbols()
        if config is None:
            config = LiveReadOnlyScannerConfig(
                symbols=resolved_symbols,
                max_symbols_per_cycle=_get_int("IBKR_MAX_SYMBOLS_PER_CYCLE", 50),
            )
        self.config = config
        self.snapshot_max_age_seconds = _get_int("IBKR_SNAPSHOT_MAX_AGE_SECONDS", 15)
        self.max_symbols_per_cycle = _get_int("IBKR_MAX_SYMBOLS_PER_CYCLE", 50)
        self.fallback_enabled = _get_bool("IBKR_FALLBACK_ENABLED", True)
        self.fallback_source = os.getenv("IBKR_FALLBACK_SOURCE", "static")
        self.auto_lockdown_enabled = _get_bool("IBKR_AUTO_LOCKDOWN_ENABLED", False)
        self.market_data_client = market_data_client
        self.event_collector = event_collector
        self.last_data_quality_flags: dict[str, list[str]] = {}
        self.last_connectivity_issue: Optional[str] = None
        self.last_snapshot_success_count = 0
        self.last_snapshot_attempted_count = 0
        self._fallback_provider: Optional[MockScannerProvider] = None
        print("[BOOT] LiveReadOnlyScanner instantiated — IBKR read-only market data")

    def validate_startup(self) -> None:
        """Validate connectivity and market data type configuration."""
        try:
            self.market_data_client.connect()
            self.market_data_client.disconnect()
        except Exception as exc:
            self.last_connectivity_issue = f"IBKR market data error: {exc}"
            print(
                "[SCAN][FALLBACK] IBKR unavailable — switching to MOCK provider "
                f"reason={exc}"
            )
            self._fallback_provider = MockScannerProvider()
            return None

    def run_scan_cycle(self) -> List[ScannerCandidate]:
        self.last_data_quality_flags = {}
        self.last_connectivity_issue = None
        self.last_snapshot_success_count = 0
        self.last_snapshot_attempted_count = 0
        if self._fallback_provider is not None:
            return self._run_mock_cycle()
        symbols = self._resolve_symbols()
        if not symbols:
            print("[SCAN] LiveReadOnlyScanner has no symbols to query")
            return []

        session = _current_market_session()
        candidates: List[ScannerCandidate] = []

        try:
            self.market_data_client.connect()
            for symbol in symbols:
                self.last_snapshot_attempted_count += 1
                snapshot = self.market_data_client.snapshot_stock(symbol)
                if "CONTRACT_QUALIFY_FAILED" in snapshot.data_quality_flags:
                    self.last_data_quality_flags[symbol] = snapshot.data_quality_flags
                    print(
                        "[MD][WARN] symbol={symbol} contract qualification failed flags={flags}".format(
                            symbol=symbol,
                            flags=snapshot.data_quality_flags,
                        )
                    )
                    continue

                price = self._resolve_price(snapshot)
                data_quality_flags = list(snapshot.data_quality_flags)
                has_any_price = snapshot.bid is not None or snapshot.ask is not None or snapshot.last is not None
                if has_any_price:
                    self.last_snapshot_success_count += 1
                if price is None:
                    data_quality_flags.append("MISSING_PRICE")
                if snapshot.bid is None or snapshot.ask is None:
                    data_quality_flags.append("INCOMPLETE_BID_ASK")
                if snapshot.volume is None:
                    data_quality_flags.append("MISSING_VOLUME")

                if data_quality_flags:
                    self.last_data_quality_flags[symbol] = data_quality_flags

                log_prefix = "[MD][WARN]" if data_quality_flags else "[MD]"
                print(
                    "{prefix} symbol={symbol} bid={bid} ask={ask} last={last} "
                    "spread={spread} vol={volume} flags={flags}".format(
                        prefix=log_prefix,
                        symbol=symbol,
                        bid=snapshot.bid,
                        ask=snapshot.ask,
                        last=snapshot.last,
                        spread=snapshot.spread,
                        volume=snapshot.volume,
                        flags=data_quality_flags,
                    )
                )

                candidates.append(
                    ScannerCandidate(
                        symbol=symbol,
                        price=float(price) if price is not None else None,
                        gap_percent=None,
                        rvol=None,
                        float_millions=None,
                        rationale="IBKR snapshot market data",
                        session=session,
                        bid=snapshot.bid,
                        ask=snapshot.ask,
                        spread=snapshot.spread,
                        volume=snapshot.volume,
                        vwap=snapshot.vwap,
                        data_quality_flags=data_quality_flags,
                    )
                )
        except Exception as exc:
            self.last_connectivity_issue = f"IBKR market data error: {exc}"
            print(f"[SCAN] Connectivity issue: {self.last_connectivity_issue}")
        finally:
            self.market_data_client.disconnect()

        print(f"[SCAN] produced candidates={len(candidates)} mode=LIVE_READONLY")
        if self.event_collector is not None:
            self.event_collector.emit(
                event_type="SCAN_COMPLETE",
                source="LiveReadOnlyScanner",
                payload={"candidates": len(candidates)},
            )
        return candidates

    def _run_mock_cycle(self) -> List[ScannerCandidate]:
        symbols = self._fallback_provider.get_top_gainers(self.max_symbols_per_cycle)
        session = _current_market_session()
        candidates: List[ScannerCandidate] = []
        for symbol in symbols:
            quote = self._fallback_provider.get_quote(symbol)
            price = quote.last or quote.bid or quote.ask
            candidates.append(
                ScannerCandidate(
                    symbol=symbol,
                    price=float(price) if price is not None else None,
                    gap_percent=None,
                    rvol=None,
                    float_millions=None,
                    rationale="MOCK fallback market data",
                    session=session,
                    bid=quote.bid,
                    ask=quote.ask,
                    spread=None,
                    volume=quote.volume,
                    vwap=quote.vwap,
                    data_quality_flags=["MOCK_FALLBACK"],
                )
            )
        print(f"[SCAN] produced candidates={len(candidates)} mode=MOCK_FALLBACK")
        return candidates

    def _resolve_symbols(self) -> List[str]:
        symbols = self.config.symbols or DEFAULT_SCAN_SYMBOLS
        symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
        if self.config.max_symbols_per_cycle and len(symbols) > self.config.max_symbols_per_cycle:
            symbols = symbols[: self.config.max_symbols_per_cycle]
        return symbols

    @staticmethod
    def _resolve_price(snapshot) -> Optional[float]:
        if snapshot.last is not None:
            return snapshot.last
        if snapshot.bid is not None and snapshot.ask is not None:
            return round((snapshot.bid + snapshot.ask) / 2, 4)
        return None
