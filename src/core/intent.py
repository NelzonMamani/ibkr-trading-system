from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping

from src.models.data_models import DecisionArtifact, TradeIntent


@dataclass(frozen=True)
class ExecutionIntent:
    strategy_name: str
    mode: str
    session_phase: str
    scan_only: bool
    trade_enabled: bool
    ranking_intent: str
    enforcement: Dict[str, int]
    notes: str


def _mode_allows_trading(mode_value: str) -> bool:
    normalized = mode_value.strip().upper()
    if normalized in {"READONLY", "READ_ONLY", "LIVE_READ_ONLY", "LIVE_READONLY"}:
        return False
    return normalized in {"PAPER", "LIVE"}


def build_execution_intent(
    *,
    strategy_name: str,
    mode: str,
    session_phase: str,
    policy: Any,
    execution_enabled: bool,
) -> ExecutionIntent:
    trade_allowed_by_mode = _mode_allows_trading(mode)
    trade_enabled = trade_allowed_by_mode and execution_enabled
    scan_only = not trade_allowed_by_mode
    ranking_intent = getattr(policy, "ranking_intent", "ROSS_MOMENTUM_STOCK_SELECTION")
    enforcement = {
        "watchlist_limit_k": int(getattr(policy, "watchlist_limit_k", 0)),
        "focus_limit_m": int(getattr(policy, "focus_limit_m", 0)),
        "top_gainers_n": int(getattr(policy, "top_gainers_n", 0)),
        "max_symbols_per_cycle": int(getattr(policy, "max_symbols_per_cycle", 0)),
    }
    notes = []
    if not trade_allowed_by_mode:
        notes.append("mode_blocks_trading")
    if not execution_enabled:
        notes.append("execution_disabled")
    return ExecutionIntent(
        strategy_name=strategy_name,
        mode=mode,
        session_phase=session_phase,
        scan_only=scan_only,
        trade_enabled=trade_enabled,
        ranking_intent=ranking_intent,
        enforcement=enforcement,
        notes=";".join(notes) if notes else "mode_allows_execution",
    )


def _normalize_intent_payload(intent: TradeIntent) -> Dict[str, Any]:
    payload = asdict(intent)
    for key in ("data_quality_flags", "regime_notes"):
        if key in payload and isinstance(payload[key], list):
            payload[key] = sorted(payload[key])
    return payload


def _sorted_intents(intents: Iterable[TradeIntent]) -> List[TradeIntent]:
    return sorted(
        intents,
        key=lambda intent: (
            intent.symbol,
            intent.trader_type,
            intent.direction,
            intent.confidence,
        ),
    )


def build_decision_artifact(
    *,
    strategy_name: str,
    run_mode: str,
    session_phase: str,
    intents: Iterable[TradeIntent],
    source: str,
    created_at: str,
    metadata: Mapping[str, Any] | None = None,
) -> DecisionArtifact:
    ordered_intents = _sorted_intents(intents)
    payload = {
        "strategy_name": strategy_name,
        "run_mode": run_mode,
        "session_phase": session_phase,
        "source": source,
        "created_at": created_at,
        "intents": [_normalize_intent_payload(intent) for intent in ordered_intents],
        "metadata": dict(metadata or {}),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    decision_hash = hashlib.sha256(encoded).hexdigest()[:16]
    decision_id = f"DECISION-{decision_hash}"
    return DecisionArtifact(
        decision_id=decision_id,
        strategy_name=strategy_name,
        run_mode=run_mode,
        session_phase=session_phase,
        source=source,
        created_at=created_at,
        intents=list(ordered_intents),
        metadata=dict(metadata or {}),
    )
