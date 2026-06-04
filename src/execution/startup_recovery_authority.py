from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.core.active_trade_registry import ActiveTrade, ActiveTradeRegistry


class RecoveryState(str, Enum):
    RECOVERY_PENDING = "RECOVERY_PENDING"
    RECOVERY_COMPLETE = "RECOVERY_COMPLETE"
    RECOVERY_FAILED = "RECOVERY_FAILED"


@dataclass(frozen=True)
class StartupRecoveryResult:
    state: RecoveryState
    positions_count: int = 0
    orders_count: int = 0
    lifecycle_open_loaded: int = 0
    stops_adopted: int = 0
    targets_reconstructed: int = 0
    protection_findings: int = 0
    reason: str | None = None
    errors: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return self.state == RecoveryState.RECOVERY_COMPLETE


class StartupRecoveryAuthority:
    """Fail-closed startup recovery coordinator for broker-backed trading."""

    def __init__(
        self,
        *,
        run_mode: str,
        provider: Any | None,
        post_fill_lifecycle: Any,
        trade_registry: ActiveTradeRegistry,
        trade_lifecycle_engine: Any | None = None,
    ) -> None:
        self.run_mode = str(run_mode or "SIM").upper()
        self.provider = provider
        self.post_fill_lifecycle = post_fill_lifecycle
        self.trade_registry = trade_registry
        self.trade_lifecycle_engine = trade_lifecycle_engine
        self.state = RecoveryState.RECOVERY_PENDING
        self.result = StartupRecoveryResult(state=self.state, reason="RECOVERY_NOT_RUN")

    def run(self) -> StartupRecoveryResult:
        self.state = RecoveryState.RECOVERY_PENDING
        print("[RECOVERY][START]")
        lifecycle_result = self._load_lifecycle()
        if not bool(lifecycle_result.get("ok", True)) or bool(lifecycle_result.get("degraded", False)):
            return self._fail(
                "LIFECYCLE_RECOVERY_FAILED",
                positions_count=0,
                orders_count=0,
                lifecycle_result=lifecycle_result,
            )

        positions_result = self._load_broker_positions()
        if not positions_result["ok"]:
            return self._fail(
                "BROKER_POSITION_LOAD_FAILED",
                errors=[str(positions_result.get("error") or "")],
                lifecycle_result=lifecycle_result,
            )
        positions = list(positions_result["positions"])
        print(f"[RECOVERY][POSITIONS] count={len(positions)}")

        orders_result = self._load_broker_orders()
        if not orders_result["ok"]:
            return self._fail(
                "BROKER_ORDER_LOAD_FAILED",
                positions_count=len(positions),
                errors=[str(orders_result.get("error") or "")],
                lifecycle_result=lifecycle_result,
            )
        broker_orders = list(orders_result["orders"])
        print(f"[RECOVERY][ORDERS] count={len(broker_orders)}")

        lifecycle_trades = self._open_lifecycle_trades()
        print(
            "[RECOVERY][LIFECYCLE] "
            f"open_loaded={int(lifecycle_result.get('open_loaded', 0) or 0)} "
            f"open_available={len(lifecycle_trades)}"
        )
        lifecycle_symbols = {
            str(getattr(trade, "symbol", "") or "").upper()
            for trade in lifecycle_trades
            if str(getattr(trade, "symbol", "") or "").strip()
        }
        broker_symbols = {
            self._position_symbol(position)
            for position in positions
            if self._position_symbol(position)
        }
        missing_broker_positions = sorted(lifecycle_symbols - broker_symbols)
        if missing_broker_positions:
            return self._fail(
                "LIFECYCLE_BROKER_POSITION_MISMATCH",
                positions_count=len(positions),
                orders_count=len(broker_orders),
                lifecycle_result=lifecycle_result,
                missing_broker_positions=missing_broker_positions,
            )

        startup_summary = self.post_fill_lifecycle.startup_safe_state(
            positions,
            broker_orders,
            lifecycle_trades=lifecycle_trades,
        )

        broker_orders_after_recovery = broker_orders
        if self.provider is not None:
            refreshed_orders = self._load_broker_orders()
            if not refreshed_orders["ok"]:
                return self._fail(
                    "BROKER_ORDER_REFRESH_FAILED",
                    positions_count=len(positions),
                    orders_count=len(broker_orders),
                    errors=[str(refreshed_orders.get("error") or "")],
                    lifecycle_result=lifecycle_result,
                    startup_summary=startup_summary,
                )
            broker_orders_after_recovery = list(refreshed_orders["orders"])

        protection_summary = self.post_fill_lifecycle.reconcile_orders(
            broker_orders_after_recovery,
            repair=True,
        )
        stop_findings = len(protection_summary.get("stop_recovery", []) or [])
        target_count = int(startup_summary.get("target_reconstructed", 0) or 0)
        print(f"[RECOVERY][STOPS] findings={stop_findings}")
        print(f"[RECOVERY][TARGETS] reconstructed={target_count}")

        if startup_summary.get("decision") != "READY":
            return self._fail(
                "RECOVERY_QUARANTINE",
                positions_count=len(positions),
                orders_count=len(broker_orders_after_recovery),
                lifecycle_result=lifecycle_result,
                startup_summary=startup_summary,
                protection_summary=protection_summary,
            )
        if bool(protection_summary.get("block_new_entries", False)):
            return self._fail(
                "PROTECTION_RECONCILIATION_BLOCKED",
                positions_count=len(positions),
                orders_count=len(broker_orders_after_recovery),
                lifecycle_result=lifecycle_result,
                startup_summary=startup_summary,
                protection_summary=protection_summary,
            )

        adopted = self._adopt_broker_positions(positions, lifecycle_trades)
        self.state = RecoveryState.RECOVERY_COMPLETE
        self.result = StartupRecoveryResult(
            state=self.state,
            positions_count=len(positions),
            orders_count=len(broker_orders_after_recovery),
            lifecycle_open_loaded=int(lifecycle_result.get("open_loaded", 0) or 0),
            stops_adopted=int(startup_summary.get("stop_adopted", 0) or 0),
            targets_reconstructed=target_count,
            protection_findings=len(protection_summary.get("findings", []) or []),
            reason="RECOVERY_COMPLETE",
            details={
                "adopted_positions": adopted,
                "lifecycle": lifecycle_result,
                "startup": startup_summary,
                "protection": protection_summary,
            },
        )
        print("[RECOVERY][COMPLETE]")
        return self.result

    def _load_lifecycle(self) -> dict[str, Any]:
        if self.trade_lifecycle_engine is None:
            return {"ok": True, "open_loaded": 0, "degraded": False, "skipped": True}
        try:
            return dict(self.trade_lifecycle_engine.recover_open_state() or {})
        except Exception as exc:
            return {"ok": False, "open_loaded": 0, "degraded": True, "error": str(exc)}

    def _open_lifecycle_trades(self) -> list[Any]:
        if self.trade_lifecycle_engine is None:
            return []
        getter = getattr(self.trade_lifecycle_engine, "get_open_lifecycle_trades", None)
        if callable(getter):
            return list(getter() or [])
        return []

    def _load_broker_positions(self) -> dict[str, Any]:
        if self.provider is None:
            return {"ok": True, "positions": []}
        try:
            snapshot = self.provider.get_positions()
            return {"ok": True, "positions": list(getattr(snapshot, "positions", []) or [])}
        except Exception as exc:
            return {"ok": False, "positions": [], "error": str(exc)}

    def _load_broker_orders(self) -> dict[str, Any]:
        if self.provider is None:
            return {"ok": True, "orders": []}
        try:
            return {"ok": True, "orders": list(self.provider.get_open_orders() or [])}
        except Exception as exc:
            return {"ok": False, "orders": [], "error": str(exc)}

    def _adopt_broker_positions(self, positions: list[Any], lifecycle_trades: list[Any]) -> int:
        lifecycle_by_symbol = {
            str(getattr(trade, "symbol", "") or "").upper(): trade
            for trade in lifecycle_trades
            if str(getattr(trade, "symbol", "") or "").strip()
        }
        adopted = 0
        for position in positions:
            symbol = str(getattr(position, "symbol", "") or "").upper()
            if not symbol:
                contract = getattr(position, "contract", None)
                symbol = str(getattr(contract, "symbol", "") or "").upper()
            quantity = self._position_quantity(position)
            if not symbol or quantity <= 0:
                continue
            lifecycle = lifecycle_by_symbol.get(symbol)
            trader_type = str(getattr(position, "trader_type", "RECOVERY") or "RECOVERY")
            if self.trade_registry.get_trade(symbol, trader_type) is not None:
                continue
            stop_loss_price = self._position_stop(position)
            if stop_loss_price is None and lifecycle is not None:
                stop_loss_price = getattr(lifecycle, "stop_price", None)
            if stop_loss_price is None:
                continue
            entry_price = self._position_entry_price(position)
            if entry_price is None and lifecycle is not None:
                entry_price = getattr(lifecycle, "entry_avg_price", None)
            strategy_name = (
                getattr(position, "strategy_name", None)
                or (getattr(lifecycle, "strategy_name", None) if lifecycle is not None else None)
                or "RECOVERY"
            )
            target_price = (
                getattr(position, "take_profit_price", None)
                or (getattr(lifecycle, "target_price", None) if lifecycle is not None else None)
            )
            recovered_trade = ActiveTrade(
                symbol=symbol,
                trader_type=trader_type,
                entry_tick=int(getattr(position, "entry_tick", 0) or 0),
                entry_price=float(entry_price or 0.0),
                direction=self._position_side(position),
                quantity=quantity,
                strategy_name=str(strategy_name or "RECOVERY"),
                stop_loss_price=float(stop_loss_price),
                take_profit_price=float(target_price) if target_price is not None else None,
                pattern_name=getattr(position, "pattern_name", None),
                invalidation_level=(
                    float(getattr(position, "invalidation_level"))
                    if getattr(position, "invalidation_level", None) is not None
                    else None
                ),
            )
            self.trade_registry.register_trade(recovered_trade)
            adopted += 1
            print(
                "[RECOVERY][RESTORED] "
                f"symbol={symbol} trader_type={trader_type} quantity={quantity}"
            )
        return adopted

    @staticmethod
    def _position_symbol(position: Any) -> str:
        symbol = str(getattr(position, "symbol", "") or "").upper()
        if symbol:
            return symbol
        contract = getattr(position, "contract", None)
        return str(getattr(contract, "symbol", "") or "").upper()

    @staticmethod
    def _position_quantity(position: Any) -> int:
        value = getattr(position, "quantity", None)
        if value is None:
            value = getattr(position, "position", None)
        return abs(int(value or 0))

    @staticmethod
    def _position_side(position: Any) -> str:
        direction = str(getattr(position, "direction", "") or "").upper()
        if direction:
            return "SHORT" if direction in {"SELL", "SHORT"} else "LONG"
        raw = getattr(position, "quantity", None)
        if raw is None:
            raw = getattr(position, "position", 0)
        return "SHORT" if float(raw or 0) < 0 else "LONG"

    @staticmethod
    def _position_entry_price(position: Any) -> float | None:
        value = getattr(position, "entry_price", None)
        if value is None:
            value = getattr(position, "avg_entry_price", None)
        if value is None:
            value = getattr(position, "avgCost", None)
        return float(value) if value is not None else None

    @staticmethod
    def _position_stop(position: Any) -> float | None:
        value = getattr(position, "stop_loss_price", None)
        return float(value) if value is not None else None

    def _fail(
        self,
        reason: str,
        *,
        positions_count: int = 0,
        orders_count: int = 0,
        errors: list[str] | None = None,
        **details: Any,
    ) -> StartupRecoveryResult:
        self.state = RecoveryState.RECOVERY_FAILED
        self.result = StartupRecoveryResult(
            state=self.state,
            positions_count=positions_count,
            orders_count=orders_count,
            reason=reason,
            errors=[error for error in (errors or []) if error],
            details=details,
        )
        print(f"[RECOVERY][FAILED] reason={reason}")
        return self.result


__all__ = [
    "RecoveryState",
    "StartupRecoveryAuthority",
    "StartupRecoveryResult",
]
