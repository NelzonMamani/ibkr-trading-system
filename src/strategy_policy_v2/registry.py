from __future__ import annotations

from typing import Callable

from src.strategy_policy_v2.policy_v2 import StrategyPolicyV2


_POLICY_IMPORT_PATHS: dict[str, str] = {
    "ross_momentum": "src.strategies.ross_momentum.strategy_policy_v2.POLICY_V2",
    "statistical_intraday_momentum": "src.strategies.statistical_intraday_momentum.strategy_policy_v2.POLICY_V2",
    # TODO(P03): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P04): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P05): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P06): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P07): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P08): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P09): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P10): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P11): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P12): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P13): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P14): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P15): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P16): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P17): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P18): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P19): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
    # TODO(P20): "<strategy_key>": "src.strategies.<module>.strategy_policy_v2.POLICY_V2",
}


_RESOLVERS: dict[str, Callable[[], StrategyPolicyV2]] = {
    "ross_momentum": lambda: __import__(
        "src.strategies.ross_momentum.strategy_policy_v2",
        fromlist=["POLICY_V2"],
    ).POLICY_V2,
    "statistical_intraday_momentum": lambda: __import__(
        "src.strategies.statistical_intraday_momentum.strategy_policy_v2",
        fromlist=["POLICY_V2"],
    ).POLICY_V2,
}


def resolve_policy_v2(strategy_key: str) -> StrategyPolicyV2 | None:
    resolver = _RESOLVERS.get(str(strategy_key or "").strip().lower())
    if resolver is None:
        return None
    return resolver()


def has_policy_v2(strategy_key: str) -> bool:
    return str(strategy_key or "").strip().lower() in _RESOLVERS


def list_registered_policies_v2() -> dict[str, str]:
    return dict(_POLICY_IMPORT_PATHS)
