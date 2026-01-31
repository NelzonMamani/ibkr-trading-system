# FILE: verification_scripts/verify_focus_injection.py
# TITLE: Verify whether the system supports injecting focus symbols (no guessing method names)

import inspect
from typing import Dict, Any, List

def verify_focus_injection() -> Dict[str, Any]:
    out: Dict[str, Any] = {"status": "PASS", "details": {}}
    try:
        from src.core.orchestrator import CoreOrchestrator  # type: ignore

        orch = CoreOrchestrator()

        # List orchestrator methods that look relevant
        candidates: List[str] = []
        for name, member in inspect.getmembers(orch, predicate=callable):
            lname = name.lower()
            if any(k in lname for k in ("focus", "watchlist", "dispatch", "inject", "override", "manual")):
                candidates.append(name)

        out["details"]["orchestrator_focus_related_methods"] = sorted(candidates)

        # If there is no focus/dispatch API, mark as FAIL (because you need this for readiness tests)
        if len(candidates) == 0:
            out["status"] = "FAIL"
            out["details"]["reason"] = (
                "No focus/watchlist injection surface found on CoreOrchestrator. "
                "We should add a stable public method (e.g., orchestrator.inject_focus_symbols(...)) "
                "for verification + manual control."
            )

        return out
    except Exception as e:
        out["status"] = "ERROR"
        out["details"] = {"error": repr(e)}
        return out
# END
