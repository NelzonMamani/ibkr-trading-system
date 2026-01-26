"""Persistence helpers for Statistical Intraday Momentum readiness artefacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any, Dict, List

from src.config.config_resolver import get_config
from src.config.system_config import get_current_market_session
from src.utils.time_utils import to_ny_time, utc_now


ARTEFACT_DIR = Path("data/cache/statistical_intraday_momentum")


def _ensure_dir() -> None:
    ARTEFACT_DIR.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _baseline_path(session_date: str) -> Path:
    return ARTEFACT_DIR / f"baseline_universe_{session_date}.json"


def _distribution_path(session_date: str) -> Path:
    return ARTEFACT_DIR / f"distribution_store_{session_date}.json"


def _readiness_path(session_date: str) -> Path:
    return ARTEFACT_DIR / f"session_readiness_{session_date}.json"


def build_or_load_baseline_universe(session_date: str) -> Dict[str, Any]:
    _ensure_dir()
    path = _baseline_path(session_date)
    if path.exists():
        payload = _read_json(path)
        payload["source"] = payload.get("source") or "cache"
        return payload

    symbols = _load_baseline_symbols()
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "artefact_name": "baseline_universe",
        "session_date": session_date,
        "created_at_utc": now,
        "version": "v1",
        "count": len(symbols),
        "symbols": symbols,
        "sample": symbols[:10],
        "source": "builder",
        "is_valid": bool(symbols),
    }
    _write_json(path, payload)
    return payload


def load_distribution_store(session_date: str) -> Dict[str, Any]:
    _ensure_dir()
    path = _distribution_path(session_date)
    if not path.exists():
        return {
            "artefact_name": "distribution_store",
            "session_date": session_date,
            "version": None,
            "source": "missing",
            "is_valid": False,
        }
    payload = _read_json(path)
    valid_until = payload.get("valid_until")
    is_valid = bool(payload.get("version")) and (
        valid_until is None or session_date <= str(valid_until)
    )
    payload["is_valid"] = is_valid
    return payload


def build_or_load_session_readiness(session_date: str) -> Dict[str, Any]:
    _ensure_dir()
    path = _readiness_path(session_date)
    if path.exists():
        payload = _read_json(path)
        payload["source"] = payload.get("source") or "cache"
        return payload

    now = utc_now()
    ny_time = to_ny_time(now)
    phase = get_current_market_session(now)
    payload = {
        "artefact_name": "session_readiness",
        "session_date": session_date,
        "created_at_utc": now.isoformat(),
        "ny_time": ny_time.isoformat(),
        "phase": phase,
        "allowed": phase in {"PRE", "REGULAR", "AFTER"},
        "source": "builder",
        "is_valid": True,
    }
    _write_json(path, payload)
    return payload


def build_distribution_store(session_date: str, *, source: str = "bootstrap") -> Dict[str, Any]:
    _ensure_dir()
    path = _distribution_path(session_date)
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "artefact_name": "distribution_store",
        "session_date": session_date,
        "created_at_utc": now,
        "version": "v1",
        "count": 1,
        "source": source,
        "valid_until": "9999-12-31",
        "note": "Bootstrapped placeholder store for readiness wiring.",
        "store": {"sample": {"mean": 0.0, "stdev": 1.0}},
    }
    _write_json(path, payload)
    return payload


def _load_baseline_symbols() -> List[str]:
    path = Path("src/scanner/mock_universe.txt")
    symbols: List[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            symbol = line.strip().upper()
            if symbol:
                symbols.append(symbol)
    if not symbols:
        fallback = get_config("SCANNER_DEFAULT_SYMBOLS") or []
        symbols = [symbol.upper() for symbol in fallback if symbol]
    if not symbols:
        symbols = ["AAPL", "MSFT", "NVDA", "AMD", "TSLA"]
    return symbols
