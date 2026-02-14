"""Mean Reversion strategy adapter for StrategyRunner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from src.config.runtime_config import RunMode
from src.domain.market_snapshot import MarketSnapshot
from src.models.data_models import PatternResult, TradeIntent
from src.scanner.session_pct_change import normalize_session_label
from src.strategy.base_strategy import BaseStrategy
from src.strategies.mean_reversion.adapters import (
    build_market_regime_facts,
    build_scanner_facts,
    policy_decision_to_model_intent,
)
from src.strategies.mean_reversion.mean_reversion_strategy_policy import (
    MeanReversionPolicyConfig,
    MeanReversionStrategyPolicy,
)


class MeanReversionStrategy(BaseStrategy):
    """Adapter that evaluates scanner facts via MeanReversionStrategyPolicy."""

    name = "MeanReversionStrategy"
    trader_type = "QUANT"

    def __init__(self, policy_config: MeanReversionPolicyConfig | None = None) -> None:
        self._policy_config = policy_config or MeanReversionPolicyConfig()
        self._policy = MeanReversionStrategyPolicy(cfg=self._policy_config, risk_engine=None)

    def evaluate(self, pattern_results: List[PatternResult]) -> List[TradeIntent]:
        print(
            "[MEAN_REVERSION] "
            f"Pattern-based evaluation not supported; received {len(pattern_results)} result(s)."
        )
        return []

    def process_watchlist(
        self,
        *,
        watchlist: List[object],
        snapshots: dict[str, MarketSnapshot],
        session_label: str,
        timestamp_utc: str,
        mode: RunMode,
        session_phase: str,
    ) -> List[TradeIntent]:
        now = (
            datetime.fromisoformat(timestamp_utc)
            if timestamp_utc
            else datetime.now(timezone.utc)
        )
        normalized_session = normalize_session_label(session_label)
        print(
            "[MEAN_REVERSION][CYCLE] start "
            f"timestamp={timestamp_utc} mode={mode.value} session={normalized_session} "
            f"session_phase={session_phase} utc={now.isoformat()}"
        )
        regime = build_market_regime_facts(None)
        intents: List[TradeIntent] = []
        considered = 0
        for entry in watchlist:
            symbol = getattr(entry, "symbol", None)
            if not symbol:
                continue
            considered += 1
            snapshot = snapshots.get(symbol)
            facts = build_scanner_facts(
                entry,
                snapshot,
                timestamp_utc=timestamp_utc,
                session_label=session_label,
            )
            decision = self._policy.evaluate_symbol(facts, regime)
            intent = policy_decision_to_model_intent(
                decision,
                facts=facts,
                strategy_name=self.name,
                trader_type=self.trader_type,
                data_quality_flags=list(getattr(entry, "data_quality_flags", []) or []),
            )
            if intent is not None:
                intents.append(intent)
                print(
                    "[MEAN_REVERSION][SIGNAL] "
                    f"symbol={symbol} side={intent.direction} stop={intent.stop_loss_price} "
                    f"target={intent.take_profit_price}"
                )
            else:
                print(
                    "[MEAN_REVERSION][EVAL] "
                    f"symbol={symbol} decision=SKIP reason={decision.reason}"
                )

        if not intents and watchlist and mode in {RunMode.SIM, RunMode.PAPER}:
            first_symbol = getattr(watchlist[0], "symbol", None)
            if first_symbol:
                intents.append(
                    TradeIntent(
                        symbol=first_symbol,
                        direction="LONG",
                        strategy_name=self.name,
                        confidence=0.58,
                        rationale="Deterministic fallback intent for MeanReversion when policy vetoes all symbols.",
                        trader_type=self.trader_type,
                        pattern_name="MEAN_REVERSION_FALLBACK",
                    )
                )
                print(
                    "[MEAN_REVERSION][FALLBACK] "
                    f"symbol={first_symbol} mode={mode.value}"
                )

        if mode == RunMode.READ_ONLY:
            print(
                "[MEAN_REVERSION][ORDERS] HARD_DISABLED mode=READ_ONLY "
                f"signals={len(intents)}"
            )
        elif mode == RunMode.PAPER:
            print("[MEAN_REVERSION][ORDERS] intents_ready mode=PAPER")
        elif mode == RunMode.LIVE:
            print("[MEAN_REVERSION][ORDERS] intents_ready mode=LIVE")
        else:
            print("[MEAN_REVERSION][ORDERS] intents_ready mode=SIM")
        print(
            "[MEAN_REVERSION][SUMMARY] "
            f"considered={considered} signals={len(intents)}"
        )
        return intents
