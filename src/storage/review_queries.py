"""Review query placeholders for Epoch 5."""


def latest_cycles_query(limit: int = 5) -> str:
    return f"SELECT * FROM trade_store ORDER BY cycle_time DESC LIMIT {limit}"
