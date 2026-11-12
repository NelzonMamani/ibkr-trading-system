from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from config.config_resolver import set_config_overrides  # noqa: E402
from core.active_trade_registry import ActiveTrade, ActiveTradeRegistry  # noqa: E402
from core.event_collector import EventCollector  # noqa: E402
from core.stop_controller import StopController  # noqa: E402
from execution.execution_engine import ExecutionEngine  # noqa: E402
from execution.execution_providers import OrderSnapshot, PositionSnapshot  # noqa: E402
from models.execution_result import ExecutionResult  # noqa: E402
from risk.risk_engine import RiskEngine  # noqa: E402
from strategies.strategy_contracts import (  # noqa: E402
    DecisionType,
    Direction,
    StrategyRiskPayload,
    TimeInForcePolicy,
    TradeIntent,
)


class _StartupRecoveryProvider:
    def __init__(self, positions: list[object], orders: list[object] | None = None):
        self._positions = positions
        self._orders = list(orders or [])

    def name(self) -> str:
        return "STARTUP_RECOVERY_PROVIDER"

    def is_live(self) -> bool:
        return True

    def place_order(self, request):
        raise RuntimeError("not used in this test")

    def cancel(self, order_id: str):
        raise RuntimeError("not used in this test")

    def get_positions(self) -> PositionSnapshot:
        return PositionSnapshot(positions=self._positions, as_of="2026-03-26T00:00:00+00:00")

    def get_open_orders(self) -> list:
        return list(self._orders)


def _decision_without_stop(symbol: str = "AAPL"):
    payload = StrategyRiskPayload(
        strategy_id="UnitTestStrategy",
        symbol=symbol,
        intents=[
            TradeIntent(
                intent_id="intent-stop-test",
                symbol=symbol,
                direction=Direction.LONG,
                entry_model="MKT",
                stop_model="STRUCTURE",
                target_model=None,
                time_in_force_policy=TimeInForcePolicy.DAY,
                invalidations=[],
                rationale_text="unit-test",
                risk_flags=[],
            )
        ],
        decision_type=DecisionType.EMIT_INTENT,
        confidence=0.9,
        rationale_text="unit-test",
        risk_flags=[],
    )
    decision = RiskEngine(stop_controller=StopController()).evaluate_strategy_payload(payload)
    decision.decision_id = "decision-stop-test"
    decision.stop_loss_price = None
    return decision


def test_startup_recovery_restores_protected_position_once() -> None:
    set_config_overrides({"RUN_MODE": "LIVE", "EXECUTION_ENABLED": True})
    try:
        registry = ActiveTradeRegistry()
        recovered = ActiveTrade(
            symbol="MSFT",
            trader_type="MOMENTUM",
            entry_tick=100,
            entry_price=412.25,
            direction="LONG",
            quantity=3,
            strategy_name="UnitTestStrategy",
            stop_loss_price=409.50,
        )
        provider = _StartupRecoveryProvider(
            [recovered],
            [
                OrderSnapshot(
                    order_id="STOP-MSFT",
                    symbol="MSFT",
                    status="Submitted",
                    order_type="STP",
                    metadata={"stop_price": 409.50, "quantity": 3, "trade_id": "recovery:MSFT"},
                )
            ],
        )
        _ = ExecutionEngine(
            provider=provider,
            trade_registry=registry,
            event_collector=EventCollector(),
        )
        assert registry.count_active() == 1
        assert registry.get_trade("MSFT", "MOMENTUM") is not None
    finally:
        set_config_overrides(None)


def test_startup_recovery_flags_unprotected_position_and_skips_restore(capsys) -> None:
    set_config_overrides({"RUN_MODE": "LIVE", "EXECUTION_ENABLED": True})
    try:
        registry = ActiveTradeRegistry()
        unprotected = SimpleNamespace(
            symbol="TSLA",
            trader_type="MOMENTUM",
            entry_tick=1,
            entry_price=180.0,
            direction="LONG",
            quantity=2,
            strategy_name="UnitTestStrategy",
            stop_loss_price=None,
        )
        provider = _StartupRecoveryProvider([unprotected])
        _ = ExecutionEngine(
            provider=provider,
            trade_registry=registry,
            event_collector=EventCollector(),
        )
        captured = capsys.readouterr().out
        assert "[CRITICAL][UNPROTECTED_POSITION]" in captured
        assert registry.count_active() == 0
    finally:
        set_config_overrides(None)


def test_execution_resolves_stop_loss_when_missing_in_paper_mode() -> None:
    set_config_overrides({"RUN_MODE": "PAPER", "EXECUTION_ENABLED": True})
    try:
        engine = ExecutionEngine(event_collector=EventCollector(), stop_controller=StopController())
        engine.current_tick = 7
        result: ExecutionResult = engine.execute_trade(_decision_without_stop())
        assert result.stop_loss_price is not None
        assert result.status in {"SIMULATED", "REJECTED", "EXPIRED", "BLOCKED", "PARTIAL", "FULL", "NOT_FILLED"}
    finally:
        set_config_overrides(None)


# This child deliberately imports the canonical src modules.  The older tests
# above also exercise legacy import aliases; none of their fixtures or patched
# startup/recovery outcomes cross this fresh interpreter boundary.
_NATIVE_CORE_COLD_START_CHILD = r'''
import copy
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import threading
import traceback
from datetime import datetime, timezone
from types import SimpleNamespace as NS

database_path, facts_path, report_path, fault = sys.argv[1:]
facts = json.loads(Path(facts_path).read_text(encoding='utf-8'))
observe_pristine_cycle = bool(facts.get('observe_pristine_readonly_cycle')
                              or facts.get('observe_pristine_paper_cycle'))
base_external_facts = {key: copy.deepcopy(value) for key, value in facts.items()
                       if key != 'cycle_scenarios'}
current_external_facts = copy.deepcopy(base_external_facts)
external_fault = fault
report = {'pid': os.getpid(), 'parent_pid': os.getppid(), 'fault': fault,
          'constructor_complete': False, 'constructor_count': 0,
          'cycle_attempted': False, 'scenarios': [],
          'sdk_attempts': [], 'wire_attempts': [], 'native_read_requests': [], 'network_attempts': [],
          'cached_order_status_reads': [], 'cycles': [], 'cleanup': {},
          'external_provider_calls': [], 'external_history_calls': [],
          'availability_witness_calls': [],
          'stage': 'BOOTSTRAP'}
# Establish the child/supervisor binding before importing the application.  A
# killed child cannot write terminal evidence, so timeout evidence stays partial.
Path(report_path).write_text(json.dumps(report), encoding='utf-8')
core = None
client = None
manager = None
first_sdk_source = None
first_sdk_patcher = None

class SyntheticWriteBoundary(BaseException):
    pass

class ForbiddenExternalIO(BaseException):
    pass

def deny_network(operation):
    def forbidden(*args, **kwargs):
        report['network_attempts'].append({'operation': operation})
        raise ForbiddenExternalIO('COLD_CORE_REAL_NETWORK_FORBIDDEN:' + operation)
    return forbidden

no_network = deny_network('socket.connect')
socket.socket.connect = no_network
socket.socket.connect_ex = deny_network('socket.connect_ex')
socket.socket.sendto = deny_network('socket.sendto')
for operation in ('create_connection', 'getaddrinfo', 'gethostbyname', 'gethostbyname_ex', 'gethostbyaddr'):
    setattr(socket, operation, deny_network('socket.' + operation))
if hasattr(socket.socket, 'sendmsg'):
    socket.socket.sendmsg = deny_network('socket.sendmsg')

def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [plain(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, 'value'):
        return plain(value.value)
    if hasattr(value, '__dict__'):
        return plain(vars(value))
    return value

def database_snapshot():
    # Read the real owner's committed rows through a separate read-only handle.
    connection = sqlite3.connect('file:' + database_path + '?mode=ro', uri=True)
    try:
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        result = {}
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            cursor = connection.execute('SELECT * FROM ' + quoted)
            columns = [column[0] for column in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            result[table] = sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, default=str))
        return result
    finally:
        connection.close()

def exception_record(exc):
    return {'type': type(exc).__name__, 'message': str(exc),
            'traceback': traceback.format_exc()}

def native_namespace(snapshot):
    rows = snapshot.get('position_lifecycle_transitions', [])
    row = next((row for row in rows if row.get('transition_id') ==
                'execution.native_orders.v1:PAPER'), None)
    if row is None:
        return None
    try:
        return json.loads(row['reason'])
    except (ValueError, TypeError):
        return {'corrupt_retained_raw': row.get('reason')}

def engine_snapshot(engine):
    recovery = getattr(engine, 'startup_recovery_result', None)
    return plain({
        'startup_recovery_state': getattr(engine, 'startup_recovery_state', None),
        'startup_recovery_result': recovery,
        'native_loaded': getattr(engine, '_native_loaded', None),
        'native_quarantined': getattr(engine, '_native_quarantined', None),
        'failsafe_block_new_entries': getattr(engine, '_failsafe_block_new_entries', None),
        'native_state': getattr(engine, '_native_state', None),
        'native_orders': getattr(engine, '_native_orders', None),
        'position_records': getattr(engine, 'position_records', None),
        'post_fill': engine.post_fill_lifecycle.snapshot(),
        'capital_reserved': engine.capital_authority.total_reserved_capital,
        'capital_used': engine.capital_authority.total_used_exposure,
        'capital_recovery_failed': engine.capital_authority.recovery_failed,
        'capital_reservations': engine.capital_authority.active_reservations,
        'allocation_reservations': engine.strategy_allocation_authority.active_reservations,
        'capital_scope': engine.capital_authority.capital_scope,
        'capital_writer_present': engine.capital_authority._capital_writer is not None,
        'canonical_trades': {key: engine._trade_lifecycle_engine.get_trade(key)
            for key in engine._native_orders} if engine._trade_lifecycle_engine is not None else {},
        'protection': {key: engine.post_fill_lifecycle.assess_trade_stop_protection(key)
            for key in engine._native_orders if engine.post_fill_lifecycle.get_trade(key) is not None},
        'registry': engine.trade_registry.snapshot(),
        'managed_positions': (engine.relationship_manager.snapshot_positions()
            if getattr(engine, 'relationship_manager', None) is not None else {}),
    })

def native_shutdown_snapshot(core, provided_positions, provided_orders):
    """Observe retained ownership separately from local connection availability."""
    engine = core.execution_engine
    strategies = {row['request'].get('strategy_name') for row in engine._native_orders.values()}
    return plain(dict(engine=engine_snapshot(engine), database=database_snapshot(),
        allocation_used_by_strategy={name:engine.strategy_allocation_authority.strategy_used_exposure(name)
            for name in strategies if name},
        supplied_positions=provided_positions, supplied_open_orders=provided_orders,
        manager_has_original_client=manager.existing_client is client,
        client_stop_event_set=client._stop_event.is_set()))

def validate_pristine_native_ack_shutdown_ownership(*, before, parent, root_id, plan,
        provided_positions, provided_orders, callbacks, dispatches, cycles):
    """Observe the unfilled native request and its real reservation binding."""
    def require(value, reason):
        if not value:
            raise ForbiddenExternalIO('NATIVE_GRACEFUL_SHUTDOWN_ACK_PRECONDITION:' + reason)
    request = parent['request']
    require(len(cycles) == 1 and [row['role'] for row in dispatches] == ['entry']
        and dispatches[0]['root_id'] == root_id
        and str(dispatches[0]['native_id']) == str(parent.get('broker_order_id'))
        and not callbacks and not provided_positions and len(provided_orders) == 1, 'ACK_ONLY')
    working = provided_orders[0]
    contract = getattr(working,'contract',None)
    order = getattr(working,'order',None)
    require(str(getattr(working,'orderId',None)) == str(parent.get('broker_order_id'))
        and getattr(contract,'conId',None) == plan['con_id'] and getattr(contract,'symbol',None) == plan['symbol']
        and getattr(contract,'currency',None) == plan['currency'] and getattr(contract,'exchange',None) == plan['exchange']
        and getattr(order,'orderType',None) == 'MKT' and getattr(order,'action',None) == 'BUY'
        and getattr(order,'totalQuantity',None) == 1 and getattr(order,'parentId',None) == 0
        and getattr(order,'orderRef',None) == '' and getattr(order,'account',None) == plan['account']
        and getattr(order,'clientId',None) == plan['client_id']
        and getattr(getattr(working,'orderState',None),'status',None) == 'Submitted', 'WORKING_ENTRY')
    require(type(parent.get('requested')) is int and parent['requested'] == 1
        and type(parent.get('filled')) is int and parent['filled'] == 0
        and parent.get('terminal') is False and not parent.get('protection_confirmed')
        and not parent.get('cached_update_in_progress') and parent.get('notional') == 0
        and parent.get('mode') == 'PAPER' and parent.get('account') == plan['account']
        and parent.get('native_client_id') == plan['client_id']
        and parent.get('native_connection_epoch') == plan['epoch']
        and parent.get('symbol') == plan['symbol'] and parent.get('side') in {'LONG','BUY'}
        and isinstance(parent.get('decision_id'),str) and bool(parent['decision_id']), 'RETAINED_REQUEST')
    require(request.get('client_order_id') == root_id and request.get('symbol') == plan['symbol']
        and request.get('quantity') == 1 and request.get('direction') == parent['side']
        and request.get('setup_family_id') == 'PREMARKET_HIGH_BREAK'
        and request.get('stop_loss_price') == plan['stop_price']
        and request.get('invalidation_level') == plan['entry_price']
        and request.get('take_profit_price') is None and bool(request.get('target_model'))
        and bool(request.get('setup_metadata')) and not request.get('relationship_context'), 'NATIVE_CONTRACT')
    require(before['capital_used'] == 0 and before['capital_reserved'] == plan['entry_price']
        and not before['position_records'] and not before['registry'] and not before['managed_positions']
        and not before['post_fill'] and not before['protection']
        and before['canonical_trades'].get(root_id) is None
        and len(before['capital_reservations']) == len(before['allocation_reservations']) == 1,
        'UNFILLED_OWNERS')
    capital = next(iter(before['capital_reservations'].values()))
    allocation = next(iter(before['allocation_reservations'].values()))
    require(isinstance(capital.get('decision_id'),str) and bool(capital['decision_id'])
        and isinstance(allocation.get('decision_id'),str) and bool(allocation['decision_id'])
        and allocation.get('global_capital_decision_id') == capital['decision_id'], 'ALLOCATION_BINDING')
    for reservation in (capital,allocation):
        require(reservation.get('order_id') == root_id and reservation.get('symbol') == request['symbol']
            and reservation.get('side') == request['direction'].upper()
            and reservation.get('strategy_id','').upper() == request['strategy_name'].upper()
            and reservation.get('run_mode') == 'PAPER' and reservation.get('status') == 'ACTIVE'
            and type(reservation.get('quantity')) is int and reservation['quantity'] == 1
            and type(reservation.get('remaining_quantity')) is int and reservation['remaining_quantity'] == 1
            and reservation.get('filled_quantity') == 0 and reservation.get('exposure_notional') == 0
            and reservation.get('notional') == reservation.get('remaining_notional') == plan['entry_price'],
            'RESERVATION')

def observe_pristine_native_graceful_shutdown(core, provided_positions, provided_orders):
    """Call actual shutdown only after explicit ACK-only or protected PAPER facts.

    This observer never repairs a mutation, supplies a fill, clears ownership or
    interprets disconnection as flat. The parent test asserts the desired truth
    invariant; an actual legacy failure remains a failed reproduction.
    """
    probe = dict(attempted=False, verify_empty_calls=[])
    report['native_graceful_shutdown'] = probe
    if core is None:
        raise ForbiddenExternalIO('NATIVE_GRACEFUL_SHUTDOWN_NO_CORE')
    probe['before'] = native_shutdown_snapshot(core,provided_positions,provided_orders)
    engine = core.execution_engine
    before = probe['before']['engine']
    ack_only = facts.get('observe_pristine_native_ack_graceful_shutdown') is True
    roots = [(key,row) for key,row in before['native_orders'].items() if row.get('side') in {'LONG','BUY'}]
    if (os.environ.get('EXECUTION_ENV') != 'TEST' or core.run_mode.value != 'PAPER'
            or not facts.get('observe_pristine_paper_cycle') or not engine.provider.is_live() or len(roots) != 1
            or report.get('native_before') is not None or report['after_constructor']['native_state'] is not None
            or not report.get('cycles') or any(row.get('result') is not True or row.get('exception')
                for row in report['cycles'])
            or [row['role'] for row in report['synthetic_memory_dispatches']] != (['entry'] if ack_only else ['entry','stop'])
            or before['capital_scope'] is not None or before['capital_writer_present']
            or before['native_quarantined'] or before['startup_recovery_state'] != 'RECOVERY_COMPLETE'):
        raise ForbiddenExternalIO('NATIVE_GRACEFUL_SHUTDOWN_PROTECTED_PRECONDITION')
    root_id,parent = roots[0]
    plan = facts['paper_memory_plan']
    life = before['post_fill'].get(root_id)
    canonical = before['canonical_trades'].get(root_id)
    if ack_only:
        validate_pristine_native_ack_shutdown_ownership(before=before,parent=parent,root_id=root_id,plan=plan,
            provided_positions=provided_positions,provided_orders=provided_orders,
            callbacks=report['paper_execution_callbacks'],dispatches=report['synthetic_memory_dispatches'],
            cycles=report['cycles'])
    elif (not parent.get('terminal') or parent.get('filled') != 1 or not parent.get('protection_confirmed')
            or parent.get('cached_update_in_progress') or parent['request'].get('setup_family_id') != 'PREMARKET_HIGH_BREAK'
            or parent['request'].get('relationship_context')
            or life is None or life['filled_qty'] != 1 or not before['protection'][root_id]['protected']
            or canonical is None or canonical['quantity_open'] != 1 or canonical['quantity_closed'] != 0
            or before['capital_used'] != plan['fill_price']
            or before['capital_reserved'] != 0 or before['capital_reservations'] or before['allocation_reservations']
            or len(before['registry']) != 1 or len(provided_positions) != 1 or provided_positions[0].position != 1
            or provided_positions[0].symbol != plan['symbol'] or provided_positions[0].con_id != plan['con_id']
            or provided_positions[0].account != plan['account'] or provided_positions[0].avgCost != plan['fill_price']
            or len(provided_orders) != 1 or provided_orders[0].order.orderType != 'STP'
            or provided_orders[0].contract.conId != plan['con_id'] or provided_orders[0].contract.symbol != plan['symbol']
            or provided_orders[0].order.action != 'SELL' or provided_orders[0].order.totalQuantity != 1
            or provided_orders[0].order.auxPrice != plan['stop_price']
            or str(provided_orders[0].orderId) != str(life['stop']['broker_order_id'])
            or str(provided_orders[0].order.parentId) != str(parent['broker_order_id'])
            or provided_orders[0].order.orderRef != 'PROTECT|' + root_id
            or any(row.get('leg') != 'entry' for row in report['paper_execution_callbacks'])):
        raise ForbiddenExternalIO('NATIVE_GRACEFUL_SHUTDOWN_OWNERSHIP_PRECONDITION')
    actual_verify_empty = core.trade_registry.verify_empty
    def observed_shutdown_verify_empty(*args,**kwargs):
        result = actual_verify_empty(*args,**kwargs)
        probe['verify_empty_calls'].append(dict(result=result,registry=plain(core.trade_registry.snapshot())))
        return result
    core.trade_registry.verify_empty = observed_shutdown_verify_empty
    events_before = len(core.event_collector.snapshot_all())
    probe['mutation_attempts_before'] = mutation_snapshot()
    probe['attempted'] = True
    try:
        from src.core.stop_controller import StopMode
        core._shutdown(StopMode.GRACEFUL)
    except BaseException as exc:
        probe['exception'] = exception_record(exc)
    finally:
        core.trade_registry.verify_empty = actual_verify_empty
        probe['after'] = native_shutdown_snapshot(core,provided_positions,provided_orders)
        proof = getattr(core,'shutdown_evidence',None)
        probe['shutdown_evidence'] = plain(proof.payload()) if proof is not None else None
        probe['events'] = plain(core.event_collector.snapshot_all()[events_before:])
        probe['mutation_attempts_after'] = mutation_snapshot()

def validate_pristine_paper_memory_write(*, actual_client, expected_client, core,
        plan, dispatches, native_id, contract, native, committed, risk_rows, now, max_scope_age):
    """Observe actual owners before an exclusively in-memory external ACK.

    This is a fixture boundary, not execution permission. The ordinary submit
    owner and its final read-only guard have already run before this function.
    No SDK encoder or underlying transport is called by the memory boundary.
    """
    def require(value, reason):
        if not value:
            raise ForbiddenExternalIO('PRISTINE_PAPER_MEMORY_CERTIFICATE:' + reason)
    require(actual_client is expected_client and core is not None, 'CLIENT')
    engine = core.execution_engine
    scope = engine._native_scope
    require(core.run_mode.value == engine.run_mode.value == 'PAPER'
        and os.environ.get('EXECUTION_ENV') == 'TEST', 'MODE')
    require(scope is not None and scope[0] == plan['account'] and scope[1] is expected_client
        and 0 <= (now-scope[2]).total_seconds() <= max_scope_age
        and expected_client.client_id == plan['client_id']
        and expected_client._position_connection_epoch == plan['epoch']
        and expected_client.isConnected() and not expected_client.readonly_enabled, 'SCOPE')
    require(engine.capital_authority.capital_scope is None
        and engine.capital_authority._capital_writer is None
        and not engine._native_quarantined and engine.startup_recovery_complete(), 'OWNER')
    require(committed == engine._native_state
        and committed == dict(version=1, mode='PAPER', orders=engine._native_orders), 'DURABLE')
    require(len(engine._native_orders) == 1 and type(native_id) is int and native_id > 0
        and native_id not in [row['native_id'] for row in dispatches], 'UNIQUE')
    root_id, parent = next(iter(engine._native_orders.items()))
    request = parent['request']
    require(parent['account'] == plan['account'] and parent['native_client_id'] == plan['client_id']
        and parent['native_connection_epoch'] == plan['epoch']
        and request['client_order_id'] == root_id and request['symbol'] == plan['symbol']
        and request['quantity'] == parent['requested'] == 1
        and request['setup_family_id'] == 'PREMARKET_HIGH_BREAK'
        and not request['relationship_context'] and request['setup_metadata']
        and request['stop_loss_price'] == plan['stop_price']
        and request['invalidation_level'] == plan['entry_price']
        and request['take_profit_price'] is None and request['target_model'], 'REQUEST')
    matched = [row for row in risk_rows if row['decision']['decision_id'] == parent['decision_id']]
    require(len(matched) == 1 and matched[0]['decision']['allowed'] is True
        and matched[0]['decision']['max_position_size'] == 1
        and matched[0]['intent']['entry_price'] == plan['entry_price']
        and matched[0]['intent']['setup_metadata'] == request['setup_metadata']
        and matched[0]['intent']['target_model'] == request['target_model'], 'RISK')
    require(contract.symbol == plan['symbol'] and contract.secType == 'STK'
        and contract.currency == plan['currency'] and contract.exchange == plan['exchange']
        and contract.conId in (0, plan['con_id'])
        and not isinstance(native.totalQuantity, bool) and native.totalQuantity == 1, 'SECURITY_SIZE')
    if not dispatches:
        require(native.action == 'BUY' and native.orderType == 'MKT'
            and native.parentId == 0 and not native.orderRef
            and parent['status'] == 'DISPATCH_UNCERTAIN' and parent['broker_order_id'] is None
            and parent['filled'] == 0 and not parent['terminal'], 'ENTRY')
        reservations = list(engine.capital_authority.active_reservations.values())
        allocations = list(engine.strategy_allocation_authority.active_reservations.values())
        require(len(reservations) == len(allocations) == 1, 'RESERVATION_COUNT')
        capital, allocation = reservations[0], allocations[0]
        # Risk, capital and strategy allocation issue different decisions. The
        # existing order binding and allocation's global-capital link join them;
        # the retained native parent carries only the original Risk decision.
        require(isinstance(capital.decision_id,str) and capital.decision_id
            and isinstance(allocation.decision_id,str) and allocation.decision_id
            and allocation.global_capital_decision_id == capital.decision_id, 'RESERVATION_LINK')
        for reservation in (capital,allocation):
            require(reservation.order_id == root_id and reservation.symbol == request['symbol']
                and reservation.side == request['direction'].upper()
                and reservation.strategy_id.upper() == request['strategy_name'].upper()
                and reservation.run_mode == 'PAPER' and reservation.status == 'ACTIVE'
                and type(reservation.quantity) is int and reservation.quantity == 1
                and type(reservation.remaining_quantity) is int and reservation.remaining_quantity == 1
                and reservation.filled_quantity == 0 and reservation.exposure_notional == 0
                and reservation.notional == reservation.remaining_notional == plan['entry_price'], 'RESERVATION_BINDING')
        require(engine.capital_authority.total_reserved_capital == plan['entry_price']
            and engine.capital_authority.total_used_exposure == 0
            and not engine.position_records and not engine.trade_registry.snapshot(), 'RESERVATION')
        role = 'entry'
    else:
        require(len(dispatches) == 1 and dispatches[0]['role'] == 'entry'
            and native.action == 'SELL' and native.orderType == 'STP'
            and native.auxPrice == plan['stop_price']
            and native.parentId == dispatches[0]['native_id']
            and native.orderRef == 'PROTECT|' + root_id
            and parent['broker_order_id'] == str(dispatches[0]['native_id'])
            and parent.get('cached_update_in_progress') == dict(filled=1, remaining=0,
                status='FILLED', average_price=plan['fill_price']), 'STOP')
        # Initial protection is installed within factual accounting, before
        # canonical completion/terminal native progress. Observe that ordering;
        # do not manufacture terminal-accounted state to satisfy this boundary.
        position = engine.position_records.get(root_id, {})
        life = engine.post_fill_lifecycle.get_trade(root_id)
        require(position.get('filled_qty') == 1 and position.get('entry_price') == plan['fill_price']
            and engine.capital_authority.total_used_exposure == plan['fill_price']
            and engine.capital_authority.total_reserved_capital == 0
            and life is not None and life.filled_qty == 1
            and life.avg_fill_price == plan['fill_price']
            and life.selected_stop_price == plan['stop_price'] and life.stop.status == 'PENDING_SUBMIT', 'ACCOUNTING')
        executions = expected_client.cached_native_executions(dispatches[0]['native_id'])
        require(len(executions) == 1, 'EXECUTION_COVERAGE')
        execution = executions[0]
        require(execution['orderId'] == dispatches[0]['native_id']
            and execution['account'] == plan['account'] and execution['clientId'] == plan['client_id']
            and execution['connection_epoch'] == plan['epoch'] and execution['conId'] == plan['con_id']
            and execution['symbol'] == plan['symbol'] and execution['side'] == 'BOT'
            and execution['shares'] == execution['cumQty'] == 1
            and float(execution['price']) == float(execution['avgPrice']) == plan['fill_price']
            and execution['timestamp_utc'] <= now, 'EXECUTION_BINDING')
        positions = expected_client.positions()
        require(len(positions) == 1 and positions[0].symbol == plan['symbol']
            and positions[0].position == 1 and positions[0].con_id == plan['con_id']
            and positions[0].account == plan['account'] and positions[0].avgCost == plan['fill_price'], 'POSITION_FACT')
        role = 'stop'
    return root_id, role

def validate_pristine_paper_market_fact(*, plan, quote, now, max_age):
    """Accept raw quote facts only; actual source callbacks still build quotes."""
    import math
    def require(value, reason):
        if not value:
            raise ForbiddenExternalIO('PRISTINE_PAPER_MARKET_CERTIFICATE:' + reason)
    require(isinstance(quote,dict) and set(quote) == {
        'symbol','con_id','bid','ask','last_price','quote_timestamp_utc'}, 'FIELDS')
    require(quote['symbol'] == plan['symbol'] and type(quote['con_id']) is int
        and quote['con_id'] == plan['con_id'], 'SECURITY')
    require(all(type(quote[key]) in (int,float) and math.isfinite(quote[key])
        and quote[key] > 0 for key in ('bid','ask','last_price')), 'PRICE')
    require(quote['bid'] <= quote['last_price'] <= quote['ask'], 'SPREAD')
    stamp = datetime.fromisoformat(quote['quote_timestamp_utc'])
    require(stamp.tzinfo is not None and 0 <= (now-stamp).total_seconds() <= max_age, 'TIME')
    return {key:value for key,value in quote.items() if key not in {'symbol','con_id'}}

def validate_pristine_paper_execution_fact(*, actual_client, expected_client, core,
        plan, dispatches, raw, now):
    """Bind supplied financial callbacks to the already dispatched native leg."""
    def require(value, reason):
        if not value:
            raise ForbiddenExternalIO('PRISTINE_PAPER_EXECUTION_CERTIFICATE:' + reason)
    require(actual_client is expected_client and core is not None
        and os.environ.get('EXECUTION_ENV') == 'TEST', 'CLIENT')
    engine = core.execution_engine
    require(core.run_mode.value == engine.run_mode.value == 'PAPER'
        and engine._native_callback_client() is expected_client
        and expected_client.isConnected() and expected_client.client_id == plan['client_id']
        and expected_client._position_connection_epoch == plan['epoch'], 'SCOPE')
    require(isinstance(raw,dict) and set(raw) == {'leg','contract','execution','status'}, 'FIELDS')
    matches = [row for row in dispatches if row['role'] == raw['leg']]
    require(len(matches) == 1 and raw['leg'] in {'entry','stop'}, 'LEG')
    bound = matches[0]
    entries = [row for row in dispatches if row['role'] == 'entry']
    require(len(entries) == 1 and bound['root_id'] == entries[0]['root_id']
        and bound['root_id'] in engine._native_orders, 'ROOT')
    contract = raw['contract']; execution = raw['execution']; status = raw['status']
    require(contract == dict(symbol=plan['symbol'],conId=plan['con_id'],exchange=plan['exchange'],
        currency=plan['currency'],secType='STK'), 'SECURITY')
    require(set(execution) == {'execId','acctNumber','clientId','side','shares','cumQty',
        'price','avgPrice','time'} and isinstance(execution['execId'],str) and execution['execId']
        and execution['acctNumber'] == plan['account'] and type(execution['clientId']) is int
        and execution['clientId'] == plan['client_id'], 'IDENTITY')
    require(type(execution['shares']) is int and type(execution['cumQty']) is int
        and execution['shares'] == execution['cumQty'] == 1, 'QUANTITY')
    expected_price = plan['fill_price'] if raw['leg'] == 'entry' else plan.get('stop_fill_price')
    require(type(execution['price']) in (int,float) and type(execution['avgPrice']) in (int,float)
        and execution['price'] == execution['avgPrice'] == expected_price
        and status == dict(status='Filled',filled=1,remaining=0,avgFillPrice=expected_price), 'FILL')
    stamp = datetime.fromisoformat(execution['time'])
    require(stamp.tzinfo is not None and stamp <= now, 'TIME')
    native = bound['order']
    if raw['leg'] == 'entry':
        require(execution['side'] == 'BOT' and native['action'] == 'BUY'
            and native['orderType'] == 'MKT' and native['parentId'] == 0, 'ENTRY')
    else:
        require(execution['side'] == 'SLD' and native['action'] == 'SELL'
            and native['orderType'] == 'STP' and native['auxPrice'] == plan['stop_price']
            and native['parentId'] == entries[0]['native_id']
            and native['orderRef'] == 'PROTECT|' + bound['root_id']
            and expected_price <= plan['stop_price'], 'STOP')
        trade = engine._trade_lifecycle_engine.get_trade(bound['root_id'])
        require(trade is not None and trade.entry_avg_price == plan['fill_price']
            and trade.stop_price == plan['stop_price'] and trade.target_price is None
            and datetime.fromisoformat(trade.opened_at) <= stamp, 'ACCOUNTED_ENTRY')
    return bound

def observed_pristine_paper_exposure_release(actual_release, owner, label, *args, **kwargs):
    """Observe and forward the actual instance method exactly once, unmodified."""
    def exposure():
        return (owner.total_used_exposure if label == 'capital'
                else owner.strategy_used_exposure(kwargs['strategy_id']))
    row = dict(authority=label,cycle=active_cycle[0],args=plain(args),kwargs=plain(kwargs),
        exposure_before=exposure())
    report['exposure_release_calls'].append(row)
    try:
        result = actual_release(*args, **kwargs)
    except BaseException as exc:
        row['exception'] = exception_record(exc)
        raise
    else:
        row['result'] = plain(result)
        return result
    finally:
        row['exposure_after'] = exposure()

def validate_pristine_paper_fee_fact(*, actual_client, expected_client, core,
        plan, dispatches, raw, delivered, now, first_sdk_source=None):
    """Bind supplied commission facts to actual cached fills and source."""
    import math
    def require(value, reason):
        if not value:
            raise ForbiddenExternalIO('PRISTINE_PAPER_FEE_CERTIFICATE:' + reason)
    require(actual_client is expected_client and core is not None
        and os.environ.get('EXECUTION_ENV') == 'TEST', 'CLIENT')
    engine = core.execution_engine
    require(type(plan['client_id']) is int and type(plan['epoch']) is int and plan['epoch'] >= 0
        and core.run_mode.value == engine.run_mode.value == 'PAPER'
        and engine._native_callback_client() is expected_client
        and expected_client.isConnected() and not expected_client._stop_event.is_set()
        and expected_client._position_transport_available is True
        and type(expected_client.client_id) is int and expected_client.client_id == plan['client_id']
        and type(expected_client._position_connection_epoch) is int
        and expected_client._position_connection_epoch == plan['epoch']
        and tuple(expected_client._managed_accounts) == (plan['account'],), 'SCOPE')
    require(isinstance(raw,dict) and set(raw) == {'leg','execId','commission','currency'}, 'FIELDS')
    require(raw['leg'] in {'entry','stop'} and isinstance(raw['execId'],str) and raw['execId'], 'LEG')
    matches = [row for row in dispatches if row['role'] == raw['leg']]
    require(len(matches) == 1, 'DISPATCH')
    bound = matches[0]
    entries = [row for row in dispatches if row['role']=='entry']
    require(len(entries)==1 and bound['root_id']==entries[0]['root_id']
        and type(bound['native_id']) is int and bound['native_id'] > 0
        and bound['order']['parentId'] == (0 if raw['leg']=='entry' else entries[0]['native_id']), 'LEG_BINDING')
    parent = engine._native_orders.get(bound['root_id'])
    require(parent is not None and parent['account'] == plan['account']
        and parent['native_client_id'] == plan['client_id']
        and parent['native_connection_epoch'] == plan['epoch']
        and parent['request']['client_order_id'] == bound['root_id']
        and parent['request']['symbol'] == plan['symbol']
        and parent['request']['quantity'] == 1 and parent['request']['take_profit_price'] is None, 'ROOT')
    if first_sdk_source is None:
        require(type(raw['commission']) in (int,float) and math.isfinite(raw['commission'])
            and raw['commission'] == {'entry':.01,'stop':.02}[raw['leg']]
            and raw['currency'] == plan['currency'] == 'USD', 'SUPPLIED_POSITIVE_AMOUNT')
    else:
        validate_pristine_first_sdk_scope(expected_client,first_sdk_source)
        require(raw['currency'] == plan['currency'] == 'USD'
            and ((raw['leg']=='entry' and type(raw['commission']) is str
                    and raw['commission'] in {'0','0.0','0.00'})
                or (raw['leg']=='stop' and type(raw['commission']) is float and raw['commission']==.02)),
            'SUPPLIED_FIRST_SDK_AMOUNT')
    require(raw['execId'] not in delivered, 'REPEAT')
    rows = expected_client.cached_native_executions(bound['native_id'])
    require(len(rows) == 1 and rows[0]['execId'] == raw['execId'], 'EXECUTION')
    execution = rows[0]
    require(all(type(execution[key]) is int for key in ('orderId','clientId','connection_epoch','conId'))
        and execution['orderId'] == bound['native_id']
        and execution['account'] == plan['account'] and execution['clientId'] == plan['client_id']
        and execution['connection_epoch'] == plan['epoch'] and execution['conId'] == plan['con_id']
        and execution['symbol'] == plan['symbol'] and execution['secType'] == 'STK'
        and execution['side'] == ('BOT' if raw['leg']=='entry' else 'SLD')
        and not isinstance(execution['shares'],bool) and not isinstance(execution['cumQty'],bool)
        and execution['shares'] == execution['cumQty'] == 1
        and float(execution['price']) == float(execution['avgPrice'])
        == (plan['fill_price'] if raw['leg']=='entry' else plan['stop_fill_price'])
        and isinstance(execution['timestamp_utc'],datetime) and execution['timestamp_utc'].tzinfo is not None
        and execution['timestamp_utc'] <= now, 'EXECUTION_BINDING')
    fee_rows = expected_client.cached_native_execution_fees(bound['native_id'])
    require(len(fee_rows) == 1 and fee_rows[0]['execution']['execId'] == raw['execId']
        and fee_rows[0]['execution_currency'] == plan['currency'], 'EXECUTION_CURRENCY')
    return bound, execution

def deliver_pristine_paper_fee_fact(*, client, core, plan, dispatches, raw, delivered, now,
        first_sdk_source=None):
    """Supply the public callback; never construct financial owner results."""
    bound,execution = validate_pristine_paper_fee_fact(actual_client=client,
        expected_client=client,core=core,plan=plan,dispatches=dispatches,
        raw=raw,delivered=delivered,now=now,first_sdk_source=first_sdk_source)
    if first_sdk_source is None:
        from ibapi.commission_report import CommissionReport
        commission = CommissionReport()
        commission.execId,commission.commission,commission.currency = raw['execId'],raw['commission'],raw['currency']
        delivered.add(raw['execId'])
        client.commissionReport(commission)
    else:
        delivered.add(raw['execId'])
        first_sdk_source.deliver_commission_frame(raw['execId'],raw['commission'],raw['currency'])
    return dict(leg=raw['leg'],native_id=bound['native_id'],exec_id=execution['execId'],
        amount=raw['commission'],currency=raw['currency'],received_at=now.isoformat())

def validate_pristine_first_sdk_opt_in(facts):
    """The new first-SDK path is an explicit bounded PAPER-only fixture."""
    def require(value,reason):
        if not value:
            raise ForbiddenExternalIO('PRISTINE_FIRST_SDK_OPT_IN:' + reason)
    require(facts.get('observe_pristine_paper_first_sdk_zero_fee_feedback') is True
        and facts.get('observe_pristine_paper_cycle') is True
        and facts.get('observe_pristine_paper_positive_fee_feedback') is True
        and facts.get('observe_pristine_paper_loss_feedback') is True
        and not facts.get('observe_pristine_readonly_cycle')
        and facts.get('cycle_scenarios') is None, 'SCOPE')
    config = facts.get('config',{})
    require(config.get('RUN_MODE') == config.get('RUN_MODE_EFFECTIVE') == 'PAPER'
        and config.get('EXECUTION_ENABLED') is True, 'MODE')
    require(type(facts.get('client_id')) is int and facts['client_id'] >= 0
        and type(facts.get('epoch',0)) is int and facts.get('epoch',0) == 0
        and isinstance(facts.get('account'),str) and facts['account']
        and facts['account'] == facts['account'].strip() and ',' not in facts['account']
        and 'next_order_id' not in facts and facts.get('connected',True) is True, 'FIRST_SCOPE')
    require(isinstance(facts.get('paper_cycle_steps'),list) and len(facts['paper_cycle_steps']) == 5,
        'FIVE_STEPS')

def validate_pristine_first_sdk_packet(payload, *, client_id, seen):
    """Only the original SDK's three memory-bootstrap writes are supplied."""
    from ibapi import comm
    def require(value,reason):
        if not value:
            raise ForbiddenExternalIO('PRISTINE_FIRST_SDK_PACKET:' + reason)
    require(type(client_id) is int and client_id >= 0 and type(payload) is bytes, 'TYPE')
    if not seen:
        sdk = _FIRST_SDK_CONNECT.__globals__
        version = 'v%d..%d' % (sdk['MIN_CLIENT_VER'],sdk['MAX_CLIENT_VER'])
        require(payload == b'API\0' + comm.make_msg(version), 'NEGOTIATION')
        opcode = 'API'
    else:
        size,body,rest = comm.read_msg(payload)
        require(body and not rest and size == len(body), 'FRAME')
        fields = comm.read_fields(body)
        if len(seen) == 1:
            require(fields == (b'71',b'2',str(client_id).encode('ascii'),b''), 'START_API')
            opcode = '71'
        else:
            require(len(seen) == 2 and fields == (b'59',b'1',b'1'), 'MARKET_DATA_TYPE')
            opcode = '59'
    seen.append(dict(opcode=opcode,payload_hex=payload.hex()))
    return opcode

def validate_pristine_first_sdk_scope(client, source):
    """Read the existing native first-owner predicate; mint no SDK witness."""
    def require(value,reason):
        if not value:
            raise ForbiddenExternalIO('PRISTINE_FIRST_SDK_SCOPE:' + reason)
    require(source is not None and source.closed is False and source.initial_client is client, 'SOURCE')
    proxy = getattr(client,'_commission_decoder_proxy',None)
    # Let the existing owner observe/latch source loss before local detail
    # checks could short-circuit it. Restoring a value cannot rearm that owner.
    require(proxy is not None and client._commission_decoder_current(proxy) is True, 'CURRENT_FIRST_OWNER')
    require(type(client.client_id) is int and client.client_id == source.initial_client_id
        and type(client.clientId) is int and client.clientId == source.initial_client_id
        and type(client._position_connection_epoch) is int
        and client._position_connection_epoch == source.initial_epoch == 0
        and type(client._commission_connection_attempts) is int and client._commission_connection_attempts == 1
        and tuple(client._managed_accounts) == (source.initial_account,)
        and client.isConnected() and not client._stop_event.is_set()
        and client._position_transport_available is True, 'NATIVE')
    require(client.conn is source.initial_connection and source.connection is source.initial_connection
        and client.reader is source.initial_reader and source.reader is source.initial_reader
        and client.decoder is source.initial_decoder and source.decoder is source.initial_decoder
        and client.msg_queue is source.initial_queue and client.msg_queue is client._commission_constructor_queue
        and client.reader.conn is client.conn and client.reader.msg_queue is client.msg_queue
        and client._thread is source.initial_worker and source.initial_reader.is_alive()
        and source.initial_worker.is_alive() and client.serverVersion() == client.decoder.serverVersion == 151, 'SDK')
    return 151

def bootstrap_pristine_first_sdk(client, patcher, *, account, clock=None):
    """Reuse the accepted memory fixture behind exclusive, temporary guards.

    This function is not wired into a Core cycle. Its only callers are the
    dedicated pure memory tests until a future independently reviewed opt-in.
    """
    from ibapi.client import EClient
    from ibapi.connection import Connection
    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
    def require(value,reason):
        if not value:
            raise ForbiddenExternalIO('PRISTINE_FIRST_SDK_BOOTSTRAP:' + reason)
    require(sys.flags.optimize == 0, 'OPTIMIZED_FIXTURE_UNSUPPORTED')
    require(type(client) is IbkrClient and isinstance(account,str) and account
        and account == account.strip() and ',' not in account, 'CLIENT')
    require(_FIRST_SDK_CONNECT.__code__ is _FIRST_SDK_CONNECT_CODE
        and _FIRST_NATIVE_CONNECT.__code__ is _FIRST_NATIVE_CONNECT_CODE
        and _FIRST_SDK_INITIALIZER.__globals__.get('_NATIVE_SDK_CONNECT') is _FIRST_SDK_CONNECT
        and _FIRST_SDK_INITIALIZER.__globals__.get('_NATIVE_SOURCE_CONNECT') is _FIRST_NATIVE_CONNECT, 'ORIGINAL_OWNERS')
    require(type(client.client_id) is int and client.client_id >= 0
        and type(client._position_connection_epoch) is int and client._position_connection_epoch == 0
        and type(client._commission_connection_attempts) is int and client._commission_connection_attempts == 0
        and client._commission_zero_disabled is False and client._thread is None
        and client.conn is None and client.reader is None and client.decoder is None
        and client.clientId is None and client.serverVersion() is None
        and not client.isConnected() and client._managed_accounts == []
        and client._position_transport_available is False
        and client.msg_queue is client._commission_constructor_queue and client.msg_queue.empty()
        and not any(name in vars(client) for name in ('isConnected','serverVersion'))
        and not client.connectionOptions and not client.optCapab
        and client.market_data_type == 'LIVE', 'PRISTINE')
    owner_thread = threading.get_ident()
    original_queue = client.msg_queue
    previous_sdk,previous_connection = EClient.connect,Connection.connect
    captured = dict(reader=None,worker=None,decoder=None,connection=None,socket=None)
    seen = []
    state = dict(sdk_entered=False,sdk_active=False,connection_entered=False,active=True)
    source = None
    source_close = None
    def remember():
        for key,attribute in (('reader','reader'),('worker','_thread'),('decoder','decoder')):
            observed = getattr(client,attribute,None)
            if observed is not None:
                require(captured[key] is None or captured[key] is observed, 'REPLACED_' + key.upper())
                captured[key] = observed
    def guarded_sdk_connect(actual_client,host,port,client_id):
        require(state['active'] and not state['sdk_entered'] and threading.get_ident() == owner_thread
            and actual_client is client and host == client.host and port == client.port
            and type(client_id) is int and client_id == client.client_id
            and client._commission_connection_attempts == 1, 'EXCLUSIVE_SDK_CONNECT')
        state['sdk_entered'] = True  # Before delegation; no uncertain retry.
        state['sdk_active'] = True
        try:
            return _FIRST_SDK_CONNECT(actual_client,host,port,client_id)
        finally:
            remember()
            state['sdk_active'] = False
    class ExclusivePatch:
        def setattr(self,obj,name,value):
            if obj is EClient and name == 'connect':
                require(value is _FIRST_SDK_CONNECT, 'SDK_REPLACEMENT')
                scoped.setattr(obj,name,guarded_sdk_connect)
            elif obj is Connection and name == 'connect':
                def guarded_connection(connection):
                    require(state['active'] and state['sdk_active'] and not state['connection_entered']
                        and threading.get_ident() == owner_thread and connection is client.conn
                        and connection.host == client.host and connection.port == client.port
                        and connection.socket is None and client.clientId == client.client_id, 'EXCLUSIVE_CONNECTION')
                    state['connection_entered'] = True
                    captured['connection'] = connection
                    value(connection)  # Accepted MemorySocket body, never a socket connect.
                    socket = connection.socket
                    captured['socket'] = socket
                    original_send = socket.send
                    def observed_send(payload):
                        require(state['active'] and threading.get_ident() == owner_thread
                            and client.conn is connection and connection.socket is socket, 'BOOTSTRAP_SOCKET')
                        remember()  # Capture reader BEFORE START_API can fail/reset.
                        opcode = validate_pristine_first_sdk_packet(payload,client_id=client.client_id,seen=seen)
                        if opcode == '71':
                            require(captured['reader'] is not None and captured['decoder'] is not None, 'READER_BEFORE_START')
                        if opcode == '59':
                            require(captured['worker'] is not None, 'WORKER_BEFORE_TYPE')
                        return original_send(payload)
                    socket.send = observed_send
                scoped.setattr(obj,name,guarded_connection)
            else:
                patcher.setattr(obj,name,value)
    def close_retained():
        failure = None
        def cleanup(action):
            nonlocal failure
            try:
                action()
            except BaseException as exc:
                if failure is None:
                    failure = exc
        # Release the retained memory source before any joins, even if an SDK
        # reset erased client.conn or the source factory never returned.
        client._stop_event.set()
        if captured['socket'] is not None:
            cleanup(captured['socket'].close)
        if captured['connection'] is not None:
            cleanup(captured['connection'].disconnect)
        try:
            if source is not None:
                cleanup(source_close or source.close)
            else:
                cleanup(client.disconnect)
        finally:
            for key in ('reader','worker'):
                owned = captured[key]
                if owned is not None:
                    def finish(owned=owned,key=key):
                        if owned.ident is not None and owned is not threading.current_thread():
                            owned.join(2)
                        require(not owned.is_alive(), 'LEAKED_' + key.upper())
                    cleanup(finish)
        if failure is not None:
            raise failure
    try:
        with patcher.context() as scoped:
            source = _FIRST_SDK_INITIALIZER(client,ExclusivePatch(),account=account,clock=clock,
                constructor_frames=([59,1,'constructor.unowned',0,'USD','','',0],))
        require(EClient.connect is previous_sdk and Connection.connect is previous_connection, 'DENY_RESTORATION')
        require(state['sdk_entered'] and state['connection_entered']
            and [row['opcode'] for row in seen] == ['API','71','59']
            and source.constructor_queued.is_set(), 'COMPLETED_BOOTSTRAP')
        remember()
        source_close = source.close
        source.initial_client,source.initial_client_id,source.initial_account = client,client.client_id,account
        source.initial_epoch = client._position_connection_epoch
        source.initial_connection,source.initial_reader = captured['connection'],captured['reader']
        source.initial_decoder,source.initial_worker = captured['decoder'],captured['worker']
        source.initial_queue = original_queue
        source.bootstrap_packets = seen
        source.close = close_retained
        validate_pristine_first_sdk_scope(client,source)
        return source
    except BaseException:
        close_retained()
        raise
    finally:
        state['active'] = False

def validate_pristine_paper_currency_read(*, actual_client, expected_client, core,
        plan, fields, owned_reads, response, now, monotonic_now, max_scope_age, first_sdk_source=None):
    """Certify only this complete native root's real SDK ledger read/cleanup."""
    import math
    def require(value, reason):
        if not value:
            raise ForbiddenExternalIO('PRISTINE_PAPER_CURRENCY_CERTIFICATE:' + reason)
    require(actual_client is expected_client and core is not None
        and os.environ.get('EXECUTION_ENV') == 'TEST', 'CLIENT')
    engine = core.execution_engine
    scope = engine._native_scope
    require(type(plan['client_id']) is int and type(plan['epoch']) is int and plan['epoch'] >= 0
        and isinstance(now,datetime) and now.tzinfo is not None
        and type(max_scope_age) in (int,float) and math.isfinite(max_scope_age) and max_scope_age >= 0
        and core.run_mode.value == engine.run_mode.value == 'PAPER'
        and engine._native_callback_client() is expected_client
        and core.connection_manager.get_ibkr_client(ensure_connected=False) is expected_client
        and scope is not None and scope[0] == plan['account'] and scope[1] is expected_client
        and isinstance(scope[2],datetime) and scope[2].tzinfo is not None
        and 0 <= (now-scope[2]).total_seconds() <= max_scope_age
        and type(expected_client.client_id) is int and expected_client.client_id == plan['client_id']
        and type(expected_client._position_connection_epoch) is int
        and expected_client._position_connection_epoch == plan['epoch']
        and expected_client.isConnected() and not expected_client._stop_event.is_set()
        and expected_client._position_transport_available is True
        and tuple(expected_client._managed_accounts) == (plan['account'],), 'SCOPE')
    require(not engine._native_quarantined and engine.startup_recovery_complete()
        and engine.capital_authority.capital_scope is None
        and engine.capital_authority._capital_writer is None, 'OWNER')
    truth = core._latest_position_truth_snapshot
    require(truth is not None and truth.snapshot_status == 'HEALTHY'
        and getattr(truth.broker_positions.get(plan['symbol']),'quantity',0) == 0
        and getattr(truth.system_positions.get(plan['symbol']),'quantity',0) == 0, 'FLAT_TRUTH')
    candidates = engine.native_roundtrip_fee_candidates()
    require(len(candidates) == 1, 'COMPLETE_CANDIDATE')
    root, candidate = next(iter(candidates.items()))
    parent = engine._native_orders.get(root)
    require(parent is not None and candidate['root_order_id'] == root
        and candidate['source_client'] is expected_client and candidate['account'] == plan['account']
        and candidate['entry_terminal'] is True and candidate['entry_status'] == 'FILLED'
        and type(candidate['entry_requested_quantity']) is int
        and type(candidate['entry_filled_quantity']) is int
        and candidate['entry_requested_quantity'] == candidate['entry_filled_quantity'] == 1
        and candidate['decision_id'] == parent['decision_id']
        and parent['request']['symbol'] == plan['symbol'], 'CANDIDATE_BINDING')
    require(isinstance(response,dict) and set(response) == {'account','rows','end_received'}
        and response['account'] == plan['account'] and response['end_received'] is True
        and isinstance(response['rows'],list) and len(response['rows']) == 2, 'SUPPLIED_RESPONSE')
    require(response['rows'] == [dict(tag='CashBalance',value='123.45',currency=plan['currency']),
        dict(tag='AccruedCash',value='0',currency=plan['currency'])]
        and plan['currency'] == 'USD', 'SUPPLIED_CURRENCY')
    server_version = (180 if first_sdk_source is None else validate_pristine_first_sdk_scope(expected_client,first_sdk_source))
    require(expected_client.serverVersion() == server_version and len(fields) in (4,6)
        and fields[0] in {'62','63'} and fields[1] == '1'
        and fields[-1] == '' and fields[2].isdigit(), 'PACKET')
    request_id = int(fields[2])
    require(request_id > 0 and fields[2] == str(request_id)
        and not expected_client._request_id_conflicted(request_id), 'REQUEST_ID')
    context = expected_client._request_context_by_req_id.get(request_id)
    require(isinstance(context,dict) and context.get('request_type') == 'ACCOUNT_CURRENCY_STRICT', 'CONTEXT')
    if fields[0] == '62':
        require(fields == ['62','1',str(request_id),'All','$LEDGER','']
            and request_id not in owned_reads
            and expected_client._request_type_by_req_id.get(request_id) == 'ACCOUNT_CURRENCY_STRICT', 'REQUEST_PACKET')
        query = context.get('account_currency_query')
        require(isinstance(query,dict) and query.get('status') == 'PARTIAL'
            and query.get('account') == plan['account'] and type(query.get('client_id')) is int
            and query['client_id'] == plan['client_id'] and type(query.get('epoch')) is int
            and query['epoch'] == plan['epoch'] and query.get('completed_at') is None
            and query.get('currency') is None and type(query.get('tags')) is set and not query['tags']
            and type(query.get('deadline')) in (int,float) and math.isfinite(query['deadline'])
            and not query['event'].is_set() and monotonic_now < query['deadline'], 'QUERY')
        return request_id, 'REQUEST', context, query
    require(fields == ['63','1',str(request_id),''] and request_id in owned_reads, 'CANCEL_PACKET')
    previous = owned_reads[request_id]
    query = previous['query']
    require(previous['context'] is context and previous['client'] is expected_client
        and previous['epoch'] == plan['epoch'] and previous['account'] == plan['account']
        and not previous['cancelled'] and previous['end_observed'] is True
        and context.get('account_currency_query') is None
        and request_id not in expected_client._request_type_by_req_id, 'RETIREMENT')
    require(query['status'] == 'COMPLETE' and query['currency'] == plan['currency']
        and query['account'] == plan['account'] and type(query['client_id']) is int
        and query['client_id'] == plan['client_id'] and type(query['epoch']) is int
        and query['epoch'] == plan['epoch']
        and query['tags'] == {'CashBalance','AccruedCash'} and query['event'].is_set()
        and isinstance(query['completed_at'],datetime) and query['completed_at'].tzinfo is not None
        and 0 <= (now-query['completed_at']).total_seconds() <= max_scope_age, 'END_COMPLETION')
    return request_id, 'CANCEL', context, query

def validate_pristine_paper_history_read(*, actual_client, expected_client, core,
        plan, fields, owned_reads, timeframe_request, source_response, supplied_bars,
        now, monotonic_now, max_scope_age, first_sdk_source=None):
    """One supplied native history response; no management/result substitution."""
    def require(value, reason):
        if not value:
            raise ForbiddenExternalIO('PRISTINE_PAPER_HISTORY_CERTIFICATE:' + reason)
    require(actual_client is expected_client and core is not None
        and os.environ.get('EXECUTION_ENV') == 'TEST', 'CLIENT')
    engine = core.execution_engine
    scope = engine._native_scope
    require(core.run_mode.value == engine.run_mode.value == 'PAPER'
        and engine._native_callback_client() is expected_client
        and scope is not None and scope[0] == plan['account'] and scope[1] is expected_client
        and 0 <= (now-scope[2]).total_seconds() <= max_scope_age
        and expected_client.client_id == plan['client_id']
        and expected_client._position_connection_epoch == plan['epoch']
        and expected_client.isConnected() and not engine._native_quarantined, 'SCOPE')
    parents = [(key,row) for key,row in engine._native_orders.items()
        if row.get('side') in {'LONG','BUY'} and row.get('symbol') == plan['symbol']]
    require(len(parents) == 1, 'ROOT_COUNT')
    root_id,parent = parents[0]
    request = parent['request']
    stream = (request.get('setup_metadata') or {}).get('execution_stream') or {}
    require(parent.get('terminal') and parent.get('filled') == parent.get('requested') == 1
        and parent.get('protection_confirmed') and not parent.get('cached_update_in_progress')
        and parent.get('account') == plan['account'] and parent.get('native_client_id') == plan['client_id']
        and parent.get('native_connection_epoch') == plan['epoch'] and parent.get('security_id') == plan['con_id']
        and request.get('setup_family_id') == 'PREMARKET_HIGH_BREAK' and not request.get('relationship_context')
        and request.get('symbol') == plan['symbol'] and request.get('client_order_id') == root_id
        and request.get('stop_loss_price') == plan['stop_price']
        and request.get('invalidation_level') == plan['entry_price'] and request.get('take_profit_price') is None
        and stream.get('execution_trigger_timeframe') == timeframe_request.logical_timeframe == '10s', 'ROOT')
    # SDK server151 and180 omit the historical VERSION field. Use the actual
    # read encoder layout, distinct from quote requests' reqId at fields[2].
    server_version = (180 if first_sdk_source is None else validate_pristine_first_sdk_scope(expected_client,first_sdk_source))
    require(expected_client.serverVersion() == server_version and len(fields) == 24
        and fields[0] == '20' and fields[-1] == '', 'PACKET')
    require(fields[1].isdigit(), 'REQUEST_ID')
    request_id = int(fields[1])
    context = expected_client._request_context_by_req_id.get(request_id,{})
    state = expected_client._historical_states.get(request_id)
    require(request_id not in owned_reads
        and expected_client._request_type_by_req_id.get(request_id) == 'HISTORICAL_DATA'
        and context.get('request_type') == 'HISTORICAL_DATA'
        and context.get('symbol') == plan['symbol'] and context.get('con_id') == plan['con_id']
        and state is not None and state.get('status') == 'PENDING' and state.get('sent') is True
        and state.get('end_received') is False and state.get('streaming') is False
        and monotonic_now <= state['deadline']
        and not expected_client._request_id_conflicted(request_id), 'REQUEST_OWNER')
    require(fields[2] == str(plan['con_id']) and fields[3] == plan['symbol'] and fields[4] == 'STK'
        and fields[9] == plan['exchange'] and fields[11] == plan['currency']
        and fields[12] in {'',plan['symbol']} and fields[14] == '0'
        and fields[15] == '' and fields[16] == timeframe_request.bar_size_setting
        and fields[17] == str(timeframe_request.duration_seconds) + ' S'
        and fields[18:23] == ['0','TRADES','1','0',''], 'PARAMETERS')
    require(source_response.get('status') == 'COMPLETE_BARS'
        and source_response.get('end_received') is True and supplied_bars, 'SUPPLIED_COMPLETION')
    return request_id

try:
    # This check runs before application imports/cache setup/constructor. The
    # startup guard also blocks native curl transfers, which socket patches do
    # not observe. Missing guard inheritance must fail before any acquisition.
    startup_guard = sys.modules.get('sitecustomize')
    guard_path = Path(getattr(startup_guard, '__file__', '')).resolve()
    if str(guard_path) != os.environ.get('COLD_CORE_EXPECTED_OFFLINE_GUARD'):
        raise ForbiddenExternalIO('COLD_CORE_OFFLINE_STARTUP_GUARD_MISSING')
    report['offline_guard'] = dict(path=str(guard_path), native_curl_checked=False)
    report['native_curl_denials'] = []
    # Observe the existing deny function without replacing either transfer entry
    # point or its identity. The profile is owned by this bounded child only.
    native_deny_code = getattr(getattr(startup_guard, '_deny_native_transfer', None), '__code__', None)
    previous_profile = sys.getprofile()
    previous_thread_profile = threading.getprofile()
    def observe_native_denial(frame, event, arg):
        if event == 'call' and frame.f_code is native_deny_code:
            report['native_curl_denials'].append(dict(thread_id=threading.get_ident()))
        if previous_profile is not None:
            previous_profile(frame, event, arg)
    sys.setprofile(observe_native_denial)
    threading.setprofile(observe_native_denial)
    if 'curl_cffi' in sys.modules:
        from curl_cffi import Curl, AsyncCurl
        if (Curl.perform is not startup_guard._deny_native_transfer
                or AsyncCurl.add_handle is not startup_guard._deny_native_transfer):
            raise ForbiddenExternalIO('COLD_CORE_NATIVE_CURL_GUARD_MISSING')
        report['offline_guard']['native_curl_checked'] = True
    from ibapi.client import EClient
    from ibapi.contract import Contract, ContractDetails
    from ibapi.order import Order
    from ibapi.message import OUT
    from src.config.config_resolver import set_config_overrides
    from src.adapters.brokers.ibkr.ibkr_client import IbkrClient
    from src.adapters.brokers.ibkr import ibkr_connection_manager as connection_module
    from src.core.managers import connection_manager as core_connection_module
    from src.brokers import ibkr_live_broker as broker_module
    from src.core import orchestrator as core_module
    from src.execution import execution_engine as execution_module
    from src.execution import position_truth, post_fill_lifecycle_engine
    from src.ibkr.position_snapshot import BrokerPositionResult
    from src.ibkr.mutation_audit import snapshot as mutation_snapshot
    from src.scanner import scanner_runner
    from src.scanner.providers import factory as scanner_factory
    from src.scanner.providers.base import QuoteData, IntradayStats
    from src.strategies.common.candles.candle_types import Candle
    from src.strategies.ross_momentum.patterns import pattern_trace

    overrides = dict(RUN_MODE='PAPER', RUN_MODE_EFFECTIVE='PAPER',
        EXECUTION_ENABLED=True, RISK_PROFILE='SMALL',
        IBKR_READONLY_ENABLED=False, IBKR_ORDER_SUBMISSION_ENABLED=True,
        IBKR_ORDER_TRANSLATION_ENABLED=True, IBKR_API_WRITE_ALLOWED=True,
        IBKR_KILL_SWITCH=False, IBKR_FALLBACK_ENABLED=False,
        FORCE_CLEAN_START=False, LEARNING_ENABLED=False,
        MANUAL_FOCUS_ENABLED=False, SELECTED_STRATEGY='ross_momentum',
        ROSS_MOMENTUM_STRATEGY_ENABLED=True, PERSISTENCE_SQLITE_PATH=database_path)
    overrides.update(facts.get('config', {}))
    scenarios = facts.get('cycle_scenarios')
    if scenarios is not None:
        if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 12:
            raise ValueError('COLD_CORE_SCENARIOS_MUST_BE_A_LIST_OF_ONE_TO_TWELVE')
        if any(not isinstance(row, dict) or not row.get('name') for row in scenarios):
            raise ValueError('COLD_CORE_SCENARIOS_REQUIRE_NAMED_RAW_EXTERNAL_BUNDLES')
    base_overrides = copy.deepcopy(overrides)
    set_config_overrides(overrides)
    if facts.get('now') or facts.get('cycle_scenarios') is not None:
        observed = (datetime.fromisoformat(facts['now']) if facts.get('now')
                    else datetime.now(timezone.utc))
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls.fromtimestamp(observed.timestamp(), tz=tz)
        # The clock is an external fact, not an admission/recovery outcome.
        for module in (core_module, execution_module, position_truth,
                       post_fill_lifecycle_engine, broker_module, scanner_runner,
                       pattern_trace):
            module.datetime = Clock
    else:
        observed = datetime.now(timezone.utc)
    base_observed = observed
    if observe_pristine_cycle:
        # Existing joined fixtures treat this UTC clock and canonical cache as
        # external inputs. Classification, maintenance and Focus remain real.
        from src.news import evidence_store, news_intelligence_service, standalone_lookup, maintenance, batch_rss_adapter, news_fetcher
        from src.strategies.ross_momentum.policy import catalyst_policy
        from src.domain import quote_freshness
        from src.market_data import float_provider, reference_resolver, market_data_snapshot_manager
        from src.ibkr import market_data_client as source_quote_module
        from src.adapters.brokers.ibkr import ibkr_client as native_callback_module
        from src.adapters.brokers.ibkr import ibkr_order_submitter as native_submitter_module
        from src.config import system_config as risk_calendar_module
        from src.utils import time_utils as risk_utc_module
        import time as real_elapsed_time
        class ExternalUtcClock:
            @staticmethod
            def time():
                return observed.timestamp()
            def __getattr__(self,name):
                return getattr(real_elapsed_time,name)
        utc_clock = ExternalUtcClock()
        # UTC facts are local module dependencies. Do not patch shared time.time
        # or the real monotonic scheduling/timeout clocks.
        for module in (scanner_runner,catalyst_policy,news_fetcher,batch_rss_adapter):
            module.time = utc_clock
        for module in (evidence_store, news_intelligence_service, standalone_lookup, quote_freshness,
                       float_provider,reference_resolver,market_data_snapshot_manager,source_quote_module,native_callback_module,
                       maintenance,batch_rss_adapter,news_fetcher,risk_calendar_module,risk_utc_module,
                       native_submitter_module):
            module.datetime = Clock
        report['external_clock'] = dict(utc=observed.isoformat(),
            monotonic_unchanged=utc_clock.monotonic is real_elapsed_time.monotonic)
        # Supplied numeric fundamentals enter through their actual cache writer,
        # never by replacing symbol enrichment or its float gate.
        float_store = float_provider.FloatProvider()
        report['supplied_float_observations'] = []
        for symbol, row in facts.get('candidate_observations', {}).items():
            value = row.get('float_shares')
            if type(value) is int and value > 0:
                float_store.record_discovery(symbol, value, 'SUPPLIED_SYNTHETIC_OBSERVATION')
                report['supplied_float_observations'].append(dict(symbol=symbol, value=value,
                    source='SUPPLIED_SYNTHETIC_OBSERVATION'))
        from src.news.evidence_store import CanonicalNewsEvidenceStore, evidence_from_mapping
        news_request = scanner_runner._ross_news_request()
        source_evidence = facts.get('news_evidence', {})
        news_items = {symbol: tuple(evidence_from_mapping(row, request=news_request)
            for row in rows) for symbol, rows in source_evidence.items()}
        if any(item is None for rows in news_items.values() for item in rows):
            raise ValueError('SUPPLIED_CANONICAL_NEWS_EVIDENCE_INVALID')
        report['news_cache_seed_receipt'] = plain(CanonicalNewsEvidenceStore(
            Path(os.environ['NEWS_CACHE_FILE'])).write(news_items, news_request,
            retrieval_by_symbol=facts.get('news_last_retrieval', {})))
        if report['news_cache_seed_receipt'].get('cache_write_failed'):
            raise ValueError('SUPPLIED_CANONICAL_NEWS_CACHE_WRITE_FAILED')
        # Neither proof enrolls atomic/operational capital. PAPER reuses the
        # existing unenrolled process-local owners, not restart authority.
        from src.storage.storage_engine import StorageEngine
        from src.storage.sqlite_store import SQLiteStore
        report['capital_enrollment_attempts'] = []
        def forbid_capital_enrollment(*args, **kwargs):
            report['capital_enrollment_attempts'].append('initialize_synthetic_capital_scope')
            raise ForbiddenExternalIO('PRISTINE_READONLY_CAPITAL_ENROLLMENT_FORBIDDEN')
        StorageEngine.initialize_synthetic_capital_scope = forbid_capital_enrollment
        SQLiteStore.initialize_synthetic_capital_scope = forbid_capital_enrollment

    account = facts.get('account', 'SYNTHETIC_TEST')
    client_id = int(facts.get('client_id', 999))
    client = IbkrClient('offline.invalid', 7497, client_id, 1, 'LIVE', False)
    connected = [True]
    if facts.get('observe_pristine_paper_first_sdk_zero_fee_feedback'):
        validate_pristine_first_sdk_opt_in(facts)
        # Capture the accepted fixture's real SDK owners BEFORE installing the
        # global denies. Only its exclusive adapter may enter MemorySocket.
        sys.path.insert(0,str(guard_path.parent.parent))
        from test_ibkr_cached_client_access import (
            native_commission_decoder_source as _FIRST_SDK_INITIALIZER,
            _NATIVE_SDK_CONNECT as _FIRST_SDK_CONNECT,
            _NATIVE_SOURCE_CONNECT as _FIRST_NATIVE_CONNECT)
        from ibapi.connection import Connection
        from pytest import MonkeyPatch
        _FIRST_SDK_CONNECT_CODE = _FIRST_SDK_CONNECT.__code__
        _FIRST_NATIVE_CONNECT_CODE = _FIRST_NATIVE_CONNECT.__code__
        EClient.connect = no_network
        Connection.connect = no_network
        first_sdk_patcher = MonkeyPatch()
        first_sdk_source = bootstrap_pristine_first_sdk(client,first_sdk_patcher,account=account,clock=Clock)
        report['first_sdk_bootstrap'] = dict(server_version=client.serverVersion(),client_id=client.clientId,
            account=tuple(client._managed_accounts),epoch=client._position_connection_epoch,
            attempts=client._commission_connection_attempts,packets=copy.deepcopy(first_sdk_source.bootstrap_packets),
            reader_alive=first_sdk_source.initial_reader.is_alive(),worker_alive=first_sdk_source.initial_worker.is_alive(),
            global_denies_restored=EClient.connect is no_network and Connection.connect is no_network)
    else:
        client.isConnected = lambda: connected[0]
        client.serverVersion_ = 180
        client._position_connection_epoch = int(facts.get('epoch', 0))
        client._managed_accounts = [account]
        client._managed_accounts_event.set()
        client.nextValidId(int(facts.get('next_order_id', 1000)))
    positions = [NS(**row) for row in facts.get('positions', [])]
    def native_inventory(rows):
        result = []
        for row in rows:
            contract = Contract()
            for key, value in row.get('contract', {}).items():
                setattr(contract, key, value)
            order = Order()
            for key, value in row.get('order', {}).items():
                setattr(order, key, value)
            result.append(NS(orderId=row['orderId'], contract=contract, order=order,
                             orderState=NS(**row.get('orderState', {}))))
        return result
    orders = native_inventory(facts.get('open_orders', []))
    client._open_orders_snapshot = {row.orderId: row for row in orders}

    def position_rows(*args, **kwargs):
        if external_fault in {'positions_missing', 'positions_incomplete'}:
            raise RuntimeError('SYNTHETIC_POSITION_INVENTORY_UNAVAILABLE')
        return copy.deepcopy(positions)

    def open_orders(*args, **kwargs):
        if external_fault in {'orders_missing', 'orders_incomplete'}:
            raise RuntimeError('SYNTHETIC_OPEN_ORDER_INVENTORY_UNAVAILABLE')
        return copy.deepcopy(orders)

    client.positions = position_rows
    client.openOrders = open_orders
    client.position_snapshot = lambda **kw: BrokerPositionResult(
        tuple(position_rows()), current_external_facts.get('position_status', 'COMPLETE'), account, observed)
    active_cycle = [None]
    active_scenario = [None]
    cached_order_status = client.cached_order_status
    def observe_cached_order_status(order_id, *args, **kwargs):
        report['cached_order_status_reads'].append({
            'native_id': order_id, 'cycle': active_cycle[0], 'scenario': active_scenario[0]})
        return cached_order_status(order_id, *args, **kwargs)
    client.cached_order_status = observe_cached_order_status

    # Supply discovery through its external provider protocol, never through a
    # prepared scanner payload, Focus row, pattern result or admission decision.
    raw_fields = frozenset(('symbol', 'company_name', 'long_name', 'aliases', 'con_id', 'exchange',
        'primary_exchange', 'trading_class', 'local_symbol', 'currency',
        'instrument_type', 'last_price', 'bid', 'ask', 'open', 'high', 'low',
        'close', 'prev_close', 'ref_close_rth', 'volume', 'float_shares',
        'current_intraday_volume', 'average_daily_volume_20d',
        'average_daily_volume_window_days', 'historical_outcome', 'historical_end_received',
        'volume_velocity_5m',
        'volume_velocity_15m', 'quote_timestamp_utc', 'quote_timestamp_source',
        'requested_market_data_type', 'returned_market_data_type',
        'market_data_type_confirmed', 'received_at_utc',
        'market_data_type_received_at_utc', 'request_id', 'snapshot_complete'))
    def candidate_inventory(rows):
        return {str(symbol).upper(): {key: copy.deepcopy(value)
            for key, value in row.items() if key in raw_fields}
            for symbol, row in rows.items()}
    def historical_inventory(streams):
        # This opt-in source clock is a datetime subclass. Preserve original
        # external timestamps while satisfying its ordinary datetime type checks;
        # retained-state cases keep their previous parser and clock behavior.
        parse_timestamp = (Clock.fromisoformat if observe_pristine_cycle
                           else datetime.fromisoformat)
        return {timeframe: [Candle(
            open=row['open'], high=row['high'], low=row['low'], close=row['close'],
            volume=row['volume'], timestamp=(parse_timestamp(row['timestamp'])
                if row.get('timestamp') else None)) for row in rows]
            for timeframe, rows in streams.items()}
    candidates = candidate_inventory(facts.get('candidate_observations', {}))
    source_bars = historical_inventory(facts.get('source_timeframe_bars', {}))
    availability_phase = [False]
    def external_call(kind, method, **details):
        entry = dict(method=method, cycle=active_cycle[0],
                     scenario=active_scenario[0], **details)
        key = ('availability_witness_calls' if availability_phase[0] else
               'external_provider_calls' if kind == 'provider' else 'external_history_calls')
        report[key].append(dict(kind=kind, **entry))

    class ExternalScannerFacts:
        source_name = 'IBKR'
        market_data_client = None
        last_scan_details = {'symbol_details': {symbol: dict(
            conId=row.get('con_id'), exchange=row.get('exchange'),
            primaryExchange=row.get('primary_exchange'),
            tradingClass=row.get('trading_class'), localSymbol=row.get('local_symbol'),
            currency=row.get('currency'), secType=row.get('instrument_type'),
            longName=row.get('long_name',row.get('company_name')),company_name=row.get('company_name'),
            aliases=row.get('aliases',())) for symbol, row in candidates.items()}}

        def connect(self):
            external_call('provider', 'connect')

        def disconnect(self):
            external_call('provider', 'disconnect')

        def get_top_gainers(self, limit, request=None):
            external_call('provider', 'get_top_gainers', limit=limit)
            return list(candidates)[:limit]

        def get_quote(self, symbol):
            external_call('provider', 'get_quote', symbol=symbol)
            row = candidates[symbol]
            return QuoteData(symbol=symbol, bid=row.get('bid'), ask=row.get('ask'),
                last=row.get('last_price'), vwap=None, open=row.get('open'),
                high=row.get('high'), low=row.get('low'),
                close=row.get('close', row.get('prev_close')), change_percent=None,
                volume=row.get('volume'), timestamp_utc=row.get('quote_timestamp_utc'),
                timestamp_source=row.get('quote_timestamp_source', 'UNKNOWN'),
                data_quality_flags=(), **{key: row[key] for key in (
                    'requested_market_data_type', 'returned_market_data_type',
                    'market_data_type_confirmed', 'received_at_utc',
                    'market_data_type_received_at_utc', 'request_id', 'snapshot_complete')
                    if key in row})

        def get_prev_close(self, symbol):
            external_call('provider', 'get_prev_close', symbol=symbol)
            return candidates[symbol].get('prev_close')

        def get_intraday_stats(self, symbol):
            external_call('provider', 'get_intraday_stats', symbol=symbol)
            row = candidates[symbol]
            return IntradayStats(
                current_intraday_volume=row.get('current_intraday_volume', row.get('volume')),
                current_volume_source_label='SUPPLIED_SYNTHETIC_OBSERVATION',
                average_daily_volume_20d=row.get('average_daily_volume_20d'),
                average_daily_volume_window_days=row.get('average_daily_volume_window_days'),
                relative_volume=None, relative_volume_category=None,
                volume_velocity_5m=row.get('volume_velocity_5m'),
                volume_velocity_15m=row.get('volume_velocity_15m'),
                volume_data_quality_flag=None,
                historical_outcome=row.get('historical_outcome'),
                historical_end_received=row.get('historical_end_received'))

        def get_float(self, symbol):
            external_call('provider', 'get_float', symbol=symbol)
            return candidates[symbol].get('float_shares')

        def get_previous_rth_close(self, identity):
            symbol = getattr(identity, 'symbol', identity)
            external_call('provider', 'get_previous_rth_close', symbol=symbol)
            return candidates[symbol].get('ref_close_rth')

        def get_average_daily_volume(self, identity, window):
            symbol = getattr(identity, 'symbol', identity)
            external_call('provider', 'get_average_daily_volume', symbol=symbol, window=window)
            row = candidates[symbol]
            return row.get('average_daily_volume_20d'), row.get('average_daily_volume_window_days')

        def get_daily_bars(self, identity, lookback_days, **kwargs):
            external_call('provider', 'get_daily_bars',
                symbol=getattr(identity, 'symbol', identity), lookback_days=lookback_days)
            return []  # No daily-history completion was supplied by these facts.

    scanner_facts = ExternalScannerFacts()
    def external_provider_factory(*, market_data_client=None, connection_manager=None):
        external_call('provider', 'build_provider')
        scanner_facts.market_data_client = market_data_client
        return scanner_facts
    scanner_runner.build_provider = external_provider_factory
    scanner_factory.build_provider = external_provider_factory
    def external_history(*, symbol, timeframe='1m', limit=50, **kwargs):
        external_call('history', 'get_intraday_bars', symbol=symbol,
                      timeframe=timeframe, limit=limit)
        bars = list(source_bars.get(timeframe, []))[-limit:] if symbol in candidates else []
        response = facts.get('historical_source_responses', {}).get(timeframe)
        if response is not None:
            from src.ibkr.market_data_client import HistoricalDataResult
            from src.market_data.candidate_identity import CandidateIdentity
            return HistoricalDataResult(response['status'],tuple(bars),response['end_received'],
                contract_identity=CandidateIdentity(**response['contract_identity']))
        return bars
    pattern_trace.get_intraday_bars = external_history
    pattern_trace.historical_data_provider.get_intraday_bars = external_history
    # This availability witness tests only the external fixture boundary.  Its
    # calls cannot be mistaken for discovery/history reads by an actual cycle.
    def external_availability_witness():
        availability_phase[0] = True
        try:
            return {
                'scope': 'RAW_EXTERNAL_FACTS_ONLY_NO_ELIGIBILITY_PROOF',
                'raw_candidate_fields': sorted(raw_fields), 'candidates': copy.deepcopy(candidates),
                'quotes': {symbol: plain(scanner_facts.get_quote(symbol)) for symbol in candidates},
                'bar_counts': {symbol: {timeframe: len(external_history(
                    symbol=symbol, timeframe=timeframe, limit=len(bars)))
                    for timeframe, bars in source_bars.items()} for symbol in candidates},
                'provider_boundary_installed': True, 'history_boundary_installed': True}
        finally:
            availability_phase[0] = False
    report['external_fact_availability'] = external_availability_witness()
    # Feed callback facts through the real callback owner and real cache reader.
    def apply_callback_frames(bundle):
        frames = bundle.get('callback_frames', [bundle.get('callbacks', {})])
        for frame in frames:
            for order_id, update in frame.items():
                client.orderStatus(int(order_id), update.get('status', 'Submitted'),
                    update.get('filled', 0), update.get('remaining', 0),
                    update.get('avgFillPrice', 0), update.get('permId', 0),
                    update.get('parentId', 0), update.get('lastFillPrice', 0),
                    update.get('clientId', client_id), update.get('whyHeld', ''), 0)
        return copy.deepcopy(frames)
    apply_callback_frames(facts)

    manager = connection_module.IbkrConnectionManager(connection_module.IbkrConnectionConfig(
        'offline.invalid', 7497, client_id, 1, 'LIVE', False, 'PAPER'))
    manager._client = client
    manager._connected_client_id = client_id
    manager._connection_generation = int(facts.get('epoch', 0))
    report['initial_external_scope'] = plain(dict(account=client._managed_accounts[0],
        client_id=client.client_id, epoch=client._position_connection_epoch))
    def shared_manager(**kwargs):
        if fault == 'constructor_failure':
            raise RuntimeError('SYNTHETIC_EXTERNAL_MANAGER_FACTORY_FAILURE')
        return manager
    for module in (connection_module, core_connection_module, broker_module):
        module.get_shared_ibkr_connection_manager = shared_manager
    connection_module._default_manager = manager

    def apply_external_scenario(scenario):
        # Independent fact variants share this already constructed Core.  Reset
        # external observations to the original bundle, then apply the variant;
        # no application latch, ledger, reservation or owner is reset here.
        global observed, account, client_id, positions, orders, candidates
        global source_bars, current_external_facts, external_fault
        if first_sdk_source is not None:
            raise ForbiddenExternalIO('PRISTINE_FIRST_SDK_SCENARIO_REBIND_FORBIDDEN')
        current_external_facts = copy.deepcopy(base_external_facts)
        current_external_facts.update({key: copy.deepcopy(value)
            for key, value in scenario.items() if key != 'name'})
        observed = (datetime.fromisoformat(current_external_facts['now'])
                    if current_external_facts.get('now') else base_observed)
        account = current_external_facts.get('account', 'SYNTHETIC_TEST')
        client_id = int(current_external_facts.get('client_id', 999))
        external_fault = current_external_facts.get('fault', fault)
        connected[0] = bool(current_external_facts.get('connected', True))
        client.client_id = client_id
        client.clientId = client_id
        client._position_connection_epoch = int(current_external_facts.get('epoch', 0))
        client._managed_accounts = [account]
        manager._connected_client_id = client_id
        manager._connection_generation = int(current_external_facts.get('epoch', 0))
        positions = [NS(**row) for row in current_external_facts.get('positions', [])]
        orders = native_inventory(current_external_facts.get('open_orders', []))
        client._open_orders_snapshot = {row.orderId: row for row in orders}
        candidates = candidate_inventory(current_external_facts.get('candidate_observations', {}))
        source_bars = historical_inventory(current_external_facts.get('source_timeframe_bars', {}))
        scanner_facts.last_scan_details = {'symbol_details': {symbol: dict(
            conId=row.get('con_id'), exchange=row.get('exchange'),
            primaryExchange=row.get('primary_exchange'),
            tradingClass=row.get('trading_class'), localSymbol=row.get('local_symbol'),
            currency=row.get('currency'), secType=row.get('instrument_type'),
            longName=row.get('company_name')) for symbol, row in candidates.items()}}
        scenario_overrides = copy.deepcopy(base_overrides)
        scenario_overrides.update(current_external_facts.get('config', {}))
        set_config_overrides(scenario_overrides)
        frames = apply_callback_frames(current_external_facts)
        return plain(dict(name=scenario['name'], now=observed, account=account, client_id=client_id,
            epoch=client._position_connection_epoch, connected=connected[0],
            position_status=current_external_facts.get('position_status', 'COMPLETE'),
            positions=copy.deepcopy(current_external_facts.get('positions', [])),
            open_orders=copy.deepcopy(current_external_facts.get('open_orders', [])),
            callback_frames=frames, config=scenario_overrides, fault=external_fault,
            candidate_observations=copy.deepcopy(candidates),
            source_timeframe_bars=copy.deepcopy(source_bars)))

    # Keep the audited SDK methods/encoder.  Observe before forwarding, then
    # stop at the synthetic sendMsg boundary before any real transport exists.
    for method_name in ('placeOrder', 'cancelOrder', 'reqGlobalCancel'):
        sdk_method = getattr(EClient, method_name)
        def observed_sdk(self, *args, _name=method_name, _method=sdk_method, **kwargs):
            row = {'method': _name, 'native_id': args[0] if args else None,
                   'scenario': active_scenario[0], 'cycle': active_cycle[0]}
            if _name == 'placeOrder':
                contract, native = args[1:3]
                row.update(symbol=contract.symbol, con_id=contract.conId,
                    quantity=native.totalQuantity, order_type=native.orderType,
                    stop_price=native.auxPrice, parent_id=native.parentId,
                    order_ref=native.orderRef)
            report['sdk_attempts'].append(row)
            return _method(self, *args, **kwargs)
        setattr(EClient, method_name, observed_sdk)

    owned_quote_reads = set()
    owned_history_reads = set()
    owned_currency_reads = {}
    def send_message(message):
        fields = str(message).split('\0')
        opcode = fields[0]
        report['wire_attempts'].append({'opcode': opcode,
            'mutation': opcode in {str(OUT.PLACE_ORDER), str(OUT.CANCEL_ORDER), str(OUT.REQ_GLOBAL_CANCEL)}})
        if report['wire_attempts'][-1]['mutation']:
            raise SyntheticWriteBoundary('COLD_CORE_SYNTHETIC_NATIVE_WRITE_ATTEMPT')
        if observe_pristine_cycle:
            # Only this supplied security's real read encoders reach a memory
            # transport. The actual Native callbacks retain request ownership.
            if (facts.get('observe_pristine_paper_positive_fee_feedback')
                    and facts.get('observe_pristine_paper_cycle') and opcode in {'62','63'}):
                from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
                request_id,role,context,query = validate_pristine_paper_currency_read(
                    actual_client=client,expected_client=client,core=core,
                    plan=facts['paper_memory_plan'],fields=fields,owned_reads=owned_currency_reads,
                    response=facts['paper_currency_response'],now=observed,
                    monotonic_now=real_elapsed_time.monotonic(),
                    max_scope_age=get_ibkr_snapshot_max_age_seconds(),
                    **({'first_sdk_source':first_sdk_source} if facts.get('observe_pristine_paper_first_sdk_zero_fee_feedback') else {}))
                if role == 'REQUEST':
                    record = dict(context=context,query=query,client=client,
                        account=query['account'],epoch=query['epoch'],cancelled=False,end_observed=False)
                    owned_currency_reads[request_id] = record
                    response = facts['paper_currency_response']
                    for row in response['rows']:
                        client.accountSummary(request_id,response['account'],row['tag'],row['value'],row['currency'])
                    client.accountSummaryEnd(request_id)
                    record['end_observed'] = (query['status']=='COMPLETE' and query['event'].is_set()
                        and query['currency']==facts['paper_memory_plan']['currency']
                        and query['tags']=={'CashBalance','AccruedCash'})
                    report['native_read_requests'].append(dict(opcode=opcode,request_id=request_id,
                        request_type='ACCOUNT_CURRENCY_STRICT',account=query['account'],
                        epoch=query['epoch'],currency=query['currency'],status=query['status'],
                        completed_at=plain(query['completed_at']),end_observed=record['end_observed']))
                else:
                    owned_currency_reads[request_id]['cancelled'] = True
                    report['native_read_requests'].append(dict(opcode=opcode,request_id=request_id,
                        request_type='OWNED_ACCOUNT_CURRENCY_CANCEL',account=query['account'],
                        epoch=query['epoch'],currency=query['currency'],status=query['status'],
                        active_type_absent=request_id not in client._request_type_by_req_id,
                        query_retired=context.get('account_currency_query') is None))
                return  # Synthetic read cleanup, never an order cancellation.
            if opcode in {str(OUT.REQ_CONTRACT_DATA),str(OUT.REQ_MKT_DATA)}:
                request_id = int(fields[2])
                context = client._request_context_by_req_id.get(request_id,{})
                symbol = context.get('symbol')
                row = candidates.get(symbol)
                expected = ('CONTRACT_DETAILS' if opcode==str(OUT.REQ_CONTRACT_DATA) else 'MARKET_DATA')
                if row is None or context.get('request_type')!=expected or context.get('con_id') not in (0,row['con_id']):
                    raise ForbiddenExternalIO('UNSUPPLIED_SYNTHETIC_READ_SCOPE:'+opcode)
                report['native_read_requests'].append(dict(opcode=opcode,request_id=request_id,
                    symbol=symbol,request_type=expected,con_id=row['con_id']))
                if expected=='CONTRACT_DETAILS':
                    detail=ContractDetails();detail.contract=Contract()
                    for name,value in dict(symbol=symbol,conId=row['con_id'],exchange=row['exchange'],
                            currency=row['currency'],secType=row['instrument_type'],localSymbol=row['local_symbol']).items():
                        setattr(detail.contract,name,value)
                    detail.longName=row['company_name']
                    client.contractDetails(request_id,detail)
                    client.contractDetailsEnd(request_id)
                else:
                    owned_quote_reads.add(request_id)
                    client.marketDataType(request_id,{'LIVE':1,'FROZEN':2,'DELAYED':3,'DELAYED_FROZEN':4}[row['returned_market_data_type']])
                    for kind,value in ((1,row['bid']),(2,row['ask']),(4,row['last_price']),(9,row['prev_close'])):
                        client.tickPrice(request_id,kind,value,None)
                    client.tickSize(request_id,8,row['volume'])
                    stamp=datetime.fromisoformat(row['quote_timestamp_utc'])
                    client.tickString(request_id,45,str(int(stamp.timestamp())))
                    if row['snapshot_complete'] is True:
                        client.tickSnapshotEnd(request_id)
                return
            if opcode==str(OUT.REQ_MARKET_DATA_TYPE):
                # Actual quote owner selects its request mode before reqMktData.
                if int(fields[2])!=client._requested_market_data_type_code or not candidates:
                    raise ForbiddenExternalIO('UNSUPPLIED_SYNTHETIC_READ_MODE')
                report['native_read_requests'].append(dict(opcode=opcode,request_type='MARKET_DATA_MODE',mode=int(fields[2])))
                return
            if opcode==str(OUT.CANCEL_MKT_DATA) and int(fields[2]) in owned_quote_reads:
                report['native_read_requests'].append(dict(opcode=opcode,request_type='OWNED_MARKET_DATA_CANCEL',request_id=int(fields[2])))
                return  # Read subscription cleanup, never an order cancellation.
            if facts.get('observe_pristine_paper_cycle') and opcode==str(OUT.REQ_HISTORICAL_DATA):
                from src.adapters.data.historical_bar_timeframes import resolve_intraday_timeframe_request
                from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
                from ibapi.common import BarData
                request = resolve_intraday_timeframe_request(timeframe='10s',requested_bars=10)
                bars = source_bars.get('10s',[])
                request_id = validate_pristine_paper_history_read(actual_client=client,expected_client=client,
                    core=core,plan=facts['paper_memory_plan'],fields=fields,owned_reads=owned_history_reads,
                    timeframe_request=request,source_response=facts.get('historical_source_responses',{}).get('10s',{}),
                    supplied_bars=bars,now=observed,monotonic_now=real_elapsed_time.monotonic(),
                    max_scope_age=get_ibkr_snapshot_max_age_seconds(),
                    **({'first_sdk_source':first_sdk_source} if facts.get('observe_pristine_paper_first_sdk_zero_fee_feedback') else {}))
                owned_history_reads.add(request_id)
                report['native_read_requests'].append(dict(opcode=opcode,request_type='HISTORICAL_DATA',
                    request_id=request_id,symbol=facts['paper_memory_plan']['symbol'],timeframe='10s',
                    source_dates=[bar.timestamp.isoformat() for bar in bars],source_count=len(bars)))
                for supplied in bars:
                    bar = BarData()
                    # Existing callback date field carries the ORIGINAL supplied
                    # aware ISO time. This is no broker date-wire normalization
                    # certificate and never retimes a pre-fill completed bar.
                    bar.date = supplied.timestamp.isoformat()
                    for name in ('open','high','low','close','volume'):
                        setattr(bar,name,getattr(supplied,name))
                    client.historicalData(request_id,bar)
                client.historicalDataEnd(request_id,bars[0].timestamp.isoformat(),bars[-1].timestamp.isoformat())
                return  # Normal End-complete nonstreaming reads need no opcode25.
        raise ForbiddenExternalIO('UNSUPPLIED_SYNTHETIC_PROVIDER_REQUEST:' + opcode)
    client.sendMsg = send_message
    EClient.connect = no_network
    if facts.get('observe_pristine_paper_cycle'):
        from types import MethodType
        from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
        paper_plan = facts['paper_memory_plan']
        report['synthetic_memory_dispatches'] = []
        report['paper_external_steps'] = []
        delivered_fee_executions = set()
        if facts.get('observe_pristine_paper_positive_fee_feedback'):
            report['positive_fee_callbacks'] = []
        if first_sdk_source is not None:
            report['first_sdk_fee_callbacks'] = []
        report['trade_exit_shutdown_calls'] = []
        from src.execution.trade_exit_engine import TradeExitEngine
        actual_trade_exit_shutdown = TradeExitEngine.shutdown
        def observed_trade_exit_shutdown(actual_engine, *args, **kwargs):
            report['trade_exit_shutdown_calls'].append(dict(cycle=active_cycle[0],
                core_owned=core is not None and actual_engine is core.trade_exit_engine))
            return actual_trade_exit_shutdown(actual_engine, *args, **kwargs)
        TradeExitEngine.shutdown = observed_trade_exit_shutdown
        def memory_place_order(actual_client, native_id, contract, native):
            committed = native_namespace(database_snapshot())
            root_id, role = validate_pristine_paper_memory_write(
                actual_client=actual_client, expected_client=client, core=core, plan=paper_plan,
                dispatches=report['synthetic_memory_dispatches'], native_id=native_id,
                contract=contract, native=native, committed=committed,
                risk_rows=report.get('risk_evaluations', []), now=observed,
                max_scope_age=get_ibkr_snapshot_max_age_seconds())
            # No SDK encoder/sendMsg call: this single instance has a provided
            # memory-only external exchange. Global mutation barriers remain.
            report['synthetic_memory_dispatches'].append(dict(role=role, native_id=native_id,
                root_id=root_id, contract=plain(contract), order=plain(native),
                committed_before_ack=copy.deepcopy(committed), cycle=active_cycle[0]))
            supplied_contract = Contract()
            for name,value in dict(symbol=paper_plan['symbol'], conId=paper_plan['con_id'],
                    exchange=paper_plan['exchange'], currency=paper_plan['currency'], secType='STK').items():
                setattr(supplied_contract,name,value)
            supplied_order = copy.deepcopy(native)
            supplied_order.account = paper_plan['account']
            supplied_order.clientId = paper_plan['client_id']
            row = NS(orderId=native_id, contract=supplied_contract, order=supplied_order,
                orderState=NS(status='Submitted'))
            orders.append(row)
            client.openOrder(native_id, supplied_contract, supplied_order, row.orderState)
            client.orderStatus(native_id, 'Submitted', 0, 1, 0., native_id, native.parentId,
                0., paper_plan['client_id'], '', 0.)
        client.placeOrder = MethodType(memory_place_order,client)

    report['database_before'] = database_snapshot()
    report['native_before'] = native_namespace(report['database_before'])
    if fault == 'timeout':
        # Supervision-only adversity at a controlled external setup boundary.
        # No startup/recovery/admission owner or constructor outcome is replaced.
        report['stage'] = 'SUPERVISION_TIMEOUT_BEFORE_CORE_CONSTRUCTION'
        Path(report_path).write_text(json.dumps(plain(report), default=str), encoding='utf-8')
        threading.Event().wait(30)
    report['stage'] = 'CORE_CONSTRUCTION'
    # Invoke the ordinary constructor, including every actual startup owner.
    # If construction fails, process exit closes otherwise unreachable handles.
    try:
        report['constructor_count'] += 1
        core = core_module.CoreOrchestrator()
        report['constructor_complete'] = True
    except BaseException as exc:
        report['constructor_exception'] = exception_record(exc)
    engine = getattr(core, 'execution_engine', None)
    if engine is not None:
        report['after_constructor'] = engine_snapshot(engine)
        report['types'] = {'core': type(core).__module__ + '.' + type(core).__name__,
            'engine': type(engine).__module__ + '.' + type(engine).__name__,
            'provider': type(engine.provider).__module__ + '.' + type(engine.provider).__name__,
            'broker': type(engine.broker).__module__ + '.' + type(engine.broker).__name__,
            'manager': type(manager).__module__ + '.' + type(manager).__name__,
            'client': type(client).__module__ + '.' + type(client).__name__}
    report['database_after_constructor'] = database_snapshot()
    report['native_after_constructor'] = native_namespace(report['database_after_constructor'])
    if report['constructor_complete'] and observe_pristine_cycle:
        report['registry_evaluations'] = []
        report['decision_artifacts'] = []
        report['risk_evaluations'] = []
        report['focus_selections'] = []
        for strategy in core.strategy_runner.strategies:
            registry = getattr(strategy, '_pattern_registry', None)
            if registry is None:
                continue
            actual_registry_run = registry.run
            def observed_registry(inputs, _actual=actual_registry_run, **kwargs):
                result = _actual(inputs, **kwargs)
                report['registry_evaluations'].append(plain(dict(
                    result_count=len(result), results=result, source=inputs)))
                return result
            registry.run = observed_registry
        actual_artifact_builder = core_module.build_decision_artifact
        def observed_artifact(**kwargs):
            artifact = actual_artifact_builder(**kwargs)
            report['decision_artifacts'].append(plain(artifact))
            return artifact
        core_module.build_decision_artifact = observed_artifact
        actual_risk = core.risk_engine.evaluate_trade_intent
        def observed_risk(intent, *args, **kwargs):
            decision = actual_risk(intent, *args, **kwargs)
            report['risk_evaluations'].append(dict(intent=plain(intent), decision=plain(decision)))
            return decision
        core.risk_engine.evaluate_trade_intent = observed_risk
        actual_focus = scanner_runner._select_ross_focus_contexts
        def observed_focus(contexts, news, thresholds, **kwargs):
            result = actual_focus(contexts, news, thresholds, **kwargs)
            report['focus_selections'].append(dict(contexts=plain(contexts), news=plain(news),
                selected=plain(result)))
            return result
        scanner_runner._select_ross_focus_contexts = observed_focus
        if facts.get('observe_pristine_paper_cycle'):
            report['execution_results'] = []
            if facts.get('observe_pristine_paper_loss_feedback'):
                report['exposure_release_calls'] = []
                for label,owner in (('capital',core.execution_engine.capital_authority),
                        ('allocation',core.execution_engine.strategy_allocation_authority)):
                    actual_release = owner.release_exposure
                    def observed_release(*args,_actual=actual_release,_owner=owner,_label=label,**kwargs):
                        return observed_pristine_paper_exposure_release(_actual,_owner,_label,*args,**kwargs)
                    owner.release_exposure = observed_release
            actual_execute = core.execution_engine.execute_trade
            def observed_execute(decision):
                result = actual_execute(decision)
                report['execution_results'].append(plain(result))
                return result
            core.execution_engine.execute_trade = observed_execute
            report['selected_failure_evaluations'] = []
            actual_selected_failure = core.trade_management_engine.evaluate_selected_completed_failure
            def observed_selected_failure(order,bars,**kwargs):
                result = actual_selected_failure(order,bars,**kwargs)
                report['selected_failure_evaluations'].append(dict(root_id=order['request']['client_order_id'],
                    bars=plain(bars),result=plain(result),observed_at=plain(kwargs['observed_at'])))
                return result
            core.trade_management_engine.evaluate_selected_completed_failure = observed_selected_failure
    if report['constructor_complete']:
        def run_actual_cycle(scenario_name=None, scenario_cycle=None):
            index = len(report['cycles']) + 1
            if index > 26:
                raise ValueError('COLD_CORE_TOTAL_CYCLE_LIMIT_IS_TWENTY_SIX')
            active_cycle[0] = index
            report['stage'] = 'CORE_CYCLE_' + str(index)
            cycle = {'index': index, 'scenario': scenario_name,
                     'scenario_cycle': scenario_cycle,
                     'cached_reads_before': len(report['cached_order_status_reads'])}
            events_before = len(core.event_collector.snapshot_all())
            try:
                report['cycle_attempted'] = True
                cycle['result'] = core.run_once()
                report['cycle_result'] = cycle['result']
            except BaseException as exc:
                cycle['exception'] = exception_record(exc)
                report['cycle_exception'] = cycle['exception']
            cycle['engine'] = engine_snapshot(core.execution_engine)
            governor = core.daily_risk_governor
            cycle['daily_risk'] = dict(state=plain(governor.state),
                decision=(governor.last_decision.to_dict() if governor.last_decision is not None else None))
            if facts.get('observe_pristine_paper_positive_fee_feedback'):
                from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
                cycle['fee_feedback'] = plain(core.trade_lifecycle_engine.native_fee_feedback_snapshot(
                    now=observed,max_age_seconds=get_ibkr_snapshot_max_age_seconds()))
                cycle['fee_source_observations'] = plain(tuple({key:
                    (dict(value) if key in {'execution','first_report','latest_report'} and value is not None else value)
                    for key,value in row.items()}
                    for dispatch in report['synthetic_memory_dispatches']
                    for row in client.cached_native_execution_fees(dispatch['native_id'])))
            if facts.get('observe_pristine_paper_loss_feedback'):
                cycle['exposure_release_calls_after'] = len(report['exposure_release_calls'])
            cycle['database'] = database_snapshot()
            cycle['native'] = native_namespace(cycle['database'])
            cycle['cached_reads_after'] = len(report['cached_order_status_reads'])
            cycle['sdk_attempts_after'] = len(report['sdk_attempts'])
            cycle['events'] = plain(core.event_collector.snapshot_all()[events_before:])
            cycle['fault_events'] = [event for event in cycle['events']
                if event.get('event_type') in {'FAULT_DETECTED', 'FAULT_ACTION_TAKEN'}]
            cycle['external_provider_calls_after'] = len(report['external_provider_calls'])
            cycle['external_history_calls_after'] = len(report['external_history_calls'])
            report['cycles'].append(cycle)
            report['after_cycle'] = cycle['engine']
            return index
        paper_steps = facts.get('paper_cycle_steps')
        if paper_steps is not None:
            if (not facts.get('observe_pristine_paper_cycle') or scenarios is not None
                    or not isinstance(paper_steps,list) or not 1 <= len(paper_steps) <= 5):
                raise ValueError('PRISTINE_PAPER_STEPS_INVALID')
            from decimal import Decimal
            from ibapi.execution import Execution
            report['paper_execution_callbacks'] = []
            for step in paper_steps:
                observed = datetime.fromisoformat(step['now'])
                if 'market_quote' in step:
                    from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
                    update = validate_pristine_paper_market_fact(plan=facts['paper_memory_plan'],
                        quote=step['market_quote'],now=observed,max_age=get_ibkr_snapshot_max_age_seconds())
                    candidates[facts['paper_memory_plan']['symbol']].update(update)
                positions = [NS(**row) for row in step['positions']]
                supplied_orders = []
                for raw in step['open_orders']:
                    matches = [row for row in report['synthetic_memory_dispatches'] if row['role']==raw['leg']]
                    if len(matches)!=1:
                        raise ForbiddenExternalIO('UNBOUND_PAPER_INVENTORY_LEG')
                    bound = matches[0]
                    value = copy.deepcopy(raw)
                    value['orderId'] = bound['native_id']
                    if value['order'].get('orderRef') == '$RETAINED_ROOT':
                        value['order']['orderRef'] = bound['root_id']
                    if value['order'].get('orderRef') == 'PROTECT|$RETAINED_ROOT':
                        value['order']['orderRef'] = 'PROTECT|' + bound['root_id']
                    if value['order'].get('parentId') == '$ENTRY_NATIVE_ID':
                        value['order']['parentId'] = next(row['native_id'] for row in
                            report['synthetic_memory_dispatches'] if row['role']=='entry')
                    supplied_orders.extend(native_inventory([value]))
                orders = supplied_orders
                client._open_orders_snapshot = {row.orderId:row for row in orders}
                for row in orders:
                    client.openOrder(row.orderId,row.contract,row.order,row.orderState)
                for raw in step.get('executions', []):
                    bound = validate_pristine_paper_execution_fact(actual_client=client,expected_client=client,
                        core=core,plan=facts['paper_memory_plan'],dispatches=report['synthetic_memory_dispatches'],
                        raw=raw,now=observed)
                    contract = Contract()
                    for name,value in raw['contract'].items():
                        setattr(contract,name,value)
                    execution = Execution()
                    for name,value in raw['execution'].items():
                        setattr(execution,name,Decimal(str(value)) if name in {'shares','cumQty'} else value)
                    execution.orderId = bound['native_id']
                    client.execDetails(-1,contract,execution)
                    status = raw['status']
                    client.orderStatus(bound['native_id'],status['status'],status['filled'],
                        status['remaining'],status['avgFillPrice'],bound['native_id'],bound['order']['parentId'],
                        status['avgFillPrice'],raw['execution']['clientId'],'',0.)
                    report['paper_execution_callbacks'].append(dict(leg=raw['leg'],native_id=bound['native_id'],
                        root_id=bound['root_id'],parent_id=bound['order']['parentId'],execution=plain(execution)))
                for raw_fee in step.get('commissions',[]):
                    if not facts.get('observe_pristine_paper_positive_fee_feedback'):
                        raise ForbiddenExternalIO('UNSUPPLIED_PRISTINE_PAPER_FEE_CALLBACK')
                    destination = 'positive_fee_callbacks' if first_sdk_source is None else 'first_sdk_fee_callbacks'
                    report[destination].append(deliver_pristine_paper_fee_fact(
                        client=client,core=core,plan=facts['paper_memory_plan'],
                        dispatches=report['synthetic_memory_dispatches'],raw=raw_fee,
                        delivered=delivered_fee_executions,now=observed,
                        **({'first_sdk_source':first_sdk_source} if facts.get('observe_pristine_paper_first_sdk_zero_fee_feedback') else {})))
                report['paper_external_steps'].append(plain(step))
                run_actual_cycle(step['name'],1)
        elif scenarios is None:
            cycle_count = int(facts.get('cycles', 2))
            if not 0 <= cycle_count <= 5:
                raise ValueError('COLD_CORE_CYCLE_COUNT_MUST_BE_BETWEEN_ZERO_AND_FIVE')
            for _ in range(cycle_count):
                run_actual_cycle()
        else:
            report['scenario_scope'] = 'EXTERNAL_ADVERSITY_AFTER_ONE_FRESH_CONSTRUCTOR'
            for scenario in scenarios:
                active_scenario[0] = scenario['name']
                scenario_report = {'name': scenario['name'], 'cycle_indices': [],
                    'applied_external_facts': apply_external_scenario(scenario),
                    'external_fact_availability': external_availability_witness()}
                report['scenarios'].append(scenario_report)
                for index in (1, 2):
                    scenario_report['cycle_indices'].append(run_actual_cycle(scenario['name'], index))
            active_scenario[0] = None
        active_cycle[0] = None
        report['events'] = plain(core.event_collector.snapshot_all())
        report['registry'] = plain(core.trade_registry.snapshot())
    report['database_after_cycle'] = database_snapshot()
    report['native_after_cycle'] = native_namespace(report['database_after_cycle'])
    if facts.get('observe_pristine_paper_cycle'):
        report['native_history_pending_ids'] = sorted(client._historical_states)
    report['mutation_attempts'] = mutation_snapshot()
    if (facts.get('observe_pristine_native_graceful_shutdown')
            or facts.get('observe_pristine_native_ack_graceful_shutdown')):
        report['stage'] = 'NATIVE_PAPER_GRACEFUL_SHUTDOWN'
        observe_pristine_native_graceful_shutdown(core,positions,orders)
    report['stage'] = 'COMPLETE'
except BaseException as exc:
    report['harness_exception'] = exception_record(exc)
finally:
    sys.setprofile(globals().get('previous_profile'))
    threading.setprofile(globals().get('previous_thread_profile'))
    if core is not None and facts.get('observe_pristine_readonly_cycle'):
        try:
            if (core.run_mode.value != 'READ_ONLY' or core.trade_registry.snapshot()
                    or native_namespace(report.get('database_before', {})) is not None):
                raise RuntimeError('PRISTINE_ONLY_SHUTDOWN_PRECONDITION_FAILED')
            from src.core.stop_controller import StopMode
            core._shutdown(StopMode.GRACEFUL)
            report['cleanup']['core_shutdown_evidence'] = plain(core.shutdown_evidence.payload())
            report['cleanup']['core_shutdown_complete'] = all(row['completed']
                for row in core.shutdown_evidence.hooks)
        except BaseException as exc:
            report['cleanup']['core_shutdown_exception'] = exception_record(exc)
    elif core is not None and facts.get('observe_pristine_paper_cycle'):
        # Preserve the owned protected PAPER position. Core._shutdown would
        # invoke TradeExitEngine's synthetic force-close; never use that as a
        # fabricated broker terminal fact. Close only this process's resources.
        report['cleanup']['paper_before_resource_close'] = engine_snapshot(core.execution_engine)
        maintenance = getattr(core,'_news_maintenance',None)
        try:
            report['cleanup']['news_maintenance_closed'] = maintenance is None or maintenance.close()
            scanner_runner.reset_scanner_runtime_state(clear_persistent_provider=True,
                suppress_disconnect_errors=False)
            report['cleanup']['scanner_runtime_close_complete'] = True
            core.execution_engine.shutdown()
            report['cleanup']['execution_resource_close_complete'] = True
        except BaseException as exc:
            report['cleanup']['paper_resource_close_exception'] = exception_record(exc)
        report['cleanup']['paper_after_resource_close'] = engine_snapshot(core.execution_engine)
    # No synthetic flat/terminal outcome and no reservation/latch clearing.
    # Close only this interpreter's external connection and owned DB handle.
    try:
        if manager is not None:
            manager.disconnect(reason='offline_cold_core_fixture_cleanup')
        report['cleanup']['manager_disconnected'] = manager is None or manager.existing_client is None
    except BaseException as exc:
        report['cleanup']['manager_exception'] = exception_record(exc)
    finally:
        if client is not None:
            connected[0] = False
    if first_sdk_patcher is not None:
        try:
            if first_sdk_source is not None:
                first_sdk_source.close()
                report['cleanup']['first_sdk_source'] = dict(closed=first_sdk_source.closed,
                    retained_connection_closed=first_sdk_source.initial_connection.socket is None,
                    reader_alive=first_sdk_source.initial_reader.is_alive(),
                    worker_alive=first_sdk_source.initial_worker.is_alive())
        except BaseException as exc:
            report['cleanup']['first_sdk_exception'] = exception_record(exc)
        finally:
            first_sdk_patcher.undo()
    try:
        storage = getattr(core, 'storage_engine', None)
        if storage is not None:
            storage.shutdown()
        report['cleanup']['storage_closed'] = storage is not None
        report['cleanup']['partial_constructor_handles_close_on_process_exit'] = core is None
    except BaseException as exc:
        report['cleanup']['storage_exception'] = exception_record(exc)
    report['cleanup']['live_threads'] = [thread.name for thread in threading.enumerate()
                                        if thread is not threading.current_thread() and thread.is_alive()]
    try:
        report['database_final'] = database_snapshot()
    except BaseException as exc:
        report['snapshot_exception'] = exception_record(exc)
    Path(report_path).write_text(json.dumps(plain(report), sort_keys=True, default=str), encoding='utf-8')
'''


def run_native_core_cold_start(database_path, facts_path, evidence_dir, *,
                               fault='none', timeout=20):
    """Supervise a real offline Core boot; return evidence without asserting policy.

    Facts contain external positions, raw native inventory, callback frames and
    clock/account/client scope.  Every application authority and both execution
    constructors run unchanged.  The first actual SDK encoding attempt is
    recorded and stopped before transport; protocol failures remain visible.
    """
    import json
    import os
    import subprocess

    database_path = Path(database_path).resolve()
    facts_path = Path(facts_path).resolve()
    evidence_dir = Path(evidence_dir).resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sandbox = evidence_dir / 'child-workspace'
    sandbox.mkdir(exist_ok=True)
    prep = sandbox / 'data' / 'prep' / 'premarket_prep.json'
    prep.parent.mkdir(parents=True, exist_ok=True)
    # A truthful empty prep artifact avoids immediate background acquisition;
    # the real startup method hydrates it and schedules the normal future tick.
    prep.write_text(json.dumps({'symbols': [], 'source': 'OFFLINE_EMPTY_FIXTURE'}), encoding='utf-8')
    report_path = evidence_dir / 'child-report.json'
    report_path.unlink(missing_ok=True)
    repository_root = Path(__file__).resolve().parents[1]
    offline_root = repository_root / 'tests' / 'offline'
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(offline_root), str(repository_root))),
        COLD_CORE_EXPECTED_OFFLINE_GUARD=str((offline_root / 'sitecustomize.py').resolve()),
        EXECUTION_ENV='TEST', PERSISTENCE_SQLITE_PATH=str(database_path),
        IBKR_ORDER_ID_STATE_PATH=str(sandbox / 'order-state.json'),
        IBKR_GUARD_PERSIST_PATH=str(sandbox / 'submission-guard.json'),
        NEWS_CACHE_FILE=str(sandbox / 'news.json'),
        SCANNER_FLOAT_CACHE_FILE=str(sandbox / 'float.json'),
        DECISION_TRACE_PATH=str(sandbox / 'decision-trace.jsonl'),
        FORCE_CLEAN_START='false', FLATTEN_ON_STARTUP='false',
        LEARNING_ENABLED='false', MANUAL_FOCUS_ENABLED='false',
        # Redirected Windows stdio otherwise uses the locale code page: real
        # pipeline logging can abort a cycle before any native entry exists.
        PYTHONIOENCODING='utf-8')
    # Keep the unchanged child body out of Windows' bounded command line.
    # Retain the exact launched source alongside its existing private evidence.
    child_source = evidence_dir / 'native-core-child.py'
    child_source.write_text(_NATIVE_CORE_COLD_START_CHILD, encoding='utf-8')
    process = subprocess.Popen([sys.executable, str(child_source),
        str(database_path), str(facts_path), str(report_path), str(fault)],
        cwd=sandbox, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8')
    timed_out = False
    supervisor_errors = []
    stdout = stderr = ''
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        except Exception as exc:
            supervisor_errors.append({'stage': 'communicate', 'type': type(exc).__name__,
                                      'message': str(exc)})
    finally:
        if process.poll() is None:
            process.kill()
        try:
            if timed_out or supervisor_errors:
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except Exception as exc:
                    supervisor_errors.append({'stage': 'drain_after_kill',
                        'type': type(exc).__name__, 'message': str(exc)})
            process.wait(timeout=5)
        finally:
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
    report = json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
    report['evidence_dir'] = str(evidence_dir)
    report['supervisor'] = {'pid': process.pid, 'returncode': process.returncode,
        'timed_out': timed_out, 'reaped': process.poll() is not None,
        'distinct_process': process.pid != os.getpid(),
        'child_pid_matched': report.get('pid') == process.pid,
        'child_parent_matched': report.get('parent_pid') == os.getpid(),
        'pipes_closed': all(pipe is None or pipe.closed for pipe in (process.stdout, process.stderr)),
        'errors': supervisor_errors}
    report['stdout'] = stdout
    report['stderr'] = stderr
    (evidence_dir / 'stdout.txt').write_text(stdout, encoding='utf-8')
    (evidence_dir / 'stderr.txt').write_text(stderr, encoding='utf-8')
    (evidence_dir / 'supervised-report.json').write_text(
        json.dumps(report, sort_keys=True, default=str), encoding='utf-8')
    return report



def test_native_core_child_absolute_offline_guard_blocks_fake_backends(monkeypatch, tmp_path):
    """Exercise captured child env using fake backends; never call networking."""
    import json, os, subprocess, sys
    import pytest
    captured = {}
    captured_argv = []
    captured_stdio = {}
    # Reproduce Windows redirected-stdio encoding even on a UTF-8 host.
    monkeypatch.setenv('PYTHONIOENCODING', 'cp1252')
    class CapturedEnvironment(BaseException):
        pass
    def capture_process(argv, **kwargs):
        captured_argv.extend(argv)
        captured.update(kwargs['env'])
        captured_stdio['encoding'] = kwargs.get('encoding')
        raise CapturedEnvironment()
    facts = tmp_path / 'guard-facts.json'
    facts.write_text('{}')
    with monkeypatch.context() as context:
        context.setattr(subprocess, 'Popen', capture_process)
        with pytest.raises(CapturedEnvironment):
            run_native_core_cold_start(tmp_path / 'never-opened.sqlite3', facts, tmp_path / 'capture-env')
    # Windows CreateProcess rejects the grown child body when passed via -c.
    # The same supervised source must live in the existing evidence directory.
    assert captured_argv[1] != '-c', 'Child source must not occupy the Windows command line'
    child_source = tmp_path / 'capture-env' / 'native-core-child.py'
    assert captured_argv == [sys.executable, str(child_source.resolve()),
        str((tmp_path / 'never-opened.sqlite3').resolve()), str(facts.resolve()),
        str((tmp_path / 'capture-env' / 'child-report.json').resolve()), 'none']
    assert child_source.read_text(encoding='utf-8') == _NATIVE_CORE_COLD_START_CHILD
    assert len(subprocess.list2cmdline(captured_argv)) < 32767
    backends = tmp_path / 'fake-backends'
    backends.mkdir()
    (backends / 'socket.py').write_text("""import sys
calls=[]
class socket:
    def connect(self, address):
        sys.audit('socket.connect', self, address)
        calls.append('connect')
    def connect_ex(self, address):
        sys.audit('socket.connect_ex', self, address)
        calls.append('connect_ex')
    def sendto(self, data, address):
        sys.audit('socket.sendto', self, data, address)
        calls.append('sendto')
def getaddrinfo(*args):
    sys.audit('socket.getaddrinfo', *args)
    calls.append('getaddrinfo')
def create_connection(address):
    socket().connect(address)
""")
    (backends / 'curl_cffi.py').write_text("""calls=[]
class Curl:
    def perform(self):
        calls.append('native_curl')
class AsyncCurl:
    def add_handle(self, handle):
        calls.append('async_curl')
""")
    script = """import json, socket, sys
from curl_cffi import Curl, AsyncCurl
calls={'dns':lambda:socket.getaddrinfo('fixture.invalid',1),
       'connect':lambda:socket.socket().connect(('fixture.invalid',1)),
       'connect_ex':lambda:socket.socket().connect_ex(('fixture.invalid',1)),
       'create_connection':lambda:socket.create_connection(('fixture.invalid',1)),
       'udp':lambda:socket.socket().sendto(b'x',('fixture.invalid',1)),
       'curl':lambda:Curl.perform(None),
       'async_curl':lambda:AsyncCurl.add_handle(None,None)}
denied=[]
for name,call in calls.items():
    try:call()
    except OSError:denied.append(name)
import curl_cffi
print(json.dumps({'denied':denied,'socket_backend_calls':socket.calls,
 'curl_backend_calls':curl_cffi.calls,
 'guard_file':getattr(sys.modules.get('sitecustomize'),'__file__',None),
 'unicode_log':'native \u2192 pipeline \u2014'},ensure_ascii=False))
sys.stderr.write('stderr \u2192 \u2014 \u00e9')
"""
    env = dict(captured)
    env['PYTHONPATH'] = str(backends) + os.pathsep + env['PYTHONPATH']
    child = subprocess.run([sys.executable, '-c', script], cwd=backends, env=env,
        text=True, encoding=captured_stdio['encoding'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    assert child.returncode == 0, child.stderr
    result = json.loads(child.stdout)
    assert result['unicode_log'] == 'native \u2192 pipeline \u2014'
    assert child.stderr == 'stderr \u2192 \u2014 \u00e9'
    assert captured['PYTHONIOENCODING'] == captured_stdio['encoding'] == 'utf-8'
    (tmp_path / 'offline-backend-proof.json').write_text(json.dumps(result, indent=2))
    assert result['socket_backend_calls'] == [] and result['curl_backend_calls'] == [], result
    assert set(result['denied']) == {'dns','connect','connect_ex','create_connection','udp','curl','async_curl'}, result
    root = Path(__file__).resolve().parents[1]
    assert Path(result['guard_file']).resolve() == root / 'tests' / 'offline' / 'sitecustomize.py'
    assert captured['PYTHONPATH'].split(os.pathsep)[0] == str(root / 'tests' / 'offline')
