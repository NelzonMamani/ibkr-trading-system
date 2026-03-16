from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Sequence

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.models.data_models import PatternResult
from src.risk.risk_engine import RiskEngine
from src.strategies.common.candles.candle_types import Candle
from src.strategies.ross_momentum.patterns.pattern_evaluator import PatternEvaluator
from src.strategies.ross_momentum.patterns.pattern_inputs import IndicatorSet, LevelSet, LiquidityContext, PatternInputs
from src.strategies.ross_momentum.strategy_policy import RossMomentumPolicy
from src.strategies.strategy_contracts import SessionContext
from src.strategy.momentum_continuation_strategy import MomentumContinuationStrategy
from src.strategy.strategy_runner import StrategyRunner


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify trade pipeline for one symbol without placing orders by default")
    parser.add_argument("--symbol", required=True, help="Ticker symbol to run through diagnostics")
    parser.add_argument("--execute-live", action="store_true", help="Enable LIVE readiness decision flag (still diagnostic-only)")
    parser.add_argument("--dry-run", action="store_true", help="Use deterministic synthetic market data instead of IBKR snapshot")
    return parser.parse_args(argv)


def _hydrate_symbol(symbol: str, dry_run: bool) -> tuple[bool, dict]:
    if dry_run:
        return True, {"last": 10.0, "bid": 9.98, "ask": 10.02, "volume": 120_000}

    manager = get_shared_ibkr_connection_manager(readonly_enabled=True)
    client = manager.get_client()
    snapshot = client.get_market_snapshot(symbol)
    hydrated = any(value is not None for value in (snapshot.last, snapshot.bid, snapshot.ask))
    return hydrated, {
        "last": snapshot.last,
        "bid": snapshot.bid,
        "ask": snapshot.ask,
        "volume": snapshot.volume,
    }


def _pattern_inputs(symbol: str, data: dict) -> PatternInputs:
    last = float(data.get("last") or 10.0)
    bid = float(data.get("bid") or (last - 0.02))
    ask = float(data.get("ask") or (last + 0.02))
    spread = max(ask - bid, 0.01)
    volume = int(data.get("volume") or 100_000)
    candles = [
        Candle(open=last * 0.98, high=last * 0.99, low=last * 0.975, close=last * 0.985, volume=max(volume // 10, 1)),
        Candle(open=last * 0.985, high=last * 0.995, low=last * 0.98, close=last * 0.99, volume=max(volume // 9, 1)),
        Candle(open=last * 0.99, high=last * 1.005, low=last * 0.988, close=last, volume=max(volume // 8, 1)),
    ]
    return PatternInputs(
        symbol=symbol,
        timeframe="1m",
        candles=candles,
        session_context=SessionContext.PRE,
        levels=LevelSet(premarket_high=last * 1.01, hod=last * 1.02, prior_close=last * 0.97),
        indicators=IndicatorSet(ema9=last * 0.997, ema20=last * 0.994, vwap=last * 0.996),
        liquidity_context=LiquidityContext(spread=spread, float_millions=20.0, rvol=2.0),
        data_quality_flags=[],
    )


def _to_strategy_pattern(symbol: str, summary) -> list[PatternResult]:
    setup = summary.best_long_setup or summary.best_short_setup
    if setup is None or not setup.detected:
        return []

    pattern_name = setup.pattern_name
    if pattern_name == "ORB_BREAK":
        pattern_name = "ORB_BREAKOUT"
    elif pattern_name == "FIRST_PULLBACK_LONG":
        pattern_name = "FIRST_PULLBACK"

    return [
        PatternResult(
            symbol=symbol,
            pattern_name=pattern_name,
            confidence=float(setup.confidence),
            rationale=setup.rationale_text,
            data_quality_flags=list(setup.risk_flags or []),
        )
    ]


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    symbol = args.symbol.upper()

    _ = RossMomentumPolicy()

    print("[PIPELINE_TEST]")
    print(f"symbol={symbol}")

    print("\n[DATA]")
    try:
        hydration_ok, hydrated = _hydrate_symbol(symbol, args.dry_run)
    except Exception as exc:
        hydration_ok, hydrated = False, {}
        print(f"hydration=FAILED ({exc})")
    else:
        print(f"hydration={'SUCCESS' if hydration_ok else 'FAILED'}")

    evaluator = PatternEvaluator()
    summary = evaluator.evaluate([_pattern_inputs(symbol, hydrated)])
    pattern_detected = bool(summary.best_long_setup or summary.best_short_setup)
    print("\n[PATTERN]")
    print(f"pattern_detected={pattern_detected}")

    strategy_patterns = _to_strategy_pattern(symbol, summary)
    strategy_runner = StrategyRunner(strategies=[MomentumContinuationStrategy()])
    intents = strategy_runner.generate_trade_intents(strategy_patterns)
    intent_generated = len(intents) > 0
    print("\n[STRATEGY]")
    print(f"intent_generated={intent_generated}")

    risk_approved = False
    if intents:
        intent = intents[0]
        intent.decision_id = f"pipeline-test:{symbol}:{datetime.now(timezone.utc).timestamp()}"
        risk_decision = RiskEngine().evaluate_trade_intent(intent)
        risk_approved = bool(risk_decision.allowed)
    print("\n[RISK]")
    print(f"risk_approved={risk_approved}")

    order_would_be_placed = bool(intent_generated and risk_approved)
    print("\n[EXECUTION]")
    print(f"order_would_be_placed={order_would_be_placed}")
    if args.execute_live and order_would_be_placed:
        print("live_execution_requested=True")
        print("live_execution_submitted=False")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
