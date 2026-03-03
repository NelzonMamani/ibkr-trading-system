from __future__ import annotations

from dataclasses import dataclass

THESIS_HEALTHY_SCORE = 0.70
THESIS_DEGRADED_SCORE = 0.50


@dataclass(frozen=True)
class ThesisHealthSnapshot:
    score: float | None
    status: str
    reasons: list[str]


def compute_thesis_health_snapshot(*, symbol: str, context) -> tuple[ThesisHealthSnapshot | None, list[str]]:
    normalized_symbol = str(symbol or "").upper()
    if not normalized_symbol:
        return None, ["symbol"]

    health_by_symbol = _context_value(context, "thesis_health_by_symbol")
    score_by_symbol = _context_value(context, "thesis_health_score_by_symbol")
    status_by_symbol = _context_value(context, "thesis_health_status_by_symbol")
    reasons_by_symbol = _context_value(context, "thesis_health_reasons_by_symbol")

    missing: list[str] = []
    symbol_entry = None
    if isinstance(health_by_symbol, dict):
        symbol_entry = health_by_symbol.get(normalized_symbol)
    else:
        missing.append("thesis_health_by_symbol")

    score = None
    status = None
    reasons: list[str] = []

    if isinstance(symbol_entry, dict):
        score = _safe_float(symbol_entry.get("score"))
        status = _normalize_status(symbol_entry.get("status"))
        reasons = _normalize_reasons(symbol_entry.get("reasons"))

    if score is None and isinstance(score_by_symbol, dict):
        score = _safe_float(score_by_symbol.get(normalized_symbol))
    elif score is None:
        missing.append("thesis_health_score_by_symbol")

    if not status and isinstance(status_by_symbol, dict):
        status = _normalize_status(status_by_symbol.get(normalized_symbol))

    if not reasons and isinstance(reasons_by_symbol, dict):
        reasons = _normalize_reasons(reasons_by_symbol.get(normalized_symbol))

    if symbol_entry is None and score is None and not status and not reasons:
        if "thesis_health_by_symbol" not in missing:
            missing.append("thesis_health_by_symbol")
        if "thesis_health_score_by_symbol" not in missing:
            missing.append("thesis_health_score_by_symbol")
        return None, missing

    resolved_status = classify_thesis_health(score)
    if resolved_status == "UNKNOWN" and status:
        resolved_status = status

    return (
        ThesisHealthSnapshot(
            score=score,
            status=resolved_status,
            reasons=reasons,
        ),
        missing,
    )


def classify_thesis_health(score: float | None) -> str:
    if score is None:
        return "UNKNOWN"
    if score >= THESIS_HEALTHY_SCORE:
        return "HEALTHY"
    if score >= THESIS_DEGRADED_SCORE:
        return "DEGRADED"
    return "BROKEN"


def _context_value(context, key: str):
    if isinstance(context, dict):
        return context.get(key)
    return getattr(context, key, None)


def _normalize_status(value) -> str | None:
    if value is None:
        return None
    label = str(value).upper()
    if label in {"HEALTHY", "DEGRADED", "BROKEN", "UNKNOWN"}:
        return label
    return None


def _normalize_reasons(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return []


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
