from __future__ import annotations

from pathlib import Path


CONTRACT_PATH = Path("docs/strategy/ROSS_MOMENTUM_STRATEGY_CONTRACT.md")


def _contract_text() -> str:
    assert CONTRACT_PATH.exists(), "Ross Momentum strategy contract must exist"
    return CONTRACT_PATH.read_text(encoding="utf-8")


def test_pr1052_contract_has_required_authority_index_columns() -> None:
    text = _contract_text()

    for column in (
        "Domain",
        "Canonical behavior",
        "Formula/threshold",
        "Session semantics",
        "Authoritative source hierarchy",
        "Canonical production file(s)",
        "Canonical class/function(s)",
        "Protecting tests",
        "Status",
        "Last verified PR/commit",
        "Notes/conflicts",
    ):
        assert column in text


def test_pr1052_contract_locks_five_pillars_and_supporting_metrics() -> None:
    text = _contract_text()

    for pillar in (
        "Price",
        "Gap / percentage move",
        "Float",
        "Volume",
        "News / catalyst",
    ):
        assert pillar in text

    assert "RVOL, spread/liquidity, session normalization, data quality, ranking weights, halt/SSR state, patterns, and technical structure" in text
    assert "Supporting metric only. Do not promote to a sixth pillar." in text


def test_pr1052_contract_preserves_safety_and_fail_closed_invariants() -> None:
    text = _contract_text()

    for invariant in (
        "Hard max is `20M` shares",
        "unknown float is not A-quality Focus evidence",
        "`DATA_UNAVAILABLE` cannot become confirmed catalyst",
        "`PAPER_READY=NO`",
        "`PAPER_READINESS_GATE=FAIL`",
        "`ZERO_BROKER_ORDER_MUTATIONS=YES`",
        "no synthetic trade intents in real READ_ONLY proof",
    ):
        assert invariant in text


def test_pr1052_contract_records_accepted_drift_risks_without_fixing_1051() -> None:
    text = _contract_text()

    assert "Primary: existing news engine not invoked in READ_ONLY." in text
    assert "Secondary: preparation cache not reused as accepted runtime catalyst authority." in text
    assert "Do not fix in #1052." in text
    assert "Trade-management code contains enforced partial/trailing/breakeven behavior, but Ross certification remains partial" in text
