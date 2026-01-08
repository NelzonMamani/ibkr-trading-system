from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from config.runtime_config import (
    get_ibkr_max_symbols_per_cycle,
    get_ibkr_readonly_enabled,
    get_scanner_symbols,
)
from config.system_config import get_current_market_session
from ibkr.market_data_client import MarketDataClient
from models.data_models import ScannerCandidate


DEFAULT_SCAN_SYMBOLS = ["AAPL", "TSLA", "NVDA", "AMD", "SPY"]


@dataclass(frozen=True)
class LiveReadOnlyScannerConfig:
    symbols: List[str]
    max_symbols_per_cycle: int


class LiveReadOnlyScanner:
    """Scanner that uses live IBKR read-only market data snapshots."""

    def __init__(
        self,
        market_data_client: MarketDataClient,
        config: Optional[LiveReadOnlyScannerConfig] = None,
    ) -> None:
        if not get_ibkr_readonly_enabled():
            raise RuntimeError("LIVE_READONLY scanner requires IBKR_READONLY_ENABLED=True")
        resolved_symbols = get_scanner_symbols()
        if config is None:
            config = LiveReadOnlyScannerConfig(
                symbols=resolved_symbols,
                max_symbols_per_cycle=get_ibkr_max_symbols_per_cycle(),
            )
        self.config = config
        self.market_data_client = market_data_client
        self.last_data_quality_flags: dict[str, list[str]] = {}
        self.last_connectivity_issue: Optional[str] = None
        print("[BOOT] LiveReadOnlyScanner instantiated — IBKR read-only market data")

    def validate_startup(self) -> None:
        """Validate connectivity and market data type configuration."""
        self.market_data_client.connect()
        self.market_data_client.disconnect()

    def run_scan_cycle(self) -> List[ScannerCandidate]:
        self.last_data_quality_flags = {}
        self.last_connectivity_issue = None
        symbols = self._resolve_symbols()
        if not symbols:
            print("[SCAN] LiveReadOnlyScanner has no symbols to query")
            return []

        session = get_current_market_session()
        candidates: List[ScannerCandidate] = []

        try:
            self.market_data_client.connect()
            for symbol in symbols:
                snapshot = self.market_data_client.snapshot_for_symbol(symbol)
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
                        price=float(price) if price is not None else 0.0,
                        gap_percent=0.0,
                        rvol=0.0,
                        float_millions=0.0,
                        rationale=(
                            "Live read-only IBKR snapshot; "
                            "gap/rvol/float/news placeholders for Phase 22."
                        ),
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
