from __future__ import annotations

from typing import Any, Mapping

from src.scanner.session_pct_change import canonical_session_label, normalize_session_label


def build_canonical_session_contract(*, detected_session: str, session_decision_source: str) -> dict[str, Any]:
    normalized = normalize_session_label(detected_session or "")
    canonical = canonical_session_label(normalized)
    return {
        "detected_session": detected_session,
        "normalized_session": normalized,
        "canonical_session": canonical,
        "session_decision_source": session_decision_source,
    }


def attach_session_contract(context: dict[str, Any], session_contract: Mapping[str, Any]) -> None:
    contract = dict(session_contract or {})
    context["session_contract"] = contract
    canonical = contract.get("canonical_session")
    if canonical is None:
        canonical = canonical_session_label(normalize_session_label(str(context.get("session") or "")))
        context["session_contract"]["canonical_session"] = canonical
    context["canonical_session"] = canonical
