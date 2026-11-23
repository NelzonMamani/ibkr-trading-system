"""The required Windows check must fail when any verification owner is incomplete."""
from contextlib import redirect_stdout
from io import StringIO
from itertools import product
import json
from pathlib import Path
import re
import textwrap

import pytest


WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/pytest.yml'


def _jobs():
    # Only split the workflow's top-level job blocks; no YAML dependency added.
    section = WORKFLOW.read_text(encoding='utf-8').split('\njobs:\n', 1)[1]
    matches = list(re.finditer(r'^  ([\w-]+):\n', section, re.MULTILINE))
    return {match.group(1): section[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(section)]
            for i, match in enumerate(matches)}


def _gate_code():
    block = _jobs()['windows-offline'].split('        run: |\n', 1)[1]
    return compile(textwrap.dedent(block), str(WORKFLOW), 'exec')


def _evaluate(monkeypatch, needs):
    monkeypatch.setenv('NEEDS_CONTEXT', json.dumps(needs))
    with redirect_stdout(StringIO()):
        exec(_gate_code(), {})


def test_actual_aggregate_requires_all_authoritative_results(monkeypatch):
    statuses = ('success', 'failure', 'cancelled', 'skipped')
    for scope_result, flag, suite_result, lifecycle_result, harness_result in product(statuses, ('true', 'false'), statuses, statuses, statuses):
        needs = {
            'verification-scope': {'result': scope_result, 'outputs': {'harness_only': flag}},
            'windows-offline-suite': {'result': suite_result},
            'windows-lifecycle-suite': {'result': lifecycle_result},
            'windows-controlled-process': {'result': harness_result},
        }
        allowed = (scope_result == 'success' and harness_result == 'success'
                   and suite_result == lifecycle_result == ('skipped' if flag == 'true' else 'success'))
        if allowed:
            _evaluate(monkeypatch, needs)
        else:
            with pytest.raises(SystemExit):
                _evaluate(monkeypatch, needs)


def test_missing_or_ambiguous_scope_cannot_authorize_a_skipped_suite(monkeypatch):
    for flag in (None, '', 'TRUE', 'False', True, False, 'unknown'):
        with pytest.raises(SystemExit):
            _evaluate(monkeypatch, {
                'verification-scope': {'result': 'success', 'outputs': {'harness_only': flag}},
                'windows-offline-suite': {'result': 'skipped'},
                'windows-lifecycle-suite': {'result': 'skipped'},
                'windows-controlled-process': {'result': 'success'},
            })
    with pytest.raises(SystemExit):
        _evaluate(monkeypatch, {'verification-scope': {'result': 'success'}})


def test_missing_or_malformed_job_results_fail_closed(monkeypatch):
    for missing in ('windows-offline-suite', 'windows-lifecycle-suite', 'windows-controlled-process', 'verification-scope'):
        needs = {
            'verification-scope': {'result': 'success', 'outputs': {'harness_only': 'false'}},
            'windows-offline-suite': {'result': 'success'},
            'windows-lifecycle-suite': {'result': 'success'},
            'windows-controlled-process': {'result': 'success'},
        }
        del needs[missing]
        with pytest.raises((KeyError, SystemExit)):
            _evaluate(monkeypatch, needs)
    monkeypatch.setenv('NEEDS_CONTEXT', 'not-json')
    with pytest.raises(json.JSONDecodeError):
        exec(_gate_code(), {})


def test_windows_split_preserves_required_owners_budgets_and_guards():
    jobs = _jobs()
    suite, lifecycle, controlled, gate = (jobs[name] for name in
                              ('windows-offline-suite', 'windows-lifecycle-suite', 'windows-controlled-process', 'windows-offline'))
    assert '    timeout-minutes: 30\n' in jobs['test']
    for owner in (suite, lifecycle, controlled):
        assert '    timeout-minutes: 60\n' in owner
        assert '    needs: verification-scope\n' in owner
        assert '    runs-on: windows-latest\n' in owner
        assert 'python-version: "3.13.3"' in owner
        assert 'fetch-depth: 0' in owner
        assert 'python -m pip install -r requirements.txt' in owner
        assert '"last_reserved_order_id":361' in owner
        assert 'IBKR_ORDER_ID_STATE_PATH=$state' in owner
    for owner in (suite, controlled):
        assert 'if-no-files-found: error' in owner
        assert 'if: always()' in owner
        assert 'continue-on-error' not in owner
    for owner in (suite, lifecycle):
        assert "    if: needs.verification-scope.outputs.harness_only != 'true'\n" in owner
        assert '${{ github.workspace }}/tests/offline;${{ github.workspace }}' in owner
        assert 'continue-on-error' not in owner
    assert '    if: always()\n' in gate
    assert 'needs: [verification-scope, windows-offline-suite, windows-lifecycle-suite, windows-controlled-process]' in gate
    assert 'NEEDS_CONTEXT: ${{ toJSON(needs) }}' in gate
    assert 'continue-on-error' not in gate
    for command in (
        'python -m pytest -q tests/test_quote_sdk_transport_probe.py tests/test_quote_transport_operator.py tests/test_final_order_audit_completion.py',
        'python -m pytest -q tests/test_independent_news_maintenance.py',
        'python -m pytest -q -s tests/test_float_cache_concurrency.py',
    ):
        assert command in suite
    assert 'name: windows-final-order-evidence' in suite
    assert "${{ runner.temp }}/ps-status-final-orders-*/" in suite
    for command in (
        'python -m pip install pytest "yfinance>=0.2.54"',
        'python -m pytest -q tests/test_readonly_observation_duration.py',
        'python tests/powershell/verify_cache_probe.py',
        '.\\tests\\powershell\\test_offline_exit_status.ps1',
        '.\\tests\\powershell\\test_readonly_observation.ps1',
        '.\\tests\\powershell\\verify_quote_transport.ps1',
    ):
        assert command in controlled
    assert controlled.count('shell: powershell') == 4
    assert "Windows PowerShell 5.1 PAPER caller parser and missing-pin gate" in controlled
    assert r"docs\ross\ORDINARY_RTH_PAPER_LOCAL_EXECUTION.ps1.in" in controlled
    assert "PAPER_RELEASE_ACCEPTED_SOURCE_PIN_MISSING" in controlled
    assert controlled.count('if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }') == 2
    assert 'name: windows-powershell-status-evidence' in controlled
    assert '${{ runner.temp }}/ps-status-*/' in controlled
    assert '${{ runner.temp }}/ps-observation-*/' in controlled


def test_full_windows_jobs_select_complementary_tests():
    jobs = _jobs()
    modules = (
        'tests/test_native_stop_price_prerequisite.py',
        'tests/test_standalone_pmh_late_fill_protection.py',
    )
    remaining = next(line for line in jobs['windows-offline-suite'].splitlines()
                     if line.startswith('        run: python -m pytest -q --ignore='))
    lifecycle = next(line for line in jobs['windows-lifecycle-suite'].splitlines()
                     if line.startswith('        run: python -m pytest -v '))
    assert remaining.split()[5:] == [f'--ignore={module}' for module in modules]
    assert lifecycle.split()[5:] == list(modules)
