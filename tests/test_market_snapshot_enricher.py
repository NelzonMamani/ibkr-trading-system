from __future__ import annotations

from src.market_data.market_snapshot_enricher import MarketSnapshotEnricher


class _Ticker:
    def __init__(self) -> None:
        self.last = 10.0
        self.bid = 9.9
        self.ask = 10.1
        self.volume = 1000
        self.close = 9.5


class _Contract:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.conId = 1
        self.exchange = "SMART"
        self.primaryExchange = "NASDAQ"
        self.currency = "USD"
        self.secType = "STK"


class _IB:
    def __init__(self) -> None:
        self.wait_calls = 0
        self.cancel_calls = 0

    def qualifyContracts(self, *contracts):
        return list(contracts)

    def reqMktData(self, contract, genericTickList="", snapshot=True, regulatorySnapshot=False):
        return _Ticker()

    def waitOnUpdate(self, timeout=0.2):
        self.wait_calls += 1
        return True

    def cancelMktData(self, contract):
        self.cancel_calls += 1


class _Manager:
    def __init__(self, ib):
        self._ib = ib

    def get_client(self):
        return self._ib


def test_snapshot_results_are_logged_once_per_symbol(capsys):
    ib = _IB()
    enricher = MarketSnapshotEnricher(connection_manager=_Manager(ib), batch_timeout_seconds=0.5)

    snapshots = enricher.fetch_snapshots(["AAPL"], {"AAPL": {"contract": _Contract("AAPL")}})

    assert snapshots["AAPL"]["last_price"] == 10.0
    output = capsys.readouterr().out
    assert "[IBKR][SNAPSHOT_REQUEST]" in output
    assert output.count("[IBKR][SNAPSHOT_RECEIVED] symbol=AAPL") == 1
    assert ib.cancel_calls == 1
