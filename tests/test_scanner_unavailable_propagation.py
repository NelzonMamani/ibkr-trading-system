"""Offline end-to-end scanner availability boundary; fixture transports only."""
from types import SimpleNamespace as NS
import pytest
from src.scanner.providers import ibkr_provider as provider_module
from src.scanner.providers.ibkr_provider import IbkrScannerProvider
from src.scanner.scanner_runner import _resolve_universe_symbols
from src.scanner.scanner_contract import ScannerRequest
from src.strategies.ross_momentum.strategy_policy import UniverseSource
from src.config.runtime_config import RunMode
from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.ibkr.market_data_client import MarketDataClient
from test_ibkr_provider_scanner_location_fallback import _DummySubscription, _scanner_item


@pytest.fixture
def setup_boundary(monkeypatch):
    monkeypatch.setattr(provider_module,'safe_import_ib_insync',lambda:(None,None,_DummySubscription))
    monkeypatch.setattr(provider_module,'get_run_mode',lambda:RunMode.READ_ONLY)
    monkeypatch.setattr(provider_module,'get_ibkr_fallback_enabled',lambda:False)
    monkeypatch.setattr(provider_module,'get_scanner_symbols',lambda **kwargs:pytest.fail('local candidates injected'))


def resolve(provider):
    request=ScannerRequest('ross_momentum','ROSS_MOMENTUM','GAINERS','RTH',
        UniverseSource.IBKR_TOP_GAINERS,'TOP_PERC_GAIN',50)
    return _resolve_universe_symbols(provider=provider,request=request,
        limits={'resolved_symbol_limit':50},diagnostics={},allow_mock_fallback=False)


@pytest.mark.parametrize('response',[None,False,0,{},''])
@pytest.mark.parametrize('universe',[False,True])
def test_missing_or_invalid_response_never_becomes_confirmed_empty(setup_boundary,response,universe,caplog,capsys):
    calls=[]
    client=NS(connection_manager=object())
    client.request_scanner_data=lambda sub:(calls.append(sub),response)[1]
    provider=IbkrScannerProvider(market_data_client=client)
    provider.last_scan_details={'scan_status':'CONFIRMED_EMPTY','returned_rows':0}
    with pytest.raises(RuntimeError,match='scanner response unavailable'):
        resolve(provider) if universe else provider.get_top_gainers(50)
    assert len(calls)==1
    assert provider.last_scan_details['scan_status']=='UNAVAILABLE'
    assert provider.last_scan_details['returned_rows'] is None
    assert '[BROKER_EMPTY]' not in caplog.text
    assert 'local_fallback_source=' not in capsys.readouterr().out


@pytest.mark.parametrize('failure',[TimeoutError,RuntimeError])
def test_raised_unavailability_propagates_unchanged(setup_boundary,failure):
    error=failure('controlled unavailable response')
    def unavailable(sub):raise error
    provider=IbkrScannerProvider(market_data_client=NS(connection_manager=object(),request_scanner_data=unavailable))
    with pytest.raises(failure) as caught:resolve(provider)
    assert caught.value is error
    assert provider.last_scan_details['returned_rows'] is None


@pytest.mark.parametrize('response',['empty','rows','missing','partial','error'])
def test_native_market_provider_universe_completion_chain(setup_boundary,response):
    native=IbkrClient('offline',0,123,0,'LIVE',True)
    native.isConnected=lambda:True
    native.connect=lambda:pytest.fail('connection attempted')
    native.cancelScannerSubscription=lambda req:None
    def deliver(req,*args):
        if response in {'rows','partial'}:
            native.scannerData(req,0,_scanner_item('FIXTURE').contractDetails,'','','','')
        if response in {'empty','rows'}:native.scannerDataEnd(req)
        if response=='error':native.error(req,321,'controlled scanner rejection')
    native.reqScannerSubscription=deliver
    market=MarketDataClient(connection_manager=NS(get_client=lambda:native),allow_direct_connection=False)
    provider=IbkrScannerProvider(market_data_client=market)
    if response in {'empty','rows'}:
        assert resolve(provider)==(['FIXTURE'] if response=='rows' else [])
        assert provider.last_scan_details['scan_status']==('COMPLETE' if response=='rows' else 'CONFIRMED_EMPTY')
    else:
        with pytest.raises((TimeoutError,RuntimeError)):resolve(provider)
        assert provider.last_scan_details['returned_rows'] is None
        assert provider.last_scan_details['scan_status']=='UNAVAILABLE'
    assert market._scanner_request_active is False
    assert native.last_scanner_request['completion_status']==('COMPLETE' if response in {'empty','rows'} else 'UNAVAILABLE')


def test_unverified_native_delegate_cannot_supply_empty_completion(setup_boundary):
    native=IbkrClient('offline',0,123,0,'LIVE',True)
    native.isConnected=lambda:True
    native.ib=NS(reqScannerData=lambda sub:pytest.fail('unverified delegate called'))
    market=MarketDataClient(connection_manager=NS(get_client=lambda:native),allow_direct_connection=False)
    provider=IbkrScannerProvider(market_data_client=market)
    with pytest.raises(RuntimeError,match='unverified delegate'):resolve(provider)
    assert provider.last_scan_details['scan_status']=='UNAVAILABLE'
    assert provider.last_scan_details['returned_rows'] is None
    assert native.last_scanner_request['completion_status']=='UNAVAILABLE'


@pytest.mark.parametrize('rows',[[],(),type('ConfirmedRows',(list,),{})([])])
def test_confirmed_empty_row_sequences_remain_empty(setup_boundary,rows):
    provider=IbkrScannerProvider(market_data_client=NS(connection_manager=object(),request_scanner_data=lambda sub:rows))
    assert resolve(provider)==[]
    assert provider.last_scan_details['scan_status']=='CONFIRMED_EMPTY'
    assert provider.last_scan_details['returned_rows']==0
