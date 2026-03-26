from __future__ import annotations

from src.scanner.providers.ibkr_provider import IbkrScannerProvider, _parse_shares_value


class _Resp:
    def __init__(self, *, text: str = "", payload=None) -> None:
        self.text = text
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def test_parse_shares_value_handles_suffixes_and_formatting() -> None:
    assert _parse_shares_value("12.3M") == 12_300_000
    assert _parse_shares_value("1,234,567") == 1_234_567
    assert _parse_shares_value("9.5K") == 9_500
    assert _parse_shares_value(" 2.1B shares ") == 2_100_000_000
    assert _parse_shares_value("N/A") is None


def test_finviz_fetch_detailed_success(monkeypatch) -> None:
    html = '<td>Float</td><td>17.8M</td>'
    monkeypatch.setattr(
        "src.scanner.providers.ibkr_provider.requests.get",
        lambda *args, **kwargs: _Resp(text=html),
    )
    value, reason = IbkrScannerProvider._fetch_finviz_float_detailed("PRSO")
    assert value == 17_800_000
    assert reason == "OK"


def test_finviz_fetch_detailed_success_with_shs_label(monkeypatch) -> None:
    html = '<td width="7%" class="snapshot-td2-cp">Shs Float</td><td width="8%" class="snapshot-td2">1,234.5K</td>'
    monkeypatch.setattr(
        "src.scanner.providers.ibkr_provider.requests.get",
        lambda *args, **kwargs: _Resp(text=html),
    )
    value, reason = IbkrScannerProvider._fetch_finviz_float_detailed("PRSO")
    assert value == 1_234_500
    assert reason == "OK"


def test_yahoo_fetch_detailed_invalid_numeric(monkeypatch) -> None:
    payload = {
        "quoteSummary": {
            "result": [{"defaultKeyStatistics": {"floatShares": {"fmt": "N/A"}}}]
        }
    }
    monkeypatch.setattr(
        "src.scanner.providers.ibkr_provider.requests.get",
        lambda *args, **kwargs: _Resp(payload=payload),
    )
    value, reason = IbkrScannerProvider._fetch_yahoo_float_detailed("PRSO")
    assert value is None
    assert reason == "FIELD_NOT_FOUND"


def test_yahoo_fetch_detailed_fallback_to_v11(monkeypatch) -> None:
    payload = {
        "quoteSummary": {
            "result": [{"defaultKeyStatistics": {"floatShares": {"raw": 45_000_000}}}]
        }
    }

    def _fake_get(url: str, *args, **kwargs):
        if "query1.finance.yahoo.com" in url:
            raise RuntimeError("blocked")
        return _Resp(payload=payload)

    monkeypatch.setattr("src.scanner.providers.ibkr_provider.requests.get", _fake_get)
    monkeypatch.setattr("src.scanner.providers.ibkr_provider.requests.RequestException", RuntimeError)

    value, reason = IbkrScannerProvider._fetch_yahoo_float_detailed("PRSO")
    assert value == 45_000_000
    assert reason == "OK"


def test_get_float_uses_provider_order_and_logs_fetch_ok(monkeypatch, capsys) -> None:
    provider = IbkrScannerProvider.__new__(IbkrScannerProvider)
    provider.market_data_client = None
    provider.last_scan_details = {}
    provider.last_float_source = None
    provider.last_float_failures = []

    monkeypatch.setattr(
        IbkrScannerProvider,
        "_fetch_finviz_float_detailed",
        staticmethod(lambda _symbol: (None, "FIELD_NOT_FOUND")),
    )
    monkeypatch.setattr(
        IbkrScannerProvider,
        "_fetch_yahoo_float_detailed",
        staticmethod(lambda _symbol: (7_700_000, "OK")),
    )
    monkeypatch.setattr(
        IbkrScannerProvider,
        "_fetch_ibkr_float_detailed",
        lambda self, _symbol: (None, "FIELD_NOT_FOUND"),
    )

    value = provider.get_float("PRSO")
    out = capsys.readouterr().out

    assert value == 7_700_000
    assert "[FLOAT][FETCH_START] symbol=PRSO provider=YAHOO" in out
    assert "[FLOAT][FETCH_OK] symbol=PRSO provider=YAHOO value=7700000" in out


def test_get_float_uses_cached_last_known_good_when_live_sources_fail(monkeypatch) -> None:
    provider = IbkrScannerProvider.__new__(IbkrScannerProvider)
    provider.market_data_client = None
    provider.last_scan_details = {}
    provider.last_float_source = None
    provider.last_float_failures = []

    monkeypatch.setattr(IbkrScannerProvider, "_fetch_yahoo_float_detailed", staticmethod(lambda _symbol: (None, "REQUEST_ERROR")))
    monkeypatch.setattr(IbkrScannerProvider, "_fetch_finviz_float_detailed", staticmethod(lambda _symbol: (None, "REQUEST_ERROR")))
    monkeypatch.setattr(IbkrScannerProvider, "_fetch_ibkr_float_detailed", lambda self, _symbol: (None, "REQUEST_ERROR"))

    class _Cache:
        def __init__(self, *args, **kwargs) -> None:
            self.last_float_failures = [("YAHOO", "REQUEST_ERROR")]
            self.last_cache_used = True
            self.last_fallback_used = True

        def get_float(self, symbol: str):
            return 6_600_000, "DB_LAST_KNOWN_GOOD"

    monkeypatch.setattr("src.scanner.providers.ibkr_provider.FloatProvider", _Cache)

    value = provider.get_float("PRSO")
    assert value == 6_600_000
    assert provider.last_float_source == "DB_LAST_KNOWN_GOOD"
