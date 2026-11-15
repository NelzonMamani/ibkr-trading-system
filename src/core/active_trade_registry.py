from dataclasses import dataclass, field, fields
from functools import wraps
import sys
from threading import get_ident
from typing import List, Optional

from src.core.position_lifecycle_engine import (
    LifecycleTransitionError,
    PositionState,
    is_transition_allowed,
    normalize_state,
)


@dataclass
class ActiveTrade:
    symbol: str
    trader_type: str
    entry_tick: int
    entry_price: float
    direction: str = "UNKNOWN"
    quantity: int = 1
    strategy_name: str = "UNKNOWN"
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    pattern_name: Optional[str] = None
    invalidation_level: Optional[float] = None
    state: PositionState = PositionState.FLAT
    state_history: List[dict] = field(default_factory=list)
    close_tick: Optional[int] = None
    close_price: Optional[float] = None
    realised_pnl: Optional[float] = None

    def hold_duration(self, current_tick: int) -> int:
        """Return how many ticks this trade has been held so far."""

        return max(0, current_tick - self.entry_tick)

    def transition_state(
        self,
        new_state: PositionState | str,
        tick: int,
        reason: str,
        reason_code: str = "UNSPECIFIED",
    ) -> None:
        target_state = normalize_state(new_state)
        current_state = normalize_state(self.state)
        if target_state == current_state:
            return
        if current_state == PositionState.CLOSED:
            raise LifecycleTransitionError(
                "STATE_IMMUTABLE",
                "Closed positions are immutable.",
            )
        if not is_transition_allowed(current_state, target_state):
            raise LifecycleTransitionError(
                "INVALID_TRANSITION",
                f"Invalid trade state transition {current_state.value} -> {target_state.value}",
            )
        self.state_history.append(
            {
                "from": current_state.value,
                "to": target_state.value,
                "tick": tick,
                "reason": reason,
                "reason_code": reason_code,
            }
        )
        self.state = target_state


class ActiveTradeRegistry:
    """
    Central registry tracking active trades by symbol and trader type.
    Teaching-first, in-memory only.
    """

    def __init__(self):
        reused = hasattr(self, "_p02_local_pristine")
        if getattr(self, "_p02_local_authority", None) is not None:
            _p02_taint_owner(self, "P02_LOCAL_REGISTRY_REINITIALIZED")
            raise RuntimeError("P02_LOCAL_REGISTRY_OWNER_UNAVAILABLE")
        self._active_trades: List[ActiveTrade] = []
        self._p02_local_authority = None
        self._p02_local_revision = 0
        self._p02_local_pristine = not reused
        self._p02_local_supported = True

    def bind_p02_local_authority(self, authority) -> None:
        """Bind only this constructor-created, unused empty local owner."""
        from src.execution.execution_engine import ExecutionEngine
        if (type(self) is not ActiveTradeRegistry or type(authority) is not ExecutionEngine
                or getattr(authority, "trade_registry", None) is not self
                or getattr(authority, "_p02_local", None) is None
                or getattr(self, "_p02_local_authority", None) is not None
                or getattr(self, "_p02_local_pristine", None) is not True
                or getattr(self, "_p02_local_supported", None) is not True
                or type(getattr(self, "_active_trades", None)) is not list
                or self._active_trades
                or not _p02_exact_methods(self, _P02_REGISTRY_METHODS)):
            raise RuntimeError("P02_LOCAL_REGISTRY_OWNER_UNAVAILABLE")
        self._p02_local_authority = authority
        self._p02_local_pristine = False

    def _p02_local_source_frame(self):
        authority = self._p02_local_authority
        if authority is None or _p02_original_frame(self, sys._getframe(1).f_code) is None:
            raise RuntimeError("P02_LOCAL_REGISTRY_FRAME_UNAVAILABLE")
        try:
            if type(self._active_trades) is not list:
                raise _P02UnsupportedValue("P02_LOCAL_CUSTOM_REGISTRY_STATE")
            _p02_copy_value(self._active_trades, (ActiveTrade,), (PositionState,))
        except _P02UnsupportedValue:
            _p02_taint_owner(self, "P02_LOCAL_UNSUPPORTED_REGISTRY_VALUE")
        return dict(owner=self, revision=self._p02_local_revision,
            supported=self._p02_local_supported and _p02_exact_methods(self, _P02_REGISTRY_METHODS),
            trades=self._active_trades)

    def register_trade(self, active_trade: ActiveTrade):
        if self._p02_local_authority is not None:
            # Even an original execution caller can retain its registration input.
            active_trade = _p02_copy_or_taint(self, active_trade, (ActiveTrade,), (PositionState,))
        if getattr(active_trade, "quantity", 0) <= 0:
            raise ValueError("Cannot register a trade with non-positive quantity.")
        if getattr(active_trade, "stop_loss_price", None) is None:
            raise ValueError(
                "Protective stop required; cannot register trade without stop_loss_price."
            )
        print(
            "[REGISTRY] REGISTER "
            f"symbol={active_trade.symbol} "
            f"trader_type={active_trade.trader_type} "
            f"entry_tick={active_trade.entry_tick} "
            f"entry_price={active_trade.entry_price} "
            f"direction={active_trade.direction} "
            f"quantity={active_trade.quantity} "
            f"strategy={active_trade.strategy_name}"
        )
        if active_trade.state != PositionState.OPEN:
            active_trade.transition_state(
                PositionState.OPEN,
                tick=active_trade.entry_tick,
                reason="Trade opened",
                reason_code="OPEN_INTENT_ACCEPTED",
            )
        self._active_trades.append(active_trade)

    def unregister_trade(self, symbol: str, trader_type: str):
        print(f"[REGISTRY] UNREGISTER symbol={symbol} trader_type={trader_type}")
        self._active_trades = [
            t for t in self._active_trades
            if not (t.symbol == symbol and t.trader_type == trader_type)
        ]

    def get_trade(self, symbol: str, trader_type: str) -> Optional[ActiveTrade]:
        for trade in self._active_trades:
            if trade.symbol == symbol and trade.trader_type == trader_type:
                return trade
        return None

    def mark_closed(
        self,
        symbol: str,
        trader_type: str,
        close_tick: int,
        close_price: float,
        realised_pnl: float,
    ):
        trade = self.get_trade(symbol, trader_type)
        if trade is None:
            return
        trade.close_tick = close_tick
        trade.close_price = close_price
        trade.realised_pnl = realised_pnl
        print(
            "[REGISTRY] MARK_CLOSED "
            f"symbol={symbol} "
            f"trader_type={trader_type} "
            f"close_tick={close_tick} "
            f"close_price={close_price} "
            f"realised_pnl={realised_pnl}"
        )

    def count_active_by_trader(self, trader_type: str) -> int:
        return len(
            [t for t in self._active_trades if t.trader_type == trader_type]
        )

    def count_active(self) -> int:
        return len(self._active_trades)

    def snapshot(self):
        return list(self._active_trades)

    def close_all_trades(self):
        """
        Teaching-first lifecycle reset.
        Closes all active trades deterministically.
        """
        closed = list(self._active_trades)
        self._active_trades.clear()
        return closed

    def verify_empty(self) -> bool:
        """
        Teaching-first integrity check to confirm registry state on shutdown.
        """

        active_count = len(self._active_trades)
        if active_count == 0:
            print("[REGISTRY] Verification passed — no active trades remain.")
            return True
        print(
            "[REGISTRY] Verification failed — active trades remain at shutdown: "
            f"{active_count}"
        )
        return False


class _P02UnsupportedValue(TypeError):
    pass


_P02_COPY_IN_PROGRESS = object()


def _p02_copy_value(value, dataclass_types=(), enum_types=(), memo=None):
    """Copy an exact field allowlist, without user copy/reduce/property hooks."""
    kind = type(value)
    if value is None or kind in (bool, int, float, str, bytes) or kind in enum_types:
        return value
    memo = {} if memo is None else memo
    if id(value) in memo:
        if memo[id(value)] is _P02_COPY_IN_PROGRESS:
            raise _P02UnsupportedValue("P02_LOCAL_UNSUPPORTED_VALUE_CYCLE")
        return memo[id(value)]
    if kind is list:
        result = []
        memo[id(value)] = _P02_COPY_IN_PROGRESS
        result.extend(_p02_copy_value(item, dataclass_types, enum_types, memo) for item in value)
        memo[id(value)] = result
        return result
    if kind is dict:
        result = {}
        memo[id(value)] = _P02_COPY_IN_PROGRESS
        for key, item in value.items():
            if type(key) not in (bool, int, float, str, bytes) and key is not None:
                raise _P02UnsupportedValue("P02_LOCAL_CUSTOM_MAPPING_KEY")
            result[key] = _p02_copy_value(item, dataclass_types, enum_types, memo)
        memo[id(value)] = result
        return result
    if kind is tuple:
        # Cyclic tuples and custom tuple subclasses are deliberately unsupported.
        memo[id(value)] = _P02_COPY_IN_PROGRESS
        result = tuple(_p02_copy_value(item, dataclass_types, enum_types, memo) for item in value)
        memo[id(value)] = result
        return result
    if kind in (set, frozenset):
        result = kind(_p02_copy_value(item, dataclass_types, enum_types, memo) for item in value)
        memo[id(value)] = result
        return result
    if kind in dataclass_types:
        names = tuple(item.name for item in fields(kind))
        raw = object.__getattribute__(value, "__dict__")
        if type(raw) is not dict or set(raw) != set(names):
            raise _P02UnsupportedValue("P02_LOCAL_CUSTOM_DATACLASS_FIELDS")
        result = object.__new__(kind)
        memo[id(value)] = _P02_COPY_IN_PROGRESS
        for name in names:
            object.__setattr__(result, name,
                _p02_copy_value(raw[name], dataclass_types, enum_types, memo))
        memo[id(value)] = result
        return result
    raise _P02UnsupportedValue("P02_LOCAL_CUSTOM_VALUE")


def _p02_taint_owner(owner, reason):
    owner._p02_local_supported = False
    owner._p02_local_authority._p02_invalidate(reason)


def _p02_copy_or_taint(owner, value, dataclass_types=(), enum_types=(), *, refuse=False):
    try:
        return _p02_copy_value(value, dataclass_types, enum_types)
    except _P02UnsupportedValue:
        # Existing factual processing remains available, but this source can no
        # longer support a local observation, before an unknown alias escapes.
        _p02_taint_owner(owner, "P02_LOCAL_UNSUPPORTED_OWNER_VALUE")
        if refuse:
            raise RuntimeError("P02_LOCAL_UNSUPPORTED_OWNER_VALUE") from None
        return value


def _p02_exact_methods(owner, expected):
    raw = object.__getattribute__(owner, "__dict__")
    return all(name not in raw and type(owner).__dict__.get(name) is method
        for name, method in expected.items())


def _p02_original_frame(owner, caller_code):
    authority = owner._p02_local_authority
    state = getattr(authority, "_p02_local", None)
    if state is None or caller_code not in state["source_codes"]:
        return None
    frame = state["frame_context"].get()
    return frame if (frame is not None and frame is state["frame"]
        and state["frame_thread"] == get_ident() and state["gate"].locked()) else None


def _p02_registry_method(method, *, mutation=False):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        authority = getattr(self, "_p02_local_authority", None)
        if authority is None:
            self._p02_local_pristine = False
            return method(self, *args, **kwargs)
        parent = _p02_original_frame(self, sys._getframe(1).f_code)
        if not _p02_exact_methods(self, _P02_REGISTRY_METHODS):
            _p02_taint_owner(self, "P02_LOCAL_CUSTOM_REGISTRY_OWNER")
        if mutation:
            with authority._p02_owner_mutation(self, method.__name__, parent_frame=parent):
                if parent is None:
                    args, kwargs = _p02_copy_or_taint(self, (args, kwargs), (ActiveTrade,), (PositionState,))
                result = method(self, *args, **kwargs)
                return _p02_copy_or_taint(self, result, (ActiveTrade,), (PositionState,), refuse=True) if parent is None else result
        if parent is not None:
            return method(self, *args, **kwargs)
        state = authority._p02_local
        if not state["gate"].acquire(blocking=False):
            raise RuntimeError("P02_LOCAL_OWNER_BUSY")
        try:
            args, kwargs = _p02_copy_or_taint(self, (args, kwargs), (ActiveTrade,), (PositionState,))
            return _p02_copy_or_taint(self, method(self, *args, **kwargs), (ActiveTrade,), (PositionState,), refuse=True)
        finally:
            state["gate"].release()
    return wrapped


for _p02_name in ("register_trade", "unregister_trade", "mark_closed", "close_all_trades"):
    setattr(ActiveTradeRegistry, _p02_name,
        _p02_registry_method(getattr(ActiveTradeRegistry, _p02_name), mutation=True))
for _p02_name in ("get_trade", "snapshot", "count_active_by_trader", "count_active", "verify_empty"):
    setattr(ActiveTradeRegistry, _p02_name,
        _p02_registry_method(getattr(ActiveTradeRegistry, _p02_name)))
_P02_REGISTRY_METHODS = {name: method for name, method in ActiveTradeRegistry.__dict__.items()
    if callable(method)}
