from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_MANUAL_FOCUS_CONFIG: dict[str, Any] = {
    "enabled": True,
    "manual_focus": ["TMDE", "HURA", "CYN", "OCGN"],
    "max_manual_symbols": 5,
    "live_reload_seconds": 60,
}


@dataclass(frozen=True)
class ManualFocusConfig:
    enabled: bool
    manual_focus: list[str]
    max_manual_symbols: int
    live_reload_seconds: int


REPO_ROOT = Path(__file__).resolve().parents[2]
MANUAL_FOCUS_CONFIG_PATH = REPO_ROOT / "config" / "manual_focus.json"


def _write_default_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT_MANUAL_FOCUS_CONFIG, indent=2) + "\n", encoding="utf-8")


def _sanitize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _coerce_config(raw: dict[str, Any]) -> ManualFocusConfig:
    enabled = bool(raw.get("enabled", True))
    raw_symbols = raw.get("manual_focus", [])
    if not isinstance(raw_symbols, list):
        raw_symbols = []

    max_manual_symbols = int(raw.get("max_manual_symbols", DEFAULT_MANUAL_FOCUS_CONFIG["max_manual_symbols"]))
    if max_manual_symbols < 0:
        max_manual_symbols = 0

    deduped: list[str] = []
    for symbol in raw_symbols:
        clean = _sanitize_symbol(symbol)
        if not clean or clean in deduped:
            continue
        deduped.append(clean)

    deduped = deduped[:max_manual_symbols]

    live_reload_seconds = int(raw.get("live_reload_seconds", DEFAULT_MANUAL_FOCUS_CONFIG["live_reload_seconds"]))
    if live_reload_seconds <= 0:
        live_reload_seconds = DEFAULT_MANUAL_FOCUS_CONFIG["live_reload_seconds"]

    return ManualFocusConfig(
        enabled=enabled,
        manual_focus=deduped,
        max_manual_symbols=max_manual_symbols,
        live_reload_seconds=live_reload_seconds,
    )


def load_manual_focus_config() -> ManualFocusConfig:
    path = MANUAL_FOCUS_CONFIG_PATH
    if not path.exists():
        _write_default_config(path)
        print("[MANUAL_FOCUS] config_missing_recreated")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[MANUAL_FOCUS][WARN] malformed_json path={path.as_posix()} err={exc}")
        return ManualFocusConfig(enabled=False, manual_focus=[], max_manual_symbols=0, live_reload_seconds=60)
    except OSError as exc:
        print(f"[MANUAL_FOCUS][WARN] read_failed path={path.as_posix()} err={exc}")
        return ManualFocusConfig(enabled=False, manual_focus=[], max_manual_symbols=0, live_reload_seconds=60)

    if not isinstance(raw, dict):
        print(f"[MANUAL_FOCUS][WARN] invalid_schema path={path.as_posix()} type={type(raw).__name__}")
        return ManualFocusConfig(enabled=False, manual_focus=[], max_manual_symbols=0, live_reload_seconds=60)

    cfg = _coerce_config(raw)
    symbols = cfg.manual_focus if cfg.enabled else []
    print(f"[MANUAL_FOCUS] loaded_symbols={len(symbols)} symbols={symbols}")
    return cfg


def load_manual_focus_symbols() -> list[str]:
    cfg = load_manual_focus_config()
    if not cfg.enabled:
        return []
    return list(cfg.manual_focus)
