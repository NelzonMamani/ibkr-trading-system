"""Audit logging helpers for risk decisions."""
from __future__ import annotations

from src.risk.limits import RiskDecision


def log_risk_decision(decision: RiskDecision) -> None:
    rule_summary = ",".join(decision.triggered_rules) if decision.triggered_rules else "none"
    print(
        f"RISK {decision.decision.value} size={decision.max_position_size_allowed} "
        f"reason={decision.rationale_text} rules={rule_summary}"
    )
