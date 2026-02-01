from datetime import datetime, timezone

from src.domain.market_snapshot import MarketSnapshot
from src.strategies.long_horizon_value.pipeline import (
    assemble_fundamentals,
    compute_economics,
    estimate_intrinsic_values,
    evaluate_quality,
    rank_by_margin_of_safety,
)
from src.strategies.long_horizon_value.contracts.types import SymbolRef
from src.strategies.long_horizon_value.strategy_policy import required_margin_of_safety


def test_margin_of_safety_focus_state():
    symbol = "AAPL"
    symbols = [SymbolRef(symbol=symbol, exchange="SMART", currency="USD", country="US")]
    fundamentals = assemble_fundamentals(symbols, run_id="test_mos", as_of_year=2024)
    quality = evaluate_quality(fundamentals, market_confidence={})
    economics = compute_economics(fundamentals)
    intrinsic = estimate_intrinsic_values(economics)
    required = required_margin_of_safety("MEDIUM")
    base_value = intrinsic[symbol].base
    price = base_value * (1 - required - 0.05)
    snapshots = {
        symbol: MarketSnapshot(
            symbol=symbol,
            bid=None,
            ask=None,
            last=price,
            asof_utc=datetime.now(timezone.utc),
        )
    }
    mos_results, focus_entries = rank_by_margin_of_safety(
        intrinsic_values=intrinsic,
        quality=quality,
        economics=economics,
        price_snapshots=snapshots,
    )
    assert focus_entries
    assert mos_results[0].state == "FOCUS"
