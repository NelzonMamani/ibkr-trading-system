# FILE: verification_scripts/verify_session_detection.py
# TITLE: Verify market session detection (prints UTC + session label)

from datetime import datetime, timezone
from typing import Dict, Any

def verify_session_detection() -> Dict[str, Any]:
    out: Dict[str, Any] = {"status": "PASS", "details": {}}
    try:
        from src.scanner.session_pct_change import resolve_market_session_label  # type: ignore

        now = datetime.now(timezone.utc)
        session = resolve_market_session_label()
        out["details"] = {"utc_now": now.isoformat(), "session_label": str(session)}
        return out
    except Exception as e:
        out["status"] = "ERROR"
        out["details"] = {"error": repr(e)}
        return out
# END
