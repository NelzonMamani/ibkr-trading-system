import json
from pathlib import Path

import pytest

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient


def _client(tmp_path: Path) -> IbkrClient:
    path = tmp_path / "order_state.json"
    return IbkrClient(
        host="127.0.0.1",
        port=7497,
        client_id=7,
        snapshot_timeout_seconds=1,
        market_data_type="DELAYED",
        readonly_enabled=False,
    )


def test_reserve_order_id_requires_next_valid_id(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("IBKR_ORDER_ID_STATE_PATH", str(tmp_path / "state.json"))
    client = _client(tmp_path)
    with pytest.raises(RuntimeError, match="not yet initialized"):
        client.reserve_order_id()
    out = capsys.readouterr().out
    assert "[CRITICAL] IBKR_NEXT_VALID_ID_NOT_READY" in out


def test_next_valid_id_rebases_from_persisted_local_last(tmp_path, monkeypatch, capsys):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"last_reserved_order_id": 100}), encoding="utf-8")
    monkeypatch.setenv("IBKR_ORDER_ID_STATE_PATH", str(state_path))
    client = _client(tmp_path)
    client.nextValidId(50)
    reserved = client.reserve_order_id()
    assert reserved == 101
    out = capsys.readouterr().out
    assert "[IBKR][ORDER_ID_REBASE] broker_next=50 local_last=100 chosen=101" in out
    assert "[IBKR][ORDER_ID_SOURCE] source=IBKR_NEXT_VALID_ID order_id=101" in out
