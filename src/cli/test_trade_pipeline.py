from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any, Sequence

from src.adapters.brokers.ibkr.ibkr_connection_manager import get_shared_ibkr_connection_manager
from src.core.managers.market_data_snapshot_manager import MarketDataSnapshotManager
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
    parser.add_argument("--execute-live", action="store_true", help="Enable LIVE readiness decision flag")
    parser.add_argument("--dangerous-submit-live-order", action="store_true", help="DANGEROUS: allow real order submission path")
    parser.add_argument("--dry-run", action="store_true", help="Use deterministic synthetic market data instead of IBKR snapshot")
    return parser.parse_args(argv)


def _hydrate_symbol(symbol: str, dry_run: bool) -> tuple[str, dict[str, Any]]:
    if dry_run:
        return "SUCCESS", {"last": 10.0, "bid": 9.98, "ask": 10.02, "volume": 120_000}

    manager = get_shared_ibkr_connection_manager(readonly_enabled=True)
    manager.ensure_connected()
    snapshot_manager = MarketDataSnapshotManager(manager.get_client())
    snapshot, quality = snapshot_manager.get_snapshot(symbol)
    if quality.missing_fields:
        hydration = "PARTIAL"
    else:
        hydration = "SUCCESS"
    return hydration, {
        "last": snapshot.last,
        "bid": snapshot.bid,
        "ask": snapshot.ask,
        "volume": snapshot.volume,
        "missing_fields": quality.missing_fields,
        "quality_flags": quality.data_quality_flags,
    }


def _pattern_inputs(symbol: str, data: dict[str, Any]) -> PatternInputs:
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


def run_pipeline(*, symbol: str, dry_run: bool, execute_live: bool, dangerous_submit_live_order: bool) -> dict[str, Any]:
    _ = RossMomentumPolicy()
    hydration, hydrated = _hydrate_symbol(symbol, dry_run)

    evaluator = PatternEvaluator()
    summary = evaluator.evaluate([_pattern_inputs(symbol, hydrated)])
    strategy_patterns = _to_strategy_pattern(symbol, summary)
    strategy_runner = StrategyRunner(strategies=[MomentumContinuationStrategy()])
    intents = strategy_runner.generate_trade_intents(strategy_patterns)

    risk_approved = False
    risk_reason = "NO_INTENT"
    if intents:
        intent = intents[0]
        intent.decision_id = f"pipeline-test:{symbol}:{datetime.now(timezone.utc).timestamp()}"
        risk_decision = RiskEngine().evaluate_trade_intent(intent)
        risk_approved = bool(risk_decision.allowed)
        risk_reason = "APPROVED" if risk_approved else (risk_decision.reason or "DENIED")

    order_would_be_placed = bool(intents and risk_approved)
    live_submit_requested = bool(execute_live and dangerous_submit_live_order and order_would_be_placed)

    return {
        "symbol": symbol,
        "hydration": hydration,
        "hydrated": hydrated,
        "pattern": {
            "best_long_setup": getattr(summary.best_long_setup, "pattern_name", "NONE"),
            "best_short_setup": getattr(summary.best_short_setup, "pattern_name", "NONE"),
            "detected_patterns": [p.pattern_name for p in strategy_patterns],
        },
        "strategy": {
            "strategies_evaluated": ["MomentumContinuationStrategy"],
            "intents_generated": len(intents),
        },
        "risk": {
            "first_decision_result": "ALLOW" if risk_approved else "DENY",
            "deny_reason": None if risk_approved else risk_reason,
        },
        "execution": {
            "order_would_be_placed": order_would_be_placed,
            "execute_live_requested": execute_live,
            "dangerous_submit_live_order": dangerous_submit_live_order,
            "live_execution_submitted": live_submit_requested,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    symbol = args.symbol.upper()

    print("[PIPELINE_TEST]")
    print(f"symbol={symbol}")

    try:
        result = run_pipeline(
            symbol=symbol,
            dry_run=args.dry_run,
            execute_live=args.execute_live,
            dangerous_submit_live_order=args.dangerous_submit_live_order,
        )
    except Exception as exc:
        print(f"pipeline_status=FAILED ({exc})")
        return 1

    print("\n[DATA]")
    print(f"hydration={result['hydration']}")
    print(f"last={result['hydrated'].get('last')}")
    print(f"bid={result['hydrated'].get('bid')}")
    print(f"ask={result['hydrated'].get('ask')}")
    print(f"volume={result['hydrated'].get('volume')}")

    print("\n[PATTERN]")
    print(f"best_long_setup={result['pattern']['best_long_setup']}")
    print(f"best_short_setup={result['pattern']['best_short_setup']}")
    print(f"detected_patterns={result['pattern']['detected_patterns']}")

    print("\n[STRATEGY]")
    print(f"strategies_evaluated={result['strategy']['strategies_evaluated']}")
    print(f"intents_generated={result['strategy']['intents_generated']}")

    print("\n[RISK]")
    print(f"first_decision_result={result['risk']['first_decision_result']}")
    print(f"deny_reason={result['risk']['deny_reason']}")

    print("\n[EXECUTION]")
    print(f"order_would_be_placed={result['execution']['order_would_be_placed']}")
    print(f"execute_live_requested={result['execution']['execute_live_requested']}")
    print(f"dangerous_submit_live_order={result['execution']['dangerous_submit_live_order']}")
    print(f"live_execution_submitted={result['execution']['live_execution_submitted']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
