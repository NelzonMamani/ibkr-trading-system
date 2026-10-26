"""Explicit synthetic broker-time facts for offline routing/setup controls."""
from src.domain import quote_freshness


def current_broker_quote():
    return quote_freshness.quote_evidence(
        quote_freshness.datetime.now(quote_freshness.timezone.utc).isoformat(), 'LAST_TRADE')


def current_broker_time():
    return quote_freshness.datetime.now(quote_freshness.timezone.utc)


def install_synthetic_broker_quotes(monkeypatch):
    """Opt in legacy mock routing fixtures to explicit current broker facts."""
    from dataclasses import replace
    from src.scanner.providers.mock_provider import MockScannerProvider
    original = MockScannerProvider.get_quote
    def quote(self, symbol):
        return replace(original(self, symbol), timestamp_utc=current_broker_time().isoformat(),
                       timestamp_source='LAST_TRADE')
    monkeypatch.setattr(MockScannerProvider, 'get_quote', quote)
