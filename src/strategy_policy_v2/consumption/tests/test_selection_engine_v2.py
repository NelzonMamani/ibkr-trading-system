from src.strategy_policy_v2.consumption.selection_engine import SelectionEngineV2
from src.strategies.ross_momentum.strategy_policy import POLICY_V2


def _base(symbol: str = "AAA") -> dict:
    return {
        "symbol": symbol,
        "session_label": "PRE",
        "last_price": 5.0,
        "pct_change": 20.0,
        "volume": 2_000_000,
        "premarket_volume": 200_000,
        "rvol": 6.0,
        "dollar_volume": 10_000_000.0,
        "float_millions": 10.0,
        "spread_pct": 0.2,
        "halted": False,
        "ssr": False,
        "news_catalyst": True,
    }


def test_selection_engine_drops_missing_required_field() -> None:
    c = _base()
    c.pop("last_price")
    result = SelectionEngineV2().evaluate(POLICY_V2, [c])
    assert result.metrics["dropped"] == 1
    assert "DATA_MISSING:last_price" in result.dropped[0].reasons


def test_selection_engine_drop_reason_tags() -> None:
    c = _base()
    c.update({"last_price": 30.0, "rvol": 1.0, "float_millions": 50.0, "news_catalyst": False, "spread_pct": 99.0})
    result = SelectionEngineV2().evaluate(POLICY_V2, [c])
    reasons = set(result.dropped[0].reasons)
    assert "PRICE_OUT_OF_RANGE" in reasons
    assert "RVOL_TOO_LOW" in reasons
    assert "FLOAT_TOO_HIGH" in reasons
    assert "NO_CATALYST" in reasons
