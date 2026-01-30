from __future__ import annotations

import sys

from dataclasses import replace
import argparse

if sys.platform.startswith("win"):
    import asyncio as _asyncio_tmp

    _asyncio_tmp.set_event_loop_policy(_asyncio_tmp.WindowsSelectorEventLoopPolicy())

from src.scanner.scanner_contract import scanner_request_from_policy
from src.scanner.scanner_runner import run_scanner_cycle
from src.strategies.ross_momentum.strategy_policy import (
    RossMomentumPolicy,
    stock_selection_policy_for_session_phase,
)
from src.strategies.statistical_intraday_momentum.strategy_policy import (
    StatisticalIntradayMomentumPolicy,
    statistical_stock_selection_spec,
)


def _resolve_strategy_policy(
    strategy_name: str,
    session_phase: str | None,
):
    normalized = (strategy_name or "ross_momentum").strip().lower()
    if normalized == "statistical_intraday_momentum":
        strategy_policy = StatisticalIntradayMomentumPolicy()
        stock_policy = statistical_stock_selection_spec()
        return normalized, strategy_policy, stock_policy
    strategy_policy = RossMomentumPolicy()
    stock_policy = stock_selection_policy_for_session_phase(
        strategy_policy,
        session_phase or "",
    )
    return "ross_momentum", strategy_policy, stock_policy


def main() -> None:
    parser = argparse.ArgumentParser(description="Scanner standalone runner")
    parser.add_argument("--strategy", default="ross_momentum")
    parser.add_argument("--session", default=None)
    parser.add_argument("--topn", type=int, default=None)
    args = parser.parse_args()

    strategy_name, _, stock_policy = _resolve_strategy_policy(
        args.strategy,
        args.session,
    )
    if args.topn is not None:
        universe = replace(stock_policy.universe, top_n=args.topn)
        stock_policy = replace(
            stock_policy,
            top_gainers_n=args.topn,
            universe=universe,
        )
    request = scanner_request_from_policy(
        stock_policy,
        strategy_name=strategy_name,
        session_phase=args.session,
    )
    run_scanner_cycle(
        mode="standalone",
        policy=stock_policy,
        scanner_request=request,
    )


if __name__ == "__main__":
    main()
