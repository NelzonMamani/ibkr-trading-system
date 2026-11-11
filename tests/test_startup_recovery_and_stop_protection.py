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
base_external_facts = {key: copy.deepcopy(value) for key, value in facts.items()
                       if key != 'cycle_scenarios'}
current_external_facts = copy.deepcopy(base_external_facts)
external_fault = fault
report = {'pid': os.getpid(), 'parent_pid': os.getppid(), 'fault': fault,
          'constructor_complete': False, 'constructor_count': 0,
          'cycle_attempted': False, 'scenarios': [],
          'sdk_attempts': [], 'wire_attempts': [], 'network_attempts': [],
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

class SyntheticWriteBoundary(BaseException):
    pass

class ForbiddenExternalIO(BaseException):
    pass

def no_network(*args, **kwargs):
    report['network_attempts'].append({'operation': 'socket.connect'})
    raise ForbiddenExternalIO('COLD_CORE_REAL_NETWORK_FORBIDDEN')

socket.socket.connect = no_network
socket.socket.connect_ex = no_network
socket.create_connection = no_network

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
    })

try:
    from ibapi.client import EClient
    from ibapi.contract import Contract
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

    account = facts.get('account', 'SYNTHETIC_TEST')
    client_id = int(facts.get('client_id', 999))
    client = IbkrClient('offline.invalid', 7497, client_id, 1, 'LIVE', False)
    connected = [True]
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
    raw_fields = frozenset(('symbol', 'company_name', 'con_id', 'exchange',
        'primary_exchange', 'trading_class', 'local_symbol', 'currency',
        'instrument_type', 'last_price', 'bid', 'ask', 'open', 'high', 'low',
        'close', 'prev_close', 'ref_close_rth', 'volume', 'float_shares',
        'current_intraday_volume', 'average_daily_volume_20d',
        'average_daily_volume_window_days', 'volume_velocity_5m',
        'volume_velocity_15m', 'quote_timestamp_utc', 'quote_timestamp_source',
        'requested_market_data_type', 'returned_market_data_type',
        'market_data_type_confirmed', 'received_at_utc',
        'market_data_type_received_at_utc', 'request_id', 'snapshot_complete'))
    def candidate_inventory(rows):
        return {str(symbol).upper(): {key: copy.deepcopy(value)
            for key, value in row.items() if key in raw_fields}
            for symbol, row in rows.items()}
    def historical_inventory(streams):
        return {timeframe: [Candle(
            open=row['open'], high=row['high'], low=row['low'], close=row['close'],
            volume=row['volume'], timestamp=(datetime.fromisoformat(row['timestamp'])
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
            longName=row.get('company_name')) for symbol, row in candidates.items()}}

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
                volume_data_quality_flag=None)

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
        return list(source_bars.get(timeframe, []))[-limit:] if symbol in candidates else []
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

    def send_message(message):
        opcode = str(message).split('\0', 1)[0]
        report['wire_attempts'].append({'opcode': opcode,
            'mutation': opcode in {str(OUT.PLACE_ORDER), str(OUT.CANCEL_ORDER), str(OUT.REQ_GLOBAL_CANCEL)}})
        if report['wire_attempts'][-1]['mutation']:
            raise SyntheticWriteBoundary('COLD_CORE_SYNTHETIC_NATIVE_WRITE_ATTEMPT')
        raise ForbiddenExternalIO('UNSUPPLIED_SYNTHETIC_PROVIDER_REQUEST:' + opcode)
    client.sendMsg = send_message
    EClient.connect = no_network

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
        if scenarios is None:
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
    report['mutation_attempts'] = mutation_snapshot()
    report['stage'] = 'COMPLETE'
except BaseException as exc:
    report['harness_exception'] = exception_record(exc)
finally:
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
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]),
        EXECUTION_ENV='TEST', PERSISTENCE_SQLITE_PATH=str(database_path),
        IBKR_ORDER_ID_STATE_PATH=str(sandbox / 'order-state.json'),
        IBKR_GUARD_PERSIST_PATH=str(sandbox / 'submission-guard.json'),
        NEWS_CACHE_FILE=str(sandbox / 'news.json'),
        SCANNER_FLOAT_CACHE_FILE=str(sandbox / 'float.json'),
        DECISION_TRACE_PATH=str(sandbox / 'decision-trace.jsonl'),
        FORCE_CLEAN_START='false', FLATTEN_ON_STARTUP='false',
        LEARNING_ENABLED='false', MANUAL_FOCUS_ENABLED='false')
    process = subprocess.Popen([sys.executable, '-c', _NATIVE_CORE_COLD_START_CHILD,
        str(database_path), str(facts_path), str(report_path), str(fault)],
        cwd=sandbox, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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
