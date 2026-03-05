from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    payload = {}
    for key in ("symbol", "con_id", "last", "close", "spread", "float_shares", "data_quality_flags", "session"):
        payload[key] = getattr(row, key, None)
    return payload


def write_premarket_prep_artifact(*, mode: str, session: str, scanner_payload: dict[str, Any], watchlist_k: int) -> dict[str, Any]:
    raw_scan = scanner_payload.get("universe_top_n", []) or []
    raw_scan_n = len(raw_scan)
    candidates = scanner_payload.get("candidate_metrics", []) or []

    shortlist: list[dict[str, Any]] = []
    float_hit = 0
    float_lookup = 0
    float_unknown = 0

    for row in candidates:
        d = _to_dict(row)
        symbol = (d.get("symbol") or "").upper()
        if not symbol or not symbol.isalnum():
            continue
        if d.get("con_id") in {None, 0, "0"}:
            continue
        if len(shortlist) >= watchlist_k:
            break
        float_shares = d.get("float_shares")
        float_source = d.get("float_source") or ("cache" if float_shares is not None else "missing")
        if float_source == "cache":
            float_hit += 1
        elif float_source == "lookup":
            float_lookup += 1
        else:
            float_unknown += 1
        shortlist.append(
            {
                "symbol": symbol,
                "conId": d.get("con_id"),
                "last": d.get("last"),
                "close": d.get("close"),
                "spread": d.get("spread"),
                "float_millions": round(float(float_shares) / 1_000_000.0, 3) if float_shares is not None else None,
                "float_source": float_source,
                "data_quality_flags": list(d.get("data_quality_flags") or []),
                "session_phase": session,
            }
        )

    evidence = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "session": session,
        "raw_scan_n": raw_scan_n,
        "prep_watchlist_k": len(shortlist),
        "symbols": shortlist,
        "float_cache": {"hit": float_hit, "miss": float_lookup, "unknown": float_unknown},
        "pass": len(shortlist) > 0,
    }

    out_path = Path("AUDIT_EVIDENCE/p01_premarket_prep/premarket_prep_watchlist.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    print(f"PREMARKET_PREP_WATCHLIST_K (K={len(shortlist)}): {[item['symbol'] for item in shortlist]}")
    print(f"FLOAT_CACHE: hit={float_hit} miss={float_lookup} unknown={float_unknown}")
    return evidence
