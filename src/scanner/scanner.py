"""
Scanner module skeleton for illustrating how market candidates could be produced.

Phase 3: Skeleton status only — this module contains placeholders for teaching.
No real scanning logic is implemented; outputs are empty for demonstration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List

from src.brokers import IbkrBroker
from src.config.config_resolver import get_config
from src.core.event_collector import EventCollector
from src.market_data.market_data_hub import MarketDataHub
from src.models.data_models import ScannerCandidate
from src.scanner.contracts import StockSelectionPolicy, policy_from_config
from src.scanner.scanner_contract import ScannerRequest
from src.strategies.ross_momentum.strategy_policy import UniverseSource


class RunMode(Enum):
    SIM = "SIM"
    LIVE_READ_ONLY = "LIVE_READ_ONLY"
    LIVE_MICRO = "LIVE_MICRO"
    LIVE_ONE_SHARE = "LIVE_ONE_SHARE"
    PAPER = "PAPER"
    LIVE = "LIVE"


def _get_run_mode() -> RunMode:
    raw = get_config("RUN_MODE_EFFECTIVE")
    for mode in RunMode:
        if mode.value == raw:
            return mode
    return RunMode.SIM


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


class Scanner:
    """Minimal scanner placeholder with instructional logging."""

    def __init__(
        self,
        event_collector: EventCollector | None = None,
        market_data_hub: MarketDataHub | None = None,
    ) -> None:
        self.run_mode = _get_run_mode()
        self.scan_symbols = self._resolve_scan_symbols()
        self.market_data_type = get_config("IBKR_MARKET_DATA_TYPE")
        self.snapshot_max_age_seconds = get_config("IBKR_SNAPSHOT_MAX_AGE_SECONDS")
        self.max_symbols_per_cycle = get_config("IBKR_MAX_SYMBOLS_PER_CYCLE")
        self.fallback_enabled = get_config("IBKR_FALLBACK_ENABLED")
        self.fallback_source = get_config("IBKR_FALLBACK_SOURCE")
        self.auto_lockdown_enabled = get_config("IBKR_AUTO_LOCKDOWN_ENABLED")
        self.last_data_quality_flags: Dict[str, List[str]] = {}
        self.last_connectivity_issue: str | None = None
        self.last_fallback_reason: str | None = None
        self.event_collector = event_collector
        self.market_data_hub = market_data_hub
        print("[BOOT] Scanner instantiated — phase 4 teaching placeholder (static outputs)")

    @staticmethod
    def _resolve_scan_symbols() -> List[str]:
        symbols = get_config("SCANNER_SYMBOLS")
        return list(symbols or [])

    def run_scan_cycle(
        self,
        policy: StockSelectionPolicy | None = None,
        scanner_request: ScannerRequest | None = None,
    ) -> List[ScannerCandidate]:
        """
        Demonstrate how a scan cycle would be invoked in a real system.

        Returns a deterministic list of hard-coded teaching candidates to let
        downstream modules be exercised without touching real markets.
        """

        self.last_data_quality_flags = {}
        self.last_connectivity_issue = None
        self.last_fallback_reason = None
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
        symbols = list(self.scan_symbols)
        if scanner_request is not None:
            if scanner_request.universe_source == UniverseSource.CONFIG_SYMBOLS:
                symbols = list(scanner_request.optional_symbols_override or [])
                if not symbols:
                    symbols = list(get_config("SCANNER_SYMBOLS") or [])
            elif scanner_request.universe_source == UniverseSource.IBKR_TOP_GAINERS:
                symbols = list(get_config("SCANNER_DEFAULT_SYMBOLS") or [])
        if not symbols:
            symbols = list(get_config("SCANNER_DEFAULT_SYMBOLS") or [])

        if self.run_mode in {
            RunMode.LIVE_READ_ONLY,
            RunMode.LIVE_MICRO,
            RunMode.LIVE_ONE_SHARE,
            RunMode.PAPER,
            RunMode.LIVE,
        }:
            if symbols:
                self.scan_symbols = symbols
                return self._run_live_readonly_scan(resolved_policy)
            reason = "Live scan has no symbols available; falling back to teaching mode."
            print(f"[SCAN][WARN] {reason}")
            self.last_connectivity_issue = reason
            self.last_fallback_reason = reason
            self._emit_market_data_fallback(reason)
            return self._fallback_candidates()

        print("[SCAN] Teaching scan started — using static, fake symbols only")
        print(
            "[SCAN] These candidates are simulated for instruction; no live data, "
            "no randomness, no external calls"
        )
        return self._static_candidates()

    def _run_live_readonly_scan(
        self, policy: StockSelectionPolicy
    ) -> List[ScannerCandidate]:
        mode_label = (
            "LIVE MICRO"
            if self.run_mode == RunMode.LIVE_MICRO
            else "LIVE ONE-SHARE"
            if self.run_mode == RunMode.LIVE_ONE_SHARE
            else "LIVE READ-ONLY"
        )
        print(f"[SCAN] {mode_label} scan started — using IBKR market snapshots")
        if IbkrBroker is None and self.market_data_hub is None:
            reason = "IBKR broker unavailable; live scan requires IBKR connectivity."
            print(f"[SCAN][ERROR] {reason}")
            self.last_connectivity_issue = reason
            self.last_fallback_reason = reason
            self._emit_market_data_fallback(reason, symbols=self.scan_symbols)
            return self._fallback_candidates()
        hub = self.market_data_hub or MarketDataHub(
            event_collector=self.event_collector,
            broker=IbkrBroker() if IbkrBroker is not None else None,
            max_symbols_per_cycle=self.max_symbols_per_cycle,
        )
        broker = hub.broker
        session = _current_market_session()
        candidates: List[ScannerCandidate] = []
        symbols = list(self.scan_symbols)
        max_policy_symbols = policy.max_symbols_per_cycle or self.max_symbols_per_cycle
        max_symbols = min(
            max_policy_symbols,
            self.max_symbols_per_cycle,
        )
        if max_symbols and len(symbols) > max_symbols:
            print(
                "[SCAN] Limiting scan symbols "
                f"max={max_symbols} total={len(symbols)}"
            )
            symbols = symbols[:max_symbols]
        try:
            hub.connect()
            health = broker.health() if broker is not None else {"connected": False}
            print(f"[SCAN] IBKR health status: {health}")
            if not health.get("connected", False):
                self.last_connectivity_issue = "IBKR health reported disconnected"
                print(f"[SCAN][ERROR] Connectivity issue: {self.last_connectivity_issue}")
                self.last_fallback_reason = self.last_connectivity_issue
                self._emit_market_data_fallback(self.last_connectivity_issue, symbols=symbols)
                return self._fallback_candidates()
            for symbol in symbols:
                try:
                    observation = hub.snapshot(symbol, request_source="Scanner")
                    snapshot = observation.snapshot
                except Exception as exc:
                    self.last_connectivity_issue = f"Snapshot failure symbol={symbol} err={exc}"
                    print(f"[SCAN][ERROR] Connectivity issue: {self.last_connectivity_issue}")
                    self.last_fallback_reason = self.last_connectivity_issue
                    self._emit_market_data_fallback(self.last_connectivity_issue, symbols=symbols)
                    continue
                bid = snapshot.bid
                ask = snapshot.ask
                last = snapshot.last
                volume = snapshot.volume
                spread = None
                if bid is not None and ask is not None:
                    spread = round(ask - bid, 4)
                reference_price = (
                    last
                    if last is not None
                    else round((bid + ask) / 2, 4)
                    if bid is not None and ask is not None
                    else bid
                    if bid is not None
                    else ask
                    if ask is not None
                    else 0.0
                )
                data_quality_flags = self._evaluate_data_quality(
                    snapshot=snapshot,
                    session=session,
                )
                if data_quality_flags:
                    self.last_data_quality_flags[symbol] = data_quality_flags
                print(
                    "[SCAN] IBKR snapshot "
                    f"symbol={symbol} bid={bid} ask={ask} last={last} "
                    f"volume={volume} spread={spread} session={session} "
                    f"mode={observation.data_mode} request={observation.request_mode} "
                    f"flags={data_quality_flags}"
                )
                candidates.append(
                    ScannerCandidate(
                        symbol=symbol,
                        price=float(reference_price),
                        gap_percent=0.0,
                        rvol=0.0,
                        float_millions=0.0,
                        rationale=(
                            "LIVE snapshot from IBKR; gaps/rVol/float "
                            "not computed in teaching mode"
                        ),
                        session=session,
                        bid=bid,
                        ask=ask,
                        spread=spread,
                        volume=volume,
                        data_quality_flags=data_quality_flags,
                    )
                )
        finally:
            hub.disconnect()

        if not candidates and self.fallback_enabled:
            self.last_fallback_reason = self.last_fallback_reason or "no_candidates"
            candidates = self._fallback_candidates()

        if self.event_collector:
            self.event_collector.emit(
                event_type="SCAN_COMPLETE",
                source="Scanner",
                payload={"candidates": len(candidates)},
            )
        return candidates

    def _evaluate_data_quality(self, snapshot, session: str) -> List[str]:
        flags: List[str] = []
        if snapshot is None:
            flags.append("MISSING_SNAPSHOT")
            return flags
        if snapshot.bid is None or snapshot.ask is None:
            flags.append("INCOMPLETE_BID_ASK")
        if snapshot.last is None:
            flags.append("MISSING_LAST")
        if snapshot.volume is None:
            flags.append("MISSING_VOLUME")
        if snapshot.asof_utc is None:
            flags.append("MISSING_ASOF")
        if snapshot.market_data_type is None:
            flags.append("MISSING_MARKET_DATA_TYPE")
        if snapshot.bid is not None and snapshot.ask is not None:
            if snapshot.ask < snapshot.bid:
                flags.append("NEGATIVE_SPREAD")
        return flags

    def _fallback_candidates(self) -> List[ScannerCandidate]:
        if self.last_fallback_reason is None:
            self.last_fallback_reason = "fallback"
        self._emit_market_data_fallback(self.last_fallback_reason)
        return self._static_candidates()

    def _emit_market_data_fallback(self, reason: str, symbols: List[str] | None = None) -> None:
        if self.event_collector:
            self.event_collector.emit(
                event_type="MARKET_DATA_FALLBACK",
                source="Scanner",
                payload={
                    "reason": reason,
                    "fallback_source": self.fallback_source or "UNKNOWN",
                    "data_mode": self.market_data_type or "UNKNOWN",
                    "request_source": "Scanner",
                    "symbols": symbols or [],
                },
            )

    def _static_candidates(self) -> List[ScannerCandidate]:
        return [
            ScannerCandidate(
                symbol="AAPL",
                price=123.45,
                gap_percent=0.0,
                rvol=0.0,
                float_millions=0.0,
                rationale="Teaching-only static candidate",
                session="SIM",
                bid=None,
                ask=None,
                spread=None,
                volume=None,
                data_quality_flags=[],
            )
        ]
