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
    assert reason == "INVALID_NUMERIC"
