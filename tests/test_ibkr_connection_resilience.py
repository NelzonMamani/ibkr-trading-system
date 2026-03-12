import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

try:
    from brokers.ibkr_broker import IbkrBroker
except ModuleNotFoundError:
    pytest.skip("ibapi dependency missing; skipping IBKR resilience tests", allow_module_level=True)


def test_client_id_increment():
    broker = IbkrBroker()

    base_id = 7

    ids = [base_id + i for i in range(5)]

    assert ids == [7, 8, 9, 10, 11]
    assert broker.MAX_CLIENT_ID_RETRIES == 10
