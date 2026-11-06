"""Synthetic, filesystem-only controls for the existing capital/storage owners."""
import socket
from types import SimpleNamespace
import pytest
from src.storage.sqlite_store import SQLiteStore
from src.storage.storage_engine import StorageEngine
from src.core.capital_management_authority import CapitalManagementAuthority

@pytest.fixture(autouse=True)
def no_transport(monkeypatch):
    def forbidden(*a, **k): raise AssertionError('EXTERNAL_TRANSPORT_FORBIDDEN')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    yield
    from src.ibkr.mutation_audit import snapshot
    assert not any(snapshot().values()), 'Unexpected order mutation'

def storage(path):
    store = SQLiteStore(str(path)); store.initialize_schema()
    s = StorageEngine.__new__(StorageEngine)
    s._store=store; s.enabled=True; s.backend='sqlite'; s.run_id=None
    return s

def owner(s,scope='synthetic:account-a'):
    return CapitalManagementAuthority(run_mode='PAPER',storage_engine=s,capital_scope=scope)

def admit(o,intent='i1',quantity=1,cap=100):
    return o.evaluate_entry(strategy_id='S',symbol='XYZ',side='BUY',requested_quantity=quantity,
       reference_price=100,account_equity=10000,available_capital=10000,buying_power=10000,
       max_total_exposure=cap,max_position_notional=cap,max_symbol_exposure=cap,
       current_open_positions=0, intent_id=intent)

def test_reservation_survives_restart(tmp_path):
    s=storage(tmp_path/'c.db'); s.initialize_synthetic_capital_scope('synthetic:account-a','PAPER')
    d=admit(owner(s)); assert d.executable
    s._store.close(); s=storage(tmp_path/'c.db')
    assert owner(s).total_reserved_capital==100
    assert not admit(owner(s),'i2').executable
    s._store.close()

def test_original_process_local_state_is_not_restart_authority():
    first=CapitalManagementAuthority(run_mode='PAPER')
    assert admit(first).executable
    restarted=CapitalManagementAuthority(run_mode='PAPER')
    assert restarted.total_reserved_capital==0  # Historical insufficiency remains; no fabricated backfill.

@pytest.fixture
def enrolled(tmp_path):
    s=storage(tmp_path/'c.db')
    s.initialize_synthetic_capital_scope('synthetic:account-a','PAPER')
    yield s
    s._store.close()

def effect(decision,effect='CONVERT',order='entry',cumulative=1,price=100):
    return dict(version=1,mode='PAPER',security_id='S1',symbol='XYZ',relationship_id='R1',
        decision_id=decision.decision_id,order_id=order,native_order_id='N'+order,owner='capital',
        effect=effect,cumulative_quantity=cumulative,delta_quantity=1,average_price=price,delta_price=price)

def test_full_lifecycle_exactly_once_and_detached(enrolled):
    o=owner(enrolled); d=admit(o); original=d.decision_id
    r=list(o.active_reservations.values())[0]; r.remaining_notional=0
    assert o.total_reserved_capital==100
    o.attach_order(decision_id=original,order_id='entry')
    b=effect(d)
    assert o.convert_reservation_to_exposure(decision_id=original,order_id='entry',symbol='XYZ',strategy_id='S',fill_quantity=1,fill_price=100,effect_evidence=b)==100
    assert o.total_reserved_capital==0 and o.total_used_exposure==100
    assert o.convert_reservation_to_exposure(decision_id=original,order_id='entry',symbol='XYZ',strategy_id='S',fill_quantity=1,fill_price=100,effect_evidence=b)==100
    assert o.total_used_exposure==100
    b=effect(d,'RELEASE','exit')
    assert o.release_exposure(symbol='XYZ',quantity=1,price=100,strategy_id='S',effect_evidence=b)==100
    assert o.release_exposure(symbol='XYZ',quantity=1,price=100,strategy_id='S',effect_evidence=b)==100
    assert o.total_used_exposure==0
    assert not admit(o).executable  # Duplicate admission is never new permission.
    rows=enrolled._store.connection.execute("SELECT reason FROM position_lifecycle_transitions WHERE reason_code='ATOMIC_CAPITAL_V1'").fetchall()
    import json
    assert all(json.loads(r[0])['after_version']==json.loads(r[0])['before_version']+1 for r in rows)

def test_quote_reserve_revalidates_and_blocks_tampering(enrolled):
    o=owner(enrolled)
    args=dict(strategy_id='S',symbol='XYZ',side='BUY',requested_quantity=1,reference_price=100,
              account_equity=10000,available_capital=1000,buying_power=1000,intent_id='quote',reserve=False)
    quote=o.evaluate_entry(**args)
    reservation=o.reserve(quote,intent_id='quote')
    assert reservation.notional==100
    assert o.reserve(quote,intent_id='quote').reservation_id==reservation.reservation_id
    assert o.total_reserved_capital==100

def test_stale_quote_rejects(enrolled):
    o=owner(enrolled)
    q=o.evaluate_entry(strategy_id='S',symbol='XYZ',side='BUY',requested_quantity=1,reference_price=100,intent_id='q',reserve=False)
    admit(o,'another',cap=1000)
    with pytest.raises(RuntimeError,match='STALE'):
        o.reserve(q)
    assert o.total_reserved_capital==100

def test_forged_decision_rejects(enrolled):
    q=admit(CapitalManagementAuthority(run_mode='PAPER'))
    with pytest.raises(RuntimeError,match='UNBOUND'):
        owner(enrolled).reserve(q)
    assert owner(enrolled).total_reserved_capital==0

def test_terminal_reservation_release_is_idempotent(enrolled):
    o=owner(enrolled);d=admit(o)
    o.attach_order(decision_id=d.decision_id,order_id='entry')
    assert o.total_reserved_capital==100 # acknowledgement/pending retains ownership
    assert o.release_reservation(decision_id=d.decision_id,order_id='entry',reason='DEFINITIVE_REJECTION')==100
    assert o.release_reservation(decision_id=d.decision_id,order_id='entry',reason='DEFINITIVE_REJECTION')==100
    assert o.total_reserved_capital==0
    assert not o.active_reservations

@pytest.mark.parametrize('method',['attach','convert','release','admit'])
def test_conflicting_identity_never_double_applies(enrolled,method):
    o=owner(enrolled);d=admit(o)
    if method=='attach':
        o.attach_order(decision_id=d.decision_id,order_id='one')
        call=lambda:o.attach_order(decision_id=d.decision_id,order_id='two')
    elif method=='convert':
        o.attach_order(decision_id=d.decision_id,order_id='entry')
        b=effect(d);o.convert_reservation_to_exposure(decision_id=d.decision_id,order_id='entry',symbol='XYZ',strategy_id='S',fill_quantity=1,fill_price=100,effect_evidence=b)
        call=lambda:o.convert_reservation_to_exposure(decision_id=d.decision_id,order_id='entry',symbol='XYZ',strategy_id='S',fill_quantity=1,fill_price=101,effect_evidence=dict(b,average_price=101,delta_price=101))
    elif method=='release':
        o.attach_order(decision_id=d.decision_id,order_id='entry')
        o.convert_reservation_to_exposure(decision_id=d.decision_id,order_id='entry',symbol='XYZ',strategy_id='S',fill_quantity=1,fill_price=100,effect_evidence=effect(d))
        b=effect(d,'RELEASE','exit');o.release_exposure(symbol='XYZ',quantity=1,price=100,strategy_id='S',effect_evidence=b)
        call=lambda:o.release_exposure(symbol='XYZ',quantity=1,price=101,strategy_id='S',effect_evidence=dict(b,average_price=101,delta_price=101))
    else:call=lambda:admit(o,quantity=2)
    before=enrolled.read_capital_state('synthetic:account-a','PAPER')
    with pytest.raises(RuntimeError,match='CONFLICT'):call()
    after=enrolled.read_capital_state('synthetic:account-a','PAPER')
    assert {k:v for k,v in after.items() if k!='pending'}=={k:v for k,v in before.items() if k!='pending'}
    assert after['pending'] is not None

class FailConnection:
    def __init__(self,connection,stage,commit_number=2):self.original=connection;self.stage=stage;self.commits=0;self.commit_number=commit_number
    def __getattr__(self,name):return getattr(self.original,name)
    def execute(self,sql,*args):
        if self.stage in sql:raise OSError('synthetic persistence failure')
        return self.original.execute(sql,*args)
    def executemany(self,sql,*args):
        if self.stage in sql:raise OSError('synthetic persistence failure')
        return self.original.executemany(sql,*args)
    def commit(self):
        self.commits+=1
        if self.stage=='before_commit' and self.commits==self.commit_number:raise OSError('synthetic commit failure')
        self.original.commit()
        if self.stage=='after_commit' and self.commits==self.commit_number:raise OSError('synthetic lost commit response')

@pytest.mark.parametrize('stage',['BEGIN IMMEDIATE','DELETE FROM capital_owner_reservations','INSERT INTO capital_owner_reservations','DELETE FROM capital_owner_exposure','INSERT INTO capital_owner_exposure','UPDATE capital_owner_state SET version','INSERT INTO position_lifecycle_transitions','before_commit','after_commit'])
def test_persistence_boundaries_are_all_or_nothing(enrolled,stage):
    o=owner(enrolled);con=enrolled._store.connection
    enrolled._store.connection=FailConnection(con,stage)
    with pytest.raises(OSError):admit(o)
    enrolled._store.connection=con
    assert o.recovery_failed
    with pytest.raises(RuntimeError,match='INSPECTION'):admit(o,'next')
    state=enrolled.read_capital_state('synthetic:account-a','PAPER')
    count=con.execute("SELECT COUNT(*) FROM position_lifecycle_transitions WHERE reason_code='ATOMIC_CAPITAL_V1'").fetchone()[0]
    assert state['version']==count==(1 if stage=='after_commit' else 0)
    assert owner(enrolled).total_reserved_capital==(100 if stage=='after_commit' else 0)


def test_cross_account_and_concurrent_cap(enrolled):
    from concurrent.futures import ThreadPoolExecutor
    path=enrolled._store.path
    enrolled.initialize_synthetic_capital_scope('synthetic:account-b','PAPER')
    def attempt(n):
        s=storage(path)
        try:return admit(owner(s),str(n)).executable
        finally:s._store.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,[1,2]))
    assert sum(results)==1
    assert owner(enrolled).total_reserved_capital==100
    assert owner(enrolled,'synthetic:account-b').total_reserved_capital==0
    assert admit(owner(enrolled,'synthetic:account-b')).executable

@pytest.mark.parametrize('defect',['unavailable','unenrolled','readonly','future','unfenced'])
def test_no_storage_or_scope_fallback(enrolled,monkeypatch,defect):
    o=owner(enrolled)
    if defect=='unavailable':enrolled.enabled=False
    elif defect=='unenrolled':o.capital_scope='synthetic:missing'
    elif defect=='readonly':enrolled._store.connection.execute('PRAGMA query_only=ON')
    elif defect=='future':
        enrolled._store.connection.execute('UPDATE capital_owner_state SET schema_version=999');enrolled._store.connection.commit()
    else:monkeypatch.setenv('EXECUTION_ENV','PRODUCTION')
    with pytest.raises(RuntimeError):admit(o)
    assert not o._reservations

def test_enrollment_refuses_operator_database(enrolled):
    with pytest.raises(Exception):enrolled.initialize_synthetic_capital_scope('operator-account','LIVE')
    with pytest.raises(Exception):enrolled.initialize_synthetic_capital_scope('synthetic:account-a','PAPER')
    enrolled._store.connection.execute("INSERT INTO runs (run_id) VALUES ('historical')");enrolled._store.connection.commit()
    with pytest.raises(RuntimeError,match='FORBIDDEN'):enrolled.initialize_synthetic_capital_scope('synthetic:new','PAPER')

def test_restart_does_not_adopt_or_clear_recovery(enrolled):
    o=owner(enrolled);admit(o)
    o.recovery_failed=True;o.recovery_failure_reason='unrelated'
    assert o.recover_from_lifecycle([SimpleNamespace(quantity_open=99,entry_avg_price=100,symbol='XYZ')])==0
    assert o.recover_from_open_orders([])==0
    assert o.total_reserved_capital==100 and o.total_used_exposure==0
    assert o.recovery_failed and o.recovery_failure_reason=='unrelated'

def test_corrupt_state_fails_closed(enrolled):
    o=owner(enrolled);admit(o)
    import json
    row=enrolled._store.connection.execute('SELECT reservation_id,payload FROM capital_owner_reservations').fetchone()
    data=json.loads(row[1]);data['remaining_notional']=float('inf')
    enrolled._store.connection.execute('UPDATE capital_owner_reservations SET payload=?',(json.dumps(data),));enrolled._store.connection.commit()
    with pytest.raises(RuntimeError,match='CORRUPT'):admit(o,'next')

def test_projection_failure_no_permission_after_commit(enrolled,monkeypatch):
    o=owner(enrolled);admit(o)
    def fail(*a,**k):raise OSError('synthetic projection refresh failure')
    monkeypatch.setattr(enrolled,'read_capital_state',fail)
    with pytest.raises(OSError):_ = o.total_reserved_capital
    assert not o._reservations # no stale financial cache

@pytest.mark.parametrize('crash',['before','after'])
def test_fresh_process_crash_at_commit(tmp_path,crash):
    import subprocess,sys,os
    path=tmp_path/'restart.db';s=storage(path)
    s.initialize_synthetic_capital_scope('synthetic:account-a','PAPER');s._store.close()
    code="""
import os,sys
from test_atomic_capital_owner import storage,owner,admit
s=storage(sys.argv[1]); original=s._store.connection
class Crash:
 count=0
 def __getattr__(self,k):return getattr(original,k)
 def commit(self):
  self.count+=1
  if self.count==2 and sys.argv[2]=='before':os._exit(71)
  original.commit()
  if self.count==2:os._exit(72)
s._store.connection=Crash();admit(owner(s))
"""
    env=dict(os.environ,PYTHONPATH='tests:tests/offline:.')
    r=subprocess.run([sys.executable,'-c',code,str(path),crash],env=env,timeout=15,capture_output=True)
    assert r.returncode==(71 if crash=='before' else 72)
    s=storage(path)
    assert owner(s).total_reserved_capital==(0 if crash=='before' else 100)
    assert s.read_capital_state('synthetic:account-a','PAPER')['version']==(0 if crash=='before' else 1)
    with pytest.raises(RuntimeError,match='INSPECTION'):admit(owner(s),'after-crash')
    s._store.close()

def test_partial_fill_cumulative_progress_and_release_remainder(enrolled):
    o=owner(enrolled);d=admit(o,quantity=2,cap=1000)
    o.attach_order(decision_id=d.decision_id,order_id='entry')
    for cumulative in (1,2):
        o.convert_reservation_to_exposure(decision_id=d.decision_id,order_id='entry',symbol='XYZ',strategy_id='S',fill_quantity=1,fill_price=100,effect_evidence=effect(d,cumulative=cumulative))
        assert o.total_used_exposure==100*cumulative
        assert o.total_reserved_capital==100*(2-cumulative)
    assert o.release_reservation(decision_id=d.decision_id)==0
    assert o.total_used_exposure==200

@pytest.mark.parametrize('change',[{'cumulative_quantity':2,'delta_quantity':2},{'cumulative_quantity':0},{'decision_id':'foreign'},{'native_order_id':'foreign'}])
def test_cumulative_or_binding_conflict_quarantines(enrolled,change):
    o=owner(enrolled);d=admit(o,quantity=3,cap=1000)
    o.attach_order(decision_id=d.decision_id,order_id='entry')
    o.convert_reservation_to_exposure(decision_id=d.decision_id,order_id='entry',symbol='XYZ',strategy_id='S',fill_quantity=1,fill_price=100,effect_evidence=effect(d))
    b=dict(effect(d,cumulative=2),**change)
    with pytest.raises((ValueError,RuntimeError)):
        o.convert_reservation_to_exposure(decision_id=d.decision_id,order_id='entry',symbol='XYZ',strategy_id='S',fill_quantity=b['delta_quantity'],fill_price=100,effect_evidence=b)
    assert owner(enrolled).total_used_exposure==100
    assert owner(enrolled).total_reserved_capital==200

def test_release_cannot_borrow_unconverted_identity(enrolled):
    o=owner(enrolled);d=admit(o)
    with pytest.raises(RuntimeError,match='WITHOUT_OWNED'):
        o.release_exposure(symbol='XYZ',quantity=1,price=100,strategy_id='S',effect_evidence=effect(d,'RELEASE','exit'))
    assert o.total_reserved_capital==100

@pytest.mark.parametrize('stage',['DELETE FROM capital_owner_execution','INSERT INTO capital_owner_execution','INSERT INTO capital_owner_exposure','INSERT INTO position_lifecycle_transitions','before_commit','after_commit'])
def test_conversion_boundaries_preserve_full_state_and_receipt(enrolled,stage):
    o=owner(enrolled);d=admit(o);o.attach_order(decision_id=d.decision_id,order_id='entry')
    con=enrolled._store.connection;before=enrolled.read_capital_state('synthetic:account-a','PAPER')
    enrolled._store.connection=FailConnection(con,stage)
    with pytest.raises(OSError):
        o.convert_reservation_to_exposure(decision_id=d.decision_id,order_id='entry',symbol='XYZ',strategy_id='S',fill_quantity=1,fill_price=100,effect_evidence=effect(d))
    enrolled._store.connection=con
    after=enrolled.read_capital_state('synthetic:account-a','PAPER')
    if stage=='after_commit':
        assert owner(enrolled).total_used_exposure==100 and owner(enrolled).total_reserved_capital==0
        assert len(after['progress'])==1 and after['version']==before['version']+1
    else:
        assert {k:v for k,v in after.items() if k!='pending'}=={k:v for k,v in before.items() if k!='pending'}

@pytest.mark.parametrize('mode',['SIM','READ_ONLY','LIVE'])
def test_modes_cannot_silently_enroll_or_gain_permission(enrolled,mode):
    if mode=='SIM':
        enrolled.initialize_synthetic_capital_scope('synthetic:sim',mode)
        o=CapitalManagementAuthority(run_mode=mode,storage_engine=enrolled,capital_scope='synthetic:sim')
        assert admit(o).executable
    else:
        o=CapitalManagementAuthority(run_mode=mode,storage_engine=enrolled,capital_scope='synthetic:account-a')
        with pytest.raises(RuntimeError):admit(o)
    assert owner(enrolled).total_reserved_capital==0

def test_future_base_schema_refused_before_initializer_mutates(enrolled):
    path=enrolled._store.path
    enrolled._store.connection.execute('INSERT INTO schema_meta VALUES (999,?)',('synthetic',));enrolled._store.connection.commit()
    s=SQLiteStore(path)
    try:
        with pytest.raises(RuntimeError,match='FUTURE'):s.initialize_schema()
        assert s.connection.execute('SELECT MAX(version) FROM schema_meta').fetchone()[0]==999
    finally:s.close()

def test_explicit_scope_rejects_unfenced_initializer(enrolled,monkeypatch):
    monkeypatch.setenv('EXECUTION_ENV','PRODUCTION')
    other=SQLiteStore(enrolled._store.path)
    try:
        with pytest.raises(RuntimeError,match='UNFENCED'):other.initialize_schema()
    finally:other.close()

def test_conflicting_cumulative_valuation_rejects(enrolled):
    o=owner(enrolled);d=admit(o,quantity=2,cap=1000)
    o.attach_order(decision_id=d.decision_id,order_id='entry')
    o.convert_reservation_to_exposure(decision_id=d.decision_id,order_id='entry',symbol='XYZ',strategy_id='S',fill_quantity=1,fill_price=100,effect_evidence=effect(d))
    b=dict(effect(d,cumulative=2),delta_price=101)
    with pytest.raises(RuntimeError,match='VALUATION'):
        o.convert_reservation_to_exposure(decision_id=d.decision_id,order_id='entry',symbol='XYZ',strategy_id='S',fill_quantity=1,fill_price=101,effect_evidence=b)
    assert owner(enrolled).total_used_exposure==100

def test_historical_audit_without_run_cannot_initialize(tmp_path):
    s=storage(tmp_path/'old.db')
    s._store.connection.execute("INSERT INTO capital_audit_events (event_id) VALUES ('historical')");s._store.connection.commit()
    with pytest.raises(RuntimeError,match='NONFRESH'):
        s.initialize_synthetic_capital_scope('synthetic:account-a','PAPER')
    assert s._store.connection.execute("SELECT COUNT(*) FROM capital_audit_events").fetchone()[0]==1
    assert not s._store.connection.execute("SELECT 1 FROM sqlite_master WHERE name='capital_owner_state'").fetchone()
    s._store.close()

@pytest.mark.parametrize('tamper',['atomic','version','schema'])
def test_corrupt_duplicate_receipt_cannot_grant_result(enrolled,tamper):
    import json
    o=owner(enrolled);admit(o)
    row=enrolled._store.connection.execute("SELECT transition_id,reason FROM position_lifecycle_transitions WHERE reason_code='ATOMIC_CAPITAL_V1'").fetchone()
    data=json.loads(row[1])
    if tamper=='atomic':data['atomic_capital_only']=False
    elif tamper=='version':data['after_version']=999
    else:data['schema']=True
    enrolled._store.connection.execute('UPDATE position_lifecycle_transitions SET reason=? WHERE transition_id=?',(json.dumps(data),row[0]));enrolled._store.connection.commit()
    with pytest.raises(RuntimeError,match='CONFLICT'):admit(o)
    assert owner(enrolled).total_reserved_capital==100

@pytest.mark.parametrize('defect',['remaining','duplicate','identity','progress'])
def test_corrupt_owner_state_not_authoritative(enrolled,defect):
    import json
    o=owner(enrolled);d=admit(o)
    o.attach_order(decision_id=d.decision_id,order_id='entry')
    o.convert_reservation_to_exposure(decision_id=d.decision_id,order_id='entry',symbol='XYZ',strategy_id='S',fill_quantity=1,fill_price=100,effect_evidence=effect(d))
    con=enrolled._store.connection
    row=con.execute('SELECT reservation_id,payload FROM capital_owner_reservations').fetchone();v=json.loads(row[1])
    if defect=='remaining':v['remaining_quantity']=99
    elif defect=='identity':v['effect_identity']['decision_id']='wrong'
    elif defect=='duplicate':
        v['reservation_id']='duplicate'
        con.execute('INSERT INTO capital_owner_reservations VALUES (?,?,?)',('synthetic:account-a','duplicate',json.dumps(v)))
    else:
        p=con.execute('SELECT identity,payload FROM capital_owner_execution').fetchone();b=json.loads(p[1]);b['cumulative_quantity']=-1
        con.execute('UPDATE capital_owner_execution SET payload=? WHERE identity=?',(json.dumps(b),p[0]))
    if defect in {'remaining','identity'}:con.execute('UPDATE capital_owner_reservations SET payload=? WHERE reservation_id=?',(json.dumps(v),row[0]))
    con.commit()
    with pytest.raises((ValueError,RuntimeError)):admit(o,'next')

def test_actual_execution_startup_loads_without_rebuilding(enrolled):
    from src.execution.execution_engine import ExecutionEngine
    from src.execution.startup_recovery_authority import RecoveryState
    o=owner(enrolled);admit(o)
    e=ExecutionEngine.__new__(ExecutionEngine)
    e.startup_recovery_state=RecoveryState.RECOVERY_COMPLETE
    e._trade_lifecycle_engine=None;e.post_fill_lifecycle=SimpleNamespace(_trades={})
    e.strategy_allocation_authority=SimpleNamespace(recover_from_lifecycle=lambda trades:None)
    e.capital_authority=o;e._provider=None;e.run_mode=SimpleNamespace(value='PAPER')
    e._recover_capital_state()
    assert e.capital_authority.total_reserved_capital==100
    assert e.capital_authority.total_used_exposure==0


@pytest.mark.parametrize('number',[1,2,3])
@pytest.mark.parametrize('moment',['before_commit','after_commit'])
def test_each_commit_failure_preserves_restart_quarantine(enrolled,number,moment):
    o=owner(enrolled);connection=enrolled._store.connection
    enrolled._store.connection=FailConnection(connection,moment,number)
    with pytest.raises(OSError):admit(o)
    enrolled._store.connection=connection
    restarted=owner(enrolled)
    assert restarted.total_reserved_capital==(100 if number==3 or (number==2 and moment=='after_commit') else 0)
    with pytest.raises(RuntimeError,match='INSPECTION'):admit(owner(enrolled),'new-intent')
    assert o.recovery_failed
