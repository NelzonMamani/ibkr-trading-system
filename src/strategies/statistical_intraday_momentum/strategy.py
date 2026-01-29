"""Minimal Statistical Intraday Momentum strategy adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from src.models.data_models import PatternResult, TradeIntent
from src.config.runtime_config import RunMode
from src.scanner.session_pct_change import normalize_session_label
from src.strategy.base_strategy import BaseStrategy
from src.strategy.exit_signal import ExitSignal
from src.strategies.statistical_intraday_momentum.strategy_policy import default_policy
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
        if canonical_session not in allowed_sessions:
            print(
                "[SIMOM][SKIP] "
                f"SESSION_NOT_ALLOWED session={canonical_session} allowlist={sorted(allowed_sessions)}"
            )
            print(
                "[SIMOM][SUMMARY] "
                f"considered={len(watchlist_symbols)} signals=0 orders=0 skipped={len(watchlist_symbols)}"
            )
            return []

        activation_allowed = policy.activation.allow or mode == RunMode.SIM
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
        entry_threshold = policy.signal.entry_threshold
        if mode == RunMode.SIM:
            entry_threshold = min(entry_threshold, 0.55)

        scored = []
        for entry in watchlist:
            symbol = getattr(entry, "symbol", None)
            if not symbol:
                continue
            considered += 1
            snapshot = snapshots.get(symbol)
            last_price = getattr(entry, "last_price", None)
            if snapshot is not None and snapshot.last is not None:
                last_price = snapshot.last
            pct_change = getattr(entry, "pct_change", None)
            rvol = getattr(entry, "rvol", None)
            dollar_volume = getattr(entry, "dollar_volume", None)
            bid = getattr(entry, "bid", None)
            ask = getattr(entry, "ask", None)
            spread = getattr(entry, "spread", None)
            if snapshot is not None:
                if snapshot.bid is not None:
                    bid = snapshot.bid
                if snapshot.ask is not None:
                    ask = snapshot.ask
            if bid is not None and ask is not None:
                spread = ask - bid
            spread_bps = None
            if spread is not None and last_price:
                spread_bps = round((spread / last_price) * 10000.0, 2)

            reasons = []
            if last_price is None:
                reasons.append("MISSING_LAST")
            if dollar_volume is None or dollar_volume < policy.universe.min_dollar_volume:
                reasons.append("LIQUIDITY_BELOW_MIN")
            if spread_bps is not None and spread_bps > policy.universe.max_spread_bps:
                reasons.append("SPREAD_TOO_WIDE")
            score = self._score_candidate(pct_change, rvol, dollar_volume, policy)
            decision = "PASS" if not reasons and score >= entry_threshold else "SKIP"
            if decision == "PASS":
                intent = TradeIntent(
                    symbol=symbol,
                    direction="LONG",
                    strategy_name=self.name,
                    confidence=score,
                    rationale=(
                        f"Score={score:.2f} >= threshold={entry_threshold:.2f} "
                        f"pct_change={pct_change} rvol={rvol}"
                    ),
                    trader_type=self.trader_type,
                    gap_percent=pct_change,
                    rvol=rvol,
                    float_millions=getattr(entry, "float_millions", None),
                )
                intents.append(intent)
                print(
                    "[SIMOM][SIGNAL] "
                    f"symbol={symbol} side=LONG type=CONTINUATION confidence={score:.2f}"
                )
            else:
                skipped += 1
            print(
                "[SIMOM][EVAL] "
                f"symbol={symbol} features={{pct_change:{pct_change}, rvol:{rvol}, "
                f"dollar_volume:{dollar_volume}, spread_bps:{spread_bps}}} "
                f"decision={decision} reasons={reasons or ['NONE']}"
            )
            scored.append((symbol, score))

        if mode == RunMode.LIVE_READ_ONLY:
            print(
                "[SIMOM][ORDERS] HARD_DISABLED mode=LIVE_READ_ONLY "
                f"signals={len(intents)}"
            )
        else:
            print(
                "[SIMOM][ORDERS] submitted=0 blocked=0 reason=SIMULATION_ONLY"
            )
        print(
            "[SIMOM][SUMMARY] "
            f"considered={considered} signals={len(intents)} orders=0 skipped={skipped}"
        )
        return intents

    @staticmethod
    def _score_candidate(pct_change, rvol, dollar_volume, policy) -> float:
        pct_component = max(0.0, min((pct_change or 0.0) / 10.0, 2.0)) / 2.0
        rvol_component = max(0.0, min((rvol or 0.0) / 2.0, 2.0)) / 2.0
        liquidity_component = 0.0
        if dollar_volume and policy.universe.min_dollar_volume:
            liquidity_component = min(dollar_volume / policy.universe.min_dollar_volume, 1.0)
        score = (0.5 * pct_component) + (0.3 * rvol_component) + (0.2 * liquidity_component)
        return round(min(score, 1.0), 2)
