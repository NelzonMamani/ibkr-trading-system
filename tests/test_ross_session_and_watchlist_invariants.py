from __future__ import annotations

from types import SimpleNamespace

from src.core.orchestrator import CoreOrchestrator
from src.scanner.session_pct_change import canonical_session_label, normalize_session_label


def test_noncanonical_aliases_canonicalize_for_policy() -> None:
    assert normalize_session_label('MIDDAY') == 'RTH_MID'
    assert canonical_session_label('MIDDAY') == 'RTH_MID'
    assert normalize_session_label('POWER_HOUR') == 'RTH_LATE'
    assert canonical_session_label('POWER_HOUR') == 'RTH_LATE'
    assert canonical_session_label('WEEKEND') == 'PRE'


def test_manual_focus_merge_does_not_erase_auto_focus() -> None:
    orchestrator = CoreOrchestrator.__new__(CoreOrchestrator)
    orchestrator._manual_focus_enabled = True
    merged = orchestrator._merge_focus_candidates(
        scanner_focus=[SimpleNamespace(symbol='AAA'), SimpleNamespace(symbol='BBB')],
        manual_candidates=[SimpleNamespace(symbol='CCC')],
        session_phase='RTH_MID',
    )
    assert [row.symbol for row in merged] == ['AAA', 'BBB', 'CCC']
