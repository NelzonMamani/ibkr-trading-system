"""
Scanner module skeleton for illustrating how market candidates could be produced.

Phase 3: Skeleton status only — this module contains placeholders for teaching.
No real scanning logic is implemented; outputs are empty for demonstration.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List

from src.brokers import IbkrBroker
from src.core.event_collector import EventCollector
from src.market_data.market_data_hub import MarketDataHub
from src.models.data_models import ScannerCandidate


class RunMode(Enum):
    LIVE_READ_ONLY = "LIVE_READ_ONLY"
    LIVE_MICRO = "LIVE_MICRO"
    PAPER = "PAPER"


def _get_run_mode() -> RunMode:
    raw = (os.getenv("RUN_MODE") or "").strip().upper()
    for mode in RunMode:
        if mode.value == raw:
            return mode
    return RunMode.PAPER


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no"}


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _get_current_market_session() -> str:
    now = datetime.now(timezone.utc)
    h = now.hour + now.minute / 60.0
    if 12.0 <= h < 14.0:
        return "PRE"
    if 14.0 <= h < 21.5:
        return "RTH"
    if 21.5 <= h < 23.0:
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
        self.market_data_type = os.getenv("IBKR_MARKET_DATA_TYPE", "DELAYED")
        self.snapshot_max_age_seconds = _get_int("IBKR_SNAPSHOT_MAX_AGE_SECONDS", 15)
        self.max_symbols_per_cycle = _get_int("IBKR_MAX_SYMBOLS_PER_CYCLE", 50)
        self.fallback_enabled = _get_bool("IBKR_FALLBACK_ENABLED", True)
        self.fallback_source = os.getenv("IBKR_FALLBACK_SOURCE", "static")
        self.auto_lockdown_enabled = _get_bool("IBKR_AUTO_LOCKDOWN_ENABLED", False)
        self.last_data_quality_flags: Dict[str, List[str]] = {}
        self.last_connectivity_issue: str | None = None
        self.last_fallback_reason: str | None = None
        self.event_collector = event_collector
        self.market_data_hub = market_data_hub
        print("[BOOT] Scanner instantiated — phase 4 teaching placeholder (static outputs)")

    @staticmethod
    def _resolve_scan_symbols() -> List[str]:
        raw = (os.getenv("IBKR_SCAN_SYMBOLS") or "").strip()
        if not raw:
            return []
        return [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]

    def run_scan_cycle(self) -> List[ScannerCandidate]:
        """
        Demonstrate how a scan cycle would be invoked in a real system.

        Returns a deterministic list of hard-coded teaching candidates to let
        downstream modules be exercised without touching real markets.
        """

        self.last_data_quality_flags = {}
        self.last_connectivity_issue = None
        self.last_fallback_reason = None
        if self.run_mode == RunMode.LIVE_READ_ONLY and self.scan_symbols:
            return self._run_live_readonly_scan()
        if self.run_mode == RunMode.LIVE_READ_ONLY and not self.scan_symbols:
            reason = "No IBKR_SCAN_SYMBOLS provided; falling back to static scan list."
            print(f"[SCAN] {reason}")
            self._emit_market_data_fallback(reason)
            return self._fallback_candidates() if self.fallback_enabled else []
        if self.run_mode == RunMode.LIVE_MICRO and self.scan_symbols:
            return self._run_live_readonly_scan()

        print("[SCAN] Teaching scan started — using static, fake symbols only")
        print(
            "[SCAN] These candidates are simulated for instruction; no live data, "
            "no randomness, no external calls"
        )
        return self._static_candidates()

    def _run_live_readonly_scan(self) -> List[ScannerCandidate]:
        mode_label = "LIVE MICRO" if self.run_mode == RunMode.LIVE_MICRO else "LIVE READ-ONLY"
        print(f"[SCAN] {mode_label} scan started — using IBKR market snapshots")
        if IbkrBroker is None and self.market_data_hub is None:
            print("[SCAN] IBKR broker unavailable; falling back to static candidates.")
            self._emit_market_data_fallback("IBKR broker unavailable", symbols=self.scan_symbols)
            return self._static_candidates()
        hub = self.market_data_hub or MarketDataHub(
            event_collector=self.event_collector,
            broker=IbkrBroker() if IbkrBroker is not None else None,
            max_symbols_per_cycle=self.max_symbols_per_cycle,
        )
        broker = hub.broker
        session = _get_current_market_session()
        candidates: List[ScannerCandidate] = []
        symbols = list(self.scan_symbols)
        if self.max_symbols_per_cycle and len(symbols) > self.max_symbols_per_cycle:
            print(
                "[SCAN] Limiting scan symbols "
                f"max={self.max_symbols_per_cycle} total={len(symbols)}"
            )
            symbols = symbols[: self.max_symbols_per_cycle]
        try:
            hub.connect()
            health = broker.health() if broker is not None else {"connected": False}
            print(f"[SCAN] IBKR health status: {health}")
            if not health.get("connected", False):
                self.last_connectivity_issue = "IBKR health reported disconnected"
                print(f"[SCAN] Connectivity issue: {self.last_connectivity_issue}")
                self._emit_market_data_fallback(self.last_connectivity_issue, symbols=symbols)
                return self._fallback_candidates() if self.fallback_enabled else []
            for symbol in symbols:
                try:
                    observation = hub.snapshot(symbol, request_source="Scanner")
                    snapshot = observation.snapshot
                except Exception as exc:
                    self.last_connectivity_issue = f"Snapshot failure symbol={symbol} err={exc}"
                    print(f"[SCAN] Connectivity issue: {self.last_connectivity_issue}")
                    self._emit_market_data_fallback(self.last_connectivity_issue, symbols=symbols)
                    if self.fallback_enabled:
                        return self._fallback_candidates()
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
                            "placeholders for micro-execution validation."
                        ),
                        session=session,
                        bid=bid,
                        ask=ask,
                        spread=spread,
                        volume=volume,
                        data_quality_flags=data_quality_flags,
                    )
                )
            if self._should_trigger_fallback():
                reason = "Data quality flags detected; triggering fallback source"
                print(f"[SCAN] {reason} source={self.fallback_source}")
                self.last_fallback_reason = reason
                self._emit_market_data_fallback(reason, symbols=symbols)
                return self._fallback_candidates()
        except Exception as exc:
            self.last_connectivity_issue = f"IBKR connection failed: {exc}"
            print(f"[SCAN] Connectivity issue: {self.last_connectivity_issue}")
            self._emit_market_data_fallback(self.last_connectivity_issue, symbols=symbols)
            if self.fallback_enabled:
                return self._fallback_candidates()
            return []
        finally:
            hub.disconnect()
        print("[SCAN] Returning IBKR-backed candidates for downstream teaching modules")
        return candidates

    def _static_candidates(self) -> List[ScannerCandidate]:
        candidates: List[ScannerCandidate] = [
            ScannerCandidate(
                symbol="ABC",
                price=12.35,
                gap_percent=8.4,
                rvol=3.1,
                float_millions=22.0,
                rationale="Small float name gapping on imaginary news with strong relative volume.",
                session="REGULAR",
                premarket_high=12.05,
                early_session_high=12.25,
                opening_range_high=12.18,
                opening_range_low=11.92,
                opening_range_minutes=5,
                breakout_volume_ratio=2.4,
                breakout_hold_minutes=2,
                breakout_reject=False,
            ),
            ScannerCandidate(
                symbol="XYZ",
                price=47.8,
                gap_percent=5.2,
                rvol=2.4,
                float_millions=150.0,
                rationale="Mid-cap showing moderate gap with sustained liquidity for teaching entry sizing.",
                session="REGULAR",
                opening_range_high=47.6,
                opening_range_low=46.9,
                opening_range_minutes=5,
                breakout_volume_ratio=2.1,
                breakout_hold_minutes=2,
                breakout_reject=False,
                vwap=47.5,
                vwap_hold_minutes=3,
                momentum_move_pct=6.2,
                pullback_pct=2.1,
                pullback_high=47.7,
                pullback_volume_ratio=0.6,
                higher_low=True,
            ),
            ScannerCandidate(
                symbol="LMN",
                price=6.75,
                gap_percent=12.0,
                rvol=4.8,
                float_millions=18.5,
                rationale="Low float ticker with double-digit gap and elevated relative volume — classic momentum demo.",
                session="REGULAR",
                premarket_high=6.6,
                early_session_high=6.7,
                hod=6.68,
                consolidation_range_pct=1.2,
                breakout_volume_ratio=2.8,
                breakout_hold_minutes=3,
                breakout_reject=False,
                extension_pct=0.02,
            ),
            ScannerCandidate(
                symbol="QRS",
                price=83.4,
                gap_percent=3.1,
                rvol=1.6,
                float_millions=320.0,
                rationale="Large-cap grinder with modest gap and steady rVol to illustrate higher-float behavior.",
                session="REGULAR",
                opening_range_high=83.9,
                opening_range_low=82.7,
                opening_range_minutes=5,
                breakout_volume_ratio=1.2,
                breakout_hold_minutes=1,
                breakout_reject=True,
            ),
        ]
        for candidate in candidates:
            print(
                f"[SCAN] Candidate {candidate.symbol}: gap={candidate.gap_percent}% "
                f"rVol={candidate.rvol} float={candidate.float_millions}M — {candidate.rationale}"
            )
        print("[SCAN] Returning static candidate list for downstream teaching modules")
        return candidates

    def _evaluate_data_quality(self, snapshot, session: str) -> List[str]:
        flags: List[str] = []
        if snapshot.bid is None and snapshot.ask is None:
            flags.append("MISSING_BID_ASK")
        elif snapshot.bid is None or snapshot.ask is None:
            flags.append("INCOMPLETE_BID_ASK")
        if snapshot.last is None and snapshot.bid is None and snapshot.ask is None:
            flags.append("MISSING_PRICE")
        if snapshot.volume is None:
            flags.append("MISSING_VOLUME")
        elif snapshot.volume == 0:
            flags.append("ZERO_VOLUME")
        age_seconds = (datetime.now(timezone.utc) - snapshot.asof_utc).total_seconds()
        if age_seconds > self.snapshot_max_age_seconds:
            flags.append(f"STALE_PRICE>{self.snapshot_max_age_seconds}s")
        if snapshot.market_data_type != "LIVE":
            flags.append(f"DATA_TYPE_{snapshot.market_data_type}")
        if snapshot.market_data_type in {"DELAYED", "DELAYED_FROZEN"} and session != "CLOSED":
            flags.append("DELAYED_DATA_DURING_OPEN_SESSION")
        return flags

    def _should_trigger_fallback(self) -> bool:
        return bool(self.fallback_enabled and self.last_data_quality_flags)

    def _fallback_candidates(self) -> List[ScannerCandidate]:
        if self.fallback_source == "STATIC":
            print("[SCAN] Fallback source STATIC selected.")
            return self._static_candidates()
        print(f"[SCAN] Unknown fallback source '{self.fallback_source}'; returning empty list.")
        return []

    def _emit_market_data_fallback(self, reason: str, symbols: List[str] | None = None) -> None:
        if self.market_data_hub is not None:
            self.market_data_hub.emit_fallback(
                reason=reason,
                request_source="Scanner",
                symbols=symbols,
                fallback_source=self.fallback_source,
            )
            return
        if not self.event_collector:
            return
        self.event_collector.emit(
            event_type="MARKET_DATA_FALLBACK",
            source="Scanner",
            payload={
                "reason": reason,
                "fallback_source": self.fallback_source,
                "data_mode": "FALLBACK",
                "request_source": "Scanner",
                "symbols": symbols or [],
            },
        )
