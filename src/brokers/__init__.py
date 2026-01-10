from .base_broker import BaseBroker, BrokerOrderRequest
from .sim_broker import SimBroker

try:
    from .ibkr_broker import IbkrBroker
    from .ibkr_live_broker import IbkrLiveBroker
except ModuleNotFoundError:  # pragma: no cover - optional dependency missing
    IbkrBroker = None  # type: ignore
    IbkrLiveBroker = None  # type: ignore


def _load_ibkr_broker():
    global IbkrBroker
    if IbkrBroker is None:
        try:
            from .ibkr_broker import IbkrBroker as _IbkrBroker
        except ModuleNotFoundError:  # pragma: no cover - optional dependency missing
            return None
        IbkrBroker = _IbkrBroker
    return IbkrBroker


def _load_ibkr_live_broker():
    global IbkrLiveBroker
    if IbkrLiveBroker is None:
        try:
            from .ibkr_live_broker import IbkrLiveBroker as _IbkrLiveBroker
        except ModuleNotFoundError:  # pragma: no cover - optional dependency missing
            return None
        IbkrLiveBroker = _IbkrLiveBroker
    return IbkrLiveBroker


def __getattr__(name):
    if name == "IbkrBroker":
        broker = _load_ibkr_broker()
        if broker is None:
            print("[BROKERS] ibapi dependency missing; IbkrBroker unavailable.")
        return broker
    if name == "IbkrLiveBroker":
        broker = _load_ibkr_live_broker()
        if broker is None:
            print("[BROKERS] ibapi dependency missing; IbkrLiveBroker unavailable.")
        return broker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["BaseBroker", "BrokerOrderRequest", "SimBroker", "IbkrBroker", "IbkrLiveBroker"]
