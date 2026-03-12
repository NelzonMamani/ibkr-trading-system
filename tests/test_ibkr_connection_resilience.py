from src.adapters.brokers.ibkr.ibkr_connection_manager import IbkrConnectionConfig


def test_connection_config_is_immutable_dataclass():
    config = IbkrConnectionConfig(
        host="127.0.0.1",
        port=7497,
        base_client_id=7,
        snapshot_timeout_seconds=5,
        market_data_type="LIVE",
        readonly_enabled=False,
    )

    assert config.host == "127.0.0.1"
    assert config.port == 7497
    assert config.base_client_id == 7
