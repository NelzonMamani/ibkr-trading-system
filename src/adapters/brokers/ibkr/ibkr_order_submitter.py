from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from src.domain.models.internal_order import InternalOrder
from src.events.event_types import (
    ORDER_SUBMISSION_ATTEMPTED,
    ORDER_SUBMISSION_BLOCKED,
    ORDER_SUBMISSION_FAILED,
    ORDER_SUBMITTED_ACK,
    ORDER_FILL_RECORDED,
)
from src.ibkr.read_only_guard import assert_read_only_allows
from src.config.runtime_config import broker_orders_allowed


@dataclass(frozen=True)
class SubmissionResult:
    client_order_id: str
    ibkr_order_id: Optional[int]
    status: str
    error: Optional[str]
    submitted_at: datetime
    acked_at: Optional[datetime]
    filled_at: Optional[datetime] = None
    filled_quantity: Optional[int] = None
    remaining_quantity: Optional[int] = None
    average_fill_price: Optional[float] = None
    last_fill_price: Optional[float] = None
    fill_status: Optional[str] = None
    commission: Optional[float] = None
    slippage: Optional[float] = None


@dataclass
class OrderSubmissionSettings:
    run_mode: Any
    order_submission_enabled: bool
    kill_switch: bool
    max_orders_per_run: int
    paper_only_enforced: bool
    paper_host: str
    paper_port: int
    live_port: int
    submit_only_symbol: Optional[str]
    ack_timeout_seconds: int
    client_id: int
    submit_only_order_type: str = "MKT"
    allow_shorting: bool = False


class IbkrOrderSubmitter:
    """
    Submit exactly one IBKR paper trade order under strict safety gates.
    """

    SOURCE = "IBKR_ORDER_SUBMITTER"

    def __init__(self, ibkr_client, translator, event_bus, config, guard, logger=None):
        self.ibkr_client = ibkr_client
        self.translator = translator
        self.event_bus = event_bus
        self.config = config
        self.guard = guard
        self.logger = logger

    def submit_once(self, internal_order: InternalOrder) -> SubmissionResult:
        self._log_banner()
        self._log_settings()
        self._log_order(internal_order)

        blocked_reason = self._preflight(internal_order)
        if blocked_reason:
            self._emit_blocked(internal_order, blocked_reason)
            return self._result(internal_order, status="BLOCKED", error=blocked_reason)

        self._log("[TRANSLATE] Translating internal order via IbkrOrderTranslator")
        contract, order = self.translator.translate(internal_order)
        self._log_translation(contract, order)

        host, port = self._resolve_connection()
        self._log(
            f"[CONNECT] Connecting to IBKR gateway host={host} "
            f"port={port} client_id={self.config.client_id}"
        )

        submitted_at = datetime.now(timezone.utc)
        try:
            self.ibkr_client.connect()
        except Exception as exc:
            error = f"IBKR connection failed: {exc}"
            self._log(f"[ERROR] {error}")
            self._emit_failed(internal_order, reason=error, ibkr_order_id=None)
            return self._result(
                internal_order,
                status="FAILED",
                error=error,
                submitted_at=submitted_at,
            )

        try:
            self._emit_attempted(internal_order, ibkr_order_id=None)
            try:
                ibkr_order_id = self.ibkr_client.submit_order(contract, order)
            except Exception as exc:
                error = f"IBKR placeOrder failed: {exc}"
                self._log(f"[ERROR] {error}")
                self._emit_failed(internal_order, reason=error, ibkr_order_id=None)
                return self._result(
                    internal_order,
                    status="FAILED",
                    error=error,
                    submitted_at=submitted_at,
                )

            self.guard.mark_submitted(internal_order.client_order_id)
            self._log(
                f"[GUARD] Submission recorded client_order_id={internal_order.client_order_id} "
                f"submitted_count={self.guard.submitted_count()}"
            )

            ack_status, acked_at = self._wait_for_ack(ibkr_order_id)
            if acked_at:
                self._emit_ack(internal_order, ibkr_order_id, ack_status)
                self._log(
                    f"[ACK] Order acknowledged ibkr_order_id={ibkr_order_id} status={ack_status}"
                )
                fill_payload = self._capture_fill_details(
                    internal_order,
                    ibkr_order_id,
                )
                return self._result(
                    internal_order,
                    status="ACKED",
                    error=None,
                    submitted_at=submitted_at,
                    acked_at=acked_at,
                    ibkr_order_id=ibkr_order_id,
                    **fill_payload,
                )

            reason = "Acknowledgement timeout"
            self._emit_failed(
                internal_order,
                reason=reason,
                ibkr_order_id=ibkr_order_id,
            )
            self._log(f"[TIMEOUT] {reason}")
            return self._result(
                internal_order,
                status="TIMED_OUT",
                error=reason,
                submitted_at=submitted_at,
                acked_at=acked_at,
                ibkr_order_id=ibkr_order_id,
            )
        finally:
            try:
                self.ibkr_client.disconnect()
            except Exception as exc:  # pragma: no cover - defensive
                self._log(f"[WARN] Disconnect raised: {exc}")

    # --- internals ---
    def _preflight(self, internal_order: InternalOrder) -> Optional[str]:
        if not self.config.order_submission_enabled:
            raise RuntimeError("disabled by config")

        if self.config.kill_switch:
            raise RuntimeError("Kill-switch enabled")

        run_mode = getattr(self.config.run_mode, "value", self.config.run_mode)
        normalized_run_mode = str(run_mode).upper()
        if not broker_orders_allowed(normalized_run_mode):
            raise RuntimeError(
                "IBKR submission requires RUN_MODE in {LIVE, LIVE_MICRO, PAPER}"
            )

        if not self.guard.can_submit():
            return "Submission limit reached for this run"

        if self.guard.already_submitted(internal_order.client_order_id):
            return "Duplicate client_order_id detected"

        if self.config.paper_only_enforced and self.config.paper_port == self.config.live_port:
            raise RuntimeError("Live port detected; paper-only enforced")

        if self.config.submit_only_symbol and internal_order.symbol != self.config.submit_only_symbol:
            raise RuntimeError("Symbol not allowed")

        if (
            self.config.submit_only_order_type
            and internal_order.order_type != self.config.submit_only_order_type
        ):
            raise RuntimeError("Only MKT allowed in Step 12.4")

        if not self.config.allow_shorting and internal_order.direction.upper() == "SHORT":
            raise RuntimeError("Shorting is blocked for IBKR submission mode")

        if normalized_run_mode == "LIVE_MICRO" and internal_order.quantity != 1:
            raise RuntimeError("LIVE_MICRO enforces quantity == 1 share")

        # Execution safety guard applies ONLY outside SIM
        if normalized_run_mode != "SIM":
            assert_read_only_allows("PLACE_ORDER")

        return None

    def _wait_for_ack(self, ibkr_order_id: int) -> tuple[Optional[str], Optional[datetime]]:
        status = self.ibkr_client.wait_for_order_status(
            ibkr_order_id, timeout_seconds=self.config.ack_timeout_seconds
        )
        if status is None:
            return None, None
        ack_status = status.get("status")
        return ack_status, datetime.now(timezone.utc)

    def _capture_fill_details(self, internal_order: InternalOrder, ibkr_order_id: int) -> dict:
        status = self.ibkr_client.wait_for_order_status(
            ibkr_order_id, timeout_seconds=self.config.ack_timeout_seconds
        )
        if status is None:
            return {}
        filled = int(status.get("filled", 0) or 0)
        remaining = int(status.get("remaining", 0) or 0)
        avg_fill_price = status.get("avgFillPrice")
        last_fill_price = status.get("lastFillPrice")
        fill_status = "NONE"
        if filled > 0 and remaining == 0:
            fill_status = "FULL"
        elif filled > 0 and remaining > 0:
            fill_status = "PARTIAL"

        commission = self.ibkr_client.commission_for_order(ibkr_order_id)
        slippage = None
        if avg_fill_price is not None and internal_order.limit_price is not None:
            slippage = float(avg_fill_price) - float(internal_order.limit_price)

        fill_payload = {
            "filled_at": datetime.now(timezone.utc),
            "filled_quantity": filled,
            "remaining_quantity": remaining,
            "average_fill_price": avg_fill_price,
            "last_fill_price": last_fill_price,
            "fill_status": fill_status,
            "commission": commission,
            "slippage": slippage,
        }
        self._emit_fill(internal_order, ibkr_order_id, fill_payload)
        self._log(
            "[FILL] ibkr_order_id={oid} status={status} filled={filled} remaining={remaining} "
            "avg_fill_price={avg} last_fill_price={last} commission={commission} slippage={slippage}".format(
                oid=ibkr_order_id,
                status=fill_status,
                filled=filled,
                remaining=remaining,
                avg=avg_fill_price,
                last=last_fill_price,
                commission=commission,
                slippage=slippage,
            )
        )
        return fill_payload

    def _resolve_connection(self) -> tuple[str, int]:
        if hasattr(self.ibkr_client, "host") and hasattr(self.ibkr_client, "port"):
            return self.ibkr_client.host, self.ibkr_client.port
        run_mode = getattr(self.config.run_mode, "value", self.config.run_mode)
        normalized_run_mode = str(run_mode).upper()
        if normalized_run_mode in {"LIVE", "LIVE_MICRO"}:
            return self.config.paper_host, self.config.live_port
        return self.config.paper_host, self.config.paper_port

    def _emit_attempted(self, internal_order: InternalOrder, ibkr_order_id: Optional[int]) -> None:
        payload = self._base_payload(internal_order, ibkr_order_id=ibkr_order_id)
        self.event_bus.emit(
            event_type=ORDER_SUBMISSION_ATTEMPTED,
            source=self.SOURCE,
            payload=payload,
        )

    def _emit_blocked(self, internal_order: InternalOrder, reason: str) -> None:
        payload = self._base_payload(
            internal_order,
            ibkr_order_id=None,
            reason=reason,
        )
        self.event_bus.emit(
            event_type=ORDER_SUBMISSION_BLOCKED,
            source=self.SOURCE,
            payload=payload,
        )

    def _emit_ack(
        self,
        internal_order: InternalOrder,
        ibkr_order_id: Optional[int],
        ack_status: Optional[str],
    ) -> None:
        payload = self._base_payload(
            internal_order,
            ibkr_order_id=ibkr_order_id,
        )
        payload["ack_status"] = ack_status
        self.event_bus.emit(
            event_type=ORDER_SUBMITTED_ACK,
            source=self.SOURCE,
            payload=payload,
        )

    def _emit_fill(
        self,
        internal_order: InternalOrder,
        ibkr_order_id: Optional[int],
        fill_payload: dict,
    ) -> None:
        payload = self._base_payload(
            internal_order,
            ibkr_order_id=ibkr_order_id,
        )
        payload.update(
            {
                "filled_quantity": fill_payload.get("filled_quantity"),
                "remaining_quantity": fill_payload.get("remaining_quantity"),
                "average_fill_price": fill_payload.get("average_fill_price"),
                "last_fill_price": fill_payload.get("last_fill_price"),
                "fill_status": fill_payload.get("fill_status"),
                "commission": fill_payload.get("commission"),
                "slippage": fill_payload.get("slippage"),
            }
        )
        self.event_bus.emit(
            event_type=ORDER_FILL_RECORDED,
            source=self.SOURCE,
            payload=payload,
        )

    def _emit_failed(
        self,
        internal_order: InternalOrder,
        reason: str,
        ibkr_order_id: Optional[int],
    ) -> None:
        payload = self._base_payload(
            internal_order,
            ibkr_order_id=ibkr_order_id,
            reason=reason,
        )
        self.event_bus.emit(
            event_type=ORDER_SUBMISSION_FAILED,
            source=self.SOURCE,
            payload=payload,
        )

    def _base_payload(
        self,
        internal_order: InternalOrder,
        ibkr_order_id: Optional[int],
        reason: Optional[str] = None,
    ) -> dict[str, Any]:
        payload = {
            "client_order_id": internal_order.client_order_id,
            "symbol": internal_order.symbol,
            "direction": internal_order.direction,
            "quantity": internal_order.quantity,
            "order_type": internal_order.order_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ibkr_order_id": ibkr_order_id,
        }
        if reason is not None:
            payload["reason"] = reason
        return payload

    def _result(
        self,
        internal_order: InternalOrder,
        status: str,
        error: Optional[str],
        submitted_at: Optional[datetime] = None,
        acked_at: Optional[datetime] = None,
        ibkr_order_id: Optional[int] = None,
        filled_at: Optional[datetime] = None,
        filled_quantity: Optional[int] = None,
        remaining_quantity: Optional[int] = None,
        average_fill_price: Optional[float] = None,
        last_fill_price: Optional[float] = None,
        fill_status: Optional[str] = None,
        commission: Optional[float] = None,
        slippage: Optional[float] = None,
    ) -> SubmissionResult:
        return SubmissionResult(
            client_order_id=internal_order.client_order_id,
            ibkr_order_id=ibkr_order_id,
            status=status,
            error=error,
            submitted_at=submitted_at or datetime.now(timezone.utc),
            acked_at=acked_at,
            filled_at=filled_at,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            average_fill_price=average_fill_price,
            last_fill_price=last_fill_price,
            fill_status=fill_status,
            commission=commission,
            slippage=slippage,
        )

    def _log_banner(self) -> None:
        run_mode = getattr(self.config.run_mode, "value", self.config.run_mode)
        self._log(
            "IBKR SUBMISSION MODE — SINGLE ORDER — KILL SWITCH AVAILABLE "
            f"(run_mode={run_mode})"
        )

    def _log_settings(self) -> None:
        self._log(
            f"[SETTINGS] run_mode={getattr(self.config.run_mode, 'value', self.config.run_mode)} "
            f"enabled={self.config.order_submission_enabled} kill_switch={self.config.kill_switch} "
            f"paper_only_enforced={self.config.paper_only_enforced} max_orders_per_run={self.config.max_orders_per_run}"
        )
        self._log(
            f"[SETTINGS] paper_host={self.config.paper_host} paper_port={self.config.paper_port} "
            f"live_port={self.config.live_port} client_id={self.config.client_id}"
        )

    def _log_order(self, internal_order: InternalOrder) -> None:
        self._log(
            "[ORDER] client_order_id="
            f"{internal_order.client_order_id} symbol={internal_order.symbol} "
            f"direction={internal_order.direction} quantity={internal_order.quantity} "
            f"order_type={internal_order.order_type} tif={internal_order.time_in_force}"
        )

    def _log_translation(self, contract, order) -> None:
        self._log(
            f"[TRANSLATED] Contract symbol={getattr(contract, 'symbol', None)} "
            f"exchange={getattr(contract, 'exchange', None)} currency={getattr(contract, 'currency', None)} "
            f"secType={getattr(contract, 'secType', None)}"
        )
        order_log = (
            f"[TRANSLATED] Order action={getattr(order, 'action', None)} "
            f"orderType={getattr(order, 'orderType', None)} "
            f"totalQuantity={getattr(order, 'totalQuantity', None)} "
            f"tif={getattr(order, 'tif', None)}"
        )
        lmt_price = getattr(order, "lmtPrice", None)
        if lmt_price is not None:
            order_log += f" lmtPrice={lmt_price}"
        self._log(order_log)

    def _log(self, message: str) -> None:
        if self.logger is None:
            print(message)
            return
        if hasattr(self.logger, "info"):
            self.logger.info(message)
        else:  # pragma: no cover - fallback
            print(message)
