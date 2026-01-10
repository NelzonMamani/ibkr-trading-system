from __future__ import annotations

import importlib
import importlib.util
from typing import TYPE_CHECKING

from .base_broker import BaseBroker, BrokerOrderRequest

if TYPE_CHECKING:
    from .ibkr_broker import IbkrBroker
    from .ibkr_live_broker import IbkrLiveBroker
    from .sim_broker import SimBroker

__all__ = ["BaseBroker", "BrokerOrderRequest", "SimBroker", "IbkrBroker", "IbkrLiveBroker"]

_UNSET = object()
_SIM_BROKER = _UNSET
_IBKR_BROKER = _UNSET
_IBKR_LIVE_BROKER = _UNSET


def _ibkr_dependency_available() -> bool:
    return importlib.util.find_spec("ibapi") is not None


def _load_sim_broker():
    global _SIM_BROKER
    if _SIM_BROKER is _UNSET:
        module = importlib.import_module(f"{__name__}.sim_broker")
        _SIM_BROKER = module.SimBroker
    return _SIM_BROKER


def _load_ibkr_broker():
    global _IBKR_BROKER
    if _IBKR_BROKER is _UNSET:
        if not _ibkr_dependency_available():
            print("[BROKERS] ibapi dependency missing; IbkrBroker unavailable.")
            _IBKR_BROKER = None
        else:
            module = importlib.import_module(f"{__name__}.ibkr_broker")
            _IBKR_BROKER = module.IbkrBroker
    return _IBKR_BROKER


def _load_ibkr_live_broker():
    global _IBKR_LIVE_BROKER
    if _IBKR_LIVE_BROKER is _UNSET:
        if not _ibkr_dependency_available():
            print("[BROKERS] ibapi dependency missing; IbkrLiveBroker unavailable.")
            _IBKR_LIVE_BROKER = None
        else:
            module = importlib.import_module(f"{__name__}.ibkr_live_broker")
            _IBKR_LIVE_BROKER = module.IbkrLiveBroker
    return _IBKR_LIVE_BROKER


def __getattr__(name: str):
    if name == "SimBroker":
        return _load_sim_broker()
    if name == "IbkrBroker":
        return _load_ibkr_broker()
    if name == "IbkrLiveBroker":
        return _load_ibkr_live_broker()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(list(globals().keys()) + ["SimBroker", "IbkrBroker", "IbkrLiveBroker"])
