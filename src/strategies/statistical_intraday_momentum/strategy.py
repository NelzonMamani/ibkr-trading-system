"""Minimal Statistical Intraday Momentum strategy adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from src.models.data_models import PatternResult, TradeIntent
from src.config.runtime_config import RunMode
from src.scanner.session_pct_change import normalize_session_label
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal
from src.strategies.statistical_intraday_momentum.strategy_policy import (
    decide_trade_intent,
    default_policy,
)
from src.utils.time_utils import to_ny_time


class StatisticalIntradayMomentum(BaseStrategy):
    """Teaching-safe adapter that emits no trades unless wired to signal inputs."""

    name = "StatisticalIntradayMomentum"
    trader_type = "STATISTICAL"

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        print(
            "[STRATEGY:StatisticalIntradayMomentum] "
            f"Received {len(pattern_results)} pattern result(s); returning []"
        )
        return []

    def evaluate_exit_signals(self, active_trades: List, current_tick: int) -> List[ExitSignal]:
        return []

    def process_watchlist(
        self,
        *,
        watchlist: List[object],
        snapshots: dict,
        session_label: str,
        timestamp_utc: str,
        mode: RunMode,
        session_phase: str,
    ) -> List[TradeIntent]:
        policy = default_policy()
        now = datetime.fromisoformat(timestamp_utc) if timestamp_utc else datetime.now(timezone.utc)
        ny_time = to_ny_time(now)
        canonical_session = normalize_session_label(session_label)
        allowed_sessions = {
            normalize_session_label(session) for session in policy.universe.allowed_sessions
        }
        print(
            "[SIMOM][CYCLE] start "
            f"timestamp={timestamp_utc} mode={mode.value} session={canonical_session} "
            f"session_phase={session_phase} ny_time={ny_time.isoformat()}"
        )
        watchlist_symbols = [
            getattr(entry, "symbol", None) for entry in watchlist if getattr(entry, "symbol", None)
        ]
        print(
            "[SIMOM][INPUT] "
            f"watchlist_k={watchlist_symbols} focus_m={watchlist_symbols[:5]}"
        )
        if not watchlist_symbols:
            print("[SIMOM][SKIP] focus_m empty; no intents evaluated")
            return []
        if canonical_session not in allowed_sessions:
            if mode in {RunMode.SIM, RunMode.PAPER}:
                print(
                    "[SIMOM][WARN] non-LIVE override — session not in allowlist; "
                    f"session={canonical_session} allowlist={sorted(allowed_sessions)}"
                )
            else:
                print(
                    "[SIMOM][SKIP] "
                    f"SESSION_NOT_ALLOWED session={canonical_session} allowlist={sorted(allowed_sessions)}"
                )
                print(
                    "[SIMOM][SUMMARY] "
                    f"considered={len(watchlist_symbols)} signals=0 orders=0 skipped={len(watchlist_symbols)}"
                )
                return []

        # activation_allowed = policy.activation.allow or mode in {
        #     RunMode.SIM,
        #     RunMode.PAPER,
        #     RunMode.READ_ONLY,
        # }
        activation_allowed = (
                policy.activation.allow
                or mode in {RunMode.SIM, RunMode.PAPER}
        )

        if not activation_allowed:
            print(
                "[SIMOM][SKIP] activation disabled by policy "
                f"allow={policy.activation.allow} mode={mode.value}"
            )
            print(
                "[SIMOM][SUMMARY] "
                f"considered={len(watchlist_symbols)} signals=0 orders=0 skipped={len(watchlist_symbols)}"
            )
            return []

        intents: List[TradeIntent] = []
        considered = 0
        skipped = 0
        for entry in watchlist:
            symbol = getattr(entry, "symbol", None)
            if not symbol:
                continue
            considered += 1
            snapshot = snapshots.get(symbol)
            intent, reasons = decide_trade_intent(
                candidate=entry,
                snapshot=snapshot,
                policy=policy,
                mode=mode,
                strategy_name=self.name,
                trader_type=self.trader_type,
            )
            if intent is not None:
                intents.append(intent)
                print(
                    "[SIMOM][SIGNAL] "
                    f"symbol={symbol} side=LONG type=CONTINUATION confidence={intent.confidence:.2f} "
                    f"stop={intent.stop_loss_price} target={intent.take_profit_price}"
                )
                decision = "PASS"
            else:
                skipped += 1
                decision = "SKIP"
            print(
                "[SIMOM][EVAL] "
                f"symbol={symbol} decision={decision} reasons={reasons or ['NONE']}"
            )

        if mode == RunMode.READ_ONLY:
            print(
                "[SIMOM][ORDERS] HARD_DISABLED mode=READ_ONLY "
                f"signals={len(intents)}"
            )
        elif mode == RunMode.PAPER:
            print("[SIMOM][ORDERS] intents_ready mode=PAPER")
        else:
            print("[SIMOM][ORDERS] intents_ready mode=SIM")
        print(
            "[SIMOM][SUMMARY] "
            f"considered={considered} signals={len(intents)} orders=0 skipped={skipped}"
        )
        return intents
