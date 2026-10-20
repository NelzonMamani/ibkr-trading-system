"""Normal no-trade reporting must retain actual contract violations."""
import pytest


@pytest.mark.parametrize('focus,violations,expected', [(0, [], 'NO_FOCUS_CANDIDATES'), (8, [], 'NO_QUALIFIED_INTENT'), (8, [{'symbol':'ONE'}], 'REQUIRED INTENT CONTRACT VIOLATED')])
def test_no_intent_reporting_preserves_real_contract_faults(capsys, focus, violations, expected):
    from src.core.orchestrator import _report_intent_absence
    _report_intent_absence(focus, violations)
    output = capsys.readouterr().out
    assert expected in output
    assert ('[FATAL]' in output) is bool(violations)
