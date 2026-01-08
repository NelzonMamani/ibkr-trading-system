"""
Scanner module skeleton for illustrating how market candidates could be produced.

Phase 3: Skeleton status only — this module contains placeholders for teaching.
No real scanning logic is implemented; outputs are empty for demonstration.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List

from brokers import IbkrBroker
from config.runtime_config import (
    RunMode,
    get_ibkr_auto_lockdown_enabled,
    get_ibkr_fallback_enabled,
    get_ibkr_fallback_source,
    get_ibkr_market_data_type,
    get_ibkr_readonly_enabled,
    get_ibkr_snapshot_max_age_seconds,
    get_run_mode,
)
from config.system_config import get_current_market_session
from models.data_models import ScannerCandidate


class Scanner:
    """Minimal scanner placeholder with instructional logging."""

    def __init__(self) -> None:
        self.run_mode = get_run_mode()
        self.ibkr_readonly_enabled = get_ibkr_readonly_enabled()
        self.scan_symbols = self._resolve_scan_symbols()
        self.market_data_type = get_ibkr_market_data_type()
        self.snapshot_max_age_seconds = get_ibkr_snapshot_max_age_seconds()
        self.fallback_enabled = get_ibkr_fallback_enabled()
        self.fallback_source = get_ibkr_fallback_source()
        self.auto_lockdown_enabled = get_ibkr_auto_lockdown_enabled()
        self.last_data_quality_flags: Dict[str, List[str]] = {}
        self.last_connectivity_issue: str | None = None
        self.last_fallback_reason: str | None = None
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
            if self.ibkr_readonly_enabled:
                return self._run_live_readonly_scan()
            print(
                "[SCAN] LIVE_READ_ONLY requires IBKR_READONLY_ENABLED=True; "
                "falling back to static candidates."
            )
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
        if IbkrBroker is None:
            print("[SCAN] IBKR broker unavailable; falling back to static candidates.")
            return self._static_candidates()
        broker = IbkrBroker()
        session = get_current_market_session()
        candidates: List[ScannerCandidate] = []
        try:
            broker.connect()
            health = broker.health()
            print(f"[SCAN] IBKR health status: {health}")
            if not health.get("connected", False):
                self.last_connectivity_issue = "IBKR health reported disconnected"
                print(f"[SCAN] Connectivity issue: {self.last_connectivity_issue}")
                return self._fallback_candidates() if self.fallback_enabled else []
            for symbol in self.scan_symbols:
                try:
                    snapshot = broker.get_market_snapshot(symbol)
                except Exception as exc:
                    self.last_connectivity_issue = f"Snapshot failure symbol={symbol} err={exc}"
                    print(f"[SCAN] Connectivity issue: {self.last_connectivity_issue}")
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
                        data_quality_flags=data_quality_flags,
                    )
                )
            if self._should_trigger_fallback():
                reason = "Data quality flags detected; triggering fallback source"
                print(f"[SCAN] {reason} source={self.fallback_source}")
                self.last_fallback_reason = reason
                return self._fallback_candidates()
        except Exception as exc:
            self.last_connectivity_issue = f"IBKR connection failed: {exc}"
            print(f"[SCAN] Connectivity issue: {self.last_connectivity_issue}")
            if self.fallback_enabled:
                return self._fallback_candidates()
            return []
        finally:
            broker.disconnect()
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
            ),
            ScannerCandidate(
                symbol="XYZ",
                price=47.8,
                gap_percent=5.2,
                rvol=2.4,
                float_millions=150.0,
                rationale="Mid-cap showing moderate gap with sustained liquidity for teaching entry sizing.",
            ),
            ScannerCandidate(
                symbol="LMN",
                price=6.75,
                gap_percent=12.0,
                rvol=4.8,
                float_millions=18.5,
                rationale="Low float ticker with double-digit gap and elevated relative volume — classic momentum demo.",
            ),
            ScannerCandidate(
                symbol="QRS",
                price=83.4,
                gap_percent=3.1,
                rvol=1.6,
                float_millions=320.0,
                rationale="Large-cap grinder with modest gap and steady rVol to illustrate higher-float behavior.",
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
