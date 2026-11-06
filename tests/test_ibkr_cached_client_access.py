"""Read cached callback facts through the real, non-connecting manager API."""
from types import SimpleNamespace as NS

import pytest

from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
from src.adapters.brokers.ibkr.ibkr_connection_manager import IbkrConnectionConfig, IbkrConnectionManager
from src.config.runtime_config import RunMode
from src.core.active_trade_registry import ActiveTradeRegistry
from src.execution.execution_providers import IbkrExecutionProvider
from src.ibkr.mutation_audit import snapshot as mutations
from test_standalone_pmh_late_fill_protection import forbid_io, no_external_activity, _reset_config


@pytest.mark.parametrize('mode',[RunMode.PAPER,RunMode.READ_ONLY,RunMode.LIVE])
@pytest.mark.parametrize('availability',['present','absent','disconnected'])
def test_cached_read_uses_only_existing_connected_client(monkeypatch,tmp_path,no_external_activity,mode,availability):
    monkeypatch.setenv('IBKR_ORDER_ID_STATE_PATH',str(tmp_path/'synthetic-order-state.json'))
    manager=IbkrConnectionManager(IbkrConnectionConfig('offline',0,999,5,'LIVE',True,mode.value))
    client=IbkrClient('offline',0,999,5,'LIVE',True)
    connected=[availability!='disconnected']
    # Synthetic external connectivity and native callback. Accessor, cache,
    # provider and connection-state owners are not replaced.
    monkeypatch.setattr(client,'isConnected',lambda:connected[0])
    client.orderStatus(71,'Filled',1,0,10.31,0,0,10.31,999,'',0.)
    manager._client=None if availability=='absent' else client
    for name in ('connect','ensure_connected','get_client','_connect_locked'):
        monkeypatch.setattr(manager,name,lambda *a,**kw:pytest.fail('Cache read may not acquire/reconnect'))
    reads=[];read=client.cached_order_status
    def observed(order_id):
        reads.append(order_id)
        return read(order_id)
    monkeypatch.setattr(client,'cached_order_status',observed)
    provider=IbkrExecutionProvider(broker=NS(connection_manager=manager),trade_registry=ActiveTradeRegistry(),run_mode=mode)
    result=provider.cached_order_update('71')
    if availability=='present':
        assert result['filled']==1 and result['avgFillPrice']==10.31
        assert reads==[71] and provider.cached_order_update('999')=={}
        result['filled']=999  # Returned projection cannot mutate callback facts.
        assert provider.cached_order_update('71')['filled']==1
        with pytest.raises(ValueError):provider.cached_order_update('malformed-id')
    else:
        assert result=={} and reads==[]  # Never expose even retained fill facts offline.
    assert manager.existing_client is (None if availability=='absent' else client)
    assert no_external_activity==[] and mutations()==dict(place=0,modify=0,cancel=0)
