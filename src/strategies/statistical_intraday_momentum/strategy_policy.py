"""Interface-native policy for Statistical Intraday Momentum."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.config.runtime_config import RunMode
from src.core.take_profit_authority import TakeProfitAuthority
from src.domain.market_snapshot import MarketSnapshot
from src.models.data_models import TradeIntent
from src.scanner.result_models import CandidateMetrics
from src.strategy_portfolio.contracts import StrategyIdentity
from src.strategies.ross_momentum.strategy_policy import (
    StockSelectionSpec,
    UniverseSource,
    UniverseSpec as RossUniverseSpec,
)


@dataclass(frozen=True)
class UniverseSpec:
    """Universe selection constraints (conservative defaults)."""

    min_price: float = 5.0  # Avoid microcaps and penny stocks with noisy fills.
    max_price: float = 200.0  # Avoid very high-priced symbols with wide spreads.
    min_dollar_volume: float = 20_000_000.0  # Daily dollar volume floor for liquidity.
    max_spread_bps: float = 25.0  # Approximate spread ceiling in bps if available.
    allowed_sessions: tuple[str, ...] = (
        "REGULAR",
    )  # Regular session only until proven safe.


@dataclass(frozen=True)
class ActivationSpec:
    """Activation windows and cooldown controls."""

    allow: bool = False  # Default off to prevent accidental trading until wired.
    start_minute_of_day: int = 30  # Avoid open noise; start after ~9:30 + 30 mins.
    end_minute_of_day: int = 360  # Avoid close noise; stop before last hour.
    cooldown_seconds: int = 120  # Per-symbol cooldown to avoid rapid churn.


@dataclass(frozen=True)
class RegimeSpec:
    """Volatility and liquidity gating parameters."""

    vol_floor: float = 0.005  # Require >=0.5% realized vol proxy over 15m.
    vol_ceiling: float = 0.05  # Disallow extreme volatility spikes.
    min_liquidity_score: float = 0.5  # Normalized liquidity score floor.
    max_spread_bps: float = 25.0  # Failsafe spread ceiling for microstructure stability.


@dataclass(frozen=True)
class SignalSpec:
    """Signal lookbacks and thresholds for continuation intent."""

    lookback_minutes_short: int = 5  # Short lookback for recent momentum.
    lookback_minutes_long: int = 15  # Longer lookback for confirmation.
    confirmation_minutes: int = 2  # Require persistence over 1-3 minutes.
    entry_threshold: float = 0.7  # Conservative entry score threshold.
    hold_threshold: float = 0.5  # Maintain positions only if score remains strong.
    exit_threshold: float = 0.3  # Exit when score weakens materially.
    long_only: bool = True  # Long-only by default for v1 safety.


@dataclass(frozen=True)
class RiskSpec:
    """Risk request parameters (intent only, not execution)."""

    per_trade_risk_usd: float = 50.0  # Small default risk request per trade.
    max_concurrent_positions: int = 1  # Limit concurrent exposure until proven safe.
    stop_model: str = "atr_trailing"  # Placeholder stop model name for interface.


@dataclass(frozen=True)
class TelemetrySpec:
    """Learning-only telemetry outputs toggle."""

    enable_learning_output: bool = True  # Allow telemetry without trading impact.


@dataclass(frozen=True)
class StatisticalIntradayMomentumPolicy:
    """Top-level policy specification for the strategy."""

    name: str = "statistical_intraday_momentum"
    version: str = "1.0"
    universe: UniverseSpec = UniverseSpec()
    activation: ActivationSpec = ActivationSpec()
    regime: RegimeSpec = RegimeSpec()
    signal: SignalSpec = SignalSpec()
    risk: RiskSpec = RiskSpec()
    telemetry: TelemetrySpec = TelemetrySpec()


def policy_identity(policy: StatisticalIntradayMomentumPolicy) -> StrategyIdentity:
    return StrategyIdentity(
        strategy_id=policy.name,
        strategy_version=policy.version,
        strategy_family="statistical_intraday",
    )


def default_policy() -> StatisticalIntradayMomentumPolicy:
    return StatisticalIntradayMomentumPolicy()


def statistical_stock_selection_spec() -> StockSelectionSpec:
    """Scanner configuration for statistical intraday momentum."""
    universe = RossUniverseSpec(
        source=UniverseSource.IBKR_TOP_GAINERS,
        ibkr_scan_code="TOP_PERC_GAIN",
        top_n=75,
    )
    return StockSelectionSpec(
        policy_name="STATISTICAL_INTRADAY_MOMENTUM",
        universe=universe,
        price_min=5.0,
        price_max=200.0,
        gap_min_pct=2.0,
        gap_max_pct=None,
        rvol_min=1.5,
        float_max_millions=200.0,
        liquidity_min_dollar_volume=20_000_000.0,
        min_volume=500_000,
        min_premarket_volume=0,
        spread_max_pct=None,
        require_catalyst=False,
        allow_halts=False,
        allow_ssr=True,
        data_quality_require_price=True,
        data_quality_require_bid_ask=True,
        watchlist_limit_k=20,
        focus_limit_m=5,
        top_gainers_n=75,
        max_symbols_per_cycle=75,
        session_allowlist=("REG",),
        ranking_intent="STATISTICAL_INTRADAY_MOMENTUM_STOCK_SELECTION",
    )


def decide_trade_intent(
    *,
    candidate: CandidateMetrics,
    snapshot: MarketSnapshot | None,
    policy: StatisticalIntradayMomentumPolicy,
    mode: RunMode,
    strategy_name: str,
    trader_type: str,
) -> tuple[TradeIntent | None, list[str]]:
    reasons: list[str] = []
    flags = list(candidate.data_quality_flags or [])
    if flags:
        blocked_flags = _blocked_data_quality_flags(flags, mode)
        if blocked_flags:
            reasons.append(f"DATA_QUALITY_BLOCKED:{','.join(blocked_flags)}")
    if reasons:
        return None, reasons

    last_price = candidate.last_price
    if snapshot is not None and snapshot.last is not None:
        last_price = snapshot.last
    if last_price is None:
        return None, ["INSUFFICIENT_DATA_LAST"]

    gap_pct = candidate.gap_pct if candidate.gap_pct is not None else candidate.pct_change
    rvol = candidate.rvol if candidate.rvol is not None else candidate.relative_volume
    dollar_volume = candidate.dollar_volume
    if gap_pct is None or gap_pct < 2.0:
        reasons.append("GAP_BELOW_MIN")
    if rvol is None or rvol < 1.5:
        reasons.append("RVOL_BELOW_MIN")
    if dollar_volume is None or dollar_volume < policy.universe.min_dollar_volume:
        reasons.append("LIQUIDITY_BELOW_MIN")

    bid = candidate.bid
    ask = candidate.ask
    spread = candidate.spread
    if snapshot is not None:
        if snapshot.bid is not None:
            bid = snapshot.bid
        if snapshot.ask is not None:
            ask = snapshot.ask
    if bid is not None and ask is not None:
        spread = ask - bid
    if spread is not None and last_price:
        spread_bps = (spread / last_price) * 10000.0
        if spread_bps > policy.universe.max_spread_bps and mode != RunMode.SIM:
            reasons.append("SPREAD_TOO_WIDE")

    if reasons:
        return None, reasons

    stop_distance = max(last_price * 0.01, 0.01)
    stop_loss_price = round(max(last_price - stop_distance, 0.01), 4)
    take_profit_price = TakeProfitAuthority.r_multiple_price(
        entry_price=last_price,
        stop_loss_price=stop_loss_price,
        side="LONG",
        r_multiple=2.0,
        decimals=4,
    )
    confidence = _confidence_score(gap_pct, rvol)
    rationale_parts = [
        f"gap_pct={gap_pct}",
        f"rvol={rvol}",
        f"dollar_volume={dollar_volume}",
        "rule=gap>=2 rvol>=1.5 liquidity>=min",
    ]
    if "MOCK" in flags and mode == RunMode.SIM:
        rationale_parts.append("data_quality=MOCK_SIM_OK")
    rationale = " | ".join(rationale_parts)

    intent = TradeIntent(
        symbol=candidate.symbol,
        direction="LONG",
        strategy_name=strategy_name,
        confidence=confidence,
        rationale=rationale,
        trader_type=trader_type,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        gap_percent=gap_pct,
        rvol=rvol,
        float_millions=candidate.float_millions,
        data_quality_flags=flags,
    )
    return intent, []


def _blocked_data_quality_flags(flags: Iterable[str], mode: RunMode) -> list[str]:
    critical_flags = {
        "MISSING_LAST",
        "MISSING_PRICE",
        "INCOMPLETE_BID_ASK",
        "MD_TIMEOUT",
        "CONTRACT_QUALIFY_FAILED",
        "QUOTE_UNAVAILABLE",
    }
    blocked = []
    for flag in flags:
        if flag == "MOCK" and mode == RunMode.SIM:
            continue
        if flag == "MOCK" and mode != RunMode.SIM:
            blocked.append(flag)
            continue
        if flag in critical_flags:
            blocked.append(flag)
    return blocked


def _confidence_score(gap_pct: float | None, rvol: float | None) -> float:
    gap_score = min(max((gap_pct or 0.0) / 10.0, 0.0), 1.0)
    rvol_score = min(max((rvol or 0.0) / 3.0, 0.0), 1.0)
    score = (0.6 * gap_score) + (0.4 * rvol_score)
    return round(min(max(score, 0.0), 1.0), 2)
