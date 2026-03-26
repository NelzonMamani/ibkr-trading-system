from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.scanner.session_pct_change import canonical_session_label, normalize_session_label


_CANONICAL_SESSIONS = {"PRE", "RTH_OPEN", "RTH_MID", "RTH_LATE", "AH", "CLOSED"}
_EXECUTION_ALLOWED_SESSIONS = {"PRE", "RTH_OPEN", "RTH_MID", "RTH_LATE"}


@dataclass(frozen=True)
class CanonicalSessionContract:
    raw_detected_session: str
    canonical_session: str
    session_decision_source: str
    pct_reference_price_type: str
    gap_reference_type: str
    expected_volume_model_id: str
    execution_window_allowed: bool
    setup_family_profile: str
    trigger_profile_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _session_profile(canonical_session: str) -> tuple[str, str]:
    setup_by_session = {
        "PRE": "ROSS_PREMARKET_CONTINUATION",
        "RTH_OPEN": "ROSS_OPENING_DRIVE",
        "RTH_MID": "ROSS_MIDDAY_CONTINUATION",
        "RTH_LATE": "ROSS_POWER_HOUR",
        "AH": "ROSS_AFTER_HOURS_RESTRICTED",
        "CLOSED": "ROSS_PREP_ONLY",
    }
    trigger_by_session = {
        "PRE": "ROSS_TRIGGER_PRE_V1",
        "RTH_OPEN": "ROSS_TRIGGER_OPEN_V1",
        "RTH_MID": "ROSS_TRIGGER_MID_V1",
        "RTH_LATE": "ROSS_TRIGGER_LATE_V1",
        "AH": "ROSS_TRIGGER_AH_V1",
        "CLOSED": "ROSS_TRIGGER_DISABLED",
    }
    return (
        setup_by_session.get(canonical_session, "ROSS_PREP_ONLY"),
        trigger_by_session.get(canonical_session, "ROSS_TRIGGER_DISABLED"),
    )


def build_canonical_session_contract(
    *,
    detected_session: str | None,
    session_decision_source: str,
) -> CanonicalSessionContract:
    raw = normalize_session_label(str(detected_session or "CLOSED"))
    canonical = canonical_session_label(raw)
    if canonical not in _CANONICAL_SESSIONS:
        canonical = "CLOSED"
    setup_profile, trigger_profile = _session_profile(canonical)
    return CanonicalSessionContract(
        raw_detected_session=raw,
        canonical_session=canonical,
        session_decision_source=str(session_decision_source or "UNKNOWN"),
        pct_reference_price_type="LAST_COMPLETED_RTH_CLOSE",
        gap_reference_type="SESSION_OPEN_VS_LAST_COMPLETED_RTH_CLOSE",
        expected_volume_model_id=f"SESSION_PHASE_EXPECTED_VOLUME:{canonical}",
        execution_window_allowed=canonical in _EXECUTION_ALLOWED_SESSIONS,
        setup_family_profile=setup_profile,
        trigger_profile_id=trigger_profile,
    )


def attach_session_contract(context: dict[str, Any], contract: CanonicalSessionContract) -> dict[str, Any]:
    payload = contract.to_dict()
    context["session_contract"] = payload
    context["raw_detected_session"] = payload["raw_detected_session"]
    context["canonical_session"] = payload["canonical_session"]
    context["session_decision_source"] = payload["session_decision_source"]
    context["execution_window_allowed"] = payload["execution_window_allowed"]
    context["trigger_profile_id"] = payload["trigger_profile_id"]
    context["setup_family_profile"] = payload["setup_family_profile"]
    return context
