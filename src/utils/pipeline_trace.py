"""Canonical pipeline stage trace helpers."""

from __future__ import annotations

from typing import Optional

_intent_stage_seen: bool = False


def reset_pipeline_trace_cycle() -> None:
    """Reset per-cycle pipeline stage memory."""
    global _intent_stage_seen
    _intent_stage_seen = False


def pipeline_trace(stage: str, symbol: Optional[str] = None) -> None:
    """Print canonical pipeline trace line for each stage execution."""
    global _intent_stage_seen
    stage_name = str(stage or "").strip().upper() or "UNKNOWN"
    symbol_value = str(symbol).upper() if symbol else "GLOBAL"
    print(f"[PIPELINE][{stage_name}] symbol={symbol_value}")
    if stage_name == "INTENT":
        _intent_stage_seen = True


def intent_stage_seen() -> bool:
    """Return whether an INTENT stage has been traced in the active cycle."""
    return _intent_stage_seen

