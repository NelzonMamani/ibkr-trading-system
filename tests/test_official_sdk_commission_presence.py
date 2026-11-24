"""Actual official decoders with modeled local ownership; no sockets or orders."""
from decimal import Decimal
from datetime import datetime, timedelta
from importlib.metadata import version
import queue
import threading
from types import SimpleNamespace

import pytest

from src.adapters.brokers.ibkr import ibkr_client as module
from test_post_pr1090_market_data_authority import native


pytestmark = pytest.mark.skipif(version("ibapi") != "10.50.2", reason="Official fee decoder profile")


@pytest.fixture
def source(native, monkeypatch):
    from ibapi.connection import Connection
    from ibapi.decoder import Decoder
    from ibapi.reader import EReader
    # Model the post-connect objects without connecting. The decoders, dispatch
    # maps, SDK report/protobuf classes and owned worker below are real.
    native.serverVersion_ = 221
    native.clientId = native.client_id
    native.conn = Connection("memory-only", 0)
    native.reader = EReader(native.conn, native.msg_queue)
    native.decoder = Decoder(native, 221)
    native._commission_connection_attempts = 1
    native._position_transport_available = True
    native._managed_accounts = ["SYNTHETIC_TEST"]
    monkeypatch.setattr(native, "isConnected", lambda: True)
    native._install_commission_decoder_witness()
    assert isinstance(native._commission_decoder_proxy, module._OfficialCommissionDecoderProxy)
    tasks = queue.Queue()
    def worker():
        while True:
            task = tasks.get()
            if task is None:
                return
            action, done, result = task
            try:
                result.append(action())
            except BaseException as error:
                result.append(error)
            finally:
                done.set()
    native._thread = threading.Thread(target=worker, name="owned-fee-decoder")
    native._thread.start()
    def run(action):
        done, result = threading.Event(), []
        tasks.put((action, done, result))
        assert done.wait(3), "Owned decoder did not finish"
        if isinstance(result[0], BaseException):
            raise result[0]
        return result[0]
    def deliver(amount=0.0, *, protobuf=True, exec_id="SYNTH_FEE", payload=None):
        if protobuf:
            from ibapi.protobuf.CommissionAndFeesReport_pb2 import CommissionAndFeesReport
            message = CommissionAndFeesReport(execId=exec_id, currency="USD")
            if amount is not None:
                message.commissionAndFees = amount
            body = message.SerializeToString() if payload is None else payload
            return run(lambda: native.decoder.processProtoBuf(body, 59))
        fields = ("1", exec_id, "" if amount is None else str(amount), "USD", "0", "0", "0")
        return run(lambda: native.decoder.interpret(tuple(field.encode() for field in fields), 59))
    state = SimpleNamespace(owner=native, run=run, deliver=deliver,
        proxy=native._commission_decoder_proxy, decoder=native.decoder)
    yield state
    tasks.put(None)
    native._thread.join(3)
    assert not native._thread.is_alive()


@pytest.mark.parametrize("protobuf", [False, True])
@pytest.mark.parametrize("amount", [None, 0.0, 0.25])
def test_actual_decoder_distinguishes_wire_zero_absence_and_positive(source, protobuf, amount):
    source.deliver(amount, protobuf=protobuf)
    record = source.owner._commission_by_exec_id["SYNTH_FEE"]
    report = record["first_report"]
    assert report["amount"] == Decimal(str(0.0 if amount is None else amount))
    assert record["report_count"] == 1
    assert source.owner._commission_zero_report_current(report) is (amount == 0.0)
    if amount in (None, 0.0):
        assert report["commission_field_present"] is (amount is not None)
        assert report["commission_decoder_schema"] == "IBAPI_10_50_2_COMMISSION_FEES"
        assert report["commission_presence_source"] == module.SDK_COMMISSION_PRESENCE_SOURCE
        assert report["commission_decoder_thread_id"] == source.owner._thread.ident


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_protobuf_amount_never_grants_zero_authority(source, amount):
    source.deliver(amount)
    report = source.owner._commission_by_exec_id["SYNTH_FEE"]["first_report"]
    assert report["commission_field_present"] is None
    assert not source.owner._commission_zero_report_current(report)


def test_zero_is_published_after_original_handler_returns_with_exact_sdk_object(source, monkeypatch):
    observed = []
    original = source.proxy._corroborated_projection
    def observe(context, report):
        if context is not None and context["complete"]:
            observed.append(report)
            assert "SYNTH_FEE" not in source.owner._commission_by_exec_id
        return original(context, report)
    monkeypatch.setattr(source.proxy, "_corroborated_projection", observe)
    consumed = []
    consume = source.owner._consume_commission_witness
    def consume_exact(report):
        consumed.append(report)
        return consume(report)
    monkeypatch.setattr(source.owner, "_consume_commission_witness", consume_exact)
    events = []
    source.owner.register_execution_callback(events.append)
    source.deliver()
    assert len(observed) == 1 and len(events) == 1
    assert consumed == observed and consumed[0] is observed[0]
    assert type(observed[0]) is module._SDKCommissionReport


@pytest.mark.parametrize("change", ["account", "epoch", "reader", "connection", "queue", "client", "decoder", "legacy_map", "proto_map"])
def test_foreign_or_changed_source_never_grants_zero_authority(source, change):
    owner = source.owner
    if change == "account":
        source.deliver(exec_id="FIRST")  # Bind the first scope before changing it.
        owner._managed_accounts = ["OTHER_SYNTHETIC"]
    elif change == "epoch":
        owner._position_connection_epoch += 1
    elif change == "reader":
        owner.reader = SimpleNamespace(conn=owner.conn, msg_queue=owner.msg_queue)
    elif change == "connection":
        owner.conn = object()
    elif change == "queue":
        owner.msg_queue = queue.Queue()
    elif change == "client":
        owner.clientId += 1
    elif change == "decoder":
        from ibapi.decoder import Decoder
        owner.decoder = Decoder(owner, 221)
    elif change == "legacy_map":
        owner.decoder.msgId2handleInfo = dict(owner.decoder.msgId2handleInfo)
        owner.decoder.msgId2handleInfo.pop(59)
    else:
        owner.decoder.msgId2handleInfoProtoBuf = dict(owner.decoder.msgId2handleInfoProtoBuf)
        owner.decoder.msgId2handleInfoProtoBuf.pop(59)
    # Directly use the captured original proxy so even replaced routing cannot
    # hide whether this old decoder retains authority.
    from ibapi.protobuf.CommissionAndFeesReport_pb2 import CommissionAndFeesReport
    payload = CommissionAndFeesReport(execId="SYNTH_FEE", currency="USD", commissionAndFees=0.0).SerializeToString()
    source.run(lambda: source.proxy.process_proto(source.decoder, payload))
    report = owner._commission_by_exec_id["SYNTH_FEE"]["first_report"]
    assert report["commission_field_present"] is None
    assert not owner._commission_zero_report_current(report)
    assert owner._commission_zero_disabled


def test_foreign_thread_and_direct_callback_do_not_borrow_authority(source):
    from ibapi.protobuf.CommissionAndFeesReport_pb2 import CommissionAndFeesReport
    payload = CommissionAndFeesReport(execId="SYNTH_FEE", currency="USD", commissionAndFees=0.0).SerializeToString()
    source.proxy.process_proto(source.decoder, payload)
    report = source.owner._commission_by_exec_id["SYNTH_FEE"]["first_report"]
    assert report["commission_field_present"] is None
    assert source.owner._commission_zero_disabled


def test_raw_protobuf_callback_cannot_mutate_absent_amount_into_known_zero(source, monkeypatch):
    def mutate(message):
        message.commissionAndFees = 0.0
    monkeypatch.setattr(source.owner, "commissionAndFeesReportProtoBuf", mutate)
    source.deliver(None)
    report = source.owner._commission_by_exec_id["SYNTH_FEE"]["first_report"]
    assert report["commission_field_present"] is False
    assert not source.owner._commission_zero_report_current(report)


def test_raw_protobuf_callback_cannot_change_wire_identity_or_amount(source, monkeypatch):
    def mutate(message):
        message.execId = "MUTATED_FEE"
        message.commissionAndFees = 0.0
    monkeypatch.setattr(source.owner, "commissionAndFeesReportProtoBuf", mutate)
    source.deliver(0.25)
    report = source.owner._commission_by_exec_id["MUTATED_FEE"]["first_report"]
    assert report["commission_field_present"] is None
    assert not source.owner._commission_zero_report_current(report)


def test_early_matching_object_cannot_outlive_mismatching_final_sdk_projection(source, monkeypatch):
    def fake_then_mutate(message):
        fake = module._SDKCommissionReport()
        fake.execId, fake.currency, fake.commissionAndFees = message.execId, message.currency, 0.0
        source.proxy.commissionAndFeesReport(fake)
        message.execId = "MUTATED_FEE"
        message.commissionAndFees = 0.25
    monkeypatch.setattr(source.owner, "commissionAndFeesReportProtoBuf", fake_then_mutate)
    source.deliver()
    early = source.owner._commission_by_exec_id["SYNTH_FEE"]["first_report"]
    assert early["commission_field_present"] is None
    assert not source.owner._commission_zero_report_current(early)
    report = source.owner._commission_by_exec_id["MUTATED_FEE"]["first_report"]
    assert report["commission_field_present"] is None
    assert not source.owner._commission_zero_report_current(report)


def test_raw_callback_cannot_replace_final_sdk_callback_with_early_fake(source, monkeypatch):
    def fake_then_replace(message):
        fake = module._SDKCommissionReport()
        fake.execId, fake.currency, fake.commissionAndFees = message.execId, message.currency, 0.0
        source.proxy.commissionAndFeesReport(fake)
        monkeypatch.setattr(source.proxy, "commissionAndFeesReport", lambda report: None)
    monkeypatch.setattr(source.owner, "commissionAndFeesReportProtoBuf", fake_then_replace)
    source.deliver()
    record = source.owner._commission_by_exec_id["SYNTH_FEE"]
    assert record["report_count"] == 1
    assert record["first_report"]["commission_field_present"] is None
    assert not source.owner._commission_zero_report_current(record["first_report"])


def test_replayed_sdk_object_has_no_second_presence_receipt(source):
    events = []
    source.owner.register_execution_callback(events.append)
    source.deliver()
    original = source.owner._commission_by_exec_id["SYNTH_FEE"]["first_report"]
    source.run(lambda: source.owner.commissionAndFeesReport(events[0]["commissionReport"]))
    record = source.owner._commission_by_exec_id["SYNTH_FEE"]
    assert record["first_report"] is original and record["report_count"] == 2
    assert record["latest_report"]["commission_field_present"] is None


def test_reentrancy_disables_authority_without_lending_outer_frame(source, monkeypatch):
    def nested(message):
        monkeypatch.setattr(source.owner, "commissionAndFeesReportProtoBuf", lambda report: None)
        source.proxy.process_proto(source.decoder, message.SerializeToString())
    monkeypatch.setattr(source.owner, "commissionAndFeesReportProtoBuf", nested)
    source.deliver()
    record = source.owner._commission_by_exec_id["SYNTH_FEE"]
    assert record["first_report"]["commission_field_present"] is None
    assert record["latest_report"]["commission_field_present"] is None
    assert source.owner._commission_zero_disabled


def test_truncated_or_unknown_protobuf_never_grants_authority(source):
    # Unknown field100(varint0), followed by an otherwise exact explicit zero.
    from ibapi.protobuf.CommissionAndFeesReport_pb2 import CommissionAndFeesReport
    payload = CommissionAndFeesReport(execId="SYNTH_FEE", currency="USD", commissionAndFees=0.0).SerializeToString()
    source.deliver(payload=payload + b"\xa0\x06\x00")
    report = source.owner._commission_by_exec_id["SYNTH_FEE"]["first_report"]
    assert report["commission_field_present"] is None
    assert source.owner._commission_zero_disabled


def test_partial_protobuf_exception_preserves_unknown(source):
    from google.protobuf.message import DecodeError
    with pytest.raises(DecodeError):
        source.deliver(payload=b"\x0a\x05x")
    assert not source.owner._commission_by_exec_id
    assert source.owner._commission_zero_disabled


def test_exception_after_staged_zero_never_publishes_receipt(source, monkeypatch):
    original = source.proxy._run
    def fail_after_sdk(process, decoder, payload, facts):
        def after_callback(actual_decoder, actual_payload):
            process(actual_decoder, actual_payload)
            raise RuntimeError("synthetic post-callback failure")
        return original(after_callback, decoder, payload, facts)
    monkeypatch.setattr(source.proxy, "_run", fail_after_sdk)
    with pytest.raises(RuntimeError, match="synthetic post-callback failure"):
        source.deliver()
    assert not source.owner._commission_by_exec_id
    assert source.owner._commission_zero_disabled


def test_tampered_original_handler_globals_disable_proof(source, monkeypatch):
    monkeypatch.setitem(module._SDK_FEES_PROCESS.__globals__, "decode", lambda *args: None)
    source.deliver()
    report = source.owner._commission_by_exec_id["SYNTH_FEE"]["first_report"]
    assert report["commission_field_present"] is None
    assert source.owner._commission_zero_disabled


def test_tampered_original_handler_code_disables_proof(source, monkeypatch):
    def foreign_handler(self, fields):
        return None
    monkeypatch.setattr(module._SDK_FEES_PROCESS, "__code__", foreign_handler.__code__)
    source.deliver()  # Protobuf still decodes, but either handler tamper revokes both.
    report = source.owner._commission_by_exec_id["SYNTH_FEE"]["first_report"]
    assert report["commission_field_present"] is None
    assert source.owner._commission_zero_disabled


def test_unknown_sdk_profile_cannot_install(native, monkeypatch):
    from ibapi.decoder import Decoder
    native.decoder = Decoder(native, 221)
    monkeypatch.setattr(module, "_sdk_distribution_version", lambda name: "unknown")
    # Profile verification consults metadata independently of the import-time
    # semantic label. A label alone never grants a decoder capability.
    import src.ibkr.sdk_profile as profile
    monkeypatch.setattr(profile.metadata, "version", lambda name: "unknown")
    native._install_commission_decoder_witness()
    assert native._commission_decoder_proxy is None and native._commission_zero_disabled


@pytest.fixture
def modern_fee_consumers(source, isolated_runtime_schema, monkeypatch):
    """Modern decoder receipts joined to the existing SQLite/lifecycle owners."""
    from ibapi.contract import Contract
    from ibapi.execution import Execution
    from src.config.config_resolver import set_config_overrides
    from src.core.daily_risk_governor import DailyRiskGovernor
    from src.core.engines.trade_lifecycle_engine import TradeLifecycleEngine
    from src.storage.storage_engine import StorageEngine
    from test_p10_daily_risk_governor import BASE_CONFIG
    from test_trade_lifecycle_engine import FEE_NOW, _apply_native, _native_event
    config = {**BASE_CONFIG, "RUN_MODE_EFFECTIVE": "PAPER", "PERSISTENCE_ENABLED": True,
        "PERSISTENCE_SQLITE_PATH": str(isolated_runtime_schema), "PERSISTENCE_BACKEND": "sqlite",
        "PERSIST_FLUSH_EACH_CYCLE": True}
    set_config_overrides(config)
    storage = StorageEngine()
    engine = TradeLifecycleEngine(storage)
    class FeeClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return FEE_NOW if tz is None else FEE_NOW.astimezone(tz)
    monkeypatch.setattr(module, "datetime", FeeClock)
    def build(fees, *, protobuf=True, exit_price=10.28):
        events = []
        for index, (kind, price, order_id, fee) in enumerate((
                ("ENTRY_FILL", 10.53, 71, fees[0]), ("STOP_EXIT", exit_price, 72, fees[1]))):
            stamp = FEE_NOW - timedelta(seconds=50 - index * 10)
            event, identity = _native_event("modern-fee-" + str(index), kind, 1, price,
                native_id=order_id, timestamp=stamp.isoformat())
            identity.update(client_id=source.owner.client_id,
                connection_epoch=source.owner._position_connection_epoch)
            _apply_native(engine, event, identity, index)
            contract = Contract()
            contract.symbol, contract.secType, contract.conId, contract.currency = "JPM", "STK", 123, "USD"
            execution = Execution()
            execution.orderId, execution.execId = order_id, event.execution_id
            execution.acctNumber, execution.clientId = "SYNTHETIC_TEST", source.owner.client_id
            execution.side, execution.shares, execution.cumQty = ("BOT" if index == 0 else "SLD"), Decimal(1), Decimal(1)
            execution.price = execution.avgPrice = price
            execution.time = stamp.isoformat()
            source.owner.execDetails(-1, contract, execution)
            source.deliver(fee, protobuf=protobuf, exec_id=event.execution_id)
            events.append(event)
        governor = DailyRiskGovernor(trade_lifecycle_engine=engine, storage_engine=storage)
        currency = module.AccountCurrencyResult("COMPLETE", 81,
            source.owner._position_connection_epoch, "SYNTHETIC_TEST", source.owner.client_id,
            "USD", FEE_NOW, ("CashBalance",), True)
        return SimpleNamespace(engine=engine, storage=storage, client=source.owner, events=events,
            currency=currency, quantity=1, trading_day_for=governor.trading_day_for,
            root="NATIVE-ROOT", native_ids=(71, 72), governor=governor, now=FEE_NOW)
    def limit(value):
        set_config_overrides({**config, "DAILY_RISK_MAX_LOSS_AMOUNT": value})
    yield SimpleNamespace(build=build, limit=limit)
    storage.shutdown()
    set_config_overrides(None)


@pytest.mark.parametrize("protobuf", [False, True])
@pytest.mark.parametrize("fees,loss", [((.01, .02), .28), ((0, 0), .25), ((0, .02), .27)])
@pytest.mark.parametrize("at_limit", [False, True])
def test_modern_decoder_fee_net_reaches_existing_inclusive_daily_gate(
        modern_fee_consumers, protobuf, fees, loss, at_limit):
    from test_trade_lifecycle_engine import _apply_native_fee
    modern_fee_consumers.limit(loss if at_limit else loss + .01)
    h = modern_fee_consumers.build(fees, protobuf=protobuf)
    before = h.engine._trade_snapshot_payload(h.engine.get_trade(h.root))
    evidence = _apply_native_fee(h)
    snapshot = h.engine.native_fee_feedback_snapshot(now=h.now, max_age_seconds=15,
        expected_source_client=h.client)
    assert snapshot["required"] and snapshot["available"] and not snapshot["uncertain"]
    assert evidence["total_commission"] == pytest.approx(sum(fees))
    assert len(snapshot["evidence"]) == 1 and len(snapshot["covered_charges"]) == 2
    for fee, charge in zip(fees, snapshot["covered_charges"]):
        assert Decimal(charge["amount"]) == Decimal(str(fee))
        if fee == 0:
            witness = charge["zero_commission_witness"]
            assert witness["commission_decoder_schema"] == "IBAPI_10_50_2_COMMISSION_FEES"
            assert witness["commission_field_present"] is True
            assert witness["commission_client_object_id"] == id(h.client)
        else:
            assert "zero_commission_witness" not in charge
    persisted = h.storage.fetch_trade_lifecycle_events()
    assert len(persisted) == 3 and len(h.engine.native_feedback_snapshot()["events"]) == 2
    for _ in range(2):
        decision = h.governor.evaluate(run_mode="PAPER", now=h.now)
        assert h.governor.state.recovered
        assert decision.realized_pnl == -loss and decision.unrealized_pnl == 0
        assert decision.blocks_new_entries is at_limit
        assert decision.daily_trade_count == decision.losing_trade_count == decision.consecutive_losses == 1
        assert decision.source_counts["lifecycle"] == 1 and decision.allows_existing_position_management
        assert h.storage.fetch_trade_lifecycle_events() == persisted
    after = h.engine._trade_snapshot_payload(h.engine.get_trade(h.root))
    assert {key: value for key, value in before.items() if key != "updated_at"} == {
        key: value for key, value in after.items() if key != "updated_at"}


@pytest.mark.parametrize("protobuf", [False, True])
def test_modern_absent_amount_stays_unknown_and_selected_attempt_retains_veto(
        modern_fee_consumers, protobuf):
    from test_trade_lifecycle_engine import _apply_native_fee, _native_fee_observation
    modern_fee_consumers.limit(.25)
    h = modern_fee_consumers.build((None, .02), protobuf=protobuf)
    observation = _native_fee_observation(h)
    assert observation.fee_observations[0]["report_status"] == "UNAVAILABLE"
    assert observation.fee_observations[0]["net_status"] == "UNAVAILABLE_FOR_NET"
    assert "ZERO_COMMISSION_WIRE_PRESENCE_UNAVAILABLE" in observation.fee_observations[0]["unavailable_reasons"]
    with pytest.raises(ValueError, match="NATIVE_FEE_SOURCE_REPORT_UNAVAILABLE"):
        _apply_native_fee(h, observation)
    snapshot = h.engine.native_fee_feedback_snapshot(now=h.now, max_age_seconds=15)
    assert not snapshot["required"] and snapshot["evidence"] == snapshot["covered_charges"] == []
    decision = h.governor.evaluate(run_mode="PAPER", now=h.now)
    assert decision.realized_pnl == -.25 and decision.blocks_new_entries
    persisted = h.storage.fetch_trade_lifecycle_events()
    assert decision.daily_trade_count == 1 and len(persisted) == 2
    # Once the existing higher owner selects a fee attempt, incomplete evidence
    # retains its admission veto even below the configured financial loss limit.
    modern_fee_consumers.limit(1.0)
    assert h.engine.begin_native_roundtrip_fee_attempt(h.root,
        tuple(event.event_id for event in h.events), source_client=h.client)
    pending = h.governor.evaluate(run_mode="PAPER", now=h.now)
    assert pending.blocks_new_entries and "NATIVE_FEE_FEEDBACK_UNAVAILABLE" in pending.reason
    assert pending.realized_pnl == -.25 and pending.daily_trade_count == 1
    assert h.storage.fetch_trade_lifecycle_events() == persisted


@pytest.mark.parametrize("protobuf", [False, True])
def test_modern_zero_replay_cannot_double_charge_or_add_a_daily_trade(
        modern_fee_consumers, source, protobuf):
    from test_trade_lifecycle_engine import _apply_native_fee
    events = []
    source.owner.register_execution_callback(events.append)
    modern_fee_consumers.limit(.28)
    h = modern_fee_consumers.build((0, .02), protobuf=protobuf)
    evidence = _apply_native_fee(h)
    persisted = h.storage.fetch_trade_lifecycle_events()
    fee_events = [event for event in events if event["event_type"] == "commissionReport"]
    assert len(fee_events) == 2
    for event in fee_events:
        source.run(lambda event=event: h.client.commissionAndFeesReport(event["commissionReport"]))
        cached = h.client._commission_by_exec_id[event["execId"]]
        assert cached["report_count"] == 2
        assert cached["latest_report"]["commission_field_present"] is None
    assert _apply_native_fee(h) == evidence
    snapshot = h.engine.native_fee_feedback_snapshot(now=h.now, max_age_seconds=15)
    assert snapshot["available"] and len(snapshot["evidence"]) == 1
    assert len(snapshot["covered_charges"]) == 2
    decision = h.governor.evaluate(run_mode="PAPER", now=h.now)
    assert decision.realized_pnl == -.27 and decision.daily_trade_count == 1
    assert not decision.blocks_new_entries and h.storage.fetch_trade_lifecycle_events() == persisted
