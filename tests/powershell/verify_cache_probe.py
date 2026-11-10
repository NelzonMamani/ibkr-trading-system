"""Offline subprocess fixtures using fake yfinance; no broker/provider."""
import json
import inspect
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.certification.readonly_cache_probe import run_cache_probe

# Exercise the observation owner's actual startup/cleanup budgets. The old
# two-second override also timed nominal Windows startup and fsynced traces;
# its failure discarded the receipt before exposing the cause.
parameters = inspect.signature(run_cache_probe).parameters
probe_budget = parameters['timeout'].default
cleanup_budget = parameters['cleanup'].default
blocked = 'import threading; threading.Event().wait()\n'

with tempfile.TemporaryDirectory() as directory:
    for case in ('pass', 'import-timeout', 'set-timeout', 'bad-location', 'noisy-timeout', 'hook-failure'):
        root = Path(directory) / case
        startup = root / 'startup'
        package = startup / 'yfinance'
        package.mkdir(parents=True)
        evidence = root / 'e'; evidence.mkdir()
        shutil.copy2(REPO / 'scripts/certification/readonly_cache_sitecustomize.py', startup / 'sitecustomize.py')
        (package / '__init__.py').write_text('')
        prefix = blocked if case == 'import-timeout' else ''
        if case == 'noisy-timeout':
            prefix = "import sys\nprint('x'*100000, flush=True)\nprint('retained-error',file=sys.stderr,flush=True)\n" + blocked
        if case == 'hook-failure': prefix = "raise RuntimeError('controlled import failure')\n"
        (package / 'cache.py').write_text(prefix + '''class Manager:
    location = None
    @classmethod
    def get_location(cls): return cls.location
_TzDBManager = _CookieDBManager = _ISINDBManager = Manager
def set_cache_location(location):
''' + ('    ' + blocked if case == 'set-timeout' else '') +
            ("    Manager.location = 'incorrect'\n" if case == 'bad-location' else '    Manager.location = location\n'))
        env = dict(os.environ, PYTHONPATH=str(startup), PR1108_YFINANCE_CACHE=str(root / 'cache'))
        env.pop('PYTHONHOME', None)
        failed = False
        error = None
        try: run_cache_probe(sys.executable, REPO, evidence, env)
        except (subprocess.TimeoutExpired, RuntimeError) as exc:
            failed = True
            error = type(exc).__name__
        receipt = json.loads((evidence / 'child-cache-probe.json').read_text())
        trace = evidence / 'child-cache-stages.jsonl'
        stages = [json.loads(row)['stage'] for row in trace.read_text().splitlines()] if trace.exists() else []
        diagnostic = dict(case=case, error=error, receipt=receipt, stages=stages)
        assert failed == (case != 'pass'), diagnostic
        assert receipt['child_exited'] is True, receipt
        assert stages[0] == 'sitecustomize_enter'
        if case == 'pass':
            assert stages[-1] == 'probe_body_complete'
            assert not receipt['timed_out'] and receipt['exit_code'] == 0
        if 'timeout' in case:
            assert receipt['timed_out'] and receipt['elapsed_seconds'] < probe_budget + cleanup_budget + 2, diagnostic
            assert stages[-1] == ('cache_location_set_begin' if case == 'set-timeout' else 'yfinance_cache_import_begin')
        if case == 'noisy-timeout':
            assert (evidence / 'child-cache.stdout.log').stat().st_size > 100000
            assert 'retained-error' in (evidence / 'child-cache.stderr.log').read_text()
        if case in ('bad-location', 'hook-failure'):
            assert receipt['exit_code'] == 78 and stages[-1] == 'sitecustomize_failed'
        print(json.dumps(dict(case=case, timed_out=receipt['timed_out'],
            child_exited=receipt['child_exited'], exit_code=receipt['exit_code'],
            elapsed_seconds=receipt['elapsed_seconds'], timeout_seconds=receipt['timeout_seconds'],
            last_stage=stages[-1])))
runner = (REPO / 'scripts/certification/run_natural_readonly_preflight.ps1').read_text()
assert "-PreflightOnly" in runner
assert "'observe'" not in runner
print('Six offline cache subprocess fixtures passed; preflight-only dispatch verified.')
