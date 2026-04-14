from __future__ import annotations

from src.config.runtime_config import RunMode
from src.core.engines.entry_admission import evaluate_entry_admission


class _ExplodingVerdict(dict):
    def get(self, key, default=None):  # type: ignore[override]
        raise AssertionError(f"SIM mode should not read authority verdicts (attempted key={key})")


def test_sim_mode_is_unrestricted_and_isolated() -> None:
    verdict = evaluate_entry_admission(
        run_mode=RunMode.SIM,
        position_truth_verdict=_ExplodingVerdict(),
        fill_authority_verdict=_ExplodingVerdict(),
        lifecycle_authority_verdict=_ExplodingVerdict(),
    )

    assert verdict.entries_allowed is True
    assert verdict.hard_blocked is False
    assert verdict.reasons == []
    assert verdict.rationale == "sim_mode_unrestricted"


def test_verdict_is_serializable() -> None:
    verdict = evaluate_entry_admission(run_mode=RunMode.SIM)
    payload = verdict.to_dict()

    assert payload["entries_allowed"] is True
    assert payload["reasons"] == []
    assert payload["rationale"] == "sim_mode_unrestricted"


def test_non_sim_authority_blocks_entries() -> None:
    verdict = evaluate_entry_admission(
        run_mode=RunMode.PAPER,
        position_truth_verdict={"hard_blocked": True, "reason": "position_truth_mismatch_detected"},
    )

    assert verdict.entries_allowed is False
    assert verdict.hard_blocked is True
    assert verdict.reasons == ["position_truth_mismatch_detected"]
    assert verdict.rationale == "entry_blocked_by_authority"
