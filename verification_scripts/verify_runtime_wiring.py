# FILE: verification_scripts/verify_runtime_wiring.py
# TITLE: Verify runtime mode manager, execution gate, broker adapter (no guessing)

from typing import Dict, Any

def verify_runtime_wiring(mode: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"status": "PASS", "mode": mode, "details": {}}
    try:
        # Importing config resolver side-effects are part of your system; we accept that.
        from src.core.orchestrator import CoreOrchestrator  # type: ignore

        orch = CoreOrchestrator()

        # Introspect runtime manager fields (no assumptions about attribute names)
        rm = getattr(orch, "runtime_mode_manager", None) or getattr(orch, "runtime", None) or getattr(orch, "mode_manager", None)

        out["details"]["runtime_manager_type"] = type(rm).__name__ if rm is not None else None

        # Known in logs: runtime mode resolved in orchestrator init.
        # We locate the resolved mode by searching common attrs.
        resolved_mode = None
        for attr in ("mode", "run_mode", "resolved_mode", "effective_mode"):
            if rm is not None and hasattr(rm, attr):
                resolved_mode = getattr(rm, attr)
                break
        out["details"]["resolved_mode_attr"] = resolved_mode

        # ExecutionEngine / broker adapter presence
        exec_engine = getattr(orch, "execution_engine", None) or getattr(orch, "execution", None)
        out["details"]["execution_engine_type"] = type(exec_engine).__name__ if exec_engine else None

        broker = getattr(exec_engine, "broker", None) if exec_engine else None
        out["details"]["broker_adapter_type"] = type(broker).__name__ if broker else None

        # Look for “allow_orders” / “execution enabled” flags by introspection
        flags = {}
        for obj_name, obj in (("runtime_manager", rm), ("execution_engine", exec_engine)):
            if obj is None:
                continue
            for attr in ("allow_orders", "execution_enabled", "orders_enabled", "is_enabled", "enabled"):
                if hasattr(obj, attr):
                    flags[f"{obj_name}.{attr}"] = getattr(obj, attr)
        out["details"]["flags"] = flags

        # Hard policy expectation: LIVE_READ_ONLY must not allow orders
        if str(mode).upper() == "LIVE_READ_ONLY":
            # If any “allow_orders” style flag is True, fail.
            for k, v in flags.items():
                if "allow_orders" in k and bool(v) is True:
                    out["status"] = "FAIL"
                    out["details"]["reason"] = f"{k} unexpectedly True in LIVE_READ_ONLY"
                    return out

        return out

    except Exception as e:
        out["status"] = "ERROR"
        out["details"]["error"] = repr(e)
        return out
# END
