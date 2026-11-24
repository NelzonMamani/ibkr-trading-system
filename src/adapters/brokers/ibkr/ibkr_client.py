from __future__ import annotations

from src.domain.quote_freshness import quote_time_rejection
from src.domain.volume_evidence import (
    SHARE_UNIT_SOURCE, VERIFIED_SHARE_UNIT, native_stock_volume_rejection,
)
from src.ibkr.quote_diagnostics import record_time_assessment

from src.core.acquisition import AcquisitionCancelled, AcquisitionDeadlineExceeded, checkpoint, wait_event, bounded_timeout

import threading
from threading import Lock as _LocalSourceLock, local as _LocalSourceThread, get_ident as _local_source_thread_id
import hashlib
import inspect
from importlib.metadata import version as _sdk_distribution_version
from copy import deepcopy
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
import math
import re
import time
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from types import MappingProxyType, SimpleNamespace
from typing import Dict, List, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ibapi.client import EClient
from ibapi.common import TickerId
from ibapi.contract import Contract, ContractDetails
from ibapi.order import Order
from ibapi.wrapper import EWrapper
from ibapi.decoder import Decoder as _SDKDecoder
from ibapi.message import IN as _SDK_IN
from ibapi.utils import decode as _SDKDecode
try:
    from ibapi.commission_report import CommissionReport as _SDKCommissionReport
except ModuleNotFoundError as _commission_import_error:
    if _commission_import_error.name != "ibapi.commission_report":
        raise
    from ibapi.commission_and_fees_report import CommissionAndFeesReport as _SDKCommissionReport

from src.ibkr.quote_diagnostics import QuoteDiagnostics
from src.ibkr.position_snapshot import BrokerPositionResult
from src.domain.market_snapshot import MarketSnapshot
from src.ibkr.market_data_client import (
    MarketDataSnapshot,
    HistoricalDataResult,
    _clean,
    _market_data_type_flags,
    _returned_market_data_type,
    _resolve_snapshot_timestamp,
    _record_field_receipt,
    _snapshot_authority_metadata,
    _copy_snapshot_ticker,
    average_daily_bar_volume,
    exact_raw_volume,
)
from src.ibkr.read_only_guard import assert_read_only_allows
from src.ibkr.evidence_safety import register_account, sanitize
from src.ibkr.volume_calibration import HISTORICAL_BASIS, load_paper_volume_calibration



SDK_COMMISSION_PRESENCE_SOURCE = "IBKR_SDK_DECODER"
try:
    _SDK_COMMISSION_MODERN = _sdk_distribution_version("ibapi") == "10.50.2"
except Exception:
    _SDK_COMMISSION_MODERN = False
# A process-specific semantic profile covers the two reviewed SDK encodings.
# The original legacy profile and its eight-field interpretation are unchanged.
SDK_COMMISSION_SCHEMA = ("IBAPI_10_50_2_COMMISSION_FEES" if _SDK_COMMISSION_MODERN
    else "IBAPI_9_81_1_POST1_COMMISSION_8_FIELDS")
_SDK_COMMISSION_PROCESS = getattr(_SDKDecoder, "processCommissionReportMsg", None)
_SDK_COMMISSION_CODE = getattr(_SDK_COMMISSION_PROCESS, "__code__", None)
_SDK_COMMISSION_SOURCE_SHA256 = "624d4881337a7ed0551c225182b7ce5281d34c18dd8b79f965e63e88618914e2"
_SDK_FEES_PROCESS = getattr(_SDKDecoder, "processCommissionAndFeesReportMsg", None)
_SDK_FEES_PROTO_PROCESS = getattr(_SDKDecoder, "processCommissionAndFeesReportMsgProtoBuf", None)
_SDK_FEES_CODE = getattr(_SDK_FEES_PROCESS, "__code__", None)
_SDK_FEES_PROTO_CODE = getattr(_SDK_FEES_PROTO_PROCESS, "__code__", None)
_SDK_FEES_PROTO_CLASS = (getattr(_SDK_FEES_PROTO_PROCESS, "__globals__", {})
    .get("CommissionAndFeesReportProto"))
_SDK_FEES_SOURCE_SHA256 = "db172921859bbdc8d2762224e80687b7f2abc1a35599f1311b1ca104ada72350"
_SDK_FEES_PROTO_SOURCE_SHA256 = "953ffbb7f062b216126f09448dba1479350805989a9e533e5d74177ac2ad4df0"
_COMMISSION_PRESENCE_FIELDS = (
    "commission_field_present", "commission_presence_source", "commission_decoder_schema",
    "commission_client_object_id", "commission_decoder_object_id", "commission_decoder_epoch",
    "commission_decoder_generation", "commission_decoder_thread_id")


def _commission_sdk_schema_supported():
    try:
        if _SDK_COMMISSION_MODERN:
            from src.ibkr.sdk_profile import require_supported_sdk
            return (require_supported_sdk() == "10.50.2" and _commission_sdk_runtime_valid()
                and hashlib.sha256(inspect.getsource(_SDK_FEES_PROCESS).encode()).hexdigest()
                    == _SDK_FEES_SOURCE_SHA256
                and hashlib.sha256(inspect.getsource(_SDK_FEES_PROTO_PROCESS).encode()).hexdigest()
                    == _SDK_FEES_PROTO_SOURCE_SHA256)
        return (_sdk_distribution_version("ibapi") == "9.81.1.post1"
            and _SDK_COMMISSION_CODE is not None
            and _SDK_COMMISSION_PROCESS.__code__ is _SDK_COMMISSION_CODE
            and _SDK_COMMISSION_PROCESS.__globals__.get("decode") is _SDKDecode
            and _SDK_COMMISSION_PROCESS.__globals__.get("CommissionReport") is _SDKCommissionReport
            and hashlib.sha256(inspect.getsource(_SDK_COMMISSION_PROCESS).encode()).hexdigest()
                == _SDK_COMMISSION_SOURCE_SHA256)
    except Exception:
        return False


def _commission_sdk_runtime_valid():
    if not _SDK_COMMISSION_MODERN:
        return (_SDK_COMMISSION_PROCESS is not None
            and _SDK_COMMISSION_PROCESS.__code__ is _SDK_COMMISSION_CODE
            and _SDK_COMMISSION_PROCESS.__globals__.get("decode") is _SDKDecode
            and _SDK_COMMISSION_PROCESS.__globals__.get("CommissionReport") is _SDKCommissionReport)
    return (_SDK_FEES_CODE is not None and _SDK_FEES_PROTO_CODE is not None
        and getattr(_SDKDecoder, "processCommissionAndFeesReportMsg", None) is _SDK_FEES_PROCESS
        and getattr(_SDKDecoder, "processCommissionAndFeesReportMsgProtoBuf", None) is _SDK_FEES_PROTO_PROCESS
        and _SDK_FEES_PROCESS.__code__ is _SDK_FEES_CODE
        and _SDK_FEES_PROTO_PROCESS.__code__ is _SDK_FEES_PROTO_CODE
        and _SDK_FEES_PROCESS.__globals__.get("decode") is _SDKDecode
        and _SDK_FEES_PROCESS.__globals__.get("CommissionAndFeesReport") is _SDKCommissionReport
        and _SDK_FEES_PROTO_PROCESS.__globals__.get("CommissionAndFeesReport") is _SDKCommissionReport
        and _SDK_FEES_PROTO_CLASS is not None
        and _SDK_FEES_PROTO_PROCESS.__globals__.get("CommissionAndFeesReportProto") is _SDK_FEES_PROTO_CLASS)


class _CommissionDecoderProxy:
    """One decoder's forwarding wrapper, never a replacement EWrapper owner."""
    def __init__(self, owner, decoder):
        self.owner, self.decoder = owner, decoder
        self.queue, self.reader, self.connection = owner.msg_queue, owner.reader, owner.conn
        self.epoch, self.client_id = owner._position_connection_epoch, owner.client_id
        self.server_version = decoder.serverVersion
        self.account_scope = None
        self.thread = None
        self.local = threading.local()
        self.process = self._process

    def __getattr__(self, name):
        return getattr(self.owner, name)  # Real client-bound methods, no inherited no-op callbacks.

    def _process(self, decoder, fields):
        # Freeze exactly what the untouched SDK will parse. The installed
        # handler has eight fields and ignores the integer message version;
        # this declares no additional guessed wire-version whitelist.
        frozen = tuple(fields)
        supported = (decoder is self.decoder and len(frozen) == 8
            and all(type(field) is bytes for field in frozen)
            and self.owner._commission_decoder_current(self, require_thread=True))
        if not supported:
            self.owner._commission_zero_disabled = True
        previous = getattr(self.local, "context", None)
        context = {"fields": frozen, "present": frozen[3] != b"",
            "thread": threading.get_ident(), "complete": False,
            "pending_zero": None, "zero_claimed": False} if supported else None
        self.local.context = context
        try:
            result = _SDK_COMMISSION_PROCESS(decoder, iter(frozen))
            if context is not None:
                context["complete"] = True
        except BaseException:
            self.owner._commission_zero_disabled = True
            if context is not None:
                context["pending_zero"] = None
            raise
        finally:
            self.local.context = previous
        # A logging callback can call the proxy before the parser finishes.
        # Publish ZERO only after NORMAL SDK return, never from that early call.
        pending = context.pop("pending_zero") if context is not None else None
        if pending is not None:
            corroborated = None
            if (not context["zero_claimed"]
                    and self._corroborated_projection(context, pending) == "ZERO"):
                context["zero_claimed"] = True
                corroborated = context
            # Normal SDK return still delivered a legacy callback even when
            # current scope or corroboration no longer permits ZERO authority.
            self.local.context = None  # No active parse frame in owner listeners.
            try:
                self._forward(pending, corroborated)
            finally:
                self.local.context = previous
        return result

    def _corroborated_projection(self, context, report):
        # Object type/thread alone cannot prove SDK call origin. These are
        # exact facts corroborated by the SAME immutable frame, not a second
        # numeric parser or a claim of unforgeable report-object provenance.
        if (context is None or type(report) is not _SDKCommissionReport
                or type(report.execId) is not str or type(report.currency) is not str
                or type(report.commission) is not float or report.commission != 0.0
                or not self.owner._commission_decoder_current(self, require_thread=True)):
            return None
        try:
            same_identity = (report.execId.encode("ascii") == context["fields"][2]
                and report.currency.encode("ascii") == context["fields"][4])
        except UnicodeEncodeError:
            return None
        if not same_identity:
            return None
        raw_amount = context["fields"][3]
        if raw_amount == b"":
            return "EMPTY"  # Honest SDK empty-to-zero projection, never known ZERO.
        if raw_amount in (b"0", b"0.0"):
            return "ZERO"
        return None  # Other spellings are unsupported, not parsed a second time.

    def commissionReport(self, report):
        context = getattr(self.local, "context", None)
        projection = self._corroborated_projection(context, report)
        if projection == "ZERO":
            # Every staged report agrees with the same raw zero fact. Keep the
            # latest exact SDK object, recheck it at publication, and publish at
            # most once AFTER the original handler has completed successfully.
            context["pending_zero"] = report
            return None
        return self._forward(report, context if projection == "EMPTY" else None)

    def _forward(self, report, corroborated):
        previous = getattr(self.local, "forward", None)
        self.local.forward = {"report": report, "context": corroborated, "used": False}
        try:
            return self.owner.commissionReport(report)
        finally:
            self.local.forward = previous

    def consume(self, report):
        forward = getattr(self.local, "forward", None)
        if forward is None or forward["report"] is not report or forward["used"]:
            return None
        forward["used"] = True  # Before connection checks, diagnostics or listeners.
        if type(report) is not _SDKCommissionReport:
            self.owner._commission_zero_disabled = True
            return None
        context = forward["context"]
        if (context is None
                or (not context["complete"] and context is not getattr(self.local, "context", None))
                or context["thread"] != threading.get_ident()
                or not self.owner._commission_decoder_current(self, require_thread=True)):
            return None
        return dict(zip(_COMMISSION_PRESENCE_FIELDS, (
            context["present"], SDK_COMMISSION_PRESENCE_SOURCE, SDK_COMMISSION_SCHEMA,
            id(self.owner), id(self.decoder), self.epoch, 1, threading.get_ident())))


class _OfficialCommissionDecoderProxy(_CommissionDecoderProxy):
    """Wire presence for the exact official 10.50.2 fee decoder profile."""
    def __init__(self, owner, decoder):
        super().__init__(owner, decoder)
        self.process_proto = self._process_proto

    def _eligible(self, decoder):
        return (decoder is self.decoder and getattr(self.local, "context", None) is None
            and getattr(self.local, "forward", None) is None
            and self.owner._commission_decoder_current(self, require_thread=True))

    def _process(self, decoder, fields):
        frozen = tuple(fields)
        supported = (len(frozen) == 7 and all(type(value) is bytes for value in frozen)
            and self._eligible(decoder))
        facts = {"fields": frozen, "present": frozen[2] != b"", "encoding": "FIELDS"} if supported else None
        return self._run(_SDK_FEES_PROCESS, decoder, iter(frozen), facts)

    def _process_proto(self, decoder, payload):
        facts = None
        if type(payload) is bytes and len(payload) <= 1024 * 1024 and self._eligible(decoder):
            try:
                message = _SDK_FEES_PROTO_CLASS()
                message.ParseFromString(payload)
                clean = _SDK_FEES_PROTO_CLASS()
                clean.CopyFrom(message)
                clean.DiscardUnknownFields()
                if clean.SerializeToString() == message.SerializeToString():
                    facts = {"encoding": "PROTOBUF", "present": message.HasField("commissionAndFees"),
                        "exec_id": message.execId, "currency": message.currency,
                        "amount": message.commissionAndFees}
            except Exception:
                pass  # The untouched SDK below owns decoding errors and callbacks.
        return self._run(_SDK_FEES_PROTO_PROCESS, decoder, payload, facts)

    def _run(self, process, decoder, payload, facts):
        if facts is None:
            self.owner._commission_zero_disabled = True
        previous = getattr(self.local, "context", None)
        context = ({**facts, "thread": threading.get_ident(), "complete": False,
            "pending_zero": None, "zero_claimed": False} if facts is not None else None)
        self.local.context = context
        try:
            result = process(decoder, payload)
            if context is not None:
                context["complete"] = True
        except BaseException:
            self.owner._commission_zero_disabled = True
            if context is not None:
                context["pending_zero"] = None
            raise
        finally:
            self.local.context = previous
        pending = context.pop("pending_zero") if context is not None else None
        if pending is not None:
            corroborated = None
            if not context["zero_claimed"] and self._corroborated_projection(context, pending) == "ZERO":
                context["zero_claimed"] = True
                corroborated = context
            self.local.context = None
            try:
                self._forward(pending, corroborated)
            finally:
                self.local.context = previous
        return result

    def _corroborated_projection(self, context, report):
        if (context is None or type(report) is not _SDKCommissionReport
                or type(report.execId) is not str or type(report.currency) is not str
                or type(report.commissionAndFees) is not float
                or not math.isfinite(report.commissionAndFees) or report.commissionAndFees != 0.0
                or not self.owner._commission_decoder_current(self, require_thread=True)):
            return None
        if context["encoding"] == "PROTOBUF":
            if (report.execId != context["exec_id"] or report.currency != context["currency"]
                    or report.commissionAndFees != context["amount"]):
                return None
            return "ZERO" if context["present"] else "EMPTY"
        try:
            if (report.execId.encode("ascii") != context["fields"][1]
                    or report.currency.encode("ascii") != context["fields"][3]):
                return None
        except UnicodeEncodeError:
            return None
        raw_amount = context["fields"][2]
        return "EMPTY" if raw_amount == b"" else "ZERO" if raw_amount in (b"0", b"0.0") else None

    def commissionAndFeesReport(self, report):
        context = getattr(self.local, "context", None)
        frame = inspect.currentframe()
        caller = frame.f_back if frame is not None else None
        try:
            sdk_origin = (caller is not None
                and any(caller.f_code is code for code in (_SDK_FEES_CODE, _SDK_FEES_PROTO_CODE))
                and caller.f_locals.get("self") is self.decoder
                and caller.f_locals.get("commissionAndFeesReport") is report)
        finally:
            del caller, frame  # Do not retain the parser's mutable frame/report.
        projection = self._corroborated_projection(context, report) if sdk_origin else None
        if projection == "ZERO":
            context["pending_zero"] = report
            return None
        if context is not None:
            # The raw-protobuf callback precedes the actual SDK projection.
            # A synthetic early matching object cannot outlive a mismatching
            # final SDK report from that same mutable protobuf callback.
            context["pending_zero"] = None
        return self._forward(report, context if projection == "EMPTY" else None)

    def _forward(self, report, corroborated):
        previous = getattr(self.local, "forward", None)
        self.local.forward = {"report": report, "context": corroborated, "used": False}
        try:
            return self.owner.commissionAndFeesReport(report)
        finally:
            self.local.forward = previous


@dataclass(frozen=True)
class ScopedExecution:
    exec_id: str
    order_id: int
    con_id: int
    symbol: str
    account: str
    client_id: int
    side: str
    quantity: Decimal
    price: Decimal
    cumulative_quantity: Decimal
    average_price: Decimal
    broker_time: str


@dataclass(frozen=True)
class ExecutionQueryResult:
    """Request completion ONLY; not terminal-order or lifetime-fill finality."""

    status: str
    request_id: Optional[int]
    connection_epoch: int
    account: str
    client_id: int
    order_id: int
    con_id: int
    symbol: str
    side: str
    rows: tuple[ScopedExecution, ...] = ()
    completed_at: Optional[datetime] = None
    # IBKR supports client/account/symbol/secType/time filters, NOT order/conId.
    filter_time: str = ""
    filter_security_type: str = "STK"
    filter_side: str = ""  # Both sides requested; retained order side checked locally.
    filter_exchange: str = ""
    completion_scope: str = "REQUEST_ONLY"

    @property
    def attempt_id(self) -> tuple[int, Optional[int]]:
        # Process-local identity; never a durable broker/restart certificate.
        return self.connection_epoch, self.request_id


@dataclass(frozen=True)
class AccountCurrencyResult:
    """Initial request completion, not balances, FX or subscription finality."""

    status: str
    request_id: Optional[int]
    connection_epoch: int
    account: str
    client_id: int
    currency: Optional[str] = None
    completed_at: Optional[datetime] = None
    tags: tuple[str, ...] = ()
    cancellation_attempted: bool = False
    cleanup_complete: bool = True  # Local callback ownership retired only.
    source: str = "IBKR_ACCOUNT_SUMMARY_LEDGER"
    account_scope_generation: Optional[int] = None
    settled_cash: Optional[Decimal] = None


_CAPITAL_TAGS = ("NetLiquidation", "AvailableFunds", "BuyingPower")


@dataclass(frozen=True)
class AccountCapitalFact:
    account: str
    tag: str
    value: Decimal
    currency: str
    received_at: datetime


@dataclass(frozen=True)
class AccountCapitalResult:
    """Initial account summary evidence. Receipt times are not market mark times."""

    status: str
    account: str
    currency_evidence: AccountCurrencyResult
    request_id: Optional[int] = None
    connection_epoch: Optional[int] = None
    client_id: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    facts: tuple[AccountCapitalFact, ...] = ()
    cancellation_attempted: bool = False
    account_scope_generation: Optional[int] = None


def _market_data_type_code(market_data_type: str) -> int:
    value = market_data_type.upper()
    if value == "FROZEN":
        return 2
    if value == "DELAYED":
        return 3
    if value == "DELAYED_FROZEN":
        return 4
    return 1


@dataclass(frozen=True)
class NativePriceRule:
    """Local completion evidence, never a native attempt/version certificate."""
    status: str
    contract_key: tuple
    route: str
    rule_id: int | None
    client_id: int
    connection_epoch: int
    qualification_request: int | None = None
    request_sequence: int | None = None
    completed_at: datetime | None = None
    bands: tuple[tuple[Decimal, Decimal], ...] = ()
    source: str = "IBKR_CONTRACT_DETAILS_AND_MARKET_RULE"

    def increment(self, price):
        price = _price_decimal(price)
        if self.status != "COMPLETE" or price <= 0 or not self.bands:
            raise ValueError("Authoritative completed price bands required")
        return next(increment for edge, increment in reversed(self.bands) if edge <= price)

    def normalize_long_stop(self, proposed, *, original_stop, effective_stop, bid):
        """NEW prerequisite policy: ceil only; never widen risk or meet/cross bid.

        Absolute increment grid, re-evaluated at band transitions. This does NOT
        choose a strategy price, enroll BE/trailing, or establish broker acceptance.
        """
        price = _price_decimal(proposed)
        original, effective, bid = map(_price_decimal, (original_stop, effective_stop, bid))
        if not 0 < original <= effective < price < bid:
            raise ValueError("Long stop must tighten confirmed protection below executable bid")
        candidates = []
        for index, (edge, tick) in enumerate(self.bands):
            lower = max(price, edge)
            upper = self.bands[index+1][0] if index+1 < len(self.bands) else None
            if upper is not None and lower >= upper:
                continue
            pn, pd = lower.as_integer_ratio()
            tn, td = tick.as_integer_ratio()
            units = (pn*td + pd*tn-1)//(pd*tn)
            parts = tick.as_tuple()
            coefficient = int(''.join(map(str, parts.digits)))*units
            normalized = Decimal((0, tuple(map(int, str(coefficient))), parts.exponent))
            if normalized < bid and (upper is None or normalized < upper):
                candidates.append(normalized)
        if not candidates:
            raise ValueError("No legal tightening price below executable bid")
        return min(candidates)  # Smallest legal ceiling ACROSS bands, not an overshoot.



def _price_decimal(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a price")
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Finite decimal price required") from None
    if not price.is_finite() or abs(price.as_tuple().exponent) > 64 or len(price.as_tuple().digits) > 64:
        raise ValueError("Finite decimal price required")
    return price


@dataclass(frozen=True)
class LocalIntakeTicket:
    ticket_id: int
    kind: str
    finished: bool
    failed: bool
    revision_start: int
    revision_end: Optional[int]
    raw_fingerprint: Optional[str]
    client_object_id: int
    client_id: Optional[int]
    connection_epoch: Optional[int]
    accounts: tuple[str, ...]
    semantic_payload: Optional[tuple] = None
    publication: Optional[tuple] = None


@dataclass(frozen=True)
class LocalIntakeSnapshot:
    revision: int
    inflight: tuple[int, ...]
    dirty: tuple[LocalIntakeTicket, ...]
    client_object_id: int
    client_id: Optional[int]
    connection_epoch: Optional[int]
    accounts: tuple[str, ...]
    invocation_fingerprint: Optional[tuple] = None


@dataclass(frozen=True)
class LocalRequestCompletion:
    kind: str
    source_client: object
    client_object_id: int
    client_id: int
    connection_epoch: int
    account: str
    request_id: int
    context_id: int
    request_started_at: datetime
    completed_at: datetime
    revision_start: int
    revision_end: int
    rows: tuple = ()
    currency: Optional[str] = None
    tags: tuple[str, ...] = ()
    retired: bool = True
    cancellation_returned: bool = True
    callback_ticket_ids: tuple[int, ...] = ()

    def __reduce__(self):
        raise TypeError("P02_LOCAL_REQUEST_COMPLETION_NOT_TRANSFERABLE")

    def __copy__(self):
        raise TypeError("P02_LOCAL_REQUEST_COMPLETION_NOT_TRANSFERABLE")

    def __deepcopy__(self, memo):
        raise TypeError("P02_LOCAL_REQUEST_COMPLETION_NOT_TRANSFERABLE")


_LOCAL_NATIVE_PUBLICATION_CODES = {}
_LOCAL_NATIVE_REQUEST_CODES = {}
_LOCAL_NATIVE_FINGERPRINT_CODES = set()


def _local_native_value(value):
    """Detached builtin values only; never invoke caller repr/copy callbacks."""
    from ibapi.softdollartier import SoftDollarTier
    from ibapi.execution import Execution
    from ibapi.order_state import OrderState
    if type(value) is float and not math.isfinite(value):
        raise RuntimeError("P02_LOCAL_NONFINITE_NATIVE_VALUE")
    if type(value) in (str, int, float, bool, bytes, type(None)):
        return (type(value).__name__, value)
    if type(value) is Decimal:
        if not value.is_finite():
            raise RuntimeError("P02_LOCAL_NONFINITE_NATIVE_VALUE")
        return ("Decimal", str(value))
    if type(value) in (list, tuple):
        return (type(value).__name__, tuple(_local_native_value(item) for item in value))
    if type(value) is dict and all(type(key) is str for key in value):
        return ("dict", tuple((key, _local_native_value(value[key])) for key in sorted(value)))
    if type(value) in (Contract, ContractDetails, Order, OrderState, Execution, _SDKCommissionReport, SoftDollarTier):
        return (type(value).__name__, _local_native_value(vars(value)))
    raise RuntimeError("P02_LOCAL_UNSUPPORTED_NATIVE_VALUE")


def _instrument_local_native_intake(cls, name):
    """Constructor-lifetime boundary outside registration/parsing/publication."""
    from functools import wraps
    original = getattr(cls, name)
    _LOCAL_NATIVE_PUBLICATION_CODES[name] = inspect.unwrap(original).__code__
    @wraps(original)
    def intake(self, *args, **kwargs):
        operation = self._begin_local_source_operation(name)
        ticket = None
        state = None
        stack = ()
        failed = False
        try:
            ticket = self.begin_local_intake(name)
            if ticket is None:
                return original(self, *args, **kwargs)
            state = self._p02_local_ingress
            stack = getattr(state["thread"], "intake", ())
            state["thread"].intake = (*stack, ticket)
            try:
                # Outside I; failed/unknown inputs still reach the old owner.
                raw = _local_native_value((args, kwargs))
                fingerprint = hashlib.sha256(repr(raw).encode()).hexdigest()
                self._local_intake_fingerprint(ticket, fingerprint, semantic_payload=raw)
            except Exception:
                self._local_intake_failed(ticket)
            return original(self, *args, **kwargs)
        except BaseException:
            failed = True
            raise
        finally:
            try:
                if ticket is not None:
                    state["thread"].intake = stack
                    self.finish_local_intake(ticket, "FAILED" if failed else "RETURNED")
            finally:
                # Lifetime ownership outlives bound-ticket completion. There is
                # no registration or completion gap between these domains.
                self._finish_local_source_operation(operation, failed=failed)
    setattr(cls, name, intake)
    _LOCAL_NATIVE_FINGERPRINT_CODES.add(intake.__code__)


def _instrument_local_native_request(cls, name, kind, *, completion_owner=None):
    from functools import wraps
    original = getattr(cls, name)
    _LOCAL_NATIVE_REQUEST_CODES[kind] = inspect.unwrap(completion_owner or original).__code__
    @wraps(original)
    def request(self, *args, **kwargs):
        operation = self._begin_local_source_operation(kind)
        state = getattr(self, "_p02_local_ingress", None)
        stack = getattr(state["thread"], "requests", ()) if state is not None else ()
        if state is not None:
            state["thread"].requests = (*stack,(kind,operation,datetime.now(timezone.utc)))
        failed = False
        try:
            result = original(self,*args,**kwargs)
            if state is not None:
                with state["lock"]:
                    failed = not any(receipt.revision_start == operation[4]
                        for receipt,context in state["request_completions"].values())
            return result
        except BaseException:
            failed = True
            raise
        finally:
            if state is not None:
                state["thread"].requests = stack
            self._finish_local_source_operation(operation,failed=failed)
    setattr(cls,name,request)


class IbkrClient(EWrapper, EClient):
    MAX_CLIENT_ID_RETRIES = 10
    NON_REJECTING_ORDER_WARNING_CODES = {2109}
    ORDER_ONLY_CALLBACK_CODES = {201, 202, 399}

    """
    Thin wrapper around ibapi for read-only operations.

    Responsibilities:
    - Connect/disconnect safely
    - Resolve contracts
    - Request market data snapshots
    - Report simple health status
    """

    def _initialize_local_source_lifetime(self):
        values = object.__getattribute__(self, "__dict__")
        existing = values.get("_p02_source_lifetime")
        if existing is not None:
            with existing["lock"]:
                existing["revision"] += 1
                existing["supported"] = False
                existing["unsupported"] = existing["unsupported"] or "NATIVE_REINITIALIZATION"
                existing["ready"] = False
            if values.get("_p02_local_ingress") is not None:
                raise RuntimeError("P02_LOCAL_NATIVE_REINITIALIZATION_UNSUPPORTED")
            return existing  # Legacy reinit never resets the lifetime witness.
        state = dict(owner=None, lock=_LocalSourceLock(), revision=0, next_ticket=0,
            tickets={}, origins={}, intake_threads={}, inflight=set(), thread=_LocalSourceThread(),
            process=os.getpid(), client_object_id=id(self), ready=False,
            supported=not bool(values), unsupported="NATIVE_PRECONSTRUCTION_STATE" if values else None,
            constructor_thread=_local_source_thread_id(), next_operation=0, operations={}, operation_tickets={},
            bootstrap_accounts=None, connect_count=0, request_completions={}, occurrences={})
        object.__setattr__(self, "_p02_source_lifetime", state)
        return state

    def _begin_local_source_operation(self, kind):
        state = object.__getattribute__(self, "__dict__").get("_p02_source_lifetime")
        if state is None:
            return None  # Legacy __new__ callbacks continue, but can never enroll.
        if type(kind) is not str or not kind:
            raise RuntimeError("P02_LOCAL_NATIVE_LIFETIME_KIND_INVALID")
        with state["lock"]:
            state["revision"] += 1
            state["next_operation"] += 1
            operation_id = -state["next_operation"]
            operation = (operation_id, object(), _local_source_thread_id(), kind, state["revision"])
            state["operations"][operation_id] = operation
            stack = getattr(state["thread"], "operations", ())
            state["thread"].operations = (*stack, operation)
            if state["owner"] is None:
                initializing = (not state["ready"] and _local_source_thread_id() == state["constructor_thread"]
                    and kind.startswith("INITIALIZE_"))
                bootstrap = kind in {"nextValidId", "managedAccounts", "connect", "connectAck"}
                if kind == "connect":
                    state["connect_count"] += 1
                    bootstrap = state["connect_count"] == 1
                if not initializing and not bootstrap:
                    state["supported"] = False
                    state["unsupported"] = state["unsupported"] or "PREBIND_" + kind
            return operation

    def _finish_local_source_operation(self, operation, *, failed=False):
        if operation is None:
            return
        state = self._p02_source_lifetime
        with state["lock"]:
            current = state["operations"].get(operation[0])
            stack = getattr(state["thread"], "operations", ())
            if current is not operation or operation[2] != _local_source_thread_id() or not stack or stack[-1] is not operation:
                state["supported"] = False
                state["unsupported"] = state["unsupported"] or "NATIVE_LIFETIME_OPERATION_CONFLICT"
                raise RuntimeError("P02_LOCAL_NATIVE_LIFETIME_OPERATION_INVALID")
            associated = state["operation_tickets"].pop(operation[0], None)
            if failed and state["owner"] is None:
                state["supported"] = False
                state["unsupported"] = state["unsupported"] or "PREBIND_CALLBACK_FAILED"
            elif failed and state["owner"] is not None:
                state["revision"] += 1
                current_ticket = state["tickets"].get(associated)
                if current_ticket is None:
                    # An exception before bound registration is still observed
                    # intake. It cannot disappear with the lifetime counter.
                    state["next_ticket"] += 1
                    current_ticket = LocalIntakeTicket(state["next_ticket"], operation[3], True, True,
                        operation[4], state["revision"], None, *self._local_scope_fields())
                    state["origins"][current_ticket.ticket_id] = current_ticket
                    state["intake_threads"][current_ticket.ticket_id] = _local_source_thread_id()
                else:
                    current_ticket = replace(current_ticket, finished=True, failed=True,
                        revision_end=state["revision"])
                    state["inflight"].discard(current_ticket.ticket_id)
                state["tickets"][current_ticket.ticket_id] = current_ticket
                state["occurrences"][current_ticket.ticket_id] = current_ticket
            del state["operations"][operation[0]]
            state["thread"].operations = stack[:-1]
            state["revision"] += 1

    def __setattr__(self, name, value):
        values = object.__getattribute__(self, "__dict__")
        lifetime = values.get("_p02_source_lifetime")
        if lifetime is None or name not in {"client_id", "_position_connection_epoch", "_managed_accounts"}:
            return object.__setattr__(self, name, value)
        active = getattr(lifetime["thread"], "intake", ())
        operations = getattr(lifetime["thread"], "operations", ())
        if not lifetime["ready"] and _local_source_thread_id() == lifetime["constructor_thread"]:
            kind = "INITIALIZE_" + name
        else:
            kind = active[-1].kind if active else operations[-1][3] if operations else "SET_" + name
        operation = self._begin_local_source_operation(kind)
        ticket = None
        failed = False
        try:
            if lifetime["owner"] is None and name == "_managed_accounts" and lifetime["ready"]:
                accounts = tuple(value) if type(value) in (list, tuple) and all(type(row) is str for row in value) else None
                with lifetime["lock"]:
                    if accounts is None or (lifetime["bootstrap_accounts"] is not None
                            and lifetime["bootstrap_accounts"] != accounts):
                        lifetime["supported"] = False
                        lifetime["unsupported"] = lifetime["unsupported"] or "PREBIND_ACCOUNT_REBIND"
                    elif accounts:
                        lifetime["bootstrap_accounts"] = accounts
            ticket = self.begin_local_intake(kind)
            if ticket is not None:
                raw = _local_native_value((name,value))
                self._local_intake_fingerprint(ticket,
                    hashlib.sha256(repr(raw).encode()).hexdigest(),semantic_payload=raw)
            object.__setattr__(self, name, value)
        except BaseException:
            failed = True
            raise
        finally:
            try:
                if ticket is not None:
                    self.finish_local_intake(ticket, "FAILED" if failed else "RETURNED")
            finally:
                self._finish_local_source_operation(operation, failed=failed)

    def bind_local_cooldown_owner(self, owner) -> None:
        """Dedicated synthetic TEST/PAPER participation only, default off.

        Constructor-lifetime observation is bounded metadata, not global client
        exclusivity or broker history. Shared operational enrollment is unsupported.
        """
        from src.execution.execution_engine import ExecutionEngine
        from src.config.runtime_config import RunMode
        from src.config.config_resolver import get_config
        state = object.__getattribute__(self, "__dict__").get("_p02_source_lifetime")
        if (type(owner) is not ExecutionEngine or os.environ.get("EXECUTION_ENV") != "TEST"
                or owner.run_mode != RunMode.PAPER or get_config("RUN_MODE_EFFECTIVE") != "PAPER"
                or getattr(owner, "_p02_local", {}).get("client") is not self
                or getattr(self, "_p02_local_ingress", None) is not None or state is None):
            raise RuntimeError("P02_LOCAL_NATIVE_ENROLLMENT_UNAVAILABLE")
        if not state["lock"].acquire(blocking=False):
            raise RuntimeError("P02_LOCAL_NATIVE_ENROLLMENT_BUSY")
        try:
            if (not state["ready"] or not state["supported"] or state["owner"] is not None
                    or state["process"] != os.getpid() or state["client_object_id"] != id(self)
                    or state["operations"] or state["inflight"]):
                raise RuntimeError("P02_LOCAL_NATIVE_LIFETIME_UNAVAILABLE")
            state["owner"] = owner
            # SAME lifetime lock/revision, seeded directly: no recursive lock
            # acquisition, reset, or window for an earlier callback to disappear.
            state["revision"] += 1
            state["next_ticket"] += 1
            start = state["revision"]
            state["revision"] += 1
            ticket = LocalIntakeTicket(state["next_ticket"], "BASELINE", True, False,
                start, state["revision"], "INITIAL_OBSERVED_LOCAL_STATE", *self._local_scope_fields())
            state["tickets"][ticket.ticket_id] = ticket
            state["occurrences"][ticket.ticket_id] = ticket
            state["origins"][ticket.ticket_id] = ticket
            state["intake_threads"][ticket.ticket_id] = _local_source_thread_id()
            object.__setattr__(self, "_p02_local_ingress", state)
        finally:
            state["lock"].release()

    def _local_scope_fields(self):
        # Exact builtin owner fields only; no property/parser/SDK invocation in I.
        values = object.__getattribute__(self, "__dict__")
        client_id, epoch = values.get("client_id"), values.get("_position_connection_epoch")
        accounts = values.get("_managed_accounts", ())
        accounts = tuple(accounts) if type(accounts) in (tuple, list) and all(type(row) is str for row in accounts) else ()
        return (id(self), client_id if type(client_id) is int else None,
            epoch if type(epoch) is int else None, accounts)

    def begin_local_intake(self, kind):
        state = getattr(self, "_p02_local_ingress", None)
        if state is None:
            return None
        if type(kind) is not str or not kind:
            raise RuntimeError("P02_LOCAL_INTAKE_KIND_INVALID")
        # I performs bookkeeping only. No cache, owner, SQL or SDK lock here.
        with state["lock"]:
            state["revision"] += 1
            state["next_ticket"] += 1
            ticket = LocalIntakeTicket(state["next_ticket"], kind, False, False,
                state["revision"], None, None, *self._local_scope_fields())
            state["tickets"][ticket.ticket_id] = ticket
            state["origins"][ticket.ticket_id] = ticket
            state["intake_threads"][ticket.ticket_id] = _local_source_thread_id()
            state["inflight"].add(ticket.ticket_id)
            operations = getattr(state["thread"], "operations", ())
            if operations:
                state["operation_tickets"][operations[-1][0]] = ticket.ticket_id
            return ticket

    def _local_intake_fingerprint(self, ticket, fingerprint, *, semantic_payload=None):
        import sys
        state = self._p02_local_ingress
        with state["lock"]:
            if (sys._getframe(1).f_code not in _LOCAL_NATIVE_FINGERPRINT_CODES
                    or state["origins"].get(ticket.ticket_id) is not ticket
                    or ticket.ticket_id not in state["inflight"]
                    or state["intake_threads"].get(ticket.ticket_id) != _local_source_thread_id()):
                raise RuntimeError("P02_LOCAL_SEMANTIC_SOURCE_REQUIRED")
            current = state["tickets"].get(ticket.ticket_id)
            if current is not None:
                state["tickets"][ticket.ticket_id] = replace(current, raw_fingerprint=fingerprint,
                    semantic_payload=semantic_payload)

    def _local_intake_failed(self, ticket):
        state = self._p02_local_ingress
        with state["lock"]:
            current = state["tickets"].get(ticket.ticket_id)
            if current is not None:
                state["tickets"][ticket.ticket_id] = replace(current, failed=True)

    def _publish_local_intake(self, kind, **facts):
        state = getattr(self,"_p02_local_ingress",None)
        if state is None:
            return None
        import sys
        stack = getattr(state["thread"],"intake",())
        if (sys._getframe(1).f_code is not _LOCAL_NATIVE_PUBLICATION_CODES.get(kind)
                or not stack or stack[-1].kind != kind):
            raise RuntimeError("P02_LOCAL_PUBLICATION_SOURCE_REQUIRED")
        ticket = stack[-1]
        if any(type(key) is not str or type(value) not in (str,int,bool,type(None))
                for key,value in facts.items()):
            raise RuntimeError("P02_LOCAL_PUBLICATION_FACTS_INVALID")
        publication = tuple(sorted(dict(kind=kind,**facts).items()))
        with state["lock"]:
            current = state["tickets"].get(ticket.ticket_id)
            if (state["origins"].get(ticket.ticket_id) is not ticket
                    or state["intake_threads"].get(ticket.ticket_id) != _local_source_thread_id()
                    or ticket.ticket_id not in state["inflight"] or current is None
                    or current.publication is not None):
                raise RuntimeError("P02_LOCAL_PUBLICATION_TICKET_INVALID")
            state["revision"] += 1
            state["tickets"][ticket.ticket_id] = replace(current,publication=publication)
        return ticket.ticket_id

    def local_intake_occurrence(self, ticket):
        state = getattr(self,"_p02_local_ingress",None)
        if state is None or type(ticket) is not LocalIntakeTicket:
            raise RuntimeError("P02_LOCAL_OCCURRENCE_UNAVAILABLE")
        if not state["lock"].acquire(blocking=False):
            raise RuntimeError("P02_LOCAL_NATIVE_INGRESS_BUSY")
        try:
            if (state["occurrences"].get(ticket.ticket_id) is not ticket
                    or ticket.client_object_id != id(self)
                    or ticket.client_id != self._local_scope_fields()[1]
                    or ticket.connection_epoch != self._local_scope_fields()[2]
                    or ticket.accounts != self._local_scope_fields()[3]
                    or ticket.ticket_id not in state["origins"]):
                raise RuntimeError("P02_LOCAL_OCCURRENCE_UNAVAILABLE")
            return ticket
        finally:
            state["lock"].release()

    def local_intake_occurrences(self):
        state = getattr(self,"_p02_local_ingress",None)
        if state is None or not state["lock"].acquire(blocking=False):
            raise RuntimeError("P02_LOCAL_OCCURRENCES_UNAVAILABLE")
        try:
            self._local_intake_snapshot_locked()
            return tuple(state["occurrences"][key] for key in sorted(state["occurrences"]))
        finally:
            state["lock"].release()

    def local_financial_cache_snapshot(self):
        before = self.local_intake_snapshot()
        if before.inflight or not self._lock.acquire(blocking=False):
            raise RuntimeError("P02_LOCAL_NATIVE_CACHE_BUSY")
        try:
            def keyed(values):
                if any(type(key) is not int for key in values):
                    raise RuntimeError("P02_LOCAL_NATIVE_CACHE_KEYS_INVALID")
                return tuple((key,_local_native_value(value)) for key,value in sorted(values.items()))
            def namespace(value):
                if type(value) is not SimpleNamespace:
                    raise RuntimeError("P02_LOCAL_NATIVE_CACHE_ROW_UNSUPPORTED")
                return _local_native_value(vars(value))
            if (any(type(key) is not int for key in self._open_orders_snapshot)
                    or any(type(key) is not str or not key for key in self._commission_by_exec_id)):
                raise RuntimeError("P02_LOCAL_NATIVE_CACHE_KEYS_INVALID")
            value = dict(revision=before.revision,scope=(before.client_object_id,before.client_id,
                before.connection_epoch,before.accounts),
                exec_details_by_order=keyed(self._exec_details_by_order),
                order_status=keyed(self._order_status),
                open_orders_snapshot=tuple((key,namespace(row)) for key,row in sorted(self._open_orders_snapshot.items())),
                executions_snapshot=tuple(namespace(row) for row in self._executions_snapshot),
                native_executions=tuple((key,self.cached_native_executions(key))
                    for key in sorted(self._exec_details_by_order)),
                commission_execution_ids=tuple(sorted(self._commission_by_exec_id)),
                native_execution_fees=tuple((key,self.cached_native_execution_fees(key))
                    for key in sorted(self._exec_details_by_order)))
        finally:
            self._lock.release()
        if self.local_intake_snapshot() != before:
            raise RuntimeError("P02_LOCAL_NATIVE_CACHE_CHANGED")
        return MappingProxyType(value)

    def _issue_local_request_completion(self, kind, req_id, context, *, rows=(), currency=None, tags=()):
        state = getattr(self,"_p02_local_ingress",None)
        if state is None:
            return
        import sys
        requests = getattr(state["thread"],"requests",())
        if (sys._getframe(1).f_code is not _LOCAL_NATIVE_REQUEST_CODES.get(kind)
                or not requests or requests[-1][0] != kind):
            raise RuntimeError("P02_LOCAL_REQUEST_OWNER_REQUIRED")
        operation,started = requests[-1][1:]
        with state["lock"]:
            scope = self._local_scope_fields()
            if (state["operations"].get(operation[0]) is not operation
                    or context["epoch"] != scope[2] or context["client_id"] != scope[1]
                    or scope[3] != (context["account"],) or state["inflight"]
                    or context.get("_local_cleanup_revision") != state["revision"]):
                return
            receipt = LocalRequestCompletion(kind,self,id(self),scope[1],scope[2],context["account"],
                req_id,id(context),started,context["completed_at"],operation[4],state["revision"],
                tuple(rows),currency,tuple(tags),True,True,tuple(context.get("_local_callback_ticket_ids",())))
            state["request_completions"][(kind,req_id)] = (receipt,context)

    def _local_request_cleanup_revision(self):
        state = getattr(self,"_p02_local_ingress",None)
        if state is None:
            return None
        with state["lock"]:
            return state["revision"]

    @staticmethod
    def _local_position_completion_rows(context):
        rows = []
        for row in context["rows"].values():
            if type(row) is not SimpleNamespace or type(row.contract) is not Contract:
                raise ValueError("P02_LOCAL_POSITION_ROW_UNSUPPORTED")
            contract = row.contract
            quantity,average = row.position,row.avgCost
            if (type(contract.conId) is not int or contract.conId <= 0 or contract.secType != "STK"
                    or type(contract.currency) is not str or len(contract.currency) != 3
                    or not contract.currency.isascii() or not contract.currency.isalpha()
                    or contract.currency != contract.currency.upper()
                    or type(row.account) is not str or row.account != context["account"]
                    or type(row.symbol) is not str or not row.symbol
                    or type(contract.symbol) is not str or contract.symbol.strip().upper() != row.symbol
                    or type(quantity) not in (int,float,Decimal) or type(average) not in (int,float,Decimal)
                    or not math.isfinite(float(quantity)) or quantity != int(quantity)
                    or not math.isfinite(float(average))):
                raise ValueError("P02_LOCAL_POSITION_ROW_INVALID")
            rows.append(MappingProxyType(dict(account=row.account,con_id=contract.conId,symbol=row.symbol,
                sec_type=contract.secType,currency=contract.currency,quantity=int(quantity),avg_cost=float(average))))
        return tuple(sorted(rows,key=lambda row:(row["account"],row["con_id"],row["symbol"])))

    def local_request_completion(self, kind, request_id):
        state = getattr(self,"_p02_local_ingress",None)
        if (state is None or kind not in {"POSITIONS_MULTI","ACCOUNT_CURRENCY_STRICT"}
                or type(request_id) is not int):
            return None
        if (not self.is_connected() or self._stop_event.is_set()
                or not self._position_transport_available):
            return None
        if not state["lock"].acquire(blocking=False):
            raise RuntimeError("P02_LOCAL_NATIVE_INGRESS_BUSY")
        try:
            snapshot = self._local_intake_snapshot_locked()
            row = state["request_completions"].get((kind,request_id))
            if row is None or snapshot.inflight:
                return None
            receipt,context = row
            if (receipt.source_client is not self or receipt.context_id != id(context)
                    or (receipt.client_object_id,receipt.client_id,receipt.connection_epoch,(receipt.account,))
                        != (snapshot.client_object_id,snapshot.client_id,snapshot.connection_epoch,snapshot.accounts)):
                return None
            return receipt
        finally:
            state["lock"].release()

    def finish_local_intake(self, ticket, outcome):
        if ticket is None:
            return
        if type(ticket) is not LocalIntakeTicket:
            raise RuntimeError("P02_LOCAL_INTAKE_TICKET_INVALID")
        state = self._p02_local_ingress
        returned = type(outcome) is str and outcome == "RETURNED"
        with state["lock"]:
            current = state["tickets"].get(ticket.ticket_id)
            if (current is None or current.client_object_id != id(self)
                    or state["origins"].get(ticket.ticket_id) is not ticket
                    or state["intake_threads"].get(ticket.ticket_id) != _local_source_thread_id()
                    or ticket.revision_start != current.revision_start
                    or ticket.ticket_id not in state["inflight"]):
                raise RuntimeError("P02_LOCAL_INTAKE_TICKET_INVALID")
            state["revision"] += 1
            state["inflight"].remove(ticket.ticket_id)
            state["tickets"][ticket.ticket_id] = replace(current, finished=True,
                failed=current.failed or not returned, revision_end=state["revision"])
            state["occurrences"][ticket.ticket_id] = state["tickets"][ticket.ticket_id]
            # Completion never removes dirty intake. Only the real collector's
            # verified owner receipt can settle this exact generation.

    def _local_intake_snapshot_locked(self):
        state = self._p02_local_ingress
        if (state["process"] != os.getpid() or state["client_object_id"] != id(self)
                or not state["ready"] or not state["supported"]):
            raise RuntimeError("P02_LOCAL_NATIVE_LIFETIME_UNAVAILABLE")
        return LocalIntakeSnapshot(state["revision"], tuple(sorted((*state["inflight"], *state["operations"]))),
            tuple(state["tickets"].values()), *self._local_scope_fields())

    def local_intake_snapshot(self):
        state = getattr(self, "_p02_local_ingress", None)
        if state is None:
            raise RuntimeError("P02_LOCAL_NATIVE_NOT_ENROLLED")
        if not state["lock"].acquire(blocking=False):
            raise RuntimeError("P02_LOCAL_NATIVE_INGRESS_BUSY")
        try:
            return self._local_intake_snapshot_locked()
        finally:
            state["lock"].release()

    def settle_local_intake(self, ticket, committed_binding):
        state = self._p02_local_ingress
        before = self.local_intake_snapshot()
        if (type(ticket) is not LocalIntakeTicket or ticket not in before.dirty
                or not ticket.finished or ticket.failed or ticket.raw_fingerprint is None
                or before.inflight):
            raise RuntimeError("P02_LOCAL_INTAKE_NOT_SETTLEABLE")
        # Owner verification may read actual cache/journal state. It must run
        # OUTSIDE I, in the actual collector's still-owned mutation frame.
        if state["owner"]._verify_local_intake_settlement(self, ticket, committed_binding) is not True:
            raise RuntimeError("P02_LOCAL_INTAKE_RECEIPT_UNVERIFIED")
        if not state["lock"].acquire(blocking=False):
            raise RuntimeError("P02_LOCAL_NATIVE_INGRESS_BUSY")
        try:
            after = self._local_intake_snapshot_locked()
            if (after != before or state["tickets"].get(ticket.ticket_id) != ticket):
                raise RuntimeError("P02_LOCAL_INTAKE_CHANGED_DURING_SETTLEMENT")
            del state["tickets"][ticket.ticket_id]
            # Only the dirty marker is consumed. The original immutable
            # occurrence/origin remains available for later cache revalidation.
            state["revision"] += 1
        finally:
            state["lock"].release()

    @staticmethod
    def local_native_order_fingerprint(contract, order):
        if type(contract) is not Contract or type(order) is not Order:
            raise RuntimeError("P02_LOCAL_NATIVE_DESCRIPTOR_TYPES_UNSUPPORTED")
        return (_local_native_value(contract), _local_native_value(order))

    def placeOrder(self, orderId, contract, order):  # type: ignore[override]
        state = getattr(self, "_p02_local_ingress", None)
        if state is None:
            return delegate_sdk_place_order(self, _NATIVE_AUDITED_SDK_PLACE_ORDER,
                super().placeOrder, orderId, contract, order)
        context = getattr(state["thread"], "submit", None)
        if context is None or context.get("lease") is None:
            # Existing protective/reduction SELL paths retain their own gates.
            # A supplied entry lease never escapes comparison by changing side.
            if type(order) is Order and type(order.action) is str and order.action == "SELL":
                return delegate_sdk_place_order(self, _NATIVE_AUDITED_SDK_PLACE_ORDER,
                    super().placeOrder, orderId, contract, order)
            raise RuntimeError("P02_LOCAL_UNGUARDED_NATIVE_ENTRY")
        if context["order_id"] != orderId:
            raise RuntimeError("P02_LOCAL_NATIVE_ENTRY_ID_CHANGED")
        lease = context["lease"]
        from src.execution.execution_engine import _P02LocalEntryLease
        try:
            if type(lease) is not _P02LocalEntryLease or lease.owner is not state["owner"]:
                raise RuntimeError("P02_LOCAL_ENTRY_ISSUER_INVALID")
            initial = self.local_native_order_fingerprint(contract, order)
            detached_contract, detached_order = deepcopy(contract), deepcopy(order)
            if (self.local_native_order_fingerprint(detached_contract, detached_order) != initial
                    or self.local_native_order_fingerprint(contract, order) != initial):
                raise RuntimeError("P02_LOCAL_NATIVE_ARGUMENTS_CHANGED")
            if not state["lock"].acquire(blocking=False):
                raise RuntimeError("P02_LOCAL_NATIVE_INGRESS_BUSY")
            try:
                snapshot = replace(self._local_intake_snapshot_locked(),
                    invocation_fingerprint=(orderId, *initial))
                if snapshot.inflight or snapshot.dirty:
                    raise RuntimeError("P02_LOCAL_NATIVE_UNSETTLED_INGRESS")
                authorized = lease._consume_native_entry_locked(
                    self, orderId, detached_contract, detached_order, snapshot)
            finally:
                state["lock"].release()
            # This closes the SAME G/SQL lease before the audited SDK body.
            lease.close_after_entry()
            if authorized is not True or lease.admission_authorized is not True:
                raise RuntimeError("P02_LOCAL_NATIVE_BRIDGE_NOT_ADOPTED")
            return delegate_sdk_place_order(self, _NATIVE_AUDITED_SDK_PLACE_ORDER,
                super().placeOrder, orderId, detached_contract, detached_order)
        except BaseException:
            if type(lease) is _P02LocalEntryLease and lease.owner is state["owner"]:
                lease.abort()
            raise

    @staticmethod
    def _official_order_cancel(value):
        from ibapi.order_cancel import OrderCancel

        if value is None:
            return OrderCancel()
        if type(value) is str:
            request = OrderCancel()
            request.manualOrderCancelTime = value
            return request
        if type(value) is not OrderCancel:
            raise TypeError("IBKR_ORDER_CANCEL_ARGUMENT_INVALID")
        return value

    def cancelOrder(self, orderId, orderCancel=None):  # type: ignore[override]
        # The audited SDK boundary owns the one mutation count and the current
        # PAPER/account checks, including its immediate protobuf delegation.
        if _sdk_distribution_version("ibapi") == "10.50.2":
            return super().cancelOrder(orderId, self._official_order_cancel(orderCancel))
        if orderCancel is not None:
            raise TypeError("IBKR_LEGACY_ORDER_CANCEL_ARGUMENT_UNSUPPORTED")
        return super().cancelOrder(orderId)

    def reqGlobalCancel(self, orderCancel=None):  # type: ignore[override]
        if _sdk_distribution_version("ibapi") == "10.50.2":
            return super().reqGlobalCancel(self._official_order_cancel(orderCancel))
        if orderCancel is not None:
            raise TypeError("IBKR_LEGACY_ORDER_CANCEL_ARGUMENT_UNSUPPORTED")
        return super().reqGlobalCancel()

    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        snapshot_timeout_seconds: int,
        market_data_type: str,
        readonly_enabled: bool,
    ):
        # Mutable modern clients require an explicit local PAPER endpoint. Every
        # mutation additionally verifies the connected account and existing gates.
        if _sdk_distribution_version("ibapi") == "10.50.2":
            from src.ibkr.sdk_profile import require_sdk_paper_connection, require_supported_sdk
            require_supported_sdk()
            if readonly_enabled is not True:
                require_sdk_paper_connection(host, port)
        lifetime = self._initialize_local_source_lifetime()
        EWrapper.__init__(self)
        EClient.__init__(self, wrapper=self)
        self.host = host
        self.port = port
        self.client_id = client_id
        self._quote_trace = QuoteDiagnostics(client_id)
        self.snapshot_timeout_seconds = snapshot_timeout_seconds
        self.market_data_type = market_data_type.upper()
        self.readonly_enabled = readonly_enabled
        self._req_id = 0
        self._pending_request_allocations: set[int] = set()
        self._lock = threading.RLock()
        self._contract_events: Dict[int, threading.Event] = {}
        self._contract_details: Dict[int, List[ContractDetails]] = {}
        self._market_events: Dict[int, threading.Event] = {}
        self._market_data: Dict[int, Dict[str, Optional[float]]] = {}
        self._price_rule_requests: dict[int, dict] = {}
        self._price_rule_sequence = 0
        self._historical_states: dict[int, dict] = {}
        self._historical_events: Dict[int, threading.Event] = {}
        self._historical_data: Dict[int, List[object]] = {}
        self._errors: Dict[int, Tuple[int, str]] = {}
        self._broker_error_events: list[dict] = []
        self._request_context_by_req_id: dict[int, dict] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._connection_event = threading.Event()
        self._last_disconnect_reason: Optional[str] = None
        self._next_order_id: Optional[int] = None
        self._next_valid_order_id: Optional[int] = None
        self._last_reserved_order_id: Optional[int] = self._load_last_reserved_order_id()
        self._order_status_events: Dict[int, threading.Event] = {}
        self._order_status: Dict[int, Dict[str, Optional[float | int | str]]] = {}
        self._order_errors: Dict[int, Tuple[int, str]] = {}
        self._order_warnings: Dict[int, Tuple[int, str]] = {}
        self._exec_details_by_order: Dict[int, List[dict]] = {}
        # One existing cache: latest numeric legacy projection plus copied
        # source-report metadata. This is not a fee/NET accounting ledger.
        self._commission_by_exec_id: Dict[str, dict | float] = {}
        self._account_summary_events: Dict[int, threading.Event] = {}
        self._account_summary_rows: Dict[int, Dict[str, str]] = {}
        self._managed_accounts_event = threading.Event()
        self._managed_accounts: list[str] = []
        self._scanner_events: Dict[int, threading.Event] = {}
        self._scanner_rows: Dict[int, List[object]] = {}
        self._ticker_by_req_id: Dict[int, object] = {}
        self._req_id_by_contract_key: Dict[tuple, int] = {}
        self._market_update_event = threading.Event()
        self._request_type_by_req_id: Dict[int, str] = {}
        self._active_market_req_ids: set[int] = set()
        self._order_state_registry: Dict[int, dict] = {}
        self._execution_callbacks: list = []
        self._open_orders_snapshot: Dict[int, object] = {}
        self._open_orders_event = threading.Event()
        self._open_orders_query_lock = threading.Lock()
        self._open_orders_unresolved = False
        self._executions_snapshot: list[object] = []
        self._executions_event = threading.Event()
        self._positions_snapshot: Dict[str, object] = {}
        self._positions_event = threading.Event()
        self._position_queries: dict[int, dict] = {}
        self._position_connection_epoch = 0
        self._position_transport_available = False
        self._position_upstream_lost = False
        self._commission_constructor_queue = self.msg_queue
        self._commission_connection_attempts = 0
        self._commission_zero_disabled = False
        self._commission_decoder_proxy = None
        self._open_order_count = 0
        self._order_status_count = 0
        self._exec_details_count = 0
        with lifetime["lock"]:
            lifetime["ready"] = True
            lifetime["revision"] += 1

    def _order_id_state_path(self) -> Path:
        return Path(os.environ.get("IBKR_ORDER_ID_STATE_PATH", Path.home() / ".ibkr_order_id_state.json"))

    def _load_last_reserved_order_id(self) -> Optional[int]:
        try:
            path = self._order_id_state_path()
            if not path.exists():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            value = int(payload.get("last_reserved_order_id"))
            return value if value > 0 else None
        except Exception:
            return None

    def _persist_last_reserved_order_id(self, order_id: int) -> None:
        try:
            path = self._order_id_state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"last_reserved_order_id": int(order_id)}), encoding="utf-8")
        except Exception as exc:
            print(f"[IBKR][ORDER_ID_PERSIST_WARN] reason={exc}")


    def _ensure_order_state_registry(self) -> None:
        if not hasattr(self, "_order_state_registry") or self._order_state_registry is None:
            self._order_state_registry = {}

    def cached_order_status(self, order_id: int) -> dict:
        """Read callback-owned facts only; does not request data or connect."""
        return dict(self._order_status.get(int(order_id), {}))

    @staticmethod
    def normalize_native_execution_time(value) -> datetime:
        """Require an explicit broker instant; never infer a zone or receipt time."""
        def utc(stamp):
            try:
                return stamp.astimezone(timezone.utc)
            except (ValueError, OverflowError):
                raise ValueError("NATIVE_EXECUTION_TIME_UNAVAILABLE") from None
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("NATIVE_EXECUTION_TIME_UNAVAILABLE")
            return utc(value)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("NATIVE_EXECUTION_TIME_UNAVAILABLE")
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("NATIVE_EXECUTION_TIME_UNAVAILABLE")
            return utc(parsed)

        parts = text.split()
        if len(parts) < 2:
            raise ValueError("NATIVE_EXECUTION_TIME_UNAVAILABLE")
        zone_name = parts[-1]
        # Abbreviations such as EST/EDT and configured local zones are not an
        # unambiguous execution-time contract. Explicit IANA aliases are valid.
        if zone_name not in {"UTC", "GMT"} and "/" not in zone_name:
            raise ValueError("NATIVE_EXECUTION_TIME_UNAVAILABLE")
        try:
            # Canonical spelling for the explicit IANA alias used by TWS;
            # some installed zone databases omit the legacy alias file.
            zone = ZoneInfo({"US/Eastern": "America/New_York"}.get(zone_name, zone_name))
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("NATIVE_EXECUTION_TIME_UNAVAILABLE") from None
        core = " ".join(parts[:-1])
        local = None
        for pattern in ("%Y%m%d %H:%M:%S", "%Y%m%d-%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                local = datetime.strptime(core, pattern)
                break
            except ValueError:
                pass
        if local is None:
            raise ValueError("NATIVE_EXECUTION_TIME_UNAVAILABLE")
        candidates = [local.replace(tzinfo=zone, fold=fold) for fold in (0, 1)]
        valid = [stamp for stamp in candidates
                 if utc(stamp).astimezone(zone).replace(tzinfo=None) == local]
        if not valid or len({stamp.utcoffset() for stamp in valid}) != 1:
            # Reject spring gaps and autumn folds instead of inventing an instant.
            raise ValueError("NATIVE_EXECUTION_TIME_UNAVAILABLE")
        return utc(valid[0])

    def cached_native_executions(self, order_id: int) -> tuple[Mapping, ...]:
        """Copy unsolicited execution facts only; no history/query/reconnect.

        This is callback evidence, not permission or coverage/finality. The
        existing native owner must bind account/client/epoch/security/root and
        establish its exact cumulative interval before applying any DELTA.
        """
        if type(order_id) is not int or order_id < 0:
            raise ValueError("NATIVE_EXECUTION_ORDER_ID_INVALID")
        with self._lock:
            # Reuse the sole existing per-order callback owner. History queries
            # also append legacy rows here; their records carry no live authority.
            all_rows = [deepcopy(row) for rows in self._exec_details_by_order.values()
                        for row in rows if row.get("_native_unsolicited") is True]
            identity_conflicted = self._request_id_conflicted(order_id)
        selected = [row for row in all_rows if row.get("orderId") == order_id]
        if selected and identity_conflicted:
            raise ValueError("NATIVE_EXECUTION_IDENTITY_CONFLICT")
        identities = {row.get("execId") for row in selected
                      if isinstance(row.get("execId"), str)}
        deduped = {}
        # Conflicting use of one execution ID on another order is also visible;
        # do not let a per-order lookup hide a wrong-root execution duplicate.
        for row in all_rows:
            if row.get("orderId") != order_id:
                if not isinstance(row.get("execId"), str) or row["execId"] not in identities:
                    continue
            if (not isinstance(row.get("execId"), str) or not row["execId"].strip()
                    or any(type(row.get(key)) is not int or row[key] < minimum
                           for key, minimum in (("orderId", 0), ("clientId", 0),
                                                ("conId", 1), ("connection_epoch", 0)))
                    or not isinstance(row.get("account"), str) or not row["account"].strip()
                    or not isinstance(row.get("symbol"), str) or not row["symbol"].strip()
                    or row.get("secType") != "STK" or row.get("side") not in {"BOT", "SLD"}):
                raise ValueError("NATIVE_EXECUTION_FACTS_INVALID")
            normalized = {key: row[key] for key in (
                "execId", "time", "orderId", "account", "clientId", "conId",
                "symbol", "secType", "side", "shares", "price", "cumQty", "avgPrice",
                "connection_epoch")}
            try:
                for key in ("shares", "price", "cumQty", "avgPrice"):
                    if isinstance(row[key], bool):
                        raise ValueError
                    value = Decimal(str(row[key]))
                    if not value.is_finite() or value <= 0:
                        raise ValueError
                    normalized[key] = value
            except (KeyError, TypeError, ValueError, InvalidOperation):
                raise ValueError("NATIVE_EXECUTION_FACTS_INVALID") from None
            if normalized["cumQty"] < normalized["shares"]:
                raise ValueError("NATIVE_EXECUTION_FACTS_INVALID")
            normalized["timestamp_utc"] = self.normalize_native_execution_time(row["time"])
            previous = deduped.get(row["execId"])
            if previous is not None and previous != normalized:
                raise ValueError("NATIVE_EXECUTION_DUPLICATE_CONFLICT")
            deduped[row["execId"]] = normalized
        return tuple(MappingProxyType(dict(row)) for row in sorted(
            (row for row in deduped.values() if row["orderId"] == order_id),
            key=lambda row: (row["cumQty"], row["execId"])))

    def cached_native_execution_fees(self, order_id: int) -> tuple[Mapping, ...]:
        """Copy per-execution API report facts, never whole-trade NET authority.

        The execution owner supplies identity and BOT/SLD side; a fee callback
        supplies neither root/strategy nor account/security. Receipt time is
        local observation time, not a fill timestamp or economic-day allocation.
        """
        try:
            from ibapi.common import UNSET_DOUBLE
        except ImportError:
            from ibapi.const import UNSET_DOUBLE  # Official SDK 10.50 moved constants.

        def currency_valid(value):
            return (isinstance(value, str) and len(value) == 3 and value.isascii()
                    and value.isalpha() and value == value.upper())
        with self._lock:
            executions = self.cached_native_executions(order_id)
            observations = []
            for execution in executions:
                reasons = []
                currencies = tuple(row.get("currency") for row in self._exec_details_by_order.get(order_id, ())
                    if row.get("_native_unsolicited") is True and row.get("execId") == execution["execId"])
                instrument_currency = currencies[0] if currencies else None
                if any(value != instrument_currency for value in currencies):
                    reasons.append("EXECUTION_CURRENCY_CONFLICT")
                    instrument_currency = None
                if not currency_valid(instrument_currency):
                    reasons.append("EXECUTION_CURRENCY_UNAVAILABLE")
                if type(self.client_id) is not int or self.client_id != execution["clientId"]:
                    reasons.append("CURRENT_CLIENT_SCOPE_CHANGED")
                if (type(self._position_connection_epoch) is not int
                        or self._position_connection_epoch != execution["connection_epoch"]):
                    reasons.append("CURRENT_EXECUTION_EPOCH_CHANGED")
                if (not self.is_connected() or self._stop_event.is_set()
                        or not self._position_transport_available):
                    reasons.append("CURRENT_CONNECTION_UNAVAILABLE")
                if tuple(self._managed_accounts) != (execution["account"],):
                    reasons.append("CURRENT_ACCOUNT_SCOPE_UNAVAILABLE")
                cached = self._commission_by_exec_id.get(execution["execId"])
                first = latest = None
                count = 0
                conflict = False
                if cached is None:
                    reasons.append("MISSING_COMMISSION_REPORT")
                elif not isinstance(cached, dict):
                    reasons.append("LEGACY_COMMISSION_UNSCOPED")
                else:
                    first, latest = cached["first_report"], cached["latest_report"]
                    count, conflict = cached["report_count"], cached["conflict"]
                    if conflict:
                        reasons.append("COMMISSION_REPORT_CONFLICT")
                    if cached["unscoped_prior"]:
                        reasons.append("LEGACY_COMMISSION_UNSCOPED")
                    if (type(first["client_id"]) is not int or first["client_id"] != execution["clientId"]
                            or type(first["connection_epoch"]) is not int
                            or first["connection_epoch"] != execution["connection_epoch"]
                            or first["managed_accounts"] != (execution["account"],)
                            or first["connected"] is not True or first["stopped"] is not False
                            or first["transport_available"] is not True):
                        reasons.append("COMMISSION_REPORT_SCOPE_UNAVAILABLE")
                    amount = first["amount"]
                    if amount is None:
                        reasons.append("COMMISSION_AMOUNT_UNAVAILABLE")
                    elif not amount.is_finite() or not math.isfinite(float(amount)):
                        reasons.append("NONFINITE_COMMISSION")
                    elif float(amount) == UNSET_DOUBLE:
                        reasons.append("SDK_UNSET_COMMISSION")
                    elif amount < 0:
                        reasons.append("NEGATIVE_COMMISSION_POLICY_UNADOPTED")
                    elif amount == 0 and not self._commission_zero_report_current(first):
                        reasons.append("ZERO_COMMISSION_WIRE_PRESENCE_UNAVAILABLE")
                    if not currency_valid(first["currency"]):
                        reasons.append("COMMISSION_CURRENCY_UNAVAILABLE")
                    elif currency_valid(instrument_currency) and first["currency"] != instrument_currency:
                        reasons.append("COMMISSION_CURRENCY_MISMATCH")
                bound = not reasons
                observations.append(MappingProxyType({
                    "execution": MappingProxyType(dict(execution)),
                    "execution_currency": instrument_currency,
                    "report_currency": first["currency"] if first is not None else None,
                    "amount": first["amount"] if bound else None,
                    "first_report": MappingProxyType(dict(first)) if first is not None else None,
                    "latest_report": MappingProxyType(dict(latest)) if latest is not None else None,
                    "report_count": count, "conflict": conflict,
                    "report_status": "BOUND_API_REPORT" if bound else "UNAVAILABLE",
                    "reason": reasons[0] if reasons else None,
                    "unavailable_reasons": tuple(reasons),
                    "net_status": "UNAVAILABLE_FOR_NET", "source": "IBKR_COMMISSION_REPORT"}))
            return tuple(observations)

    def register_execution_callback(self, callback, *, internal_reconciliation=False) -> None:
        if callback is None:
            return
        if callback in self._execution_callbacks:
            return
        self._execution_callbacks.append(callback)
        if internal_reconciliation:
            if not hasattr(self, "_internal_execution_callbacks"):
                self._internal_execution_callbacks = set()
            self._internal_execution_callbacks.add(callback)

    def register_reconciliation_callback(self, callback) -> None:
        self.register_execution_callback(callback, internal_reconciliation=True)

    def _emit_execution_callback(self, payload: dict) -> None:
        for callback in list(self._execution_callbacks):
            try:
                callback(payload if callback in getattr(self, "_internal_execution_callbacks", set()) else sanitize(payload))
            except Exception as exc:
                state = getattr(self, "_p02_local_ingress", None)
                if state is not None:
                    for ticket in getattr(state["thread"], "intake", ()):
                        self._local_intake_failed(ticket)
                print(f"[IBKR][CALLBACK_ERROR] reason={exc}")

    # --- Connection management ---
    def connect(self) -> None:  # type: ignore[override]
        if not self.host or self.port is None or int(self.port) <= 0:
            raise RuntimeError(
                "INVALID_RETRY_CONFIGURATION: host/port must be configured before IBKR connect"
            )

        print(
            "[IBKR][CLIENT] connect "
            f"host={self.host} port={self.port} client_id={self.client_id} "
            f"timeout={self.snapshot_timeout_seconds} market_data_type={self.market_data_type} "
            f"readonly={self.readonly_enabled}"
        )
        self._connection_event.clear()
        self._position_upstream_lost = False
        with self._lock:
            if getattr(self, "_volume_calibration_binding", None) is not None:
                self._volume_calibration_invalidated = True
            self._volume_unit_witness = None
            self._last_native_volume_sample = None
            self._native_volume_evidence = {}
            self._calibrated_history_requests = {}
            attempts = getattr(self, "_commission_connection_attempts", None)
            if type(attempts) is not int or not hasattr(self, "_commission_constructor_queue"):
                self._commission_zero_disabled = True
            else:
                self._commission_connection_attempts = attempts + 1
            if getattr(self, "_commission_connection_attempts", None) != 1:
                self._commission_zero_disabled = True
        try:
            super().connect(self.host, self.port, int(self.client_id))
        except BaseException:
            self._commission_zero_disabled = True
            raise
        self._install_commission_decoder_witness()

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        if not wait_event(self._connection_event, self.snapshot_timeout_seconds):
            self.disconnect()
            raise RuntimeError("IBKR connection timeout waiting for handshake")

        data_type_code = _market_data_type_code(self.market_data_type)
        print(f"[IBKR] Setting market data type={self.market_data_type} code={data_type_code}")
        self.reqMarketDataType(data_type_code)
        print(f"[IBKR] connection_status={self.isConnected()}")
        print(f"[IBKR][CONNECTED] Connected client_id={self.client_id}")

    def _install_commission_decoder_witness(self):
        # Called only after the FIRST actual SDK connect installed its objects,
        # before this native owner starts the decoder loop. No reconnect rearm.
        from ibapi import decoder as sdk_decoder
        with self._lock:
            message_id = getattr(_SDK_IN, "COMMISSION_AND_FEES_REPORT" if _SDK_COMMISSION_MODERN else "COMMISSION_REPORT", None)
            if _SDK_COMMISSION_MODERN and isinstance(message_id, _SDK_IN):
                message_id = message_id.value
            handle_type = getattr(sdk_decoder, "HandleInfo", None)
            # Optional private SDK capability: unsupported installations retain
            # the preexisting connection/callback APIs with ZERO unavailable.
            if (not _commission_sdk_schema_supported() or type(message_id) is not int
                    or not callable(handle_type)):
                self._commission_zero_disabled = True
                return
            decoder = getattr(self, "decoder", None)
            handle = getattr(decoder, "msgId2handleInfo", {}).get(message_id)
            proto_handle = getattr(decoder, "msgId2handleInfoProtoBuf", {}).get(message_id)
            process = _SDK_FEES_PROCESS if _SDK_COMMISSION_MODERN else _SDK_COMMISSION_PROCESS
            eligible = (not self._commission_zero_disabled and self._commission_connection_attempts == 1
                and self._thread is None and self.msg_queue is self._commission_constructor_queue
                and decoder is not None and decoder.wrapper is self
                and handle is not None and handle.processMeth is process
                and (not _SDK_COMMISSION_MODERN or (proto_handle is not None
                    and proto_handle.processMeth is _SDK_FEES_PROTO_PROCESS))
                and self.reader is not None and self.reader.msg_queue is self.msg_queue
                and self.reader.conn is self.conn and self.is_connected()
                and type(self.client_id) is int and type(self.clientId) is int
                and self.client_id == self.clientId and type(self._position_connection_epoch) is int
                and type(decoder.serverVersion) is int and decoder.serverVersion == self.serverVersion()
                and _commission_sdk_schema_supported())
            if not eligible:
                self._commission_zero_disabled = True
                return
            proxy_type = _OfficialCommissionDecoderProxy if _SDK_COMMISSION_MODERN else _CommissionDecoderProxy
            proxy = proxy_type(self, decoder)
            decoder.msgId2handleInfo = dict(decoder.msgId2handleInfo)
            decoder.msgId2handleInfo[message_id] = handle_type(proc=proxy.process)
            if _SDK_COMMISSION_MODERN:
                decoder.msgId2handleInfoProtoBuf = dict(decoder.msgId2handleInfoProtoBuf)
                decoder.msgId2handleInfoProtoBuf[message_id] = handle_type(proc=proxy.process_proto)
            decoder.wrapper = proxy
            self._commission_decoder_proxy = proxy

    def _commission_decoder_current(self, proxy, *, require_thread=False):
        with self._lock:
            if self._commission_zero_disabled:
                return False
            handle = getattr(self.decoder, "msgId2handleInfo", {}).get(
                getattr(_SDK_IN, "COMMISSION_AND_FEES_REPORT" if _SDK_COMMISSION_MODERN else "COMMISSION_REPORT", None))
            proto_handle = getattr(self.decoder, "msgId2handleInfoProtoBuf", {}).get(
                getattr(_SDK_IN, "COMMISSION_AND_FEES_REPORT", None))
            valid = (self._commission_decoder_proxy is proxy and self.decoder is proxy.decoder
                and self.decoder.wrapper is proxy and self.msg_queue is proxy.queue
                and self.msg_queue is self._commission_constructor_queue and self.reader is proxy.reader
                and self.conn is proxy.connection and self.reader.msg_queue is proxy.queue
                and self.reader.conn is proxy.connection and self._thread is not None
                and self._thread.is_alive() and (not require_thread or self._thread is threading.current_thread())
                and (proxy.thread is None or proxy.thread is self._thread)
                and type(self.client_id) is int and self.client_id == proxy.client_id
                and type(self.clientId) is int and self.clientId == proxy.client_id
                and type(self._position_connection_epoch) is int and self._position_connection_epoch == proxy.epoch
                and self.decoder.serverVersion == proxy.server_version == self.serverVersion()
                and handle is not None and handle.processMeth is proxy.process
                and (not _SDK_COMMISSION_MODERN or (proto_handle is not None
                    and proto_handle.processMeth is proxy.process_proto))
                and _commission_sdk_runtime_valid()
                and self.is_connected() and not self._stop_event.is_set()
                and self._position_transport_available)
            if not valid:
                self._commission_zero_disabled = True
                return False
            accounts = tuple(self._managed_accounts)
            if len(accounts) != 1:
                if len(accounts) > 1:
                    self._commission_zero_disabled = True
                return False
            if proxy.account_scope is None:
                proxy.account_scope = accounts
            elif accounts != proxy.account_scope:
                self._commission_zero_disabled = True
                return False
            proxy.thread = self._thread
            return True

    def _consume_commission_witness(self, report):
        proxy = getattr(self, "_commission_decoder_proxy", None)
        witness = proxy.consume(report) if proxy is not None else None
        return witness or {key: "UNAVAILABLE" if key == "commission_presence_source" else None
                           for key in _COMMISSION_PRESENCE_FIELDS}

    def _commission_zero_report_current(self, report):
        proxy = getattr(self, "_commission_decoder_proxy", None)
        return (proxy is not None and self._commission_decoder_current(proxy)
            and report.get("commission_field_present") is True
            and report.get("commission_presence_source") == SDK_COMMISSION_PRESENCE_SOURCE
            and report.get("commission_decoder_schema") == SDK_COMMISSION_SCHEMA
            and report.get("commission_client_object_id") == id(self)
            and report.get("commission_decoder_object_id") == id(self.decoder)
            and report.get("commission_decoder_epoch") == self._position_connection_epoch
            and report.get("commission_decoder_generation") == 1
            and report.get("commission_decoder_thread_id") == getattr(self._thread, "ident", None))

    def disconnect(self, *, final_authorization=None) -> None:  # type: ignore[override]
        if final_authorization is not None:
            with self._lock:
                lifetime = self._p02_source_lifetime
                # Existing intake registration precedes status/execution/order
                # cache publication. Refuse even a callback paused in between.
                # The supplied closure uses only local observations/accounting.
                with lifetime["lock"]:
                    if any(operation[3] in {"orderStatus", "execDetails", "openOrder", "managedAccounts",
                                             "connectionClosed", "error", "position"}
                           for operation in lifetime["operations"].values()):
                        raise RuntimeError("PAPER_RELEASE_SHUTDOWN_CALLBACK_IN_FLIGHT")
                    final_authorization()
                    self._stop_event.set()
                self._invalidate_position_queries()
        print(f"[IBKR] Disconnecting client_id={self.client_id}")
        self._stop_event.set()
        self._invalidate_historical_requests()
        if final_authorization is None:
            self._invalidate_position_queries()
        try:
            try:
                with self._lock:
                    for context in getattr(self, "_request_context_by_req_id", {}).values():
                        context.pop("reference_response", None)
                        context.pop("reference_deadline", None)
            finally:
                # Metadata cleanup must never prevent socket disconnection.
                super().disconnect()
        finally:
            thread = self._thread
            if thread and thread.is_alive():
                if thread is threading.current_thread():
                    print("[IBKR] Disconnect called from network thread; skipping self-join.")
                else:
                    thread.join(timeout=2)
                    if thread.is_alive():  # pragma: no cover - defensive
                        print("[IBKR] Warning: network thread still alive after disconnect.")
            print("[IBKR][DISCONNECTED] client disconnected")

    def ensure_connection(self) -> None:
        if not self.is_connected():
            print("[IBKR] Connection lost. Reconnecting.")
            self.connect()

    def is_connected(self) -> bool:
        return self.isConnected()

    def health(self) -> dict:
        last_error = None
        if self._errors:
            _, last_error = sorted(self._errors.items())[-1]
        return {
            "connected": self.is_connected(),
            "last_error": last_error,
            "last_disconnect_reason": self._last_disconnect_reason,
            "market_data_type": self.market_data_type,
            "connection_event_set": self._connection_event.is_set(),
        }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                super().run()
            except Exception as exc:  # pragma: no cover - defensive
                if self._stop_event.is_set() and "cannot join current thread" in str(exc):
                    break
                print(f"[IBKR] Network loop error: {exc}")
                time.sleep(0.1)
            else:
                break

    # --- Request/response helpers ---
    def _next_req_id(self) -> int:
        with self._lock:
            # IBKR errors carry one numeric ID for both requests and orders.
            # Allocate both through the existing authorities under this lock,
            # always above IDs already reserved by either side. Positive gaps in
            # order IDs are legal; no guessed error-code ownership is needed.
            self._req_id = max(self._req_id, self._last_reserved_order_id or 0,
                               self._next_valid_order_id or 0,
                               max(self._order_status_events, default=0),
                               max(self._order_state_registry, default=0)) + 1
            self._pending_request_allocations.add(self._req_id)
            if len(self._pending_request_allocations) > 1024:
                self._pending_request_allocations.remove(min(self._pending_request_allocations))
            return self._req_id

    def _register_request(self, req_id: int, request_type: str, contract=None) -> None:
        if not hasattr(self, "_request_type_by_req_id"):
            self._request_type_by_req_id = {}
        with self._lock:
            if (req_id in self._order_status_events or req_id in self._order_state_registry
                    or req_id == self._last_reserved_order_id):
                raise RuntimeError("Request ID is already reserved for an order.")
            # Raw compatibility calls may supply their own positive request ID.
            # Registration must reserve that ID before a concurrent order can.
            self._pending_request_allocations.discard(req_id)
            self._req_id = max(self._req_id, req_id)
            if request_type == "CONTRACT_DETAILS" and self._stop_event.is_set():
                raise RuntimeError("Contract resolution stopped during disconnect.")
            self._request_type_by_req_id[req_id] = request_type
            if not hasattr(self, "_request_context_by_req_id"):
                self._request_context_by_req_id = {}
            self._request_context_by_req_id[req_id] = {
                "request_type": request_type,
                "symbol": getattr(contract, "symbol", None),
                "con_id": getattr(contract, "conId", None),
            }
            if request_type == "CONTRACT_DETAILS":
                self._request_context_by_req_id[req_id]["reference_epoch"] = self._position_connection_epoch
                # Register eligibility atomically with the context that disconnect
                # invalidates under this same lock. Never re-arm it after cleanup.
                self._request_context_by_req_id[req_id]["reference_deadline"] = (
                    time.monotonic() + self.snapshot_timeout_seconds
                )
            # Retain bounded context for broker errors arriving after cleanup.
            if len(self._request_context_by_req_id) > 1024:
                self._request_context_by_req_id.pop(next(iter(self._request_context_by_req_id)))

    def _cleanup_market_request(self, req_id: int) -> None:
        if not hasattr(self, "_active_market_req_ids"):
            self._active_market_req_ids = set()
        if not hasattr(self, "_request_type_by_req_id"):
            self._request_type_by_req_id = {}
        with self._lock:
            self._active_market_req_ids.discard(req_id)
            self._request_type_by_req_id.pop(req_id, None)
            self._market_events.pop(req_id, None)
            self._market_data.pop(req_id, None)
            self._ticker_by_req_id.pop(req_id, None)
            stale_keys = [key for key, value in self._req_id_by_contract_key.items() if value == req_id]
            for key in stale_keys:
                self._req_id_by_contract_key.pop(key, None)

    @staticmethod
    def _contract_key(contract) -> tuple:
        return (
            getattr(contract, "conId", None),
            getattr(contract, "symbol", None),
            getattr(contract, "secType", None),
            getattr(contract, "exchange", None),
            getattr(contract, "currency", None),
        )

    def _build_ticker(self, contract) -> object:
        return SimpleNamespace(
            contract=contract,
            volumeTickType=None,
            volumeRawValue=None,
            mixedVolumeTickTypes=False,
            volumeConnectionEpoch=self._position_connection_epoch,
            volumeClientId=self.client_id,
            volumeServerVersion=self.serverVersion(),
            bid=None,
            ask=None,
            last=None,
            close=None,
            volume=None,
            bidSize=None,
            askSize=None,
            lastSize=None,
            open=None,
            high=None,
            low=None,
            requestedMarketDataType=getattr(self, "_requested_market_data_type_code", _market_data_type_code(self.market_data_type)),
            marketDataType=None,
            marketDataTypeConfirmed=False,
            marketDataTypeReceivedAt=None,
            reqId=None,
            snapshotEnd=False,
            receivedAt=None,
            lastTime=None,
            requestStartedAt=datetime.now(timezone.utc),
            snapshotEndedAt=None,
            fieldReceivedAt={},
            brokerErrors=[],
        )

    def _request_id_conflicted(self, req_id: int) -> bool:
        return bool(getattr(self, "_order_state_registry", {}).get(req_id, {}).get("request_id_conflict"))

    def _raise_if_request_id_conflicted(self, req_id: int) -> None:
        if self._request_id_conflicted(req_id):
            raise RuntimeError("Request/order ID ownership is ambiguous.")

    def _observe_order_id(self, order_id: int) -> None:
        """Reserve observed IDs; quarantine collisions without inventing error ownership."""
        self._ensure_order_state_registry()
        with self._lock:
            known_order = order_id in self._order_status_events
            self._order_status_events.setdefault(order_id, threading.Event())
            request_type = getattr(self, "_request_type_by_req_id", {}).pop(order_id, None)
            position_query = self._position_queries.get(order_id)
            context = getattr(self, "_request_context_by_req_id", {}).get(order_id, {})
            # Completed request metadata and still-held request maps also expose
            # ambiguity. An unseen lower ID may be a retired request whose bounded
            # context has already been evicted; keep that case conservative.
            possible_request = (request_type is not None or position_query is not None
                                or bool(context.get("request_type"))
                                or (not known_order and order_id <= self._req_id))
            if not possible_request:
                return
            # Generic IBKR errors have no request-vs-order discriminator. Retain
            # this ambiguity in the existing order-ID registry even after request
            # metadata is evicted; never attribute a late shared-ID error to either.
            self._order_state_registry.setdefault(order_id, {})["request_id_conflict"] = True
            context = self._request_context_by_req_id.get(order_id, {})
            context["reference_error"] = (-1, "Request/order ID ownership is ambiguous.")
            context.pop("reference_response", None)
            context.pop("reference_deadline", None)
            execution_query = context.get("execution_query")
            if execution_query is not None:
                execution_query["status"] = "IDENTITY_CONFLICT"
                execution_query["event"].set()
            currency_query = context.get("account_currency_query")
            if currency_query is not None:
                currency_query["status"] = "IDENTITY_CONFLICT"
                currency_query["event"].set()
            if position_query is not None:
                position_query["status"] = "FAILED"
                position_query["event"].set()
            for events in (self._market_events, self._historical_events, self._contract_events,
                           self._scanner_events, self._account_summary_events):
                event = events.pop(order_id, None)
                if event is not None:
                    event.set()  # Release waiters to raise unavailable, not complete.
            for rows in (self._market_data, self._historical_data, self._contract_details,
                         self._scanner_rows, self._account_summary_rows):
                rows.pop(order_id, None)
            self._active_market_req_ids.discard(order_id)
            ticker = self._ticker_by_req_id.get(order_id)
            if ticker is not None:
                ticker.snapshotEnd = False
                for field in ("bid", "ask", "last", "close", "open", "high", "low", "volume"):
                    setattr(ticker, field, None)
                ticker.brokerErrors.append({"code": -1, "message": "REQUEST_ORDER_ID_CONFLICT"})
            if request_type == "EXECUTIONS":
                self._executions_snapshot = []
                self._executions_event.set()

    def reserve_order_id(self) -> int:
        with self._lock:
            if self._next_valid_order_id is None:
                print("[CRITICAL] IBKR_NEXT_VALID_ID_NOT_READY")
                raise RuntimeError("IBKR order id not yet initialized.")
            order_id = max(int(self._next_valid_order_id), self._req_id + 1,
                           (self._last_reserved_order_id or 0) + 1,
                           max(self._order_status_events, default=0) + 1)
            self._next_valid_order_id = int(order_id) + 1
            self._next_order_id = self._next_valid_order_id
            self._last_reserved_order_id = int(order_id)
            self._order_status_events.setdefault(order_id, threading.Event())
            self._persist_last_reserved_order_id(int(order_id))
            print(f"[IBKR][ORDER_ID_SOURCE] source=IBKR_NEXT_VALID_ID order_id={order_id}")
            print(f"[IBKR][ORDER_ID_SEQUENCE] reserved={order_id} next={self._next_valid_order_id}")
            return order_id

    def submit_order(self, contract: Contract, order, *, before_submit=None, final_entry_admission=None) -> int:
        if not self.is_connected():
            raise RuntimeError("IBKR client is not connected.")
        assert_read_only_allows("PLACE_ORDER")
        try:
            order.eTradeOnly = False
        except Exception:
            pass
        try:
            order.firmQuoteOnly = False
        except Exception:
            pass
        order_id = self.reserve_order_id()
        if getattr(self, "_p02_local_ingress", None) is not None:
            with self._lock:
                if (order_id in self._order_status or order_id in self._exec_details_by_order
                        or order_id in self._open_orders_snapshot or order_id in self._order_errors
                        or order_id in self._order_warnings or order_id in self._order_state_registry
                        or order_id in self._request_context_by_req_id
                        or self._order_status_events[order_id].is_set()):
                    raise RuntimeError("P02_LOCAL_NATIVE_PREPARATION_CACHE_OCCUPIED")
                # reserve_order_id already installed our empty event. Preserve
                # any later callback publication; never overwrite its slot.
                self._exec_details_by_order.setdefault(order_id, [])
        else:
            self._order_status_events[order_id] = threading.Event()
            self._exec_details_by_order[order_id] = []
        print(
            "[ORDER][SUBMIT] "
            f"symbol={getattr(contract, 'symbol', None)} order_id={order_id} "
            f"qty={getattr(order, 'totalQuantity', None)} side={getattr(order, 'action', None)} "
            f"order_type={getattr(order, 'orderType', None)}"
        )
        print("[EXECUTION][ORDER_OBJECT]")
        print(f"type={type(order)}")
        print(f"action={getattr(order, 'action', None)}")
        print(f"qty={getattr(order, 'totalQuantity', None)}")
        print(f"orderType={getattr(order, 'orderType', None)}")
        print(f"outsideRth={getattr(order, 'outsideRth', None)}")
        if not isinstance(order, Order):
            raise RuntimeError(f"INVALID_ORDER_OBJECT_TYPE: {type(order)}")
        if getattr(order, "action", None) not in ("BUY", "SELL"):
            raise RuntimeError("ORDER_OBJECT_CONTAMINATION_DETECTED")
        assert order.action in ("BUY", "SELL")
        assert int(order.totalQuantity) > 0
        assert order.orderType in ("MKT", "LMT", "STP")
        state = getattr(self, "_p02_local_ingress", None)
        context = {"order_id": order_id, "lease": None} if state is not None else None
        if context is not None:
            if getattr(state["thread"], "submit", None) is not None:
                raise RuntimeError("P02_LOCAL_REENTRANT_SUBMISSION")
            state["thread"].submit = context
        try:
            if before_submit is not None:
                lease = before_submit(order_id, contract, order)
                if context is not None and lease is not None:
                    from src.execution.execution_engine import _P02LocalEntryLease
                    if type(lease) is not _P02LocalEntryLease or lease.owner is not state["owner"]:
                        raise RuntimeError("P02_LOCAL_ENTRY_ISSUER_INVALID")
                    context["lease"] = lease
            if final_entry_admission is None:
                self.placeOrder(order_id, contract, order)
            else:
                # Serialize the local admission recheck and send against native
                # callback scope changes. The preparatory hook may await reads.
                with self._lock:
                    final_entry_admission(self, order_id, contract, order)
                    self.placeOrder(order_id, contract, order)
        except Exception as exc:
            print(f"[IBKR][PLACE_ORDER][ERROR] symbol={getattr(contract, 'symbol', None)} order_id={order_id} error={exc}")
            raise
        finally:
            if context is not None:
                try:
                    if context["lease"] is not None:
                        context["lease"].abort()
                finally:
                    state["thread"].submit = None
        return order_id

    def wait_for_order_status(
        self, order_id: int, timeout_seconds: int
    ) -> Optional[Dict[str, Optional[float | int | str]]]:
        event = self._order_status_events.setdefault(order_id, threading.Event())
        event.wait(timeout=timeout_seconds)
        return self._order_status.get(order_id)

    def commission_for_order(self, order_id: int) -> Optional[float]:
        exec_details = self._exec_details_by_order.get(order_id, [])
        if not exec_details:
            return None
        total_commission = 0.0
        found = False
        for detail in exec_details:
            exec_id = detail.get("execId")
            if exec_id is None:
                continue
            commission = self._commission_by_exec_id.get(exec_id)
            if isinstance(commission, dict):
                commission = commission["legacy_amount"]
            if commission is None:
                continue
            found = True
            total_commission += commission
        return round(total_commission, 2) if found else None

    def get_order_error(self, order_id: int) -> Optional[Tuple[int, str]]:
        return self._order_errors.get(order_id)

    def get_order_warning(self, order_id: int) -> Optional[Tuple[int, str]]:
        return self._order_warnings.get(order_id)

    def openOrders(self, timeout_seconds: Optional[int] = None, *, require_complete: bool = False) -> list[object]:
        # This legacy stream has no request token. Serialize acquisition and
        # never let a late end marker after a timeout certify a new strict read.
        timeout = timeout_seconds or self.snapshot_timeout_seconds
        if not self._open_orders_query_lock.acquire(timeout=timeout):
            raise RuntimeError("OPEN_ORDERS_QUERY_BUSY")
        try:
            if require_complete and self._open_orders_unresolved:
                raise RuntimeError("OPEN_ORDERS_COMPLETION_UNRESOLVED")
            if not self.is_connected():
                if require_complete:
                    raise RuntimeError("OPEN_ORDERS_DISCONNECTED")
                return list(self._open_orders_snapshot.values())
            self._open_orders_event.clear()
            with self._lock:
                self._open_orders_snapshot = {}
            self.reqOpenOrders()
            complete = self._open_orders_event.wait(timeout=timeout)
            if not complete or not self.is_connected():
                self._open_orders_unresolved = True
                if require_complete:
                    raise RuntimeError("OPEN_ORDERS_INCOMPLETE")
            return list(self._open_orders_snapshot.values())
        except BaseException:
            self._open_orders_unresolved = True
            raise
        finally:
            self._open_orders_query_lock.release()

    def cached_open_order_rows(self) -> tuple:
        with self._lock:
            return tuple(self._open_orders_snapshot.values())

    def executions(self, timeout_seconds: Optional[int] = None) -> list[object]:
        if not self.is_connected():
            return list(self._executions_snapshot)
        from ibapi.execution import ExecutionFilter

        req_id = self._next_req_id()
        self._executions_event.clear()
        self._executions_snapshot = []
        self._register_request(req_id, "EXECUTIONS")
        self.reqExecutions(req_id, ExecutionFilter())
        self._executions_event.wait(timeout=timeout_seconds or self.snapshot_timeout_seconds)
        with self._lock:
            self._raise_if_request_id_conflicted(req_id)
            return list(self._executions_snapshot)

    def execution_snapshot(self, *, account: str, order_id: int, con_id: int,
                           symbol: str, side: str,
                           timeout_seconds: Optional[float] = None) -> ExecutionQueryResult:
        """Scoped immutable history query, isolated from unsolicited live fills.

        Empty COMPLETE means this request ended, not that no late execution can
        exist. IBKR's empty time filter/history retention is NOT lifetime coverage.
        clientId=0 is a server wildcard; exact client/order/conId are also checked
        locally. No cancellation API exists for reqExecutions: retire ownership.
        """
        from ibapi.execution import ExecutionFilter
        from ibapi.server_versions import MIN_SERVER_VER_EXECUTION_DATA_CHAIN

        checkpoint()
        if (type(order_id) is not int or order_id < 0 or type(con_id) is not int or con_id <= 0
                or not isinstance(account, str) or not account.strip()
                or not isinstance(symbol, str) or not symbol.strip()
                or side not in ("BUY", "SELL")):
            raise ValueError("Explicit native execution scope required")
        symbol = symbol.strip().upper()
        timeout = self.snapshot_timeout_seconds if timeout_seconds is None else timeout_seconds
        if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError("Bounded execution query timeout required")
        with self._lock:
            epoch = self._position_connection_epoch
            client_id = self.client_id
            if type(client_id) is not int or client_id < 0:
                raise ValueError("Explicit native client identity required")
            def result(status, req_id=None, rows=(), completed_at=None):
                return ExecutionQueryResult(status, req_id, epoch, account, client_id,
                                            order_id, con_id, symbol, side, rows, completed_at)
            if (not self.is_connected() or self._stop_event.is_set()
                    or not self._position_transport_available):
                return result("DISCONNECTED")
            server_version = self.serverVersion()
            if type(server_version) is not int or server_version < MIN_SERVER_VER_EXECUTION_DATA_CHAIN:
                return result("REQUEST_CORRELATION_UNAVAILABLE")
            if tuple(self._managed_accounts) != (account,):
                return result("ACCOUNT_SCOPE_UNAVAILABLE")
            self._observe_order_id(order_id)
            if self._request_id_conflicted(order_id):
                return result("IDENTITY_CONFLICT")
            req_id = self._next_req_id()
            self._register_request(req_id, "EXECUTIONS_STRICT")
            context = self._request_context_by_req_id[req_id]
            query = {"status": "PARTIAL", "event": threading.Event(), "rows": {},
                     "epoch": epoch, "account": account, "client_id": client_id,
                     "order_id": order_id, "con_id": con_id, "symbol": symbol, "side": side,
                     "deadline": time.monotonic() + timeout, "completed_at": None}
            context["execution_query"] = query
        try:
            native_filter = ExecutionFilter()
            native_filter.clientId = client_id
            native_filter.acctCode = account
            native_filter.symbol = symbol
            native_filter.secType = "STK"
            native_filter.time = ""
            with self._lock:
                if self._execution_query_current(req_id, query):
                    self.reqExecutions(req_id, native_filter)
            wait_event(query["event"], timeout=max(0, query["deadline"] - time.monotonic()))
            with self._lock:
                self._execution_query_current(req_id, query, allow_complete=True)
                if query["status"] == "PARTIAL":
                    query["status"] = "TIMEOUT"
                return result(query["status"], req_id, tuple(query["rows"].values()),
                              query["completed_at"] if query["status"] == "COMPLETE" else None)
        except (AcquisitionCancelled, AcquisitionDeadlineExceeded):
            raise
        except Exception:
            with self._lock:
                query["status"] = "ERROR"
                return result("ERROR", req_id, tuple(query["rows"].values()))
        finally:
            with self._lock:
                # Keep bounded tombstone metadata; never reuse an allocated ID.
                context.pop("execution_query", None)
                self._request_type_by_req_id.pop(req_id, None)
                query["event"].set()

    def _execution_query_current(self, req_id, query, *, allow_complete=False):
        """Called under the existing callback lock. Any lost ownership fails closed."""
        status = query["status"]
        if status != "PARTIAL" and not (allow_complete and status == "COMPLETE"):
            return False
        if self._request_context_by_req_id.get(req_id, {}).get("execution_query") is not query:
            status = "OWNERSHIP_LOST"
        elif self._request_id_conflicted(req_id) or self._request_id_conflicted(query["order_id"]):
            status = "IDENTITY_CONFLICT"
        elif (query["epoch"] != self._position_connection_epoch or not self.is_connected()
              or self._stop_event.is_set() or not self._position_transport_available):
            status = "DISCONNECTED"
        elif tuple(self._managed_accounts) != (query["account"],) or self.client_id != query["client_id"]:
            status = "SCOPE_CHANGED"
        elif status == "PARTIAL" and time.monotonic() >= query["deadline"]:
            status = "TIMEOUT"
        else:
            return status == "PARTIAL"
        query["status"] = status
        query["event"].set()
        return False

    def _scoped_execution_callback(self, req_id, contract, execution):
        # True means this ID belongs to strict history, including retired queries.
        context = getattr(self, "_request_context_by_req_id", {}).get(req_id, {})
        if (context.get("request_type") or getattr(self, "_request_type_by_req_id", {}).get(req_id)) != "EXECUTIONS_STRICT":
            return False
        query = context.get("execution_query")
        if query is None or not self._execution_query_current(req_id, query):
            return True
        try:
            def integer(value, minimum=0):
                if isinstance(value, bool) or type(value) is not int or value < minimum:
                    raise ValueError("Invalid native identity")
                return value
            def positive(value):
                if isinstance(value, bool):
                    raise ValueError("Invalid execution quantity")
                value = Decimal(str(value))
                if not value.is_finite() or value <= 0:
                    raise ValueError("Invalid execution quantity/price")
                return value
            oid = integer(execution.orderId)
            cid = integer(execution.clientId)
            if execution.acctNumber != query["account"]:
                raise ValueError("Account filter violation")
            if cid != query["client_id"]:
                if query["client_id"] == 0:  # API zero means all clients.
                    return True
                raise ValueError("Client filter violation")
            if str(contract.symbol).upper() != query["symbol"] or contract.secType != "STK":
                raise ValueError("Security filter violation")
            if oid != query["order_id"]:
                return True  # Native filter has no orderId selector.
            native_side = {"BOT": "BUY", "SLD": "SELL"}.get(execution.side)
            if integer(contract.conId, 1) != query["con_id"] or native_side != query["side"]:
                raise ValueError("Retained order identity disagreement")
            if not isinstance(execution.execId, str) or not execution.execId.strip():
                raise ValueError("Missing execution identity")
            if not isinstance(execution.time, str) or not execution.time.strip():
                raise ValueError("Missing broker execution time")
            row = ScopedExecution(execution.execId, oid, contract.conId, query["symbol"],
                                  execution.acctNumber, cid, native_side,
                                  positive(execution.shares), positive(execution.price),
                                  positive(execution.cumQty), positive(execution.avgPrice), execution.time)
            if row.cumulative_quantity < row.quantity:
                raise ValueError("Cumulative execution disagreement")
            previous = query["rows"].get(row.exec_id)
            if previous is not None and previous != row:
                raise ValueError("Conflicting execution duplicate")
            query["rows"][row.exec_id] = row
        except (AttributeError, TypeError, ValueError, InvalidOperation):
            query["status"] = "INVALID"
            query["event"].set()
        return True

    def position_snapshot(self, timeout_seconds: Optional[float] = None) -> BrokerPositionResult:
        # The legacy reqPositions stream has no correlation token. Never cancel or
        # reassign its subscription here. reqPositionsMulti has request-scoped end
        # markers and cancellation, on the SAME canonical socket/account authority.
        checkpoint()
        with self._lock:
            accounts = tuple(self._managed_accounts)
            if not self.is_connected() or self._stop_event.is_set() or not self._position_transport_available:
                return BrokerPositionResult(status="DISCONNECTED")
            if len(accounts) != 1 or not accounts[0]:
                return BrokerPositionResult(status="ACCOUNT_SCOPE_UNAVAILABLE")
            epoch = self._position_connection_epoch
            client_id = self.client_id
            generation = getattr(self, "_managed_accounts_generation", 0)
        req_id = self._next_req_id()
        timeout = self.snapshot_timeout_seconds if timeout_seconds is None else timeout_seconds
        context = {"account": accounts[0], "client_id": client_id, "rows": {}, "event": threading.Event(),
                   "status": "PARTIAL", "completed_at": None, "epoch": epoch,
                   "deadline": time.monotonic() + max(0, timeout)}
        with self._lock:
            if (epoch != self._position_connection_epoch or not self.is_connected()
                    or self._stop_event.is_set() or not self._position_transport_available):
                return BrokerPositionResult(status="DISCONNECTED")
            self._position_queries[req_id] = context
        sent = False
        try:
            self._register_request(req_id, "POSITIONS_MULTI")
            checkpoint()
            with self._lock:
                if (epoch != self._position_connection_epoch or not self.is_connected()
                        or self._stop_event.is_set() or not self._position_transport_available):
                    return BrokerPositionResult(status="DISCONNECTED", account=accounts[0])
                self._raise_if_request_id_conflicted(req_id)
                sent = True
            self.reqPositionsMulti(req_id, accounts[0], "")
            wait_event(context["event"], max(0, context["deadline"] - time.monotonic()))
            with self._lock:
                if epoch != self._position_connection_epoch or not self.is_connected():
                    context["status"] = "DISCONNECTED"
                elif (tuple(self._managed_accounts) != accounts or client_id != self.client_id
                      or generation != getattr(self, "_managed_accounts_generation", 0)):
                    context["status"] = "WRONG_ACCOUNT"
                elif context["status"] == "PARTIAL":
                    context["status"] = "TIMEOUT"
                elif context["status"] == "COMPLETE":
                    from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
                    age = (datetime.now(timezone.utc) - context["completed_at"]).total_seconds()
                    if not 0 <= age <= get_ibkr_snapshot_max_age_seconds():
                        context["status"] = "STALE"
                scope = (client_id, epoch, generation) if context["status"] == "COMPLETE" else None
                return BrokerPositionResult(tuple(context["rows"].values()), context["status"],
                                            context["account"], context["completed_at"], scope)
        except (AcquisitionCancelled, AcquisitionDeadlineExceeded):
            raise
        except Exception:
            return BrokerPositionResult(status="FAILED", account=accounts[0])
        finally:
            # Retire before cancellation: even synchronous/late callbacks cannot
            # mutate returned evidence or complete another query.
            with self._lock:
                owned = self._position_queries.get(req_id) is context
                if owned:
                    self._position_queries.pop(req_id, None)
                    self._request_type_by_req_id.pop(req_id, None)
                can_cancel = (owned and sent and epoch == self._position_connection_epoch
                              and self.is_connected() and not self._request_id_conflicted(req_id))
            cancellation_returned = False
            context["_local_cleanup_revision"] = self._local_request_cleanup_revision()
            if can_cancel:
                try:
                    self.cancelPositionsMulti(req_id)
                    cancellation_returned = True
                except Exception:
                    pass
            if getattr(self,"_p02_local_ingress",None) is not None:
                with self._lock:
                    if (owned and sent and cancellation_returned and context["status"] == "COMPLETE"
                            and req_id not in self._position_queries and req_id not in self._request_type_by_req_id
                            and epoch == self._position_connection_epoch and self.client_id == context["client_id"]
                            and self.is_connected() and not self._stop_event.is_set() and self._position_transport_available
                            and tuple(self._managed_accounts) == accounts and not self._request_id_conflicted(req_id)):
                        try:
                            rows = self._local_position_completion_rows(context)
                            frozen = tuple(sorted(context.get("_local_position_rows",{}).values(),
                                key=lambda row:(row["account"],row["con_id"],row["symbol"])))
                            if rows == frozen and not context.get("_local_position_invalid"):
                                self._issue_local_request_completion("POSITIONS_MULTI",req_id,context,rows=frozen)
                        except (ValueError,TypeError,AttributeError,OverflowError):
                            pass  # Legacy COMPLETE alone grants no opted-in cleanup authority.

    def positions(self, timeout_seconds: Optional[int] = None) -> list[object]:
        result = self.position_snapshot(timeout_seconds)
        if result.status != "COMPLETE":
            raise RuntimeError(f"Broker position truth unavailable: {result.status}")
        return list(result.rows)

    def _invalidate_position_queries(self, *, clear_account_scope: bool = True) -> None:
        with self._lock:
            self._commission_zero_disabled = True
            for query in getattr(self, "_price_rule_requests", {}).values():
                self._finish_price_rule(query, "DISCONNECTED")
            self._position_connection_epoch += 1
            if getattr(self, "_volume_calibration_binding", None) is not None:
                self._volume_calibration_invalidated = True
            self._volume_unit_witness = None
            self._last_native_volume_sample = None
            self._native_volume_evidence = {}
            self._calibrated_history_requests = {}
            self._position_transport_available = False
            self._position_upstream_lost = True
            if clear_account_scope:
                self._managed_accounts = []
            for request in getattr(self, "_request_context_by_req_id", {}).values():
                query = request.get("execution_query")
                if query is not None:
                    query["status"] = "DISCONNECTED"
                    query["event"].set()
                currency_query = request.get("account_currency_query")
                if currency_query is not None:
                    currency_query["status"] = "DISCONNECTED"
                    currency_query["event"].set()
            for context in self._position_queries.values():
                context["status"] = "DISCONNECTED"
                context["event"].set()

    def positionMulti(self, reqId, account, modelCode, contract, pos, avgCost):
        with self._lock:
            context = self._position_queries.get(reqId)
            if context is None or context["status"] != "PARTIAL":
                return
            if account != context["account"] or modelCode:
                context["status"] = "WRONG_ACCOUNT"
                context["event"].set()
                return
            try:
                valid_quantity = math.isfinite(float(pos))
            except (TypeError, ValueError, OverflowError):
                valid_quantity = False
            if not valid_quantity:
                context["status"] = "FAILED"
                context["event"].set()
                return
            symbol = str(getattr(contract, "symbol", "") or "").strip().upper()
            if not symbol:
                context["status"] = "FAILED"
                context["event"].set()
                return
            key = (account,getattr(contract,"conId",0),symbol)
            previous = context["rows"].get(key)
            if previous is not None and (previous.position != pos or previous.avgCost != avgCost):
                # A later row can represent inventory changing during the read.
                # Neither value can certify one coherent initial snapshot.
                context["status"] = "FAILED"
                context["event"].set()
                return
            context["rows"][key] = SimpleNamespace(
                account=account, contract=contract, symbol=symbol, position=pos, avgCost=avgCost)
            if getattr(self,"_p02_local_ingress",None) is not None:
                try:
                    frozen = self._local_position_completion_rows(dict(account=context["account"],
                        rows={key:context["rows"][key]}))[0]
                    context.setdefault("_local_position_rows",{})[key] = frozen
                except (ValueError,TypeError,AttributeError,OverflowError):
                    context["_local_position_invalid"] = True
            ticket_id = self._publish_local_intake("positionMulti",cache="_position_queries",
                request_id=reqId,context_id=id(context))
            if ticket_id is not None:context.setdefault("_local_callback_ticket_ids",[]).append(ticket_id)

    def positionMultiEnd(self, reqId):
        with self._lock:
            context = self._position_queries.get(reqId)
            if context is None or context["status"] != "PARTIAL":
                return
            if (context["epoch"] != self._position_connection_epoch or not self.is_connected()
                    or self._stop_event.is_set()):
                context["status"] = "DISCONNECTED"
            elif time.monotonic() > context["deadline"]:
                context["status"] = "TIMEOUT"
            else:
                context["status"] = "COMPLETE"
                context["completed_at"] = datetime.now(timezone.utc)
                ticket_id = self._publish_local_intake("positionMultiEnd",cache="_position_queries",
                    request_id=reqId,context_id=id(context))
                if ticket_id is not None:context.setdefault("_local_callback_ticket_ids",[]).append(ticket_id)
            context["event"].set()


    def account_currency_snapshot(self, *, expected_account: str,
                                  timeout_seconds: Optional[float] = None, _deadline=None) -> AccountCurrencyResult:
        """Observe a concrete base currency through the existing summary owner.

        SDK reqAccountSummary documents $LEDGER as base-currency-only. The
        matching initial End freezes this point-in-time observation. Cancellation
        is an SDK call attempt, not a broker acknowledgement of stream termination.
        """
        return self._strict_account_summary(expected_account, timeout_seconds, deadline=_deadline)

    def account_capital_snapshot(self, *, expected_account: str,
                                 timeout_seconds: Optional[float] = None,
                                 require_settled_usd: bool = False) -> AccountCapitalResult:
        """Bind concrete account currency and capital to the same native scope."""
        timeout = self.snapshot_timeout_seconds if timeout_seconds is None else timeout_seconds
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError("Bounded account capital timeout required")
        deadline = time.monotonic() + bounded_timeout(timeout)
        if require_settled_usd:
            currency = self._strict_account_summary(
                expected_account, timeout, deadline=deadline, settled_usd=True)
        else:
            currency = self.account_currency_snapshot(
                expected_account=expected_account, timeout_seconds=timeout, _deadline=deadline)
        if currency.status != "COMPLETE":
            return AccountCapitalResult(currency.status, expected_account, currency)
        if not currency.cancellation_attempted or not currency.cleanup_complete:
            return AccountCapitalResult("CLEANUP_UNCONFIRMED", expected_account, currency)
        return self._strict_account_summary(
            expected_account, timeout, capital_currency=currency, deadline=deadline)

    def account_capital_scope(self, expected_account: str, *, request_ids=()) -> tuple[int, int, int] | None:
        """Return current local identity for a sole, connected account."""
        with self._lock:
            if (not self.is_connected() or self._stop_event.is_set()
                    or not self._position_transport_available
                    or tuple(self._managed_accounts) != (expected_account,)
                    or any(self._request_id_conflicted(req_id) for req_id in request_ids)):
                return None
            identity = (self.client_id, self._position_connection_epoch,
                        getattr(self, "_managed_accounts_generation", 0))
            return identity if all(type(value) is int and value >= 0 for value in identity) else None

    def _strict_account_summary(self, expected_account, timeout_seconds, *, capital_currency=None, deadline=None,
                                settled_usd=False):
        checkpoint()
        if (not isinstance(expected_account, str) or not expected_account
                or expected_account != expected_account.strip()):
            raise ValueError("Explicit account currency scope required")
        timeout = self.snapshot_timeout_seconds if timeout_seconds is None else timeout_seconds
        if (type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout < 0):
            raise ValueError("Bounded account currency timeout required")
        local_deadline = time.monotonic() + bounded_timeout(timeout)
        deadline = local_deadline if deadline is None else min(deadline, local_deadline)
        with self._lock:
            epoch, client_id = self._position_connection_epoch, self.client_id
            if (type(epoch) is not int or epoch < 0 or type(client_id) is not int or client_id < 0):
                raise ValueError("Explicit native account currency identity required")
            account_generation = getattr(self, "_managed_accounts_generation", 0)
            started_at = datetime.now(timezone.utc)

            def result(status, req_id=None, *, currency=None, completed_at=None, tags=(), cancelled=False):
                if capital_currency is not None:
                    return AccountCapitalResult(
                        status, expected_account, capital_currency, req_id, epoch, client_id,
                        started_at if req_id is not None else None, completed_at,
                        tuple(query["capital_facts"][tag] for tag in _CAPITAL_TAGS)
                        if status == "COMPLETE" else (), cancelled, account_generation,
                    )
                return AccountCurrencyResult(status, req_id, epoch, expected_account, client_id,
                    currency, completed_at, tags, cancelled,
                    source="IBKR_ACCOUNT_UPDATES_MULTI_USD_SECURITIES" if settled_usd else "IBKR_ACCOUNT_SUMMARY_LEDGER",
                    account_scope_generation=account_generation,
                    settled_cash=query.get("settled_cash") if settled_usd and status == "COMPLETE" else None)
            if (not self.is_connected() or self._stop_event.is_set()
                    or not self._position_transport_available):
                return result("DISCONNECTED")
            if tuple(self._managed_accounts) != (expected_account,):
                return result("ACCOUNT_SCOPE_UNAVAILABLE")
            if capital_currency is not None and (
                    capital_currency.connection_epoch != epoch or capital_currency.client_id != client_id
                    or capital_currency.account_scope_generation != account_generation):
                return result("SCOPE_CHANGED")
            if time.monotonic() >= deadline:
                return result("TIMEOUT")
            req_id = self._next_req_id()
            self._register_request(req_id, "ACCOUNT_CURRENCY_STRICT")
            context = self._request_context_by_req_id[req_id]
            query = {"status": "PARTIAL", "event": threading.Event(), "epoch": epoch,
                "account": expected_account, "client_id": client_id, "account_generation": account_generation,
                "deadline": deadline, "currency": None,
                "tags": set(), "completed_at": None}
            if settled_usd:
                query["settled_usd"] = True
                query["cash_as_of_date"] = started_at.astimezone(ZoneInfo("America/New_York")).date()
            if capital_currency is not None:
                query["capital_currency"] = capital_currency
                query["capital_facts"] = {}
            context["account_currency_query"] = query
        sent = cancelled = False
        cleanup_error = None
        try:
            with self._lock:
                if self._account_currency_query_current(req_id, query):
                    # Set before dispatch: a raised send may have reached the
                    # transport. Cleanup must not reinterpret it as unsent.
                    sent = True
                    if settled_usd:
                        self.reqAccountUpdatesMulti(req_id, expected_account, "", True)
                    else:
                        tags = ",".join(_CAPITAL_TAGS) if capital_currency is not None else "$LEDGER"
                        self.reqAccountSummary(req_id, "All", tags)
            wait_event(query["event"], max(0, query["deadline"] - time.monotonic()))
            with self._lock:
                self._account_currency_query_current(req_id, query, allow_complete=True)
                if query["status"] == "PARTIAL":
                    query["status"] = "TIMEOUT"
        except (AcquisitionCancelled, AcquisitionDeadlineExceeded):
            raise
        except Exception:
            query["status"] = "ERROR"
        finally:
            query["_local_cleanup_revision"] = self._local_request_cleanup_revision()
            with self._lock:
                current = self._request_context_by_req_id.get(req_id)
                owned = current is context and context.get("account_currency_query") is query
                if owned:
                    context.pop("account_currency_query", None)
                if ((owned or current is None)
                        and self._request_type_by_req_id.get(req_id) == "ACCOUNT_CURRENCY_STRICT"):
                    self._request_type_by_req_id.pop(req_id, None)
                query["event"].set()
            # Signaling can release another callback owner. Recheck the SAME
            # retired request and current native scope immediately at dispatch.
            with self._lock:
                tombstone_owned = (self._request_context_by_req_id.get(req_id) is context
                    and context.get("request_type") == "ACCOUNT_CURRENCY_STRICT"
                    and context.get("account_currency_query") is None
                    and req_id not in self._request_type_by_req_id)
                if owned and sent and not tombstone_owned and query["status"] == "COMPLETE":
                    query["status"] = "OWNERSHIP_LOST"
                if (owned and sent and tombstone_owned and self.is_connected()
                        and not self._stop_event.is_set()
                        and type(self._position_connection_epoch) is int
                        and epoch == self._position_connection_epoch
                        and type(self.client_id) is int and self.client_id == client_id
                        and not self._request_id_conflicted(req_id)):
                    cancelled = True
                    try:
                        if settled_usd:
                            self.cancelAccountUpdatesMulti(req_id)
                        else:
                            self.cancelAccountSummary(req_id)
                    except Exception as exc:
                        cleanup_error = str(exc)
        with self._lock:
            # Recheck current scope after cleanup callbacks, without restoring
            # the retired request or renewing its completion timestamp.
            self._account_currency_query_current(req_id, query, allow_complete=True, retired=True)
            if cleanup_error is not None or (
                    capital_currency is not None and query["status"] == "COMPLETE" and not cancelled):
                query["status"] = "CLEANUP_UNCONFIRMED"
            if (capital_currency is not None and query["status"] == "COMPLETE"
                    and not all(started_at <= fact.received_at <= query["completed_at"]
                                for fact in query["capital_facts"].values())):
                query["status"] = "INVALID_RECEIPT_TIME"
            complete = query["status"] == "COMPLETE"
            value = result(query["status"], req_id,
                currency=query["currency"] if complete else None,
                completed_at=query["completed_at"] if complete else None,
                tags=tuple(sorted(query["tags"])), cancelled=cancelled)
            if (capital_currency is None and not settled_usd and complete and cancelled and cleanup_error is None
                    and self._request_context_by_req_id.get(req_id) is context
                    and context.get("account_currency_query") is None
                    and req_id not in self._request_type_by_req_id):
                self._issue_local_request_completion("ACCOUNT_CURRENCY_STRICT",req_id,query,
                    currency=query["currency"],tags=tuple(sorted(query["tags"])))
            return value

    def _account_currency_query_current(self, req_id, query, *, allow_complete=False, retired=False):
        status = query["status"]
        if status != "PARTIAL" and not (allow_complete and status == "COMPLETE"):
            return False
        if (not retired and (self._request_context_by_req_id.get(req_id, {}).get("account_currency_query") is not query
                or self._request_type_by_req_id.get(req_id) != "ACCOUNT_CURRENCY_STRICT")):
            status = "OWNERSHIP_LOST"
        elif self._request_id_conflicted(req_id):
            status = "IDENTITY_CONFLICT"
        elif (type(self._position_connection_epoch) is not int
                or query["epoch"] != self._position_connection_epoch or not self.is_connected()
                or self._stop_event.is_set() or not self._position_transport_available):
            status = "DISCONNECTED"
        elif (tuple(self._managed_accounts) != (query["account"],)
                or query.get("account_generation", 0) != getattr(self, "_managed_accounts_generation", 0)
                or type(self.client_id) is not int or self.client_id != query["client_id"]):
            status = "SCOPE_CHANGED"
        elif query.get("capital_currency") is not None and not self._capital_currency_fresh(query["capital_currency"]):
            status = "STALE_CURRENCY"
        elif status == "PARTIAL" and time.monotonic() >= query["deadline"]:
            status = "TIMEOUT"
        elif status == "COMPLETE":
            from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
            stamp = query["completed_at"]
            age = (datetime.now(timezone.utc) - stamp).total_seconds()
            if not 0 <= age <= get_ibkr_snapshot_max_age_seconds():
                status = "STALE"
            else:
                return False
        else:
            return True
        query["status"] = status
        query["event"].set()
        return False

    @staticmethod
    def _capital_currency_fresh(currency):
        from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds

        age = (datetime.now(timezone.utc) - currency.completed_at).total_seconds()
        return 0 <= age <= get_ibkr_snapshot_max_age_seconds()

    @staticmethod
    def _account_capital_amount(value):
        if not isinstance(value, str) or not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value):
            return None
        try:
            amount = Decimal(value)
        except InvalidOperation:
            return None
        return amount if amount.is_finite() else None

    @staticmethod
    def _record_account_capital_fact(query, account, tag, value, currency):
        if account != query["account"]:
            return "WRONG_ACCOUNT"
        if tag not in _CAPITAL_TAGS:
            return "UNEXPECTED_TAG"
        if currency != query["capital_currency"].currency:
            return "AMBIGUOUS_CURRENCY"
        amount = IbkrClient._account_capital_amount(value)
        if amount is None:
            return "INVALID"
        previous = query["capital_facts"].get(tag)
        if previous is not None:
            return None if previous.value == amount else "CONFLICTING_VALUE"
        query["capital_facts"][tag] = AccountCapitalFact(
            account, tag, amount, currency, datetime.now(timezone.utc))
        return None

    def get_account_summary(self, timeout_seconds: Optional[int] = None) -> Dict[str, str]:
        if not self.is_connected():
            raise RuntimeError("IBKR client is not connected.")

        timeout = self.snapshot_timeout_seconds if timeout_seconds is None else timeout_seconds
        deadline = time.monotonic() + max(0, timeout)
        req_id = self._next_req_id()
        event = threading.Event()
        with self._lock:
            self._register_request(req_id, "ACCOUNT_SUMMARY")
            context = self._request_context_by_req_id[req_id]
            epoch = self._position_connection_epoch
            context["account_summary_deadline"] = deadline
            self._account_summary_events[req_id] = event
            self._account_summary_rows[req_id] = {}
        try:
            self.reqAccountSummary(req_id, "All", "AvailableFunds,NetLiquidation,BuyingPower")
            signaled = wait_event(event, max(0, deadline - time.monotonic()))
        finally:
            with self._lock:
                owned = self._account_summary_events.pop(req_id, None) is event
                rows = self._account_summary_rows.pop(req_id, {})
                same_context = self._request_context_by_req_id.get(req_id) is context
                if same_context and self._request_type_by_req_id.get(req_id) == "ACCOUNT_SUMMARY":
                    self._request_type_by_req_id.pop(req_id)
                if (owned and same_context and self.is_connected()
                        and epoch == self._position_connection_epoch and not self._request_id_conflicted(req_id)):
                    self.cancelAccountSummary(req_id)
        with self._lock:
            self._raise_if_request_id_conflicted(req_id)
            if (not signaled or not owned or not same_context or context.get("account_summary_end_received") is not True
                    or req_id in self._errors or not self.is_connected() or epoch != self._position_connection_epoch):
                raise RuntimeError("ACCOUNT_SUMMARY_INCOMPLETE")
            return rows

    def get_primary_account(
        self, timeout_seconds: Optional[int] = None, *, preserve_completed: bool = False
    ) -> Optional[str]:
        if not self.is_connected():
            raise RuntimeError("IBKR client is not connected.")

        timeout = timeout_seconds or self.snapshot_timeout_seconds
        if preserve_completed:
            # Keep the native bootstrap result, including empty or ambiguous replies.
            # An explicit read is bounded and never clears a concurrently arriving reply.
            if not self._managed_accounts_event.is_set():
                checkpoint()
                # Serialize dispatch with managedAccounts so a completed
                # callback can never be replaced by an unnecessary read.
                with self._lock:
                    if self._managed_accounts_event.is_set():
                        return next(iter(self._managed_accounts), None)
                    self.reqManagedAccts()
                wait_event(self._managed_accounts_event, timeout)
            with self._lock:
                if not self._managed_accounts_event.is_set():
                    return None
                return next(iter(self._managed_accounts), None)

        self._managed_accounts_event.clear()
        self._managed_accounts = []
        self.reqManagedAccts()
        self._managed_accounts_event.wait(timeout=timeout)
        return self._managed_accounts[0] if self._managed_accounts else None

    # --- Contract resolution ---
    def resolve_contract(
        self, symbol: str, exchange: str = "SMART", currency: str = "USD"
    ) -> ContractDetails:
        if not self.is_connected():
            raise RuntimeError("IBKR client is not connected.")

        req_id = self._next_req_id()
        print(f"[IBKR] Resolving contract for symbol={symbol} req_id={req_id}")

        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = exchange
        contract.currency = currency

        event = threading.Event()
        self._contract_events[req_id] = event
        self._contract_details[req_id] = []
        self._register_request(req_id, "CONTRACT_DETAILS", contract)
        if self._stop_event.is_set():
            raise RuntimeError("Contract resolution stopped during disconnect.")

        self.reqContractDetails(req_id, contract)

        if not wait_event(event, self.snapshot_timeout_seconds):
            raise RuntimeError(f"Contract resolution failed for symbol={symbol} (timeout).")

        with self._lock:
            self._raise_if_request_id_conflicted(req_id)
            details = list(self._contract_details.get(req_id, []))
        if not details:
            raise RuntimeError(f"Contract resolution failed for symbol={symbol}")

        resolved = details[0]
        print(
            f"[IBKR] Resolved contract symbol={symbol} req_id={req_id} conId={resolved.contract.conId}"
        )
        return resolved

    def get_contract_reference_metadata(self, contract) -> dict:
        """Reuse completed qualification evidence; never request or reconnect.

        Qualification's first-row choice is not name authority. Require a single
        response matching the caller's retained positive security identity.
        """
        con_id = getattr(contract, "conId", None)
        if type(con_id) is not int or con_id <= 0 or not self.is_connected():
            return {}
        for req_id, context in reversed(tuple(self._request_context_by_req_id.items())):
            if context.get("request_type") != "CONTRACT_DETAILS" or context.get("symbol") != getattr(contract, "symbol", None):
                continue
            # The latest attempt is authoritative even when it failed or timed out.
            response = context.get("reference_response")
            if not response or context.get("reference_error"):
                return {}
            completed, rows = response
            if completed > context.get("reference_deadline", float("-inf")) or len(rows) != 1:
                return {}
            row = rows[0]
            if type(row.get("conId")) is not int or row["conId"] != con_id:
                return {}
            for field in ("symbol", "secType", "currency", "primaryExchange", "localSymbol", "tradingClass", "exchange"):
                expected = getattr(contract, field, None)
                if field == "exchange" and expected == "SMART":
                    continue  # SMART is a routing instruction, not a listing venue.
                if expected and row.get(field) != expected:
                    return {}
            name = row.get("longName")
            if not isinstance(name, str) or not name.strip():
                return {}
            return {"longName": name, "conId": con_id, "request_id": req_id,
                    "source": "IBKR_CONTRACT_DETAILS", "completed_at_utc": context["reference_completed_at_utc"]}
        return {}

    @staticmethod
    def _price_contract_key(contract):
        return tuple(getattr(contract, name, None) for name in
            ("conId", "symbol", "secType", "currency", "primaryExchange", "localSymbol", "tradingClass"))

    def _qualified_price_scope(self, contract, route):
        key = self._price_contract_key(contract)
        if (type(key[0]) is not int or key[0] <= 0 or key[2] != "STK"
                or not isinstance(route, str) or not route or route != getattr(contract, "exchange", None)
                or not all(isinstance(value, str) for value in key[1:])
                or not key[1] or not key[3] or type(self.client_id) is not int or self.client_id < 0
                or not self.is_connected()):
            return None
        for req_id, context in reversed(tuple(self._request_context_by_req_id.items())):
            if context.get("request_type") != "CONTRACT_DETAILS" or context.get("symbol") != key[1]:
                continue
            response = context.get("reference_response")
            if (not response or context.get("reference_error")
                    or context.get("reference_epoch") != self._position_connection_epoch):
                return None
            completed, rows = response
            if completed > context.get("reference_deadline", -1) or len(rows) != 1:
                return None
            row = rows[0]
            fields = ("conId", "symbol", "secType", "currency", "primaryExchange", "localSymbol", "tradingClass")
            if type(row.get("conId")) is not int or tuple(row.get(name) for name in fields) != key:
                return None
            exchanges, rules = row.get("validExchanges"), row.get("marketRuleIds")
            if not isinstance(exchanges, str) or not isinstance(rules, str):
                return None
            exchanges, rules = exchanges.split(','), rules.split(',')
            if (len(exchanges) != len(rules) or len(set(exchanges)) != len(exchanges)
                    or any(not x or x != x.strip() for x in exchanges) or route not in exchanges):
                return None
            value = rules[exchanges.index(route)]
            if not value.isascii() or not value.isdigit() or int(value) <= 0:
                return None
            return key, req_id, int(value)
        return None

    def _price_rule_observed_now(self):
        return datetime.now(timezone.utc)

    def _finish_price_rule(self, query, status, bands=()):
        query["status"] = status
        query["result"] = replace(query["result"], status=status, bands=bands,
            completed_at=self._price_rule_observed_now() if status == "COMPLETE" else None)
        query["event"].set()

    def price_rule_snapshot(self, contract, *, route, timeout_seconds=None):
        """ONE request per rule per client-object lifetime; no retry after ambiguity.

        Callback has rule ID only. Same-scope COMPLETE reads reuse the ORIGINAL
        immutable receipt, never renew its clock. Busy/other-scope callers deny.
        Reconnect cannot reuse an old rule slot, even after successful completion.
        No connect/qualification/metadata-service side effect is introduced.
        """
        checkpoint()
        timeout = self.snapshot_timeout_seconds if timeout_seconds is None else timeout_seconds
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError("Bounded rule timeout required")
        with self._lock:
            scope = self._qualified_price_scope(contract, route)
            unavailable = NativePriceRule("UNAVAILABLE", self._price_contract_key(contract), route,
                None, self.client_id, self._position_connection_epoch)
            if scope is None:
                return unavailable
            key, qualification, rule_id = scope
            if getattr(self, "_price_rules_exhausted", False):
                return replace(unavailable, status="CAPACITY_EXHAUSTED")
            old = self._price_rule_requests.get(rule_id)
            if old is not None:
                result = old["result"]
                if (result.contract_key, result.route, result.qualification_request,
                        result.connection_epoch) != (key, route, qualification, self._position_connection_epoch):
                    return replace(unavailable, status="RULE_ID_REUSE_DENIED", rule_id=rule_id)
                return result  # PENDING is explicitly not completion.
            if len(self._price_rule_requests) >= 1024:
                self._price_rules_exhausted = True
                return replace(unavailable, status="CAPACITY_EXHAUSTED")
            self._price_rule_sequence += 1
            result = NativePriceRule("PENDING", key, route, rule_id, self.client_id,
                self._position_connection_epoch, qualification, self._price_rule_sequence)
            query = {"result": result, "status": "PENDING", "deadline": time.monotonic()+timeout,
                     "event": threading.Event()}
            self._price_rule_requests[rule_id] = query
        try:
            # No owner lock across potentially blocking SDK transport. If the
            # connection invalidates concurrently, this lifetime slot stays
            # retired and callbacks cannot restore authority or start a retry.
            super().reqMarketRule(rule_id)
            wait_event(query["event"], max(0,query["deadline"]-time.monotonic()))
        except BaseException:
            with self._lock:
                self._finish_price_rule(query, "INTERRUPTED")
            raise
        with self._lock:
            if query["status"] == "PENDING":
                self._finish_price_rule(query, "TIMEOUT")
            return query["result"]

    def reqMarketRule(self, marketRuleId):  # type: ignore[override]
        raise RuntimeError("Use owned price_rule_snapshot; unowned rule request forbidden")

    def marketRule(self, marketRuleId, priceIncrements):  # type: ignore[override]
        with self._lock:
            if type(marketRuleId) is not int or marketRuleId <= 0:
                return
            query = self._price_rule_requests.get(marketRuleId)
            if query is None:
                if len(self._price_rule_requests) >= 1024:
                    self._price_rules_exhausted = True
                    return
                # Unsolicited data poisons reuse; it must never certify a later call.
                result = NativePriceRule("UNSOLICITED", (), "", marketRuleId,
                    self.client_id, self._position_connection_epoch)
                query = {"result": result, "status": "UNSOLICITED", "event": threading.Event()}
                self._price_rule_requests[marketRuleId] = query
                return
            if query["status"] not in {"PENDING", "COMPLETE"}:
                return
            if query["result"].connection_epoch != self._position_connection_epoch or not self.is_connected():
                self._finish_price_rule(query, "DISCONNECTED")
                return
            if query["status"] == "PENDING" and time.monotonic() > query["deadline"]:
                self._finish_price_rule(query, "TIMEOUT")
                return
            if not isinstance(priceIncrements,(tuple,list)) or not 1 <= len(priceIncrements) <= 1024:
                self._finish_price_rule(query, "MALFORMED")
                return
            try:
                bands = tuple((_price_decimal(row.lowEdge), _price_decimal(row.increment)) for row in priceIncrements)
                if (not 1 <= len(bands) <= 1024 or bands[0][0] != 0
                        or any(edge < 0 or increment <= 0 for edge, increment in bands)
                        or any((edge.as_integer_ratio()[0]*increment.as_integer_ratio()[1]) % (edge.as_integer_ratio()[1]*increment.as_integer_ratio()[0]) for edge,increment in bands)
                        or any(a[0] >= b[0] for a,b in zip(bands,bands[1:]))):
                    raise ValueError("Malformed price bands")
            except (ValueError, TypeError, AttributeError):
                self._finish_price_rule(query, "MALFORMED")
                return
            if query["status"] == "COMPLETE":
                if query["result"].bands != bands:
                    self._finish_price_rule(query, "CONFLICTED")
                return  # Identical duplicates never renew completion.
            self._finish_price_rule(query, "COMPLETE", bands)

    def validate_price_rule(self, result, contract, *, route, observed_at, max_age_seconds):
        """Revalidate canonical live ownership after blocking checks; no renewed facts."""
        with self._lock:
            scope = self._qualified_price_scope(contract, route)
            query = self._price_rule_requests.get(getattr(result, "rule_id", None))
            if (not isinstance(result, NativePriceRule) or not query or query["result"] is not result
                    or query["status"] != "COMPLETE" or not scope
                    or scope != (result.contract_key, result.qualification_request, result.rule_id)
                    or result.connection_epoch != self._position_connection_epoch or result.client_id != self.client_id
                    or result.completed_at is None or not isinstance(observed_at, datetime) or observed_at.tzinfo is None
                    or not isinstance(max_age_seconds, (int, float)) or isinstance(max_age_seconds, bool) or not math.isfinite(max_age_seconds) or max_age_seconds < 0):
                return False
            return 0 <= (observed_at-result.completed_at).total_seconds() <= max_age_seconds

    def qualifyContracts(self, *contracts):
        """
        Compatibility wrapper for ib_insync-style APIs used by snapshot enrichment.
        """
        qualified = []
        for contract in contracts:
            symbol = getattr(contract, "symbol", None)
            if not symbol:
                continue
            try:
                details = self.resolve_contract(
                    symbol=symbol,
                    exchange=getattr(contract, "exchange", "SMART") or "SMART",
                    currency=getattr(contract, "currency", "USD") or "USD",
                )
                resolved_contract = details.contract
                for attr in ("conId", "primaryExchange", "tradingClass", "localSymbol"):
                    if hasattr(resolved_contract, attr):
                        setattr(contract, attr, getattr(resolved_contract, attr))
                qualified.append(contract)
            except Exception:
                continue
        return qualified

    def reqMarketDataType(self, marketDataType: int):  # type: ignore[override]
        self._requested_market_data_type_code = int(marketDataType)
        return super().reqMarketDataType(marketDataType)

    def _send_quote(self, *args, **kwargs):
        names = ("reqId", "contract", "genericTickList", "snapshot", "regulatorySnapshot", "mktDataOptions")
        values = {name: args[index] if len(args) > index else kwargs.get(name)
                  for index, name in enumerate(names)}
        req_id = values["reqId"]
        self._quote_trace.start(req_id, values["contract"],
            getattr(self, "_requested_market_data_type_code", _market_data_type_code(self.market_data_type)),
            values["genericTickList"], values["snapshot"], values["regulatorySnapshot"], values["mktDataOptions"],
            connection_epoch=getattr(self, "_position_connection_epoch", None))
        try:
            result = super().reqMktData(*args, **kwargs)
        except BaseException:
            self._quote_trace.sent(req_id, "SDK_RAISED")
            self._quote_trace.finish(req_id, "send_error")
            try:
                self.cancelMktData(req_id)
            except Exception:
                pass  # cancel owns finally-cleanup; retain the original exception.
            raise
        self._quote_trace.sent(req_id, "SDK_RETURNED_NOT_BROKER_ACK")
        return result

    def _quote_callback_ticker(self, req_id, kind, *, supported=True, valid=True, returned_type=None, tick_type=None):
        # Caller holds the native lock. Diagnostic counts are not authority.
        # Order-only/partially initialized callback consumers have no quote owner.
        if not hasattr(self, "_quote_trace"):
            return None
        owner = getattr(self, "_request_type_by_req_id", {}).get(req_id)
        ticker = self._ticker_by_req_id.get(req_id)
        if self._request_id_conflicted(req_id):
            reason = "conflicted"
        elif req_id not in self._active_market_req_ids:
            reason = "inactive" if req_id in self._quote_trace.requests else "unknown_request"
        elif owner != "MARKET_DATA":
            reason = "wrong_owner"
        elif ticker is None:
            reason = "missing_ticker"
        elif getattr(ticker, "freeze_on_snapshot_end", False) and ticker.snapshotEnd:
            reason = "snapshot_already_complete"
        elif getattr(ticker, "freeze_on_snapshot_end", False) and tick_type in {
                66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 88}:
            ticker.strictSnapshotNonLive = True
            reason = "unsupported_tick"
        elif not supported:
            reason = "unsupported_tick"
        elif not valid:
            reason = "invalid_value"
        else:
            reason = "accepted"
        self._quote_trace.callback(req_id, kind, reason, owner=owner, returned_type=returned_type, tick_type=tick_type)
        return ticker if reason == "accepted" else None

    def record_quote_completion(self, req_id, reason):
        self._quote_trace.finish(req_id, reason)

    def reqMktData(self, *args, **kwargs):  # type: ignore[override]
        """
        Compatibility wrapper supporting both:
        - ib_insync-style: reqMktData(contract, genericTickList="", snapshot=True, regulatorySnapshot=False)
        - raw ibapi-style: reqMktData(reqId, contract, genericTickList, snapshot, regulatorySnapshot, mktDataOptions)
        """
        if args and not isinstance(args[0], int):
            contract = args[0]
            generic_tick_list = kwargs.pop("genericTickList", "") if "genericTickList" in kwargs else (
                args[1] if len(args) > 1 else ""
            )
            snapshot = kwargs.pop("snapshot", True) if "snapshot" in kwargs else (
                args[2] if len(args) > 2 else True
            )
            regulatory_snapshot = (
                kwargs.pop("regulatorySnapshot", False)
                if "regulatorySnapshot" in kwargs
                else (args[3] if len(args) > 3 else False)
            )
            freeze = kwargs.pop("freeze_on_snapshot_end", False)
            if type(freeze) is not bool or (freeze and not snapshot):
                raise ValueError("Snapshot completion freeze requires a snapshot")
            if kwargs:
                raise TypeError(f"Unexpected reqMktData kwargs: {sorted(kwargs.keys())}")

            req_id = self._next_req_id()
            self._market_events[req_id] = threading.Event()
            self._market_data[req_id] = {"bid": None, "ask": None, "last": None, "volume": None}
            ticker = self._build_ticker(contract)
            ticker.reqId = req_id
            ticker.freeze_on_snapshot_end = freeze
            self._ticker_by_req_id[req_id] = ticker
            self._req_id_by_contract_key[self._contract_key(contract)] = req_id
            self._register_request(req_id, "MARKET_DATA", contract)
            self._active_market_req_ids.add(req_id)
            self._send_quote(
                req_id,
                contract,
                generic_tick_list,
                bool(snapshot),
                bool(regulatory_snapshot),
                [],
            )
            return ticker

        if args and isinstance(args[0], int):
            req_id = int(args[0])
            contract = args[1] if len(args) >= 2 else kwargs.get("contract")
            self._register_request(req_id, "MARKET_DATA", contract)
            if contract is not None and not isinstance(contract, int):
                self._req_id_by_contract_key[self._contract_key(contract)] = req_id
                self._ticker_by_req_id.setdefault(req_id, self._build_ticker(contract)).reqId = req_id
            self._market_events.setdefault(req_id, threading.Event())
            self._market_data.setdefault(req_id, {"bid": None, "ask": None, "last": None, "volume": None})
            self._active_market_req_ids.add(req_id)
            return self._send_quote(*args, **kwargs)

        raise TypeError("reqMktData requires either (contract, ...) or (reqId, contract, ...)")

    def cancelMktData(self, *args, **kwargs):  # type: ignore[override]
        if args and not isinstance(args[0], int):
            req_id = self._req_id_by_contract_key.get(self._contract_key(args[0]))
        elif args:
            req_id = int(args[0])
        else:
            return super().cancelMktData(*args, **kwargs)
        with self._lock:
            if req_id not in self._active_market_req_ids:
                return None
            ticker = self._ticker_by_req_id.get(req_id)
            completed = bool(getattr(ticker, "snapshotEnd", False))
            # Stop accepting ticks before sending a cancellation over the wire.
            self._active_market_req_ids.discard(req_id)
        outcome = "NOT_SENT_ALREADY_COMPLETE" if completed else "SDK_CANCEL_RAISED"
        try:
            # SDK return is not broker cancellation acknowledgement.
            if completed:
                return None
            result = super().cancelMktData(req_id)
            outcome = "SDK_CANCEL_RETURNED_NOT_BROKER_ACK"
            return result
        finally:
            self._cleanup_market_request(req_id)
            self._quote_trace.cleanup(req_id, outcome,
                active=req_id in self._active_market_req_ids,
                ticker_present=req_id in self._ticker_by_req_id,
                event_present=req_id in self._market_events)

    def reqHistoricalData(self, *args, **kwargs):  # type: ignore[override]
        """
        Compatibility wrapper supporting:

        - ib_insync-style:
            reqHistoricalData(contract, endDateTime="", durationStr="25 D", ...)

        - ibapi-style:
            reqHistoricalData(reqId, contract, ...)
        """
        if args and not isinstance(args[0], int):
            contract = args[0]
            end_date_time = kwargs.pop("endDateTime", args[1] if len(args) > 1 else "")
            duration_str = kwargs.pop("durationStr", args[2] if len(args) > 2 else "25 D")
            bar_size_setting = kwargs.pop("barSizeSetting", args[3] if len(args) > 3 else "1 day")
            what_to_show = kwargs.pop("whatToShow", args[4] if len(args) > 4 else "TRADES")
            use_rth = kwargs.pop("useRTH", args[5] if len(args) > 5 else True)
            format_date = kwargs.pop("formatDate", args[6] if len(args) > 6 else 1)
            keep_up_to_date = kwargs.pop("keepUpToDate", args[7] if len(args) > 7 else False)
            chart_options = kwargs.pop("chartOptions", args[8] if len(args) > 8 else [])
            if kwargs:
                raise TypeError(f"Unexpected reqHistoricalData kwargs: {sorted(kwargs.keys())}")

            return self._owned_historical_request(
                self._next_req_id(), contract, end_date_time, duration_str,
                bar_size_setting, what_to_show, int(bool(use_rth)), int(format_date),
                bool(keep_up_to_date), chart_options)

        if args and isinstance(args[0], int):
            return self._owned_historical_request(*args, **kwargs)

        raise TypeError(
            "reqHistoricalData requires either (contract, ...) or (reqId, contract, ...)"
        )

    def _owned_historical_request(self, req_id, contract, endDateTime="",
                                  durationStr="25 D", barSizeSetting="1 day",
                                  whatToShow="TRADES", useRTH=1, formatDate=1,
                                  keepUpToDate=False, chartOptions=None):
        # Raw reqId compatibility now uses the same bounded result contract;
        # there are no production fire-and-forget history consumers.
        event = threading.Event()
        state = {"status": "PENDING", "end_received": False, "bars": [],
                 "event": event, "sent": False, "error_code": None,
                 "streaming": bool(keepUpToDate),
                 "deadline": time.monotonic() + self.snapshot_timeout_seconds}
        with self._lock:
            # Explicit raw IDs can never reuse retired/active IDs, even after
            # bounded diagnostic metadata has been evicted. Allocated IDs come
            # from the existing shared monotonic request/order allocator.
            if (req_id in self._order_status_events or req_id in self._order_state_registry
                    or req_id == self._last_reserved_order_id):
                raise RuntimeError("Request ID is already reserved for an order.")
            if req_id <= self._req_id and req_id not in self._pending_request_allocations:
                raise RuntimeError("Historical request ID is already used or retired.")
            if req_id in self._historical_states:
                raise RuntimeError("Historical request ID already has an owner.")
            self._register_request(req_id, "HISTORICAL_DATA", contract)
            if self._stop_event.is_set() or not self.isConnected():
                self._request_type_by_req_id.pop(req_id, None)
                return HistoricalDataResult("DISCONNECTED", request_id=req_id)
            if len(self._historical_states) >= 128:
                self._request_type_by_req_id.pop(req_id, None)
                return HistoricalDataResult("ATTEMPT_CAPACITY", request_id=req_id)
            self._historical_states[req_id] = state
            self._historical_events[req_id] = event
            self._historical_data[req_id] = state["bars"]
        print(f"[IBKR][HIST_REQ] req_id={req_id} symbol={getattr(contract, 'symbol', None)}")
        try:
            checkpoint()
            # Atomic with disconnect/invalidation and order-ID discovery. SDK
            # synchronous error/end callbacks may re-enter this same owner lock.
            with self._lock:
                self._raise_if_request_id_conflicted(req_id)
                if (self._historical_states.get(req_id) is not state
                        or state["status"] != "PENDING" or self._stop_event.is_set()
                        or not self.isConnected()):
                    state["status"] = "DISCONNECTED"
                else:
                    from src.ibkr.market_data_client import historical_request_spec
                    from src.market_data.candidate_identity import CandidateIdentity
                    state["request_spec"] = historical_request_spec(
                        end_date_time=endDateTime, duration_str=durationStr,
                        bar_size_setting=barSizeSetting, what_to_show=whatToShow,
                        use_rth=int(bool(useRTH)), format_date=int(formatDate),
                        keep_up_to_date=bool(keepUpToDate), chart_options=chartOptions or [])
                    state["contract_identity"] = CandidateIdentity.from_contract(contract)
                    state["volume_scope"] = (self.client_id, self._position_connection_epoch, self.serverVersion())
                    state["request_dispatched_at_utc"] = datetime.now(timezone.utc).isoformat()
                    state["sent"] = True
                    super().reqHistoricalData(req_id, contract, endDateTime, durationStr,
                        barSizeSetting, whatToShow, int(bool(useRTH)), int(formatDate),
                        bool(keepUpToDate), chartOptions or [])
            # Wait only for a terminal owner state, never a first bar/error event
            # interpreted as completion. Preserve the existing 5s native budget.
            while True:
                checkpoint()
                with self._lock:
                    self._raise_if_request_id_conflicted(req_id)
                    if state["status"] != "PENDING":
                        break
                    if time.monotonic() >= state["deadline"]:
                        state["status"] = "TIMEOUT"
                        break
                time.sleep(bounded_timeout(min(.01, max(0, state["deadline"] - time.monotonic()))))
        except AcquisitionCancelled:
            state["status"] = "CANCELLED"
            raise
        except AcquisitionDeadlineExceeded:
            state["status"] = "TIMEOUT"
            raise
        except Exception:
            state["status"] = "ERROR"
            self._raise_if_request_id_conflicted(req_id)
        finally:
            self._retire_historical_request(req_id, state)
        from src.ibkr.market_data_client import historical_bar_facts
        volume_basis = self._historical_volume_basis(state, req_id)
        return HistoricalDataResult(state["status"], tuple(state["bars"]),
            state["end_received"], req_id, state["error_code"], len(state["bars"]) if not state["end_received"] else 0,
            contract_identity=state.get("contract_identity"),
            dispatched_contract_identity=state.get("contract_identity"), request_spec=state.get("request_spec"),
            request_dispatched_at_utc=state.get("request_dispatched_at_utc"),
            completed_at_utc=state.get("completed_at_utc"),
            callback_start=state.get("callback_start"), callback_end=state.get("callback_end"),
            raw_bar_timestamps=tuple(getattr(bar, "date", None) for bar in state["bars"]),
            source_bar_count=len(state["bars"]), raw_source_bars=historical_bar_facts(state["bars"]),
            volume_basis=volume_basis)

    def _retire_historical_request(self, req_id, state):
        with self._lock:
            owned = self._historical_states.get(req_id) is state
            if owned:
                self._historical_states.pop(req_id, None)
                self._historical_events.pop(req_id, None)
                self._historical_data.pop(req_id, None)
                self._request_type_by_req_id.pop(req_id, None)
            ambiguous = self._request_id_conflicted(req_id)
            state["event"].set()
        cancellation = "NOT_OUTSTANDING"
        if owned and state["sent"] and (not state["end_received"] or state["streaming"]) and state["status"] != "DISCONNECTED":
            if ambiguous:
                cancellation = "SKIPPED_AMBIGUOUS_ID"
            else:
                try:
                    super().cancelHistoricalData(req_id)
                    cancellation = "SDK_CANCEL_RETURNED_NOT_BROKER_ACK"
                except Exception as exc:
                    cancellation = "SDK_CANCEL_ERROR_" + type(exc).__name__
        print(f"[IBKR][HIST_RESULT] req_id={req_id} outcome={state['status']} "
              f"end_received={state['end_received']} received_count={len(state['bars'])} "
              f"retired=true cancellation={cancellation}")
        if os.environ.get("PR1090_PREMARKET_HISTORY_EVIDENCE") == "1":
            from src.ibkr.market_data_client import record_premarket_history
            record_premarket_history("ibapi", req_id, state.get("request_spec") if state["sent"] else None,
                                     state, owned=owned and not ambiguous, cancellation=cancellation)

    def cancelHistoricalData(self, req_id):  # type: ignore[override]
        with self._lock:
            state = self._historical_states.get(req_id)
            if state is None:
                return None
            state["status"] = "CANCELLED"
        self._retire_historical_request(req_id, state)

    def _invalidate_historical_requests(self):
        with self._lock:
            for state in self._historical_states.values():
                state["status"] = "DISCONNECTED"
                state["event"].set()
            self._historical_states.clear()
            for req_id in tuple(self._historical_events):
                self._request_type_by_req_id.pop(req_id, None)
            self._historical_events.clear()
            self._historical_data.clear()

    def waitOnUpdate(self, timeout: float = 0.0) -> bool:
        updated = self._market_update_event.wait(timeout=timeout)
        if updated:
            self._market_update_event.clear()
        return bool(updated)

    def contractDetails(self, reqId: int, contractDetails: ContractDetails):  # type: ignore[override]
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
            self._contract_details.setdefault(reqId, []).append(contractDetails)

    def contractDetailsEnd(self, reqId: int):  # type: ignore[override]
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
            context = getattr(self, "_request_context_by_req_id", {}).get(reqId, {})
            if "reference_deadline" in context and "reference_response" not in context:
                # Freeze only fields received by the genuine end callback. Late rows
                # cannot be promoted; error wakeups are not successful completion.
                rows = tuple({**{field: getattr(detail.contract, field, None) for field in
                             ("conId", "symbol", "secType", "currency", "exchange", "primaryExchange", "localSymbol", "tradingClass")},
                             "longName": getattr(detail, "longName", None),
                             "validExchanges": getattr(detail, "validExchanges", None),
                             "marketRuleIds": getattr(detail, "marketRuleIds", None)}
                             for detail in self._contract_details.get(reqId, ()))
                context["reference_completed_at_utc"] = datetime.now(timezone.utc).isoformat()
                context["reference_response"] = (time.monotonic(), rows)
            event = self._contract_events.get(reqId)
            if event:
                event.set()
            getattr(self, "_request_type_by_req_id", {}).pop(reqId, None)

    # --- Market data snapshot ---
    def _paper_volume_calibration(self):
        path = os.environ.get("ROSS_TWS_VOLUME_COMPARATOR_PATH")
        if not path or getattr(self, "_volume_calibration_invalidated", False):
            return None
        try:
            calibration = load_paper_volume_calibration(path, now=datetime.now(timezone.utc))
        except RuntimeError:
            if getattr(self, "_volume_calibration_binding", None):
                self._volume_calibration_invalidated = True
            return None
        expected = os.environ.get("ROSS_TWS_VOLUME_CALIBRATION_SHA256")
        if expected is not None and expected != calibration["calibration_id"]:
            self._volume_calibration_invalidated = True
            return None
        attested = (self.client_id, self._position_connection_epoch, self.serverVersion(),
                    calibration["calibration_id"])
        if (self._stop_event.is_set() or not self.isConnected()
                or self.serverVersion() != calibration["server_version"]
                or self._quote_trace.sdk_distribution != calibration["sdk_distribution"]):
            return None
        previous = getattr(self, "_volume_calibration_binding", None)
        if previous is not None and previous != attested:
            self._volume_calibration_invalidated = True
            return None
        self._volume_calibration_binding = attested
        return calibration

    def _historical_volume_basis(self, state, request_id):
        spec, identity = state.get("request_spec"), state.get("contract_identity")
        if (state["status"] != "COMPLETE_BARS" or not state["end_received"] or spec is None
                or spec.what_to_show != "TRADES" or spec.bar_size_setting != "1 day"
                or spec.duration_str != "20 D" or spec.end_date_time != "" or spec.format_date != 1
                or spec.use_rth != 1 or spec.keep_up_to_date or not spec.chart_options_empty
                or identity is None or identity.con_id is None):
            return None
        with self._lock:
            scope = (self.client_id, self._position_connection_epoch, self.serverVersion())
            if state.get("volume_scope") != scope or self._request_id_conflicted(request_id):
                return None
            historical_average, sample_count = average_daily_bar_volume(state["bars"], 20)
            basis = {"basis": HISTORICAL_BASIS, "con_id": identity.con_id, "client_id": scope[0],
                     "connection_epoch": scope[1], "server_version": scope[2], "request_id": request_id,
                     "completed_at_utc": state.get("completed_at_utc"), "end_received": True,
                     "unit": "UNKNOWN", "calibration_id": None,
                     "average": historical_average, "sample_count": sample_count}
            calibration = self._paper_volume_calibration()
            if (calibration is not None and calibration["con_id"] == identity.con_id
                    and identity.symbol == calibration["symbol"] and identity.sec_type == "STK"
                    and identity.currency == "USD" and identity.primary_exchange == calibration["primary_exchange"]):
                basis.update(unit=VERIFIED_SHARE_UNIT, calibration_id=calibration["calibration_id"])
                retained = self.__dict__.setdefault("_calibrated_history_requests", {})
                if len(retained) >= QuoteDiagnostics.MAX_REQUESTS:
                    retained.pop(next(iter(retained)), None)
                retained[request_id] = dict(basis)
            return basis

    def snapshot_volume_evidence(self, ticker):
        """Capture native volume facts separately from the unqualified quote value."""
        tick_type = getattr(ticker, "volumeTickType", None)
        if tick_type is None:
            return None
        contract = ticker.contract
        timestamp = _resolve_snapshot_timestamp(ticker)
        evidence = {
            "raw_value": ticker.volumeRawValue,
            "source": "IBKR_NATIVE_TICK_SIZE",
            "tick_type": tick_type,
            "session_basis": "IBKR_CURRENT_TRADING_DAY_CUMULATIVE",
            "symbol": str(getattr(contract, "symbol", "")).upper(),
            "con_id": getattr(contract, "conId", None),
            "security_type": getattr(contract, "secType", None),
            "currency": getattr(contract, "currency", None),
            "primary_exchange": getattr(contract, "primaryExchange", None),
            "request_id": ticker.reqId,
            "client_id": ticker.volumeClientId,
            "connection_epoch": ticker.volumeConnectionEpoch,
            "server_version": ticker.volumeServerVersion,
            "sdk_distribution": self._quote_trace.sdk_distribution,
            "received_at_utc": ticker.fieldReceivedAt.get("volume"),
            "market_timestamp_utc": timestamp.isoformat() if timestamp else None,
            "market_data_status": _returned_market_data_type(ticker),
            "mixed_volume_tick_types": ticker.mixedVolumeTickTypes,
            "nonlive_type_observed": (
                getattr(ticker, "volumeNonLiveTypeObserved", False)
                or getattr(ticker, "strictSnapshotNonLive", False)
            ),
            "broker_error_observed": bool(ticker.brokerErrors),
            "unit": "UNKNOWN",
            "unit_source": "UNVERIFIED_NATIVE_VOLUME_SETTING",
            "shares": None,
        }
        with self._lock:
            scope = (self.client_id, self._position_connection_epoch, self.serverVersion())
            if scope == (ticker.volumeClientId, ticker.volumeConnectionEpoch, ticker.volumeServerVersion):
                self._last_native_volume_sample = dict(evidence)
                if native_stock_volume_rejection(evidence) is None:
                    calibration = self._paper_volume_calibration()
                    witness = (*scope, evidence["con_id"])
                    if (calibration is not None and calibration["con_id"] == evidence["con_id"]
                            and calibration["symbol"] == evidence["symbol"]
                            and calibration["primary_exchange"] == evidence["primary_exchange"]):
                        evidence.update(unit=VERIFIED_SHARE_UNIT, unit_source=SHARE_UNIT_SOURCE,
                                        shares=evidence["raw_value"], calibration_id=calibration["calibration_id"])
                    elif (os.environ.get("ROSS_PAPER_RELEASE_ENABLED") != "1"
                            and not os.environ.get("ROSS_TWS_VOLUME_COMPARATOR_PATH")
                            and getattr(self, "_volume_unit_witness", None) == witness):
                        evidence.update(unit=VERIFIED_SHARE_UNIT, unit_source=SHARE_UNIT_SOURCE,
                                        shares=evidence["raw_value"])
                self._last_native_volume_sample = dict(evidence)
                retained = self.__dict__.setdefault("_native_volume_evidence", {})
                if len(retained) >= QuoteDiagnostics.MAX_REQUESTS:
                    retained.pop(next(iter(retained)), None)
                retained[evidence["request_id"]] = dict(evidence)
        return evidence

    def ross_volume_source_current(self, evidence):
        with self._lock:
            scope = (self.client_id, self._position_connection_epoch, self.serverVersion())
            if (not self.isConnected() or self._stop_event.is_set()
                    or native_stock_volume_rejection(
                        evidence, client_id=scope[0], connection_epoch=scope[1],
                    ) or evidence["server_version"] != scope[2]):
                return False
            if evidence.get("calibration_id") or os.environ.get("ROSS_PAPER_RELEASE_ENABLED") == "1":
                calibration = self._paper_volume_calibration()
                basis = evidence.get("adv20_volume_basis")
                if (calibration is None or calibration["calibration_id"] != evidence.get("calibration_id")
                        or not isinstance(basis, Mapping) or self._request_id_conflicted(basis.get("request_id"))
                        or getattr(self, "_calibrated_history_requests", {}).get(basis.get("request_id")) != basis):
                    return False
            elif (os.environ.get("ROSS_TWS_VOLUME_COMPARATOR_PATH")
                  or getattr(self, "_volume_unit_witness", None) != (*scope, evidence["con_id"])):
                return False
            retained = getattr(self, "_native_volume_evidence", {})
            original = retained.get(evidence["request_id"])
            if original is None or any(evidence.get(key) != value for key, value in original.items()):
                return False
            latest = next((sample for sample in reversed(retained.values())
                           if sample["con_id"] == evidence["con_id"]), None)
            return latest is not None and native_stock_volume_rejection(latest) is None

    def verify_us_stock_share_volume(self, sample, *, reference_shares, observed_at, con_id,
                                     send_us_stock_market_data_in_lots):
        """Retain the existing in-process watchlist-only component witness.

        Runtime preparation uses the private paired calibration file, which
        also checks an independent historical-volume observation.
        """
        with self._lock:
            self._volume_unit_witness = None
            now = datetime.now(timezone.utc)
            scope = (self.client_id, self._position_connection_epoch, self.serverVersion())
            if (not self.isConnected() or self._stop_event.is_set()
                    or send_us_stock_market_data_in_lots is not False
                    or not isinstance(observed_at, datetime) or type(con_id) is not int or con_id <= 0
                    or quote_time_rejection(observed_at, "LAST_TRADE", now=now)
                    or sample != getattr(self, "_last_native_volume_sample", None)
                    or native_stock_volume_rejection(sample, client_id=scope[0],
                        connection_epoch=scope[1], con_id=con_id, now=now)
                    or sample["server_version"] != scope[2]
                    or quote_time_rejection(sample["market_timestamp_utc"], "LAST_TRADE", now=observed_at)
                    or type(reference_shares) is not int or reference_shares <= 0
                    or reference_shares != sample["raw_value"]):
                return False
            self._volume_unit_witness = (*scope, con_id)
            return True

    def get_market_snapshot(self, symbol: str) -> MarketSnapshot:
        details = self.resolve_contract(symbol)
        contract = details.contract
        req_id = self._next_req_id()
        print(f"[IBKR] Requesting market snapshot symbol={symbol} req_id={req_id} conId={contract.conId}")
        event = threading.Event()
        self._market_events[req_id] = event
        self._market_data[req_id] = {"bid": None, "ask": None, "last": None, "volume": None}
        try:
            self.reqMktData(req_id, contract, "", True, False, [])
            wait_event(event, self.snapshot_timeout_seconds)
            with self._lock:
                self._raise_if_request_id_conflicted(req_id)
                # Freeze callback state before sampling its observation clock.
                # Cancellation owns cleanup; retain all values before it runs.
                ticker = _copy_snapshot_ticker(self._ticker_by_req_id[req_id])
                completed_at = datetime.now(timezone.utc)
            self.record_quote_completion(req_id, "snapshot_end" if ticker.snapshotEnd else
                                         "broker_error" if ticker.brokerErrors else "timeout")
        except BaseException:
            self.record_quote_completion(req_id, "interrupted")
            raise
        finally:
            self.cancelMktData(req_id)
        returned_type = _returned_market_data_type(ticker)
        requested_type = {1: "LIVE", 2: "FROZEN", 3: "DELAYED", 4: "DELAYED_FROZEN"}.get(ticker.requestedMarketDataType, "UNKNOWN")
        timestamp = _resolve_snapshot_timestamp(ticker)
        flags = _market_data_type_flags(returned_type)
        completion_reason = "snapshot_end" if ticker.snapshotEnd else ("broker_error" if ticker.brokerErrors else "timeout")
        if completion_reason == "timeout":
            flags.append("MD_TIMEOUT")
        if not ticker.snapshotEnd:
            flags.append("MD_SNAPSHOT_INCOMPLETE")
        if any(event["code"] == 10197 for event in ticker.brokerErrors):
            flags.append("MD_CONFLICT_10197")
        assessed_at = datetime.now(timezone.utc)
        reason = quote_time_rejection(timestamp, "LAST_TRADE" if timestamp is not None else "UNKNOWN", now=assessed_at)
        record_time_assessment(self, req_id, timestamp=timestamp,
            source="LAST_TRADE" if timestamp is not None else "UNKNOWN", assessed_at=assessed_at,
            reason=reason, assessor="IbkrClient.get_market_snapshot",
            timestamp_input=getattr(ticker, 'timestampInput', {}), completed_at=completed_at.isoformat())
        if reason:
            flags.append(reason)
        fields = {name: _clean(getattr(ticker, name, None)) for name in ("bid", "ask", "last", "volume", "close", "open", "high", "low")}
        for name in ("bid", "ask", "last", "close", "open", "high", "low"):
            if fields[name] is not None and fields[name] <= 0:
                fields[name] = None
        if fields["volume"] is not None and fields["volume"] < 0:
            fields["volume"] = None
        for name in ("bid", "ask", "last", "close", "volume"):
            if fields[name] is None:
                flags.append(f"MD_MISSING_{name.upper()}")
        if all(fields[name] is None for name in ("bid", "ask", "last")):
            flags.append("MD_EMPTY")
        snapshot = MarketSnapshot(
            symbol=symbol,
            **fields,
            bid_size=_clean(ticker.bidSize),
            ask_size=_clean(ticker.askSize),
            last_size=_clean(ticker.lastSize),
            asof_utc=datetime.now(timezone.utc),
            market_data_type=returned_type,
            requested_market_data_type=requested_type,
            returned_market_data_type=returned_type,
            market_data_type_confirmed=ticker.marketDataTypeConfirmed,
            market_timestamp_utc=timestamp,
            timestamp_source="LAST_TRADE" if timestamp else "UNKNOWN",
            market_data_type_received_at_utc=ticker.marketDataTypeReceivedAt,
            request_id=req_id,
            snapshot_complete=ticker.snapshotEnd,
            received_at_utc=ticker.receivedAt,
            data_quality_flags=tuple(flags),
            volume_evidence=self.snapshot_volume_evidence(ticker),
            **_snapshot_authority_metadata(ticker, fields, completed_at=completed_at, completion_reason=completion_reason),
        )
        print(f"[IBKR] Snapshot symbol={symbol} req_id={req_id} requested_type={requested_type} returned_type={returned_type} complete={ticker.snapshotEnd} bid={snapshot.bid} ask={snapshot.ask} last={snapshot.last}")
        return snapshot

    def snapshot_stock(self, symbol: str) -> MarketDataSnapshot:
        """Compatibility wrapper matching MarketDataClient snapshot contract."""
        snapshot = self.get_market_snapshot(symbol)
        return MarketDataSnapshot(
            symbol=symbol,
            bid=snapshot.bid,
            ask=snapshot.ask,
            last=snapshot.last,
            bid_size=snapshot.bid_size,
            ask_size=snapshot.ask_size,
            last_size=snapshot.last_size,
            volume=snapshot.volume,
            volume_evidence=snapshot.volume_evidence,
            vwap=None,
            open=snapshot.open,
            high=snapshot.high,
            low=snapshot.low,
            close=snapshot.close,
            change_percent=None,
            spread=(snapshot.ask - snapshot.bid) if snapshot.ask is not None and snapshot.bid is not None else None,
            timestamp_utc=snapshot.market_timestamp_utc.isoformat() if snapshot.market_timestamp_utc else None,
            data_quality_flags=list(snapshot.data_quality_flags),
            requested_market_data_type=snapshot.requested_market_data_type,
            returned_market_data_type=snapshot.returned_market_data_type,
            market_data_type_confirmed=snapshot.market_data_type_confirmed,
            timestamp_source="LAST_TRADE" if snapshot.market_timestamp_utc else "UNKNOWN",
            received_at_utc=snapshot.received_at_utc.isoformat() if snapshot.received_at_utc else None,
            market_data_type_received_at_utc=snapshot.market_data_type_received_at_utc.isoformat() if snapshot.market_data_type_received_at_utc else None,
            request_id=snapshot.request_id,
            snapshot_complete=snapshot.snapshot_complete,
            **{key: getattr(snapshot, key) for key in (
                "market_data_type_confirmation_source", "request_started_at_utc",
                "request_completed_at_utc", "snapshot_completed_at_utc", "completion_reason",
                "field_availability", "field_received_at_utc", "missing_fields_observed_at_utc",
                "broker_errors",
            )},
        )

    def snapshot_for_symbol(self, symbol: str) -> MarketDataSnapshot:
        return self.snapshot_stock(symbol)


    def reqScannerData(self, subscription):
        """
        Forward scanner request to underlying IB client.
        """
        self.last_scanner_request = {"completion_status": "UNAVAILABLE",
                                     "end_received": False, "wait_signalled": False,
                                     "row_count": None}
        if hasattr(self, "ib") and self.ib is not None:
            # ib_insync can return an empty ScanDataList on request errors without
            # scannerDataEnd. This branch has no native completion authority.
            raise RuntimeError("IBKR scanner response unavailable: unverified delegate; use native scanner client")

        if not self.is_connected():
            raise RuntimeError("IBKR client is not connected.")

        req_id = self._next_req_id()
        event = threading.Event()
        self._scanner_events[req_id] = event
        self._scanner_rows[req_id] = []
        self._register_request(req_id, "SCANNER_DATA")

        context = self._request_context_by_req_id[req_id]
        context["scanner_end_received"] = False
        started = time.monotonic()
        print(f"[IBKR][SCANNER_REQUEST] req_id={req_id} client_id={self.client_id} "
              f"scan={getattr(subscription, 'scanCode', None)} "
              f"location={getattr(subscription, 'locationCode', None)} "
              f"connected={self.is_connected()} timeout_seconds={self.snapshot_timeout_seconds}")
        try:
            self.reqScannerSubscription(req_id, subscription, [], [])
            signalled = wait_event(event, self.snapshot_timeout_seconds)
            with self._lock:
                self._raise_if_request_id_conflicted(req_id)
                rows = list(self._scanner_rows.get(req_id, []))
                error = self._errors.get(req_id)
                completed = bool(context["scanner_end_received"])
                receipt = {"req_id": req_id, "client_id": self.client_id,
                           "completion_status": "COMPLETE" if signalled and completed and not error else "UNAVAILABLE",
                           "end_received": completed, "wait_signalled": signalled,
                           "row_count": len(rows), "error": error,
                           "connected": self.is_connected(),
                           "elapsed_seconds": time.monotonic()-started}
                self.last_scanner_request = receipt
                print(f"[IBKR][SCANNER_RESULT] {json.dumps(sanitize(receipt), sort_keys=True)}")
            if error:
                raise RuntimeError(f"IBKR scanner request {req_id} failed: {error}")
            if not signalled or not completed:
                raise TimeoutError(f"IBKR scanner request {req_id}: scannerDataEnd missing within wait budget")
            return rows
        finally:
            try:
                self.cancelScannerSubscription(req_id)
            finally:
                with self._lock:
                    self._scanner_events.pop(req_id, None)
                    self._scanner_rows.pop(req_id, None)
                    self._request_type_by_req_id.pop(req_id, None)

    def cancelScannerSubscription(self, reqId):
        """
        Forward scanner cancellation to underlying IB client.
        """
        if hasattr(self, "ib") and self.ib is not None:
            return self.ib.cancelScannerSubscription(reqId)
        return super().cancelScannerSubscription(reqId)

    def marketDataType(self, reqId: TickerId, marketDataType: int):  # type: ignore[override]
        with self._lock:
            ticker = self._quote_callback_ticker(reqId, "marketDataType", returned_type=marketDataType)
            if ticker is None:
                return
            if getattr(ticker, "freeze_on_snapshot_end", False) and marketDataType != 1:
                ticker.strictSnapshotNonLive = True
            if marketDataType != 1:
                ticker.volumeNonLiveTypeObserved = True
            ticker.marketDataType = marketDataType if marketDataType in {1, 2, 3, 4} else None
            ticker.marketDataTypeConfirmed = ticker.marketDataType is not None
            ticker.marketDataTypeReceivedAt = datetime.now(timezone.utc)
            event = {
                "req_id": reqId,
                "symbol": getattr(ticker.contract, "symbol", None),
                "requested_market_data_type": ticker.requestedMarketDataType,
                "returned_market_data_type": ticker.marketDataType,
                "timestamp_utc": ticker.marketDataTypeReceivedAt.isoformat(),
            }
        print(f"[IBKR][MARKET_DATA_TYPE] {json.dumps(event, sort_keys=True)}")
        self._market_update_event.set()

    def tickSnapshotEnd(self, reqId: TickerId):  # type: ignore[override]
        with self._lock:
            ticker = self._quote_callback_ticker(reqId, "tickSnapshotEnd")
            if ticker is None:
                return
            ticker.snapshotEnd = True
            ticker.snapshotEndedAt = datetime.now(timezone.utc)
            event = self._market_events.get(reqId)
            if event:
                event.set()
        self._market_update_event.set()

    def tickPrice(self, reqId: TickerId, tickType: int, price: float, attrib):  # type: ignore[override]
        field = {1: "bid", 2: "ask", 4: "last", 6: "high", 7: "low", 9: "close", 14: "open",
                 66: "bid", 67: "ask", 68: "last", 72: "high", 73: "low", 75: "close", 76: "open"}.get(tickType)
        with self._lock:
            ticker = self._quote_callback_ticker(reqId, "tickPrice", supported=field is not None, tick_type=tickType)
            if ticker is None:
                return
            self._market_data[reqId][field] = price
            setattr(ticker, field, price)
            _record_field_receipt(ticker, [field])
        self._market_update_event.set()

    def tickSize(self, reqId: TickerId, tickType: int, size: float):  # type: ignore[override]
        field = {0: "bidSize", 3: "askSize", 5: "lastSize", 8: "volume",
                 69: "bidSize", 70: "askSize", 71: "lastSize", 74: "volume"}.get(tickType)
        with self._lock:
            ticker = self._quote_callback_ticker(reqId, "tickSize", supported=field is not None, tick_type=tickType)
            if ticker is None:
                return
            value = float(size)
            self._market_data[reqId][field] = value
            setattr(ticker, field, value)
            if field == "volume":
                previous = ticker.volumeTickType
                ticker.mixedVolumeTickTypes |= previous is not None and previous != tickType
                ticker.volumeTickType = tickType
                ticker.volumeRawValue = (exact_raw_volume(size) if isinstance(size, Decimal)
                                         else size if type(size) is int else _clean(size))
            _record_field_receipt(ticker, [{"bidSize": "bid_size", "askSize": "ask_size", "lastSize": "last_size"}.get(field, field)])
        self._market_update_event.set()

    def tickString(self, reqId: TickerId, tickType: int, value: str):  # type: ignore[override]
        if tickType not in {45, 88}:
            with self._lock:
                self._quote_callback_ticker(reqId, "tickString", supported=False, tick_type=tickType)
            return
        try:
            timestamp = datetime.fromtimestamp(float(value), timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            with self._lock:
                self._quote_callback_ticker(reqId, "tickString", valid=False, tick_type=tickType)
            return
        with self._lock:
            ticker = self._quote_callback_ticker(reqId, "tickString", tick_type=tickType)
            if ticker is None:
                return
            ticker.lastTime = timestamp
            try:
                ticker.timestampInput = self._quote_trace.timestamp_input(reqId, value, timestamp, datetime.now(timezone.utc), tickType)
            except Exception:
                ticker.timestampInput = {}  # Diagnostic failure cannot reject a valid callback.
            _record_field_receipt(ticker, ["market_timestamp"])
        self._market_update_event.set()

    def historicalData(self, reqId: int, bar):  # type: ignore[override]
        with self._lock:
            state = self._historical_states.get(reqId)
            if (state is None or state["status"] != "PENDING" or self._request_id_conflicted(reqId)
                    or time.monotonic() > state["deadline"]):
                return
            state["bars"].append(bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str):  # type: ignore[override]
        with self._lock:
            state = self._historical_states.get(reqId)
            if (state is None or state["status"] != "PENDING" or self._request_id_conflicted(reqId)
                    or time.monotonic() > state["deadline"]):
                return
            state["end_received"] = True
            state["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
            state["callback_start"], state["callback_end"] = start, end
            state["status"] = "COMPLETE_BARS" if state["bars"] else "COMPLETE_EMPTY"
            state["event"].set()
            print(f"[IBKR][HIST_DONE] req_id={reqId} bars={len(state['bars'])}")

    def accountSummary(
        self,
        reqId: int,
        account: str,
        tag: str,
        value: str,
        currency: str,
    ):  # type: ignore[override]
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
            context = self._request_context_by_req_id.get(reqId, {})
            if context.get("request_type") == "ACCOUNT_CURRENCY_STRICT":
                query = context.get("account_currency_query")
                if query is None or not self._account_currency_query_current(reqId, query):
                    return
                if query.get("capital_currency") is not None:
                    error = self._record_account_capital_fact(query, account, tag, value, currency)
                    if error is not None:
                        query["status"] = error
                        query["event"].set()
                    return
                if query.get("settled_usd"):
                    return
                if account != query["account"]:
                    query["status"] = "WRONG_ACCOUNT"
                elif (not isinstance(tag, str) or not tag or tag != tag.strip()
                        or not isinstance(currency, str) or len(currency) != 3
                        or not currency.isascii() or not currency.isalpha() or currency != currency.upper()):
                    query["status"] = "INVALID"
                elif query["currency"] not in (None, currency):
                    query["status"] = "AMBIGUOUS_CURRENCY"
                else:
                    query["currency"] = currency
                    query["tags"].add(tag)
                    ticket_id = self._publish_local_intake("accountSummary",cache="_request_context_by_req_id",
                        request_id=reqId,context_id=id(query))
                    if ticket_id is not None:query.setdefault("_local_callback_ticket_ids",[]).append(ticket_id)
                    return
                query["event"].set()
                return
            if context.get("request_type") != "ACCOUNT_SUMMARY":
                return  # Unowned/evicted strict callbacks are not legacy rows.
            event = self._account_summary_events.get(reqId)
            if event is None or event.is_set():
                return
            register_account(account)
            self._account_summary_rows[reqId][tag] = value

    def accountSummaryEnd(self, reqId: int):  # type: ignore[override]
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
            context = self._request_context_by_req_id.get(reqId, {})
            if context.get("request_type") == "ACCOUNT_CURRENCY_STRICT":
                query = context.get("account_currency_query")
                if query is not None and self._account_currency_query_current(reqId, query):
                    if query.get("capital_currency") is not None:
                        query["status"] = ("COMPLETE" if query["capital_facts"].keys() == set(_CAPITAL_TAGS)
                                           else "MISSING_CAPITAL")
                        if query["status"] == "COMPLETE":
                            query["completed_at"] = datetime.now(timezone.utc)
                        query["event"].set()
                        return
                    if query.get("settled_usd"):
                        return
                    query["status"] = "COMPLETE" if query["currency"] is not None else "MISSING_CURRENCY"
                    if query["status"] == "COMPLETE":
                        query["completed_at"] = datetime.now(timezone.utc)
                        ticket_id = self._publish_local_intake("accountSummaryEnd",cache="_request_context_by_req_id",
                            request_id=reqId,context_id=id(query))
                        if ticket_id is not None:query.setdefault("_local_callback_ticket_ids",[]).append(ticket_id)
                    query["event"].set()
                return
            if context.get("request_type") != "ACCOUNT_SUMMARY":
                return
            event = self._account_summary_events.get(reqId)
            if event is not None and not event.is_set():
                deadline = context.get("account_summary_deadline")
                context["account_summary_end_received"] = deadline is not None and time.monotonic() < deadline
                event.set()
            getattr(self, "_request_type_by_req_id", {}).pop(reqId, None)

    def accountUpdateMulti(self, reqId, account, modelCode, key, value, currency):  # type: ignore[override]
        with self._lock:
            query = self._request_context_by_req_id.get(reqId, {}).get("account_currency_query")
            if not query or not query.get("settled_usd") or not self._account_currency_query_current(reqId, query):
                return
            if account != query["account"] or modelCode != "":
                query["status"] = "SETTLED_CASH_SCOPE_MISMATCH"
            elif key == "AccountReady" and str(value).lower() != "true":
                query["status"] = "SETTLED_CASH_ACCOUNT_NOT_READY"
            elif key in {"SettledCashByDate-S", "$LEDGER-SettledCashByDate-S"} and currency == "USD":
                # IBKR reports available cash on the first date and cumulative
                # balances on later dates. Do not spend against future credits
                # or disregard outstanding debits to the securities segment.
                try:
                    rows = []
                    for item in value.split(";"):
                        raw_day, raw_amount = item.split(":")
                        if not re.fullmatch("[0-9]{8}", raw_day):
                            raise ValueError
                        day = datetime.strptime(raw_day, "%Y%m%d").date()
                        amount = self._account_capital_amount(raw_amount)
                        if amount is None or (rows and day <= rows[-1][0]):
                            raise ValueError
                        rows.append((day, amount))
                    if rows[0][0] != query["cash_as_of_date"]:
                        raise ValueError
                    rows = tuple(rows)
                except (AttributeError, IndexError, ValueError):
                    query["status"] = "SETTLED_CASH_INVALID"
                else:
                    previous = query.get("settled_cash_rows")
                    if previous is None or previous == rows:
                        query["settled_cash_rows"] = rows
                        query["settled_cash"] = min(amount for _, amount in rows)
                        query["currency"] = currency
                        query["tags"].add(key)
                        return
                    query["status"] = "SETTLED_CASH_CONFLICTING"
            else:
                return
            query["event"].set()

    def accountUpdateMultiEnd(self, reqId):  # type: ignore[override]
        with self._lock:
            query = self._request_context_by_req_id.get(reqId, {}).get("account_currency_query")
            if not query or not query.get("settled_usd") or not self._account_currency_query_current(reqId, query):
                return
            now = datetime.now(timezone.utc)
            if query.get("settled_cash") is None:
                query["status"] = "SETTLED_CASH_UNAVAILABLE"
            elif now.astimezone(ZoneInfo("America/New_York")).date() != query["cash_as_of_date"]:
                query["status"] = "SETTLED_CASH_DATE_CHANGED"
            else:
                query["status"] = "COMPLETE"
                query["completed_at"] = now
            query["event"].set()

    def managedAccounts(self, accountsList: str):  # type: ignore[override]
        register_account(accountsList)
        with self._lock:
            accounts = [account.strip() for account in accountsList.split(",") if account.strip()]
            if accounts != self._managed_accounts:
                self._managed_accounts_generation = getattr(self, "_managed_accounts_generation", 0) + 1
                proxy = getattr(self, "_commission_decoder_proxy", None)
                if proxy is not None and proxy.account_scope is not None and tuple(accounts) != proxy.account_scope:
                    self._commission_zero_disabled = True
                for context in self._request_context_by_req_id.values():
                    query = context.get("execution_query")
                    if query is not None and query["status"] in ("PARTIAL", "COMPLETE"):
                        query["status"] = "SCOPE_CHANGED"
                        query["event"].set()
                    currency_query = context.get("account_currency_query")
                    if currency_query is not None and currency_query["status"] in ("PARTIAL", "COMPLETE"):
                        currency_query["status"] = "SCOPE_CHANGED"
                        currency_query["event"].set()
            self._managed_accounts = accounts
            self._managed_accounts_event.set()


    def scannerData(
        self,
        reqId: int,
        rank: int,
        contractDetails: ContractDetails,
        distance: str,
        benchmark: str,
        projection: str,
        legsStr: str,
    ):  # type: ignore[override]
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
            from types import SimpleNamespace

            if reqId not in self._scanner_events:
                print(f"[IBKR][SCANNER_CALLBACK_IGNORED] req_id={reqId} event=scannerData reason=no_active_request")
                return
            self._scanner_rows.setdefault(reqId, []).append(
                SimpleNamespace(
                    rank=rank,
                    contractDetails=contractDetails,
                    distance=distance,
                    benchmark=benchmark,
                    projection=projection,
                    legsStr=legsStr,
                )
            )

    def scannerDataEnd(self, reqId: int):  # type: ignore[override]
        with self._lock:
            if self._request_id_conflicted(reqId):
                return
            event = self._scanner_events.get(reqId)
            print(f"[IBKR][SCANNER_CALLBACK] req_id={reqId} event=scannerDataEnd active={event is not None}")
            if event:
                self._request_context_by_req_id[reqId]["scanner_end_received"] = True
                event.set()
            getattr(self, "_request_type_by_req_id", {}).pop(reqId, None)

    # --- Error handling ---
    def error(self, reqId: int, errorCode: int, errorString: str, *sdk_callback_tail):  # type: ignore[override]
        # The official SDK inserts errorTime before code and optionally appends
        # rejection JSON. Preserve the existing owner/code handling, but never
        # publish that JSON or accidentally interpret the time as an error code.
        if sdk_callback_tail:
            if (len(sdk_callback_tail) not in (1, 2) or type(errorString) is not int
                    or type(sdk_callback_tail[0]) is not str):
                raise RuntimeError("IBKR_ERROR_CALLBACK_SCHEMA_UNSUPPORTED")
            errorCode, errorString = errorString, sdk_callback_tail[0]
        with self._lock:
            # This protocol has no per-attempt error token. Never guess ownership.
            for rule_id, query in getattr(self, "_price_rule_requests", {}).items():
                if reqId in (-1, rule_id):
                    self._finish_price_rule(query, "ERROR")
        timestamp_utc = datetime.now(timezone.utc).isoformat()
        request_type_by_req_id = getattr(self, "_request_type_by_req_id", {})
        context = getattr(self, "_request_context_by_req_id", {}).get(reqId, {})
        request_type = request_type_by_req_id.get(reqId) or context.get("request_type")
        with self._lock:
            ticker = self._quote_callback_ticker(reqId, "error")
        event = sanitize({
            "timestamp_utc": timestamp_utc,
            "req_id": reqId,
            "request_type": request_type,
            "symbol": getattr(getattr(ticker, "contract", None), "symbol", None) or context.get("symbol"),
            "con_id": context.get("con_id"),
            "code": int(errorCode),
            "message": errorString,
        })
        if not hasattr(self, "_broker_error_events"):
            self._broker_error_events = []
        if ticker is not None and reqId in self._active_market_req_ids:
            ticker.brokerErrors.append(event)
        self._broker_error_events.append(event)
        del self._broker_error_events[:-256]
        print(f"[IBKR][BROKER_ERROR] {json.dumps(event, sort_keys=True)}")
        self._update_position_transport(errorCode, errorString)
        with self._lock:
            if self._request_id_conflicted(reqId):
                print(f"[IBKR][ERROR][OWNERSHIP_AMBIGUOUS] id={reqId} code={errorCode}")
                return
            execution_query = context.get("execution_query")
            if context.get("request_type") == "EXECUTIONS_STRICT":
                if execution_query is not None:
                    execution_query["status"] = "ERROR"
                    execution_query["event"].set()
                return
            if context.get("request_type") == "ACCOUNT_CURRENCY_STRICT":
                currency_query = context.get("account_currency_query")
                if currency_query is not None:
                    currency_query["status"] = "ERROR"
                    currency_query["event"].set()
                return
            unknown_market_req = int(errorCode) == 300 and reqId >= 0 and request_type is None
            if unknown_market_req:
                print(
                    "[IBKR][WARN] "
                    f"code=300 reqId={reqId} request_type=UNKNOWN reason={errorString} action=downgraded"
                )
                return
            fractional_unsupported_warning = int(errorCode) == 2176
            is_non_rejecting_order_warning = (
                errorCode in self.NON_REJECTING_ORDER_WARNING_CODES and reqId in self._order_status_events
            )
            is_order_only_callback = (
                is_non_rejecting_order_warning or fractional_unsupported_warning
                or (errorCode in self.ORDER_ONLY_CALLBACK_CODES
                    and reqId in self._order_status_events)
            )
            if (request_type_by_req_id.get(reqId) == "CONTRACT_DETAILS"
                    and "reference_deadline" in context and "reference_response" not in context
                    and not is_order_only_callback):
                # Numeric order IDs share the legacy error map. Exclude known order
                # callbacks; only this active attempt can disqualify its response.
                context["reference_error"] = (errorCode, errorString)
            if reqId >= 0:
                self._errors[reqId] = (errorCode, errorString)
                if reqId in self._order_status_events:
                    existing = self._order_status.get(reqId, {})
                    if is_non_rejecting_order_warning:
                        self._order_warnings[reqId] = (errorCode, errorString)
                        self._order_status[reqId] = {
                            **existing,
                            "broker_warning_code": str(errorCode),
                            "broker_warning_message": errorString,
                        }
                    else:
                        self._order_errors[reqId] = (errorCode, errorString)
                        self._order_status[reqId] = {
                            **existing,
                            "status": existing.get("status", "REJECTED"),
                            "broker_error_code": str(errorCode),
                            "broker_error_message": errorString,
                        }
                        self._order_status_events[reqId].set()
                if reqId in self._contract_events and not is_order_only_callback:
                    self._contract_events[reqId].set()
                if reqId in self._market_events:
                    self._market_events[reqId].set()
                    self._market_update_event.set()
                history = self._historical_states.get(reqId)
                if history is not None and history["status"] == "PENDING":
                    history["status"] = "ERROR"
                    history["error_code"] = errorCode
                    history["event"].set()
                if reqId in self._account_summary_events:
                    self._account_summary_events[reqId].set()
                if reqId in self._scanner_events:
                    self._scanner_events[reqId].set()
            if fractional_unsupported_warning:
                print(
                    "[IBKR][WARN] "
                    f"type=FRACTIONAL_SHARE_UNSUPPORTED order_id={reqId} code={errorCode} message={errorString}"
                )
                message = (
                    "[IBKR][WARN] "
                    f"type=FRACTIONAL_SHARE_UNSUPPORTED reqId={reqId} code={errorCode} msg={errorString}"
                )
            elif is_non_rejecting_order_warning:
                print(f"[IBKR][WARN] order_id={reqId} code={errorCode} message={errorString}")
                message = f"[IBKR] Warning reqId={reqId} code={errorCode} msg={errorString}"
            else:
                message = f"[IBKR] Error reqId={reqId} code={errorCode} msg={errorString} timestamp_utc={timestamp_utc}"
            if not fractional_unsupported_warning:
                print(
                    "[ORDER][ERROR] "
                    f"order_id={reqId} code={errorCode} message={errorString}"
                )
                print(
                    "[IBKR][ORDER_ERROR] "
                    f"order_id={reqId} code={errorCode} message={errorString}"
                )
            print(message)
            if errorCode == 326:
                print("[IBKR][CONNECT_FAIL] code=326 client id already in use")
            context = self._position_queries.get(reqId)
            if context is not None and not is_order_only_callback:
                context["status"] = "FAILED"
                context["event"].set()

    def _update_position_transport(self, error_code: int, error_string: str) -> None:
        if error_code in (1100, 1300):  # connection/pacing
            self._invalidate_position_queries(clear_account_scope=error_code == 1300)
            self._last_disconnect_reason = f"code={error_code} msg={error_string}"
            self._connection_event.clear()
        elif error_code in (1101, 1102):
            # TWS restored the same upstream session without a new API handshake.
            # Retained account identity is scope, never position evidence. All
            # interrupted query epochs remain invalid; only a fresh query may pass.
            with self._lock:
                if self.is_connected() and not self._stop_event.is_set():
                    self._position_upstream_lost = False
                    self._position_transport_available = True
                    self._connection_event.set()


    def nextValidId(self, orderId: int):  # type: ignore[override]
        with self._lock:
            if not self._position_upstream_lost:
                self._position_transport_available = True
        broker_next = int(orderId)
        chosen = broker_next
        if self._last_reserved_order_id is not None and broker_next <= int(self._last_reserved_order_id):
            chosen = int(self._last_reserved_order_id) + 1
            print(
                "[IBKR][ORDER_ID_REBASE] "
                f"broker_next={broker_next} local_last={self._last_reserved_order_id} chosen={chosen}"
            )
        self._next_valid_order_id = chosen
        self._next_order_id = chosen
        print(f"[IBKR][NEXT_VALID_ID] order_id={chosen}")
        self._connection_event.set()

    def orderStatus(
        self,
        orderId: int,
        status: str,
        filled: float,
        remaining: float,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float,
    ):  # type: ignore[override]
        with self._lock:
            status_scope = (self._position_connection_epoch, getattr(self, "_managed_accounts_generation", 0))
        self._observe_order_id(int(orderId))
        if not hasattr(self, "_order_status_count"):
            self._order_status_count = 0
        self._order_status_count += 1
        print(
            "[IBKR][CALLBACK_RAW] "
            f"event=orderStatus order_id={orderId} status={status} filled={filled} remaining={remaining} whyHeld={whyHeld}"
        )
        print(
            "[IBKR][ORDER_STATUS] "
            f"order_id={orderId} "
            f"status={status} "
            f"filled={filled} "
            f"remaining={remaining}"
        )
        self._ensure_order_state_registry()
        with self._lock:
            if status_scope != (self._position_connection_epoch, getattr(self, "_managed_accounts_generation", 0)):
                return
            existing = self._order_status.get(orderId, {})
            # Intake owns whole-share validation. Truncation here would conceal a
            # fractional or malformed callback before that owner can reject it.
            self._order_status[orderId] = {
                **existing,
                "status": status,
                "filled": filled,
                "remaining": remaining,
                "avgFillPrice": avgFillPrice,
                "lastFillPrice": lastFillPrice,
                "status_client_id": clientId,
                "status_parent_id": parentId,
                "status_connection_epoch": status_scope[0],
                "status_account_generation": status_scope[1],
            }
        self._publish_local_intake("orderStatus",cache="_order_status",order_id=orderId)
        print(
            "[ORDER][STATUS] "
            f"order_id={orderId} status={status} filled={filled} remaining={remaining}"
        )
        print(
            "[IBKR][ORDER_STATUS] "
            f"order_id={orderId} status={status} filled={filled} remaining={remaining} "
            f"avg_fill_price={avgFillPrice} last_fill_price={lastFillPrice}"
        )
        print(
            "[EXECUTION][ORDER_TRACK] "
            f"order_id={orderId} status={status} filled={filled} remaining={remaining}"
        )
        open_order_row = self._open_orders_snapshot.get(orderId)
        ack_order = getattr(open_order_row, "order", None) if open_order_row is not None else None
        outside_rth = getattr(ack_order, "outsideRth", None)
        outside_rth_label = outside_rth if outside_rth is not None else "<unknown>"
        print(
            "[EXECUTION][ACK_CONFIRMED] "
            f"order_id={orderId} symbol={getattr(getattr(open_order_row, 'contract', None), 'symbol', None)} "
            f"outsideRth={outside_rth_label} status={status}"
        )
        self._emit_execution_callback(
            {
                "event_type": "orderStatus",
                "orderId": orderId,
                "status": status,
                "filled": filled,
                "remaining": remaining,
                "avgFillPrice": avgFillPrice,
                "lastFillPrice": lastFillPrice,
                "whyHeld": whyHeld,
            }
        )
        event = self._order_status_events.setdefault(orderId, threading.Event())
        event.set()

    def execDetails(self, reqId, contract, execution):  # type: ignore[override]
        with self._lock:
            if self._scoped_execution_callback(reqId, contract, execution):
                return
            # Only unsolicited -1 or an owned legacy query may reach the old path.
            # Unknown/wrong-kind IDs cannot turn history into live fills, even
            # after bounded request metadata eviction or raw compatibility reuse.
            if reqId != -1 and getattr(self, "_request_type_by_req_id", {}).get(reqId) != "EXECUTIONS":
                return
            unsolicited_epoch = self._position_connection_epoch if reqId == -1 else None
        if getattr(execution, "orderId", None) is not None:
            self._observe_order_id(int(execution.orderId))
        if not hasattr(self, "_exec_details_count"):
            self._exec_details_count = 0
        self._exec_details_count += 1
        self._ensure_order_state_registry()
        print(
            "[IBKR][CALLBACK_RAW] "
            f"event=execDetails order_id={getattr(execution, 'orderId', None)} "
            f"exec_id={getattr(execution, 'execId', None)} symbol={getattr(contract, 'symbol', None)}"
        )
        print(
            "[IBKR][EXEC_DETAILS] "
            f"symbol={getattr(contract, 'symbol', None)} "
            f"exec_id={getattr(execution, 'execId', None)} "
            f"order_id={getattr(execution, 'orderId', None)} "
            f"shares={getattr(execution, 'shares', None)} "
            f"price={getattr(execution, 'price', None)}"
        )
        order_id = getattr(execution, "orderId", None)
        if order_id is None:
            return
        details = {
            "execId": getattr(execution, "execId", None),
            "time": getattr(execution, "time", None),
            "price": getattr(execution, "price", None),
            "shares": getattr(execution, "shares", None),
        }
        print(
            "[ORDER][FILL] "
            f"symbol={getattr(contract, 'symbol', None)} order_id={order_id} "
            f"shares={getattr(execution, 'shares', None)} avg_price={getattr(execution, 'price', None)}"
        )
        print(
            "[IBKR][ORDER_FILL] "
            f"symbol={getattr(contract, 'symbol', None)} order_id={order_id} "
            f"shares={getattr(execution, 'shares', None)} avg_price={getattr(execution, 'price', None)}"
        )
        print(
            "[EXECUTION][ORDER_TRACK] "
            f"order_id={order_id} status=Filled shares={getattr(execution, 'shares', None)}"
        )
        if reqId == -1:
            # Only unsolicited callbacks can support active native feedback.
            # Freeze primitive broker facts now, not when a later reader asks.
            details = deepcopy({**details,
                "_native_unsolicited": True,
                "orderId": order_id,
                "account": getattr(execution, "acctNumber", None),
                "clientId": getattr(execution, "clientId", None),
                "conId": getattr(contract, "conId", None),
                "symbol": getattr(contract, "symbol", None),
                "secType": getattr(contract, "secType", None),
                # Additive raw fact only. Existing financial projection/dedupe
                # remains unchanged; the fee-source view validates this field.
                "currency": getattr(contract, "currency", None),
                "side": getattr(execution, "side", None),
                "cumQty": getattr(execution, "cumQty", None),
                "avgPrice": getattr(execution, "avgPrice", None),
                "connection_epoch": unsolicited_epoch})
        with self._lock:
            self._exec_details_by_order.setdefault(order_id, []).append(details)
        self._executions_snapshot.append(
            SimpleNamespace(contract=contract, execution=execution, orderId=order_id)
        )
        if reqId == -1:
            self._publish_local_intake("execDetails",cache="_exec_details_by_order",
                order_id=order_id,execution_id=getattr(execution,"execId",None),request_id=reqId)
        self._emit_execution_callback(
            {
                "event_type": "execDetails",
                "orderId": order_id,
                "contract": contract,
                "execution": execution,
                "shares": getattr(execution, "shares", None),
                "price": getattr(execution, "price", None),
                "time": getattr(execution, "time", None),
            }
        )

    def openOrder(self, orderId, contract, order, orderState):  # type: ignore[override]
        self._observe_order_id(int(orderId))
        if not hasattr(self, "_open_order_count"):
            self._open_order_count = 0
        self._open_order_count += 1
        self._ensure_order_state_registry()
        print(f"[ORDER][OPEN] order_id={orderId} symbol={getattr(contract, 'symbol', None)}")
        print(
            "[IBKR][CALLBACK_RAW] "
            f"event=openOrder order_id={orderId} symbol={getattr(contract, 'symbol', None)} "
            f"status={getattr(orderState, 'status', None)}"
        )
        outside_rth = getattr(order, "outsideRth", None)
        print(
            "[IBKR][ACK] "
            f"order_id={orderId} symbol={getattr(contract, 'symbol', None)} "
            f"orderType={getattr(order, 'orderType', None)} tif={getattr(order, 'tif', None)} outsideRth={outside_rth}"
        )
        outside_rth_label = outside_rth if outside_rth is not None else "<unknown>"
        print(
            "[EXECUTION][ACK_CONFIRMED] "
            f"order_id={orderId} symbol={getattr(contract, 'symbol', None)} "
            f"outsideRth={outside_rth_label} status={getattr(orderState, 'status', None)}"
        )
        row = SimpleNamespace(orderId=orderId, contract=contract, order=order, orderState=orderState)
        with self._lock:
            self._open_orders_snapshot[orderId] = row
        self._publish_local_intake("openOrder",cache="_open_orders_snapshot",order_id=orderId)
        self._emit_execution_callback(
            {
                "event_type": "openOrder",
                "orderId": orderId,
                "contract": contract,
                "order": order,
                "orderState": orderState,
            }
        )

    def commissionAndFeesReport(self, report):  # type: ignore[override]
        # The official SDK renamed both the report and its amount. Reuse the
        # existing receipt owner without borrowing the old eight-field proof.
        # In particular an absent/default zero remains UNKNOWN, not a free trade.
        if _SDK_COMMISSION_MODERN and type(report) is _SDKCommissionReport:
            # Keep the exact SDK object through single-use witness consumption.
            # Direct/unowned callbacks have no decoder receipt to consume.
            if self._commission_decoder_proxy is None:
                self._commission_zero_disabled = True
            return self.commissionReport(report)
        projected = SimpleNamespace(
            execId=getattr(report, "execId", None),
            commission=getattr(report, "commissionAndFees", None),
            currency=getattr(report, "currency", None),
        )
        return self.commissionReport(projected)

    def commissionReport(self, commissionReport):  # type: ignore[override]
        wire_witness = self._consume_commission_witness(commissionReport)
        exec_id = getattr(commissionReport, "execId", None)
        commission = (commissionReport.commissionAndFees
            if _SDK_COMMISSION_MODERN and type(commissionReport) is _SDKCommissionReport
            else getattr(commissionReport, "commission", None))
        raw_currency = getattr(commissionReport, "currency", None)
        # Bind reception before diagnostics/conversion can interleave a new
        # connection scope. Never label an old callback with a later epoch.
        with self._lock:
            reception = {"client_id": self.client_id,
                "connection_epoch": self._position_connection_epoch,
                "managed_accounts": tuple(self._managed_accounts),
                "connected": self.is_connected(), "stopped": self._stop_event.is_set(),
                "transport_available": self._position_transport_available,
                "received_at": datetime.now(timezone.utc)}
        print(
            "[IBKR][CALLBACK_RAW] "
            f"event=commissionReport exec_id={exec_id} commission={commission}"
        )
        if exec_id is None:
            return
        legacy_amount = None
        conversion_error = None
        if commission is not None:
            try:
                legacy_amount = float(commission)
            except (TypeError, ValueError, OverflowError) as exc:
                conversion_error = exc
        amount = None
        if type(commission) in (int, float, Decimal):
            try:
                amount = Decimal(str(commission))
            except InvalidOperation:
                pass
        currency = raw_currency if isinstance(raw_currency, str) else None
        # Freeze primitive facts BEFORE exposing the mutable SDK report to any
        # listener. Repeated receipts do not renew the original observation.
        with self._lock:
            report = {"amount": amount, "amount_type": type(commission).__name__,
                "currency": currency, **reception, **wire_witness}
            amount_signature = (amount if amount is not None and amount.is_finite()
                else str(amount) if amount is not None else (type(commission).__name__, str(commission)))
            # Receipt scope compares exact types too: bool is numerically equal
            # to 0/1, but cannot stand in for a native identity or availability.
            scope_signature = tuple((type(report[key]), report[key]) for key in (
                "client_id", "connection_epoch", "connected", "stopped", "transport_available"))
            signature = (amount_signature, currency, scope_signature, report["managed_accounts"])
            previous = self._commission_by_exec_id.get(exec_id)
            if isinstance(previous, dict):
                record = {**previous, "latest_report": report,
                    "report_count": previous["report_count"] + 1,
                    "conflict": previous["conflict"] or previous["signature"] != signature}
            else:
                record = {"legacy_amount": previous, "first_report": report, "latest_report": report,
                    "report_count": 1, "conflict": False, "signature": signature,
                    "unscoped_prior": previous is not None}
            if commission is not None and conversion_error is None:
                record["legacy_amount"] = legacy_amount
            self._commission_by_exec_id[exec_id] = record
        self._publish_local_intake("commissionReport",cache="_commission_by_exec_id",execution_id=exec_id)
        if conversion_error is not None:
            raise conversion_error  # Preserve the legacy callback contract.
        if commission is None:
            return
        self._emit_execution_callback(
            {
                "event_type": "commissionReport",
                "execId": exec_id,
                "commission": float(commission),
                "commissionReport": commissionReport,
            }
        )

    def openOrderEnd(self):  # type: ignore[override]
        print("[IBKR][CALLBACK_RAW] event=openOrderEnd")
        self._open_orders_event.set()

    def execDetailsEnd(self, reqId):  # type: ignore[override]
        with self._lock:
            context = getattr(self, "_request_context_by_req_id", {}).get(reqId, {})
            if context.get("request_type") == "EXECUTIONS_STRICT":
                query = context.get("execution_query")
                if query is not None and self._execution_query_current(reqId, query):
                    query["status"] = "COMPLETE"
                    query["completed_at"] = datetime.now(timezone.utc)
                    query["event"].set()
                return
            if self._request_id_conflicted(reqId):
                return
            if getattr(self, "_request_type_by_req_id", {}).get(reqId) != "EXECUTIONS":
                return
            print(f"[IBKR][CALLBACK_RAW] event=execDetailsEnd req_id={reqId}")
            self._executions_event.set()
            getattr(self, "_request_type_by_req_id", {}).pop(reqId, None)

    def position(self, account, contract, pos, avgCost):  # type: ignore[override]
        register_account(account)
        symbol = str(getattr(contract, "symbol", "") or "").upper()
        print(
            "[IBKR][CALLBACK_RAW] "
            f"event=position account_id_redacted=REDACTED symbol={symbol} pos={pos} avg_cost={avgCost}"
        )
        if not symbol:
            return
        self._positions_snapshot[symbol] = SimpleNamespace(
            account=account, contract=contract, symbol=symbol, position=pos, avgCost=avgCost
        )
        self._emit_execution_callback(
            {
                "event_type": "position",
                "account": account,
                "contract": contract,
                "symbol": symbol,
                "position": pos,
                "avgCost": avgCost,
            }
        )

    def positionEnd(self):  # type: ignore[override]
        print("[IBKR][CALLBACK_RAW] event=positionEnd")
        self._positions_event.set()
        self._emit_execution_callback({"event_type": "positionEnd"})

    def connectionClosed(self):  # type: ignore[override]
        self._invalidate_historical_requests()
        self._invalidate_position_queries()
        self._last_disconnect_reason = "connectionClosed"
        self._connection_event.clear()
        print("[IBKR] Connection closed by broker.")


from src.ibkr.mutation_audit import install_sdk, instrument_mutation, delegate_sdk_place_order
install_sdk(EClient, IbkrClient)
_NATIVE_AUDITED_SDK_PLACE_ORDER = EClient.placeOrder
instrument_mutation(IbkrClient, "submit_order")
instrument_mutation(IbkrClient, "placeOrder")


# Outermost wrappers run BEFORE the existing account-registration decorators.
# Bounded constructor-lifetime bookkeeping is always on; policy binding stays
# default off, and ordinary external callback behavior remains unchanged.
for _local_intake_name in (
        "connect", "disconnect", "connectionClosed", "nextValidId", "managedAccounts",
        "register_execution_callback", "register_reconciliation_callback",
        "execDetails", "execDetailsEnd", "orderStatus", "openOrder", "openOrderEnd",
        "error", "commissionReport", "accountSummary", "accountSummaryEnd",
        "position", "positionEnd", "positionMulti", "positionMultiEnd", "completedOrder",
        "completedOrdersEnd", "orderBound", "connectAck", "updateAccountValue", "updatePortfolio",
        "updateAccountTime", "accountDownloadEnd", "accountUpdateMulti", "accountUpdateMultiEnd"):
    _instrument_local_native_intake(IbkrClient, _local_intake_name)
del _local_intake_name

_instrument_local_native_request(IbkrClient,"position_snapshot","POSITIONS_MULTI")
_instrument_local_native_request(IbkrClient, "account_currency_snapshot", "ACCOUNT_CURRENCY_STRICT",
    completion_owner=IbkrClient._strict_account_summary)
_LOCAL_NATIVE_FINGERPRINT_CODES.add(IbkrClient.__setattr__.__code__)
