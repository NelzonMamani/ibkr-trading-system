from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.scanner.session_pct_change import normalize_session_label


@dataclass(frozen=True)
class ResolvedReferenceBundle:
    reference_price: Optional[float]
    reference_label: str
    pct_change_resolved: Optional[float]
    gap_pct_resolved: Optional[float]
    pct_source: str
    gap_source: str
    context_status: str
    execution_ready: bool
    prep_only: bool


def resolve_reference_bundle(
    *,
    session_label: str | None,
    reference_price: Optional[float],
    reference_label: Optional[str],
    pct_change: Optional[float],
    pct_source: Optional[str],
    gap_pct: Optional[float],
    gap_source: Optional[str],
) -> ResolvedReferenceBundle:
    session = normalize_session_label(session_label or "")
    prep_only = session in {"CLOSED", "WEEKEND", "OVN", "AH"}
    context_status = "prep_context" if prep_only else "live_candidate"
    execution_ready = session in {"PRE", "RTH", "RTH_OPEN", "RTH_MID", "RTH_LATE"}
    return ResolvedReferenceBundle(
        reference_price=reference_price,
        reference_label=reference_label or "LAST_RTH_CLOSE",
        pct_change_resolved=pct_change,
        gap_pct_resolved=gap_pct if gap_pct is not None else pct_change,
        pct_source=pct_source or ("PREP_CONTEXT" if prep_only else "LIVE_OR_IBKR"),
        gap_source=gap_source or ("SESSION_OPEN_VS_REF" if execution_ready else "PREP_CONTEXT"),
        context_status=context_status,
        execution_ready=execution_ready,
        prep_only=prep_only,
    )
