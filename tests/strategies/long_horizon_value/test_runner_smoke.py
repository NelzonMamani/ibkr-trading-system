from src.strategies.long_horizon_value.runner import LongHorizonValueRunner


def test_runner_returns_expected_keys():
    runner = LongHorizonValueRunner()
    context = {
        "run_window": "WEEKEND",
        "input_mode": "MANUAL_SYMBOL_LIST",
        "manual_symbols": ["AAPL", "MSFT"],
        "timestamp_utc": "2024-01-01T00:00:00Z",
        "disable_storage": True,
    }
    output = runner.run(context)
    assert set(output.keys()) == {"trade_intents", "reports", "metrics"}
    assert isinstance(output["trade_intents"], list)
    assert isinstance(output["reports"], list)
    assert isinstance(output["metrics"], dict)
