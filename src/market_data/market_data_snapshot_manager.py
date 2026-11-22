from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from collections.abc import Mapping
import math
import time
from typing import Iterable, Optional, TYPE_CHECKING

from src.config.runtime_config import get_ibkr_snapshot_max_age_seconds
from src.core.acquisition import AcquisitionCancelled, AcquisitionDeadlineExceeded, acquisition_deadline, checkpoint
from src.domain.market_snapshot import MarketSnapshot
from src.domain.quote_freshness import quote_time_rejection
from src.ibkr.position_snapshot import BrokerPositionResult
from src.ibkr.market_data_client import MarketDataClient, MarketDataSnapshot


if TYPE_CHECKING:
    from src.adapters.brokers.ibkr.ibkr_client import AccountCapitalResult


@dataclass(frozen=True)
class SnapshotQuality:
    symbol: str
    missing_fields: list[str]
    data_quality_flags: list[str]


@dataclass(frozen=True)
class HeldContractMark:
    account: str
    con_id: int
    symbol: str
    currency: str
    signed_quantity: Decimal
    price: Decimal
    gross_value: Decimal
    request_id: int
    market_timestamp: datetime
    completed_at: datetime
    source: str


@dataclass(frozen=True)
class HeldContractValuation:
    status: str
    positions_before: datetime | None = None
    positions_after: datetime | None = None
    client_id: int | None = None
    connection_epoch: int | None = None
    account_scope_generation: int | None = None
    marks: tuple[HeldContractMark, ...] = ()
    capital: AccountCapitalResult | None = None


class MarketDataSnapshotManager:
    """Deterministic snapshot capture with data-quality flags."""

    def __init__(
        self,
        market_data_client: MarketDataClient | None,
        *,
        max_workers: int = 5,
    ) -> None:
        self.market_data_client = market_data_client
        self.max_workers = max_workers

    def get_snapshot(self, symbol: str, *, expected_client=None,
                     expected_connection_epoch=None, single_attempt=False,
                     require_complete=False) -> tuple[MarketSnapshot, SnapshotQuality]:
        if type(single_attempt) is not bool or type(require_complete) is not bool:
            raise ValueError("Snapshot completion and attempt options must be boolean")
        if require_complete and not single_attempt:
            raise ValueError("Required snapshot completion requires a bound single attempt")
        if single_attempt and (expected_client is None or expected_connection_epoch is None):
            raise RuntimeError("Single-attempt snapshot requires original client scope")
        if self.market_data_client is None:
            snapshot = MarketSnapshot(
                symbol=symbol,
                bid=None,
                ask=None,
                last=None,
                volume=None,
                asof_utc=datetime.now(timezone.utc),
                market_data_type="UNKNOWN",
                source="SIM",
            )
            quality = SnapshotQuality(
                symbol=symbol,
                missing_fields=["last", "close", "volume"],
                data_quality_flags=["MD_UNAVAILABLE"],
            )
            self._log_quality(quality)
            return snapshot, quality
        options = {"single_attempt": True} if single_attempt else {}
        if require_complete:
            options["require_complete"] = True
        raw = (self.market_data_client.snapshot_stock(symbol) if
            expected_client is None and expected_connection_epoch is None else
            self.market_data_client.snapshot_stock(symbol, expected_client=expected_client,
                expected_connection_epoch=expected_connection_epoch, **options))
        snapshot, quality = self._translate_snapshot(raw)
        self._log_quality(quality)
        return snapshot, quality

    def value_held_contracts(self, client, *, expected_account: str) -> HeldContractValuation:
        """All-or-nothing same-currency gross marks; this does not enroll holdings."""
        from src.adapters.brokers.ibkr.ibkr_client import AccountCapitalResult

        if self.market_data_client is None:
            return HeldContractValuation("QUOTE_SOURCE_UNAVAILABLE")
        currency = "USD"
        max_age = get_ibkr_snapshot_max_age_seconds()

        def scope():
            with client._lock:
                if (not client.is_connected() or client._stop_event.is_set()
                        or not client._position_transport_available
                        or tuple(client._managed_accounts) != (expected_account,)):
                    return None
                return (client.client_id, client._position_connection_epoch,
                        getattr(client, "_managed_accounts_generation", 0))

        def fresh(stamp, now):
            return (isinstance(stamp, datetime) and stamp.tzinfo is not None
                    and 0 <= (now - stamp).total_seconds() <= max_age)

        def rows(snapshot, now):
            if (not isinstance(snapshot, BrokerPositionResult) or snapshot.status != "COMPLETE"
                    or snapshot.account != expected_account or not fresh(snapshot.completed_at, now)):
                return None
            positions = {}
            symbols = set()
            for row in snapshot.rows:
                contract = row.contract
                con_id = contract.conId
                symbol = row.symbol
                raw = row.position
                if (row.account != expected_account or type(con_id) is not int or con_id <= 0
                        or not isinstance(symbol, str) or not symbol or symbol != contract.symbol
                        or contract.secType != "STK" or contract.currency != currency
                        or con_id in positions or symbol in symbols or type(raw) not in (int, float, Decimal)):
                    return None
                quantity = Decimal(str(raw))
                if not quantity.is_finite():
                    return None
                symbols.add(symbol)
                positions[con_id] = (symbol, quantity)
            return positions

        try:
            checkpoint()
            initial_scope = scope()
            if initial_scope is None:
                return HeldContractValuation("CAPITAL_SCOPE_UNAVAILABLE")
            client_id, epoch, generation = initial_scope
            before = client.position_snapshot()
            monotonic_now = time.monotonic()
            now = datetime.now(timezone.utc)
            positions = rows(before, now)
            if positions is None:
                return HeldContractValuation("POSITIONS_UNQUALIFIED")
            if scope() != initial_scope:
                return HeldContractValuation("SCOPE_CHANGED")
            symbols = [symbol for symbol, quantity in positions.values() if quantity]
            if len(symbols) > max(self.max_workers, 1):
                return HeldContractValuation("COHORT_EXCEEDS_CAPACITY")
            bracket_deadline = monotonic_now + max_age - (now - before.completed_at).total_seconds()
            with acquisition_deadline(bracket_deadline):
                quotes, qualities = self.batch_snapshots(
                    symbols,
                    expected_client=client, expected_connection_epoch=epoch,
                    single_attempt=True, require_complete=True)
                marks = []
                for con_id, (symbol, quantity) in positions.items():
                    if not quantity:
                        continue
                    quote = self.clean_snapshot(quotes, qualities, symbol)
                    if quote is None:
                        return HeldContractValuation("MARK_UNQUALIFIED")
                    now = datetime.now(timezone.utc)
                    completed = (datetime.fromisoformat(quote.snapshot_completed_at_utc)
                                 if quote.snapshot_completed_at_utc else None)
                    if (quote.con_id != con_id or type(quote.con_id) is not int
                            or quote.client_id != client_id
                            or quote.connection_epoch != epoch
                            or type(quote.request_id) is not int or quote.request_id <= 0
                            or quote.market_data_type_confirmed is not True
                            or quote.returned_market_data_type != "LIVE" or quote.snapshot_complete is not True
                            or quote.completion_reason != "snapshot_end" or quote.broker_errors
                            or quote.field_availability.get("last") is not True
                            or quote_time_rejection(quote.market_timestamp_utc, quote.timestamp_source, now=now)
                            or not fresh(completed, now) or completed < before.completed_at
                            or quote.market_timestamp_utc > completed):
                        return HeldContractValuation("MARK_UNQUALIFIED")
                    price = Decimal(str(quote.last))
                    with localcontext() as context:
                        context.prec = len(price.as_tuple().digits) + len(quantity.as_tuple().digits)
                        gross = abs(quantity) * price
                    if not gross.is_finite() or gross <= 0:
                        return HeldContractValuation("MARK_UNQUALIFIED")
                    marks.append(HeldContractMark(expected_account, con_id, symbol, currency, quantity, price, gross,
                        quote.request_id, quote.market_timestamp_utc, completed, quote.source))
                if scope() != initial_scope:
                    return HeldContractValuation("POSITIONS_OR_SCOPE_CHANGED")
                capital = client.account_capital_snapshot(expected_account=expected_account)
                if (not isinstance(capital, AccountCapitalResult) or capital.status != "COMPLETE"
                        or capital.account != expected_account
                        or (capital.client_id, capital.connection_epoch, capital.account_scope_generation) != initial_scope):
                    return HeldContractValuation("CAPITAL_SCOPE_UNAVAILABLE")
                if capital.currency_evidence.currency != currency:
                    return HeldContractValuation("UNSUPPORTED_CURRENCY")
                if scope() != initial_scope:
                    return HeldContractValuation("POSITIONS_OR_SCOPE_CHANGED")
                after = client.position_snapshot()
                now = datetime.now(timezone.utc)
                if (rows(after, now) != positions or scope() != initial_scope
                        or not fresh(before.completed_at, now) or after.completed_at < before.completed_at
                        or any(mark.completed_at > after.completed_at for mark in marks)):
                    return HeldContractValuation("POSITIONS_OR_SCOPE_CHANGED")
                if not fresh(capital.completed_at, now) or not fresh(capital.currency_evidence.completed_at, now):
                    return HeldContractValuation("CAPITAL_SCOPE_UNAVAILABLE")
                if any(not fresh(mark.market_timestamp, now) or not fresh(mark.completed_at, now) for mark in marks):
                    return HeldContractValuation("MARK_STALE")
                return HeldContractValuation("COMPLETE", before.completed_at, after.completed_at, client_id,
                    epoch, generation, tuple(marks), capital)
        except AcquisitionDeadlineExceeded:
            checkpoint()  # A shorter caller deadline remains control flow.
            return HeldContractValuation("EVIDENCE_WINDOW_EXPIRED")
        except AcquisitionCancelled:
            raise
        except (AttributeError, TypeError, RuntimeError, ValueError, OverflowError, InvalidOperation):
            return HeldContractValuation("EVIDENCE_UNAVAILABLE")

    def batch_snapshots(
        self,
        symbols: Iterable[str],
        *, expected_client=None, expected_connection_epoch=None,
        single_attempt=False, require_complete=False,
    ) -> tuple[dict[str, MarketSnapshot], dict[str, SnapshotQuality]]:
        resolved_symbols = [symbol for symbol in symbols if symbol]
        snapshots: dict[str, MarketSnapshot] = {}
        quality_by_symbol: dict[str, SnapshotQuality] = {}
        if not resolved_symbols:
            return snapshots, quality_by_symbol
        max_workers = min(max(self.max_workers, 1), len(resolved_symbols))
        scope = ({} if expected_client is None and expected_connection_epoch is None else
                 {"expected_client": expected_client, "expected_connection_epoch": expected_connection_epoch})
        if single_attempt:
            scope["single_attempt"] = True
        if require_complete:
            scope["require_complete"] = True
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {}
            for symbol in resolved_symbols:
                future = (executor.submit(copy_context().run, self.get_snapshot, symbol, **scope)
                          if require_complete else executor.submit(self.get_snapshot, symbol, **scope))
                future_map[future] = symbol
            for future in as_completed(future_map):
                symbol = future_map[future]
                try:
                    snapshot, quality = future.result()
                except Exception as exc:
                    if require_complete:
                        raise
                    print(f"[SNAPSHOT][ERROR] symbol={symbol} error={exc}")
                    snapshot = MarketSnapshot(
                        symbol=symbol,
                        bid=None,
                        ask=None,
                        last=None,
                        volume=None,
                        asof_utc=datetime.now(timezone.utc),
                        market_data_type="UNKNOWN",
                        source="IBKR",
                    )
                    quality = SnapshotQuality(
                        symbol=symbol,
                        missing_fields=["last", "close", "volume"],
                        data_quality_flags=["SNAPSHOT_ERROR"],
                    )
                    self._log_quality(quality)
                snapshots[symbol] = snapshot
                quality_by_symbol[symbol] = quality
        return snapshots, quality_by_symbol

    @staticmethod
    def clean_snapshot(snapshots, quality_by_symbol, symbol):
        """Select one complete per-symbol result; a quality map is not an error list."""
        if not isinstance(snapshots, Mapping) or not isinstance(quality_by_symbol, Mapping):
            return None
        snapshot, quality = snapshots.get(symbol), quality_by_symbol.get(symbol)
        if (not isinstance(quality, SnapshotQuality) or quality.symbol != symbol
                or getattr(snapshot, "symbol", None) != symbol
                or not isinstance(quality.missing_fields, (list, tuple)) or quality.missing_fields
                or not isinstance(quality.data_quality_flags, (list, tuple)) or quality.data_quality_flags
                or not isinstance(getattr(snapshot, "data_quality_flags", None), (list, tuple))
                or snapshot.data_quality_flags):
            return None
        try:
            for name in ("bid", "ask", "last", "close", "volume"):
                value = getattr(snapshot, name, None)
                if (isinstance(value, bool) or not math.isfinite(value)
                        or (value < 0 if name == "volume" else value <= 0)):
                    return None
        except (TypeError, ValueError, OverflowError):
            return None
        return snapshot

    @staticmethod
    def _translate_snapshot(
        raw: MarketDataSnapshot,
    ) -> tuple[MarketSnapshot, SnapshotQuality]:
        missing_fields: list[str] = []
        if raw.last is None:
            missing_fields.append("last")
        if raw.bid is None:
            missing_fields.append("bid")
        if raw.ask is None:
            missing_fields.append("ask")
        if raw.close is None:
            missing_fields.append("close")
        if raw.volume is None:
            missing_fields.append("volume")
        data_quality_flags = list(raw.data_quality_flags or [])
        if raw.bid is None or raw.ask is None:
            data_quality_flags.append("SPREAD_UNKNOWN")
        snapshot_last = raw.last if raw.last is not None else raw.close
        confirmed = raw.market_data_type_confirmed is True and raw.returned_market_data_type in {
            "LIVE", "FROZEN", "DELAYED", "DELAYED_FROZEN",
        }
        returned_type = raw.returned_market_data_type if confirmed else "UNKNOWN"
        def timestamp(value):
            return datetime.fromisoformat(value) if value is not None else None
        snapshot = MarketSnapshot(
            symbol=raw.symbol,
            bid=raw.bid,
            ask=raw.ask,
            last=snapshot_last,
            volume=raw.volume,
            asof_utc=datetime.now(timezone.utc),
            market_data_type=returned_type,
            returned_market_data_type=returned_type,
            market_data_type_confirmed=confirmed,
            requested_market_data_type=raw.requested_market_data_type,
            market_timestamp_utc=timestamp(raw.timestamp_utc),
            received_at_utc=timestamp(raw.received_at_utc),
            market_data_type_received_at_utc=timestamp(raw.market_data_type_received_at_utc),
            timestamp_source=raw.timestamp_source,
            request_id=raw.request_id,
            snapshot_complete=raw.snapshot_complete,
            market_data_type_confirmation_source=(raw.market_data_type_confirmation_source if confirmed else "UNKNOWN"),
            data_quality_flags=tuple(data_quality_flags),
            **{name: getattr(raw, name) for name in (
                "request_started_at_utc", "request_completed_at_utc", "snapshot_completed_at_utc",
                "completion_reason", "field_availability", "field_received_at_utc",
                "missing_fields_observed_at_utc", "broker_errors", "close", "open", "high", "low",
                "bid_size", "ask_size", "last_size",
            )},
            source="IBKR",
            **{name: getattr(raw, name, None) for name in ("con_id", "client_id", "connection_epoch")},
        )
        quality = SnapshotQuality(
            symbol=raw.symbol,
            missing_fields=missing_fields,
            data_quality_flags=data_quality_flags,
        )
        return snapshot, quality

    @staticmethod
    def _log_quality(quality: SnapshotQuality) -> None:
        if not quality.missing_fields and not quality.data_quality_flags:
            return
        print(
            "[SNAPSHOT][QUALITY] "
            f"symbol={quality.symbol} missing={quality.missing_fields} "
            f"flags={quality.data_quality_flags}"
        )
