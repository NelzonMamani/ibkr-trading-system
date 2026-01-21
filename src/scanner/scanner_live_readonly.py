from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from src.config.config_resolver import get_config
from src.core.event_collector import EventCollector
from src.ibkr.market_data_client import MarketDataClient
from src.models.data_models import ScannerCandidate
from src.scanner.contracts import StockSelectionPolicy, policy_from_config
from src.scanner.scanner_contract import ScannerRequest
from src.scanner.providers.mock_provider import MockScannerProvider


DEFAULT_SCAN_SYMBOLS = get_config("SCANNER_DEFAULT_SYMBOLS")


@dataclass(frozen=True)
class LiveReadOnlyScannerConfig:
    symbols: List[str]
    max_symbols_per_cycle: int


def _get_scanner_symbols(override: Optional[List[str]] = None) -> List[str]:
    if override:
        return list(override)
    symbols = get_config("SCANNER_SYMBOLS")
    return list(symbols or [])


def _current_market_session() -> str:
    now = datetime.now(timezone.utc)
    h = now.hour + now.minute / 60.0
    windows = get_config("SCANNER_SESSION_WINDOWS_UTC")
    if windows["PRE_START"] <= h < windows["RTH_START"]:
        return "PRE"
    if windows["RTH_START"] <= h < windows["AFT_START"]:
        return "RTH"
    if windows["AFT_START"] <= h < windows["AFT_END"]:
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
                symbols=resolved_symbols or list(DEFAULT_SCAN_SYMBOLS),
                max_symbols_per_cycle=get_config("IBKR_MAX_SYMBOLS_PER_CYCLE"),
            )
        self.config = config
        self.snapshot_max_age_seconds = get_config("IBKR_SNAPSHOT_MAX_AGE_SECONDS")
        self.max_symbols_per_cycle = get_config("IBKR_MAX_SYMBOLS_PER_CYCLE")
        self.fallback_enabled = get_config("IBKR_FALLBACK_ENABLED")
        self.fallback_source = get_config("IBKR_FALLBACK_SOURCE")
        self.auto_lockdown_enabled = get_config("IBKR_AUTO_LOCKDOWN_ENABLED")
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

    def run_scan_cycle(
        self,
        policy: StockSelectionPolicy | None = None,
        scanner_request: ScannerRequest | None = None,
    ) -> List[ScannerCandidate]:
        self.last_data_quality_flags = {}
        self.last_connectivity_issue = None
        self.last_snapshot_success_count = 0
        self.last_snapshot_attempted_count = 0
        if self._fallback_provider is not None:
            return self._run_mock_cycle()
        policy_source = "STRATEGY" if policy is not None else "CONFIG_DEFAULTS"
        resolved_policy = policy or policy_from_config()
        print(
            "[SCANNER][POLICY] source={source} policy_name={policy_name} price={price_min}-{price_max} "
            "gap_min={gap_min} rvol_min={rvol_min} float_max_millions={float_max} "
            "spread_max_pct={spread_max_pct} watchlist_k={watchlist_k} focus_m={focus_m}".format(
                source=policy_source,
                policy_name=resolved_policy.policy_name,
                price_min=resolved_policy.price_min,
                price_max=resolved_policy.price_max,
                gap_min=resolved_policy.gap_min_pct,
                rvol_min=resolved_policy.rvol_min,
                float_max=resolved_policy.float_max_millions,
                spread_max_pct=resolved_policy.spread_max_pct,
                watchlist_k=resolved_policy.watchlist_limit_k,
                focus_m=resolved_policy.focus_limit_m,
            )
        )
        max_policy_symbols = resolved_policy.max_symbols_per_cycle or self.max_symbols_per_cycle
        override_symbols = None
        if scanner_request is not None:
            override_symbols = list(scanner_request.optional_symbols_override or [])
        symbols = self._resolve_symbols(override_symbols)
        if not symbols:
            print("[SCAN] LiveReadOnlyScanner has no symbols to query")
            return []
        max_symbols = min(max_policy_symbols, self.max_symbols_per_cycle)
        if max_symbols and len(symbols) > max_symbols:
            symbols = symbols[:max_symbols]

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
                    rationale="MOCK fallback provider",
                    session=session,
                    bid=quote.bid,
                    ask=quote.ask,
                    spread=None,
                    volume=quote.volume,
                    vwap=quote.vwap,
                    data_quality_flags=["MOCK"],
                )
            )
        return candidates

    def _resolve_symbols(self, override: Optional[List[str]] = None) -> List[str]:
        symbols = list(_get_scanner_symbols(override) or self.config.symbols)
        if self.max_symbols_per_cycle and len(symbols) > self.max_symbols_per_cycle:
            symbols = symbols[: self.max_symbols_per_cycle]
        return symbols

    def _resolve_price(self, snapshot) -> Optional[float]:
        return snapshot.last or snapshot.bid or snapshot.ask
