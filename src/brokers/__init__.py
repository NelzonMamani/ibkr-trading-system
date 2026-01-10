from __future__ import annotations

import sys
import types
from typing import Optional

from .base_broker import BaseBroker, BrokerOrderRequest
from .sim_broker import SimBroker

IbkrBroker: Optional[type] = None
IbkrLiveBroker: Optional[type] = None


def _load_ibkr_broker() -> Optional[type]:
    global IbkrBroker
    if IbkrBroker is not None:
        return IbkrBroker
    try:
        from .ibkr_broker import IbkrBroker as _IbkrBroker
    except ModuleNotFoundError:  # pragma: no cover - optional dependency missing
        print("[BROKERS] ibapi dependency missing; IbkrBroker unavailable.")
        return None
    IbkrBroker = _IbkrBroker
    return IbkrBroker


def _load_ibkr_live_broker() -> Optional[type]:
    global IbkrLiveBroker
    if IbkrLiveBroker is not None:
        return IbkrLiveBroker
    try:
        from .ibkr_live_broker import IbkrLiveBroker as _IbkrLiveBroker
    except ModuleNotFoundError:  # pragma: no cover - optional dependency missing
        print("[BROKERS] ibapi dependency missing; IbkrLiveBroker unavailable.")
        return None
    IbkrLiveBroker = _IbkrLiveBroker
    return IbkrLiveBroker


def __getattr__(name: str):
    if name == "IbkrBroker":
        return _load_ibkr_broker()
    if name == "IbkrLiveBroker":
        return _load_ibkr_live_broker()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class _BrokerModule(types.ModuleType):
    def __getattribute__(self, name: str):
        if name in {"IbkrBroker", "IbkrLiveBroker"}:
            value = super().__getattribute__(name)
            if value is None:
                return __getattr__(name)
            return value
        return super().__getattribute__(name)


sys.modules[__name__].__class__ = _BrokerModule


__all__ = ["BaseBroker", "BrokerOrderRequest", "SimBroker", "IbkrBroker", "IbkrLiveBroker"]
