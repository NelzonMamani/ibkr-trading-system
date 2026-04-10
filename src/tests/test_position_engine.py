from __future__ import annotations

from src.execution.position_engine import compute_positions_from_executions


def test_compute_positions_from_executions_splits_system_and_external() -> None:
    rows = [
        {"exec_id": "1", "symbol": "TSLA", "order_ref": "ROSS::S::TSLA::i1", "side": "BUY", "quantity": 5},
        {"exec_id": "2", "symbol": "TSLA", "order_ref": "ROSS::S::TSLA::i2", "side": "SELL", "quantity": 3},
        {"exec_id": "3", "symbol": "TSLA", "order_ref": "", "side": "BUY", "quantity": 4},
    ]
    result = compute_positions_from_executions(rows, broker_positions_by_symbol={"TSLA": 9})
    assert result["TSLA"]["system_qty"] == 2
    assert result["TSLA"]["broker_qty"] == 9
    assert result["TSLA"]["external_qty"] == 7
