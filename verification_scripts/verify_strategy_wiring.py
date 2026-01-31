# FILE: verification_scripts/verify_strategy_wiring.py
# TITLE: Verify which strategies exist + whether they have watchlist/focus handlers

import pkgutil
import importlib
import inspect
from typing import Dict, Any, List

def _safe_import(module_name: str):
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None

def verify_strategy_wiring() -> Dict[str, Any]:
    out: Dict[str, Any] = {"status": "PASS", "details": {}}
    details: Dict[str, Any] = {"strategies_found": []}

    # Discover strategy modules under src.strategies (no guessing filenames)
    base = _safe_import("src.strategies")
    if base is None:
        out["status"] = "FAIL"
        out["details"] = {"reason": "Cannot import src.strategies (package missing?)"}
        return out

    pkg_path = getattr(base, "__path__", None)
    if not pkg_path:
        out["status"] = "FAIL"
        out["details"] = {"reason": "src.strategies has no __path__ (not a package?)"}
        return out

    for m in pkgutil.walk_packages(pkg_path, prefix="src.strategies."):
        mod = _safe_import(m.name)
        if mod is None:
            continue

        # Find classes that look like strategies (heuristic: class name contains Strategy)
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if cls.__module__ != mod.__name__:
                continue
            if "Strategy" not in cls.__name__:
                continue

            handlers = {
                "on_watchlist": hasattr(cls, "on_watchlist"),
                "on_focus": hasattr(cls, "on_focus"),
                "generate_intents": hasattr(cls, "generate_intents"),
                "process": hasattr(cls, "process"),
            }

            details["strategies_found"].append(
                {
                    "module": mod.__name__,
                    "class": cls.__name__,
                    "handlers": handlers,
                }
            )

    out["details"] = details
    # If we found zero strategies, fail hard.
    if len(details["strategies_found"]) == 0:
        out["status"] = "FAIL"
        out["details"]["reason"] = "No Strategy classes discovered under src.strategies.*"
    return out
# END
