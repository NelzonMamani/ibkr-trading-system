from __future__ import annotations

import json

from src.metadata import strategy_policy_v2_audit as audit


def test_governance_lock_violation_invalidates_strategy(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "baseline_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "strategies": [
                    {
                        "strategy_id": "P01",
                        "sha256": "0" * 64,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(audit, "BASELINE_SNAPSHOT_PATH", snapshot_path)

    results = audit.run_audit()
    p01 = next(result for result in results if result.strategy_id == "P01")

    assert p01.governance_lock_violation is True
    assert p01.verdict == "INVALIDATED_PENDING_REVIEW"
    assert "GOVERNANCE_LOCK_VIOLATION" in p01.governance_lock_message


def test_governance_lock_absent_snapshot_does_not_invalidate(tmp_path, monkeypatch) -> None:
    snapshot_path = tmp_path / "missing_snapshot.json"
    monkeypatch.setattr(audit, "BASELINE_SNAPSHOT_PATH", snapshot_path)

    results = audit.run_audit()
    assert all(result.verdict != "INVALIDATED_PENDING_REVIEW" for result in results)
