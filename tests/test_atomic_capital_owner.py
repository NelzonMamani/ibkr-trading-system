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

def enroll(s,scope='synthetic:account-a',mode='PAPER'):
    # Explicit test enroller retains the issued capability, never re-reads it.
    writer=s.initialize_synthetic_capital_scope(scope,mode)
    if not hasattr(s,'_fixture_writers'):
        s._fixture_writers={}
    s._fixture_writers[scope]=writer
    return writer

def owner(s,scope='synthetic:account-a',mode='PAPER'):
    writer=getattr(s,'_fixture_writers',{}).pop(scope,None)
    return CapitalManagementAuthority(run_mode=mode,storage_engine=s,capital_scope=scope,capital_writer=writer)

def admit(o,intent='i1',quantity=1,cap=100):
    return o.evaluate_entry(strategy_id='S',symbol='XYZ',side='BUY',requested_quantity=quantity,
       reference_price=100,account_equity=10000,available_capital=10000,buying_power=10000,
       max_total_exposure=cap,max_position_notional=cap,max_symbol_exposure=cap,
       current_open_positions=0, intent_id=intent)

def test_reservation_survives_restart(tmp_path):
    s=storage(tmp_path/'c.db'); enroll(s)
    d=admit(owner(s)); assert d.executable
    s._store.close(); s=storage(tmp_path/'c.db')
    assert owner(s).total_reserved_capital==100
    with pytest.raises(RuntimeError,match='SESSION_REQUIRED'):admit(owner(s),'i2')
    s._store.close()

def test_original_process_local_state_is_not_restart_authority():
    first=CapitalManagementAuthority(run_mode='PAPER')
    assert admit(first).executable
    restarted=CapitalManagementAuthority(run_mode='PAPER')
    assert restarted.total_reserved_capital==0  # Historical insufficiency remains; no fabricated backfill.

@pytest.fixture
def enrolled(tmp_path):
    s=storage(tmp_path/'c.db')
    enroll(s)
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
    rows=enrolled._store.connection.execute("SELECT reason FROM position_lifecycle_transitions WHERE reason_code='ATOMIC_CAPITAL_V2'").fetchall()
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
    with pytest.raises((OSError,RuntimeError),match='synthetic|PERSISTENCE_UNKNOWN'):admit(o)
    enrolled._store.connection=con
    assert o.recovery_failed
    with pytest.raises(RuntimeError,match='INSPECTION'):admit(o,'next')
    state=enrolled.read_capital_state('synthetic:account-a','PAPER')
    count=con.execute("SELECT COUNT(*) FROM position_lifecycle_transitions WHERE reason_code='ATOMIC_CAPITAL_V2'").fetchone()[0]
    assert state['version']==count==(1 if stage=='after_commit' else 0)
    assert owner(enrolled).total_reserved_capital==(100 if stage=='after_commit' else 0)


def test_cross_account_and_concurrent_cap(enrolled,tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    path=tmp_path/'concurrent.db'; ready=Event(); attempted=Event()
    def authorized():
        s=storage(path)
        try:
            enroll(s);o=owner(s);ready.set()
            assert attempted.wait(10)
            return admit(o).executable
        finally:s._store.close()
    def unauthorized():
        assert ready.wait(10)
        s=storage(path)
        try:
            before=s.read_capital_state('synthetic:account-a','PAPER')
            with pytest.raises(RuntimeError,match='SESSION_REQUIRED'):admit(owner(s),'other')
            assert s.read_capital_state('synthetic:account-a','PAPER')==before
            return False
        finally:s._store.close();attempted.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(authorized);second=pool.submit(unauthorized)
        assert first.result() and not second.result()
    o=owner(enrolled);assert admit(o).executable
    enroll(enrolled,'synthetic:account-b')
    other=owner(enrolled,'synthetic:account-b')
    assert other.total_reserved_capital==0 and admit(other).executable
    assert other.total_reserved_capital==100 and o.total_reserved_capital==100

@pytest.mark.parametrize('defect',['unavailable','unenrolled','readonly','future','unfenced'])
def test_no_storage_or_scope_fallback(enrolled,monkeypatch,defect):
    o=owner(enrolled)
    if defect=='unavailable':enrolled.enabled=False
    elif defect=='unenrolled':o=CapitalManagementAuthority(run_mode='PAPER',storage_engine=enrolled,capital_scope='synthetic:missing')
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
    s._store.close()
    code="""
import os,sys
from test_atomic_capital_owner import storage,owner,admit,enroll
s=storage(sys.argv[1]); enroll(s); original=s._store.connection
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
    env=dict(os.environ,PYTHONPATH=os.pathsep.join(('tests','tests/offline','.')))
    r=subprocess.run([sys.executable,'-c',code,str(path),crash],env=env,timeout=15,capture_output=True)
    assert r.returncode==(71 if crash=='before' else 72)
    s=storage(path)
    assert owner(s).total_reserved_capital==(0 if crash=='before' else 100)
    assert s.read_capital_state('synthetic:account-a','PAPER')['version']==(0 if crash=='before' else 1)
    with pytest.raises(RuntimeError,match='SESSION_REQUIRED'):admit(owner(s),'after-crash')
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
        enroll(enrolled,'synthetic:sim',mode)
        o=owner(enrolled,'synthetic:sim',mode)
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
        enroll(s)
    assert s._store.connection.execute("SELECT COUNT(*) FROM capital_audit_events").fetchone()[0]==1
    assert not s._store.connection.execute("SELECT 1 FROM sqlite_master WHERE name='capital_owner_state'").fetchone()
    s._store.close()

@pytest.mark.parametrize('tamper',['atomic','version','schema'])
def test_corrupt_duplicate_receipt_cannot_grant_result(enrolled,tamper):
    import json
    o=owner(enrolled);admit(o)
    row=enrolled._store.connection.execute("SELECT transition_id,reason FROM position_lifecycle_transitions WHERE reason_code='ATOMIC_CAPITAL_V2'").fetchone()
    data=json.loads(row[1])
    if tamper=='atomic':data['atomic_capital_only']=False
    elif tamper=='version':data['after_version']=999
    else:data['schema']=True
    enrolled._store.connection.execute('UPDATE position_lifecycle_transitions SET reason=? WHERE transition_id=?',(json.dumps(data),row[0]));enrolled._store.connection.commit()
    with pytest.raises(RuntimeError,match='CONFLICT|INTEGRITY'):admit(o)
    with pytest.raises(RuntimeError,match='INTEGRITY'):_=owner(enrolled).total_reserved_capital
    assert enrolled._store.connection.execute('SELECT COUNT(*) FROM capital_owner_reservations').fetchone()[0]==1

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
    e.strategy_allocation_authority=SimpleNamespace(recover_from_lifecycle=lambda trades:pytest.fail('Allocation replay forbidden for enrolled capital load'))
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
    with pytest.raises(RuntimeError,match='SESSION_REQUIRED'):admit(owner(enrolled),'new-intent')
    assert o.recovery_failed

def test_lost_completion_and_lost_quarantine_is_explicit_remaining_boundary(enrolled):
    o=owner(enrolled);connection=enrolled._store.connection
    class LostObservation(FailConnection):
        def commit(self):
            self.commits+=1
            if self.commits==4:raise OSError('synthetic quarantine persistence failure')
            self.original.commit()
            if self.commits==3:raise OSError('synthetic completion response loss')
    enrolled._store.connection=LostObservation(connection,'none')
    with pytest.raises(RuntimeError,match='QUARANTINE_PERSISTENCE_UNKNOWN'):admit(o,cap=500)
    enrolled._store.connection=connection
    assert o.recovery_failed
    with pytest.raises(RuntimeError,match='INSPECTION'):admit(o,'same-process',cap=500)
    # Counterexample is retained, NOT operational recovery certification:
    # capital state+receipt prove100, but no durable failure-observation latch.
    assert owner(enrolled).total_reserved_capital==100
    assert enrolled.read_capital_state('synthetic:account-a','PAPER')['pending'] is None


def test_actual_execution_pending_gate_precedes_other_recovery(enrolled):
    from src.execution.execution_engine import ExecutionEngine
    from src.execution.startup_recovery_authority import RecoveryState
    o=owner(enrolled);admit(o)
    enrolled._store.connection.execute("UPDATE capital_owner_state SET pending='retained-interruption'")
    enrolled._store.connection.commit()
    def forbidden(*a,**k):pytest.fail('No unrelated recovery or inventory permitted')
    e=ExecutionEngine.__new__(ExecutionEngine);e.startup_recovery_state=RecoveryState.RECOVERY_COMPLETE
    e.capital_authority=owner(enrolled);e._provider=SimpleNamespace(get_open_orders=forbidden)
    e.strategy_allocation_authority=SimpleNamespace(recover_from_lifecycle=forbidden)
    e._trade_lifecycle_engine=SimpleNamespace(get_open_lifecycle_trades=forbidden)
    flags=[];e.post_fill_lifecycle=SimpleNamespace(set_startup_recovery_complete=flags.append)
    e._recover_capital_state()
    assert e.startup_recovery_state==RecoveryState.RECOVERY_FAILED
    assert e._failsafe_block_new_entries and flags==[False]
    assert e.capital_authority.total_reserved_capital==100
    assert enrolled.read_capital_state('synthetic:account-a','PAPER')['pending']=='retained-interruption'

# Policy-boundary assessment: these controls preserve the original double-failure
# test above. They do not add a resolver, clearing path, or production policy.
@pytest.fixture
def restart_histories(tmp_path, monkeypatch):
    import src.core.capital_management_authority as capital_module
    import src.storage.sqlite_store as sqlite_module
    monkeypatch.setattr(capital_module, 'uuid4', lambda: SimpleNamespace(hex='fixed-offline-identity'))
    monkeypatch.setattr(capital_module.CapitalManagementAuthority, '_now', staticmethod(lambda:'2026-11-06T12:00:00+00:00'))
    monkeypatch.setattr(sqlite_module, 'now_iso', lambda:'2026-11-06T12:00:00+00:00')
    monkeypatch.setattr(sqlite_module,'uuid4',lambda:SimpleNamespace(hex='fixed-offline-writer'))
    result={}
    for history in ('returned','lost_ack','lost_ack_and_quarantine'):
        s=storage(tmp_path/(history+'.db'))
        enroll(s)
        original=s._store.connection
        class Fault(FailConnection):
            def commit(self):
                self.commits+=1
                if history=='lost_ack_and_quarantine' and self.commits==4:
                    raise OSError('synthetic quarantine persistence failure')
                self.original.commit()
                if history!='returned' and self.commits==3:
                    raise OSError('synthetic completion response loss')
        s._store.connection=Fault(original,'none')
        o=owner(s)
        if history=='returned':
            assert admit(o,cap=500).executable
        elif history=='lost_ack':
            with pytest.raises(OSError,match='completion response loss'):admit(o,cap=500)
            assert o.recovery_failed
        else:
            with pytest.raises(RuntimeError,match='QUARANTINE_PERSISTENCE_UNKNOWN'):admit(o,cap=500)
            assert o.recovery_failed
        s._store.connection=original
        result[history]={'path':s._store.path,'dump':'\n'.join(original.iterdump())}
        s._store.close()
    return result


def _fresh_restart_assessment(path, action):
    import json,os,subprocess,sys
    code=r'''
import json,sys
from test_atomic_capital_owner import storage,owner,admit
s=storage(sys.argv[1]);o=owner(s)
state=s.read_capital_state('synthetic:account-a','PAPER')
row=s._store.connection.execute('SELECT reason FROM position_lifecycle_transitions WHERE transition_id=?',
    ('capital-atomic-v2:synthetic:account-a:'+s._store.connection.execute('SELECT last_operation FROM capital_owner_state').fetchone()[0],)).fetchone()
receipt=json.loads(row[0])
before='\n'.join(s._store.connection.iterdump())
out={'version_before':state['version'],'reserved_before':owner(s).total_reserved_capital,
     'pending':state['pending'] is not None,'receipt_version':receipt['after_version'],
     'atomic_capital_only':receipt['atomic_capital_only']}
action=sys.argv[2]
try:
 if action=='inspect':
  out['outcome']='READ_ONLY_CAPITAL_COMMITTED'
 elif action=='unavailable':
  s.enabled=False
  admit(o,'new-intent',cap=500)
 elif action=='duplicate':
  d=admit(o,cap=500);out.update(outcome=d.reason,allowed=d.executable)
 else:
  d=admit(o,'new-intent',cap=500);out.update(outcome=d.reason,allowed=d.executable)
except RuntimeError as e:
 out.update(outcome=str(e),allowed=False)
s.enabled=True
out.update(version_after=s.read_capital_state('synthetic:account-a','PAPER')['version'],
 reserved_after=owner(s).total_reserved_capital,
 unchanged=before=='\n'.join(s._store.connection.iterdump()))
s._store.close()
print('RESTART_ASSESSMENT='+json.dumps(out,sort_keys=True))
'''
    env=dict(os.environ,PYTHONPATH=os.pathsep.join(('tests','tests/offline','.')))
    r=subprocess.run([sys.executable,'-c',code,str(path),action],env=env,timeout=15,capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    lines=[s for s in r.stdout.splitlines() if s.startswith('RESTART_ASSESSMENT=')]
    assert len(lines)==1
    return json.loads(lines[0].split('=',1)[1])


def test_same_retained_sql_cannot_prove_caller_acknowledgement(restart_histories):
    assert restart_histories['returned']['dump']==restart_histories['lost_ack_and_quarantine']['dump']
    assert restart_histories['returned']['dump']!=restart_histories['lost_ack']['dump']


@pytest.mark.parametrize('history',['returned','lost_ack','lost_ack_and_quarantine'])
def test_fresh_process_establishes_capital_outcome_read_only(restart_histories,history):
    facts=_fresh_restart_assessment(restart_histories[history]['path'],'inspect')
    assert facts['atomic_capital_only'] is True
    assert facts['version_before']==facts['receipt_version']==facts['version_after']==1
    assert facts['reserved_before']==facts['reserved_after']==100
    assert facts['unchanged'] and facts['outcome']=='READ_ONLY_CAPITAL_COMMITTED'
    assert facts['pending']==(history=='lost_ack')


@pytest.mark.parametrize('history',['returned','lost_ack','lost_ack_and_quarantine'])
def test_fresh_duplicate_never_reapplies_capital_or_grants_permission(restart_histories,history):
    facts=_fresh_restart_assessment(restart_histories[history]['path'],'duplicate')
    assert not facts['allowed']
    assert facts['reserved_before']==facts['reserved_after']==100
    assert facts['version_before']==facts['version_after']==1
    assert facts['outcome']=='CAPITAL_WRITER_SESSION_REQUIRED'


@pytest.mark.parametrize('history',['returned','lost_ack_and_quarantine'])
def test_unavailable_storage_after_fresh_restart_blocks_without_writes(restart_histories,history):
    facts=_fresh_restart_assessment(restart_histories[history]['path'],'unavailable')
    assert not facts['allowed'] and facts['outcome']=='CAPITAL_STORAGE_UNAVAILABLE'
    assert facts['unchanged'] and facts['version_before']==facts['version_after']==1
    assert facts['reserved_before']==facts['reserved_after']==100


def test_fresh_restart_observed_admission_difference(restart_histories):
    retained=_fresh_restart_assessment(restart_histories['lost_ack']['path'],'new')
    absent=_fresh_restart_assessment(restart_histories['lost_ack_and_quarantine']['path'],'new')
    assert not retained['allowed'] and retained['reserved_after']==100
    assert not absent['allowed'] and absent['reserved_after']==100
    assert absent['version_before']==absent['version_after']==1


def test_required_restart_veto_remains_unresolved_after_double_failure(restart_histories):
    facts=_fresh_restart_assessment(restart_histories['lost_ack_and_quarantine']['path'],'new')
    assert not facts['allowed'], 'Unresolved caller/other-owner effects must not authorize fresh admission'
    assert facts['reserved_after']==100

def test_caller_token_fields_cannot_regrant_writer(enrolled):
    o=owner(enrolled);assert admit(o,cap=500).executable
    token=o._capital_writer
    try:
        token._claimed=False
        token._owner=None
    except AttributeError:
        pass  # Opaque handles contain no authoritative caller-mutable fields.
    before=enrolled.read_capital_state('synthetic:account-a','PAPER')
    with pytest.raises(RuntimeError,match='WRITER'):
        CapitalManagementAuthority(run_mode='PAPER',storage_engine=enrolled,
            capital_scope='synthetic:account-a',capital_writer=token)
    assert enrolled.read_capital_state('synthetic:account-a','PAPER')==before

@pytest.mark.parametrize('action',['different','duplicate','release'])
def test_second_owner_cannot_write_or_poison_current_session(enrolled,action):
    current=owner(enrolled);assert admit(current,cap=500).executable
    reader=owner(enrolled)
    before='\n'.join(enrolled._store.connection.iterdump())
    with pytest.raises(RuntimeError,match='WRITER_SESSION_REQUIRED'):
        if action=='release':reader.release_reservation(decision_id=list(current.active_reservations.values())[0].decision_id)
        else:admit(reader,'i1' if action=='duplicate' else 'other',cap=500)
    assert '\n'.join(enrolled._store.connection.iterdump())==before
    assert reader.total_reserved_capital==100
    assert admit(current,'current-next',cap=500).executable
    assert current.total_reserved_capital==200

@pytest.mark.parametrize('bad',['string','dict','unissued','borrowed','copy_owner'])
def test_public_identity_or_second_actor_cannot_mint_authority(enrolled,bad):
    from copy import copy
    from src.storage.sqlite_store import _CapitalWriter
    current=owner(enrolled);admit(current,cap=500)
    writer_id=enrolled.read_capital_state('synthetic:account-a','PAPER')['writer_id']
    token={'string':writer_id,'dict':{'writer_id':writer_id},'unissued':_CapitalWriter(),
           'borrowed':current._capital_writer}.get(bad)
    before='\n'.join(enrolled._store.connection.iterdump())
    with pytest.raises(RuntimeError,match='WRITER'):
        if bad=='copy_owner':admit(copy(current),'another',cap=500)
        else:CapitalManagementAuthority(run_mode='PAPER',storage_engine=enrolled,
                capital_scope='synthetic:account-a',capital_writer=token)
    assert '\n'.join(enrolled._store.connection.iterdump())==before

@pytest.mark.parametrize('action',['copy','deepcopy','pickle','field'])
def test_writer_token_is_opaque_and_nontransferable(enrolled,action):
    import copy,pickle
    current=owner(enrolled);token=current._capital_writer
    with pytest.raises((TypeError,AttributeError)):
        if action=='copy':copy.copy(token)
        elif action=='deepcopy':copy.deepcopy(token)
        elif action=='pickle':pickle.dumps(token)
        else:setattr(token,'writer_id','caller-asserted')
    assert admit(current).executable


def test_dead_owner_does_not_release_or_transfer_session(enrolled):
    import gc
    current=owner(enrolled);admit(current,cap=500);token=current._capital_writer
    del current;gc.collect()
    before='\n'.join(enrolled._store.connection.iterdump())
    with pytest.raises(RuntimeError,match='IDENTITY_CONFLICT'):
        CapitalManagementAuthority(run_mode='PAPER',storage_engine=enrolled,
                capital_scope='synthetic:account-a',capital_writer=token)
    assert '\n'.join(enrolled._store.connection.iterdump())==before


def test_second_store_or_reenrollment_cannot_take_over(enrolled):
    current=owner(enrolled);assert admit(current,cap=500).executable
    other=storage(enrolled._store.path)
    before='\n'.join(enrolled._store.connection.iterdump())
    try:
        with pytest.raises(RuntimeError,match='SESSION_REQUIRED'):
            CapitalManagementAuthority(run_mode='PAPER',storage_engine=other,
                capital_scope='synthetic:account-a',capital_writer=current._capital_writer)
        with pytest.raises(Exception):other.initialize_synthetic_capital_scope('synthetic:account-a','PAPER')
        assert '\n'.join(other._store.connection.iterdump())==before
        assert owner(other).total_reserved_capital==100
    finally:other._store.close()
    assert admit(current,'same-authorized-writer',cap=500).executable


def test_restored_startup_blocks_even_when_pending_is_absent(enrolled):
    from src.execution.execution_engine import ExecutionEngine
    from src.execution.startup_recovery_authority import RecoveryState
    current=owner(enrolled);admit(current)
    def forbidden(*a,**k):pytest.fail('Other owners/provider must not be replayed')
    e=ExecutionEngine.__new__(ExecutionEngine);e.startup_recovery_state=RecoveryState.RECOVERY_COMPLETE
    e.capital_authority=owner(enrolled);e._provider=SimpleNamespace(get_open_orders=forbidden)
    e.strategy_allocation_authority=SimpleNamespace(recover_from_lifecycle=forbidden)
    e._trade_lifecycle_engine=SimpleNamespace(get_open_lifecycle_trades=forbidden)
    flags=[];e.post_fill_lifecycle=SimpleNamespace(set_startup_recovery_complete=flags.append)
    e._recover_capital_state()
    assert e.startup_recovery_state==RecoveryState.RECOVERY_FAILED
    assert e.startup_recovery_result.reason=='CAPITAL_RESTART_ADMISSION_BLOCKED'
    assert e._failsafe_block_new_entries and flags==[False]
    assert e.capital_authority.total_reserved_capital==100
    assert enrolled.read_capital_state('synthetic:account-a','PAPER')['pending'] is None


def test_durable_writer_identity_mismatch_cannot_rebind(enrolled):
    current=owner(enrolled)
    enrolled._store.connection.execute("UPDATE capital_owner_state SET writer_id='another-session'")
    enrolled._store.connection.commit()
    before='\n'.join(enrolled._store.connection.iterdump())
    with pytest.raises(RuntimeError,match='WRITER_SCOPE_CONFLICT'):admit(current)
    assert '\n'.join(enrolled._store.connection.iterdump())==before
    assert enrolled.read_capital_state('synthetic:account-a','PAPER')['version']==0


def test_writer_bound_to_database_identity(enrolled,tmp_path):
    current=owner(enrolled);admit(current,cap=500)
    other=storage(tmp_path/'other.db');other._store.close()
    path=enrolled._store.path;enrolled._store.path=str(tmp_path/'other.db')
    before='\n'.join(enrolled._store.connection.iterdump())
    try:
        with pytest.raises(RuntimeError,match='IDENTITY_CONFLICT'):admit(current,'next',cap=500)
    finally:enrolled._store.path=path
    assert '\n'.join(enrolled._store.connection.iterdump())==before


@pytest.mark.skipif(not hasattr(__import__('os'),'fork'),reason='Actual inherited-handle fork control is POSIX only; fresh spawn tested on Windows')
def test_inherited_writer_fails_before_fork_child_database_access(enrolled):
    import multiprocessing
    current=owner(enrolled);admit(current,cap=500)
    context=multiprocessing.get_context('fork');read,write=context.Pipe(duplex=False)
    def child():
        class NoDatabase:
            def __getattr__(self,name):raise AssertionError('Fork child touched inherited SQLite')
        enrolled._store.connection=NoDatabase()
        try:admit(current,'fork-child',cap=500)
        except RuntimeError as e:write.send(str(e))
        finally:write.close()
    process=context.Process(target=child);process.start();write.close()
    try:
        process.join(5)
        assert not process.is_alive()
        assert process.exitcode==0 and read.poll(1)
        assert read.recv()=='CAPITAL_WRITER_SESSION_REQUIRED'
    finally:
        if process.is_alive():process.terminate();process.join(2)
        assert not process.is_alive();read.close();process.close()
    assert current.total_reserved_capital==100


def test_legacy_schema_one_inspection_never_enrolls_writer(enrolled):
    import json
    current=owner(enrolled);admit(current)
    con=enrolled._store.connection
    state=enrolled.read_capital_state('synthetic:account-a','PAPER')
    row=con.execute("SELECT transition_id,reason FROM position_lifecycle_transitions WHERE reason_code='ATOMIC_CAPITAL_V2'").fetchone()
    record=json.loads(row[1]);record['schema']=1;record.pop('writer_id')
    state['schema_version']=1
    record['state_hash']=SQLiteStore._capital_state_hash('synthetic:account-a','PAPER',1,state)
    # Construct retained legacy format only in isolated fixture, never migrate it.
    con.executescript("""
      CREATE TABLE legacy_scope AS SELECT scope,mode,1 AS schema_version,version,
        'SYNTHETIC_ONLY_V1' AS fence,pending,last_operation FROM capital_owner_state;
      DROP TABLE capital_owner_state;
      ALTER TABLE legacy_scope RENAME TO capital_owner_state;
      DROP TABLE capital_synthetic_database;
      CREATE TABLE capital_synthetic_database (version INTEGER PRIMARY KEY CHECK(version=1));
      INSERT INTO capital_synthetic_database VALUES (1);
    """)
    con.execute('UPDATE position_lifecycle_transitions SET transition_id=?,reason_code=?,reason=? WHERE transition_id=?',
        (row[0].replace('capital-atomic-v2:','capital-atomic-v1:'),'ATOMIC_CAPITAL_V1',json.dumps(record,sort_keys=True),row[0]))
    con.commit()
    other=storage(enrolled._store.path)
    try:
        before='\n'.join(other._store.connection.iterdump())
        assert owner(other).total_reserved_capital==100
        with pytest.raises(RuntimeError,match='SESSION_REQUIRED'):admit(owner(other),'new',cap=500)
        with pytest.raises(RuntimeError,match='SCHEMA_UNSUPPORTED'):
            other.initialize_synthetic_capital_scope('synthetic:account-a','PAPER')
        assert '\n'.join(other._store.connection.iterdump())==before
    finally:other._store.close()

def test_scoped_reader_cannot_demote_to_legacy_authority(enrolled):
    current=owner(enrolled);admit(current,cap=500)
    reader=owner(enrolled)
    try:reader.capital_scope=None
    except AttributeError:pass
    before='\n'.join(enrolled._store.connection.iterdump())
    with pytest.raises(RuntimeError,match='SESSION|INSPECTION'):admit(reader,'demoted',cap=500)
    assert '\n'.join(enrolled._store.connection.iterdump())==before

@pytest.mark.parametrize('disabled',[False,True])
def test_enrolled_store_cannot_be_selected_as_legacy(enrolled,disabled):
    current=owner(enrolled);admit(current)
    before='\n'.join(enrolled._store.connection.iterdump())
    if disabled:enrolled.enabled=False
    with pytest.raises(RuntimeError,match='SCOPE_REQUIRED_FOR_ENROLLED_STORAGE'):
        CapitalManagementAuthority(run_mode='PAPER',storage_engine=enrolled)
    assert '\n'.join(enrolled._store.connection.iterdump())==before


def test_legacy_owner_created_before_enrollment_cannot_write_after_enrollment(tmp_path):
    s=storage(tmp_path/'legacy-before.db')
    legacy=CapitalManagementAuthority(run_mode='PAPER',storage_engine=s)
    enroll(s);current=owner(s)
    before='\n'.join(s._store.connection.iterdump())
    try:
        with pytest.raises(RuntimeError,match='SCOPE_REQUIRED_FOR_ENROLLED_STORAGE'):admit(legacy)
        assert '\n'.join(s._store.connection.iterdump())==before
        with pytest.raises(RuntimeError,match='SCOPE_REQUIRED_FOR_ENROLLED_STORAGE'):
            legacy.recover_from_lifecycle([SimpleNamespace(quantity_open=99,entry_avg_price=100,symbol='XYZ')])
        with pytest.raises(RuntimeError,match='SCOPE_REQUIRED_FOR_ENROLLED_STORAGE'):
            legacy.recover_from_open_orders([])
        assert admit(current).executable
    finally:s._store.close()

def test_failed_writer_cannot_renew_by_resetting_public_failure_flag(enrolled):
    current=owner(enrolled);connection=enrolled._store.connection
    class LostObservation(FailConnection):
        def commit(self):
            self.commits+=1
            if self.commits==4:raise OSError('synthetic quarantine persistence failure')
            self.original.commit()
            if self.commits==3:raise OSError('synthetic completion response loss')
    enrolled._store.connection=LostObservation(connection,'none')
    with pytest.raises(RuntimeError,match='QUARANTINE_PERSISTENCE_UNKNOWN'):admit(current,cap=500)
    enrolled._store.connection=connection
    # No clearing API is authorized. Public mutable diagnostics cannot restore
    # the issuer-private writer grant after an observed uncertain operation.
    current.recovery_failed=False;current.recovery_failure_reason=None
    with pytest.raises(RuntimeError,match='WRITER_REVOKED'):admit(current,'unsafe-renewal',cap=500)
    assert current.total_reserved_capital==100

def test_dead_weak_owner_cannot_match_missing_lower_level_owner(enrolled):
    import gc
    current=owner(enrolled);admit(current,cap=500);token=current._capital_writer
    del current;gc.collect()
    before='\n'.join(enrolled._store.connection.iterdump())
    with pytest.raises(RuntimeError,match='OWNER|SESSION|IDENTITY'):
        enrolled.transact_capital('synthetic:account-a','PAPER','unauthorized','{}',
            lambda state:pytest.fail('Unowned transaction callback ran'),writer=token,owner=None)
    assert '\n'.join(enrolled._store.connection.iterdump())==before


def test_lost_enrollment_acknowledgement_cannot_reissue_writer(tmp_path):
    s=storage(tmp_path/'enrollment-loss.db');connection=s._store.connection
    s._store.connection=FailConnection(connection,'after_commit',1)
    with pytest.raises(OSError):s.initialize_synthetic_capital_scope('synthetic:account-a','PAPER')
    s._store.connection=connection
    before='\n'.join(connection.iterdump())
    assert s.read_capital_state('synthetic:account-a','PAPER')['version']==0
    with pytest.raises(RuntimeError,match='SESSION_REQUIRED'):admit(owner(s))
    with pytest.raises(Exception):s.initialize_synthetic_capital_scope('synthetic:account-a','PAPER')
    assert '\n'.join(connection.iterdump())==before
    s._store.close()
