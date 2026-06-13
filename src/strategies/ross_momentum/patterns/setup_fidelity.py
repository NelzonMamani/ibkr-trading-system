"""PR5 setup fidelity guards for Ross pattern decisions."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.strategies.ross_momentum.policy.pattern_input_policy import MissingDataBehavior
from src.strategies.ross_momentum.patterns.pattern_inputs import PatternInputs
from src.strategies.ross_momentum.patterns.pattern_types import Direction, PatternResult


_POLICY_SETUP_BY_PATTERN_ID = {
    "P_MICRO_PULLBACK": "MICRO_PULLBACK",
    "P_FIRST_PULLBACK": "FIRST_PULLBACK",
    "P_FLAT_TOP_BREAKOUT": "FLAT_TOP_BREAKOUT",
    "P_HOD_BREAK": "HOD_BREAK",
    "P_PREMARKET_HIGH_BREAK": "PMH_BREAK",
    "P_PREMKT_BREAK": "PMH_BREAK",
    "P_ORB": "ORB_GAP_GO",
    "P_GAP_GO": "ORB_GAP_GO",
    "P_BULL_FLAG": "BULL_FLAG",
    "P_ABCD": "ABCD_CONTINUATION",
    "P_TREND_CONTINUATION_STAIR_STEP": "STAIR_STEP_CONTINUATION",
    "P_FAILED_ORB_FAKEOUT": "FAILED_BREAKOUT_CAUTION",
    "P_PARABOLIC_EXHAUSTION": "EXHAUSTION_EXIT_WARNING",
}

_NON_ENTRY_SIGNALS = {"RISK_OFF", "EXIT_SIGNAL", "CAUTION"}


def setup_policy_key(pattern_id: str | None, result: Any | None = None) -> str:
    raw = str(
        getattr(result, "setup_family_id", None)
        or getattr(result, "setup_id", None)
        or getattr(result, "pattern_name", None)
        or pattern_id
        or ""
    ).strip().upper()
    if raw in _POLICY_SETUP_BY_PATTERN_ID:
        return _POLICY_SETUP_BY_PATTERN_ID[raw]
    aliases = {
        "GAP_GO": "ORB_GAP_GO",
        "OPENING_RANGE_BREAKOUT": "ORB_GAP_GO",
        "ORB": "ORB_GAP_GO",
        "PREMARKET_HIGH_BREAK": "PMH_BREAK",
        "ABCD": "ABCD_CONTINUATION",
        "TREND_CONTINUATION_STAIR_STEP": "STAIR_STEP_CONTINUATION",
        "PARABOLIC_EXHAUSTION": "EXHAUSTION_EXIT_WARNING",
        "FAILED_ORB_FAKEOUT": "FAILED_BREAKOUT_CAUTION",
    }
    return aliases.get(raw, raw)


def blocking_input_reason(inputs: PatternInputs, pattern_id: str | None) -> str | None:
    key = setup_policy_key(pattern_id)
    quality = dict((inputs.setup_quality or {}).get(key) or {})
    if str(quality.get("action") or "").upper() != MissingDataBehavior.BLOCK.value:
        return None
    missing = list(quality.get("missing") or [])
    primary = next(
        (
            item
            for item in missing
            if str(item.get("behavior") or "").upper() == MissingDataBehavior.BLOCK.value
        ),
        None,
    )
    if primary is None:
        return f"pr4_input_block:{key}"
    return (
        f"pr4_input_block:{key}:"
        f"{primary.get('item')}={primary.get('provenance')}"
    )


def apply_detected_setup_fidelity(
    result: PatternResult,
    inputs: PatternInputs,
    *,
    pattern_id: str | None = None,
) -> PatternResult:
    if not result.detected:
        return result

    policy_key = setup_policy_key(pattern_id, result)
    if _is_risk_off_result(result):
        print(
            "[ROSS][DECISION][RISK_OFF] "
            f"symbol={inputs.symbol} setup={policy_key} pattern={result.pattern_name}"
        )
        return _with_pr4_metadata(result, inputs, policy_key, disposition="RISK_OFF")

    entry_ok, reason = is_tradeable_entry_candidate(result, policy_key=policy_key)
    if not entry_ok:
        print(
            "[ROSS][SETUP][DROP] "
            f"symbol={inputs.symbol} setup={policy_key} pattern={result.pattern_name} reason={reason}"
        )
        return replace(
            result,
            detected=False,
            confidence=0.0,
            rejection_reason=reason,
            rationale_text=f"Rejected: {reason}",
        )

    enriched = _with_pr4_metadata(result, inputs, policy_key, disposition="ENTRY_READY")
    print(
        "[ROSS][SETUP][DETECTED] "
        f"symbol={inputs.symbol} setup={policy_key} pattern={result.pattern_name} "
        f"trigger={enriched.trigger_level or enriched.entry_zone} stop={enriched.stop_level or enriched.stop_suggestion}"
    )
    print(
        "[ROSS][DECISION][ENTRY_READY] "
        f"symbol={inputs.symbol} setup={policy_key} pattern={result.pattern_name}"
    )
    return enriched


def is_tradeable_entry_candidate(setup: Any, *, policy_key: str | None = None) -> tuple[bool, str]:
    if setup is None:
        return False, "missing_setup"
    if not bool(getattr(setup, "detected", False)):
        return False, "not_detected"
    direction = getattr(setup, "direction", None)
    direction_value = direction.value if hasattr(direction, "value") else str(direction or "").upper()
    if direction_value != Direction.LONG.value:
        return False, "non_long_setup"
    if _is_risk_off_result(setup):
        return False, "risk_off_non_entry"
    if _has_pr4_block_for_setup(setup, policy_key=policy_key):
        return False, "pr4_input_block_flag"
    if getattr(setup, "trigger_level", None) is None and not getattr(setup, "entry_zone", None):
        return False, "missing_trigger"
    if (
        getattr(setup, "stop_level", None) is None
        and getattr(setup, "invalidation_level", None) is None
        and not getattr(setup, "stop_suggestion", None)
    ):
        return False, "missing_stop"
    rationale = str(getattr(setup, "rationale_text", "") or "").strip()
    if not rationale or rationale.lower().startswith("rejected:"):
        return False, "missing_rationale"
    return True, "ok"


def setup_quality_disposition(inputs: PatternInputs, policy_key: str) -> str:
    quality = dict((inputs.setup_quality or {}).get(policy_key) or {})
    return str(quality.get("action") or "UNKNOWN").upper()


def _has_pr4_block_for_setup(setup: Any, *, policy_key: str | None = None) -> bool:
    key = policy_key or setup_policy_key(None, setup)
    if not key:
        return False
    scoped_flag = f"PATTERN_INPUT_BLOCK_{key}"
    return scoped_flag in {str(flag).upper() for flag in list(getattr(setup, "data_quality_flags", []) or [])}


def _is_risk_off_result(result: Any) -> bool:
    signal_class = str(getattr(result, "signal_class", "") or "").upper()
    trigger_mode = str(getattr(result, "trigger_mode", "") or "").upper()
    risk_flags = {str(flag).upper() for flag in list(getattr(result, "risk_flags", []) or [])}
    return (
        bool(getattr(result, "non_entry_signal", False))
        or signal_class in _NON_ENTRY_SIGNALS
        or trigger_mode in _NON_ENTRY_SIGNALS
        or bool(risk_flags & _NON_ENTRY_SIGNALS)
    )


def _with_pr4_metadata(
    result: PatternResult,
    inputs: PatternInputs,
    policy_key: str,
    *,
    disposition: str,
) -> PatternResult:
    quality = dict((inputs.setup_quality or {}).get(policy_key) or {})
    action = str(quality.get("action") or "UNKNOWN").upper()
    tags = list(dict.fromkeys(
        list(result.setup_quality_tags or [])
        + [f"PR4_{action}", f"TF_PRIMARY_{inputs.primary_timeframe}", f"TF_EXEC_{inputs.execution_refinement_timeframe}"]
    ))
    risk_flags = list(result.risk_flags or [])
    if action in {"DEGRADE", "WARN"}:
        risk_flags.append(f"PR4_INPUT_{action}")
    metadata = dict(result.setup_metadata or {})
    metadata.update(
        {
            "pr4_policy_setup": policy_key,
            "pr4_setup_quality_action": action,
            "pr5_disposition": disposition,
            "primary_timeframe": inputs.primary_timeframe,
            "execution_refinement_timeframe": inputs.execution_refinement_timeframe,
            "context_timeframe": inputs.context_timeframe,
            "timeframe_provenance": dict(inputs.timeframe_provenance or {}),
            "indicator_provenance": dict(inputs.indicator_provenance or {}),
            "missing_data": list(quality.get("missing") or []),
        }
    )
    return replace(
        result,
        setup_quality_tags=tags,
        tags=tags,
        risk_flags=list(dict.fromkeys(risk_flags)),
        setup_metadata=metadata,
    )
