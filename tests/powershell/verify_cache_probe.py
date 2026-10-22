"""Offline subprocess fixtures using fake yfinance; no broker/provider."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.certification.readonly_cache_probe import run_cache_probe

with tempfile.TemporaryDirectory() as directory:
    for case in ('pass', 'import-timeout', 'set-timeout', 'bad-location', 'noisy-timeout', 'hook-failure'):
        root = Path(directory) / case
        startup = root / 'startup'
        package = startup / 'yfinance'
        package.mkdir(parents=True)
        evidence = root / 'e'; evidence.mkdir()
        shutil.copy2(REPO / 'scripts/certification/readonly_cache_sitecustomize.py', startup / 'sitecustomize.py')
        (package / '__init__.py').write_text('')
        prefix = 'import time; time.sleep(10)\n' if case == 'import-timeout' else ''
        if case == 'noisy-timeout':
            prefix = "import sys,time\nprint('x'*100000, flush=True)\nprint('retained-error',file=sys.stderr,flush=True)\ntime.sleep(10)\n"
        if case == 'hook-failure': prefix = "raise RuntimeError('controlled import failure')\n"
        (package / 'cache.py').write_text(prefix + '''class Manager:
    location = None
    @classmethod
    def get_location(cls): return cls.location
_TzDBManager = _CookieDBManager = _ISINDBManager = Manager
def set_cache_location(location):
''' + ('    import time; time.sleep(10)\n' if case == 'set-timeout' else '') +
            ("    Manager.location = 'incorrect'\n" if case == 'bad-location' else '    Manager.location = location\n'))
        env = dict(os.environ, PYTHONPATH=str(startup), PR1108_YFINANCE_CACHE=str(root / 'cache'))
        env.pop('PYTHONHOME', None)
        failed = False
        try: run_cache_probe(sys.executable, REPO, evidence, env, timeout=2, cleanup=2)
        except (subprocess.TimeoutExpired, RuntimeError): failed = True
        assert failed == (case != 'pass'), case
        receipt = json.loads((evidence / 'child-cache-probe.json').read_text())
        assert receipt['child_exited'] is True, receipt
        stages = [json.loads(row)['stage'] for row in (evidence / 'child-cache-stages.jsonl').read_text().splitlines()]
        assert stages[0] == 'sitecustomize_enter'
        if case == 'pass':
            assert stages[-1] == 'probe_body_complete'
            assert not receipt['timed_out'] and receipt['exit_code'] == 0
        if 'timeout' in case:
            assert receipt['timed_out'] and receipt['elapsed_seconds'] < 6
            assert stages[-1] == ('cache_location_set_begin' if case == 'set-timeout' else 'yfinance_cache_import_begin')
        if case == 'noisy-timeout':
            assert (evidence / 'child-cache.stdout.log').stat().st_size > 100000
            assert 'retained-error' in (evidence / 'child-cache.stderr.log').read_text()
        if case in ('bad-location', 'hook-failure'):
            assert receipt['exit_code'] == 78 and stages[-1] == 'sitecustomize_failed'
runner = (REPO / 'scripts/certification/run_natural_readonly_preflight.ps1').read_text()
assert "'preflight',$Root,$ExpectedCommit" in runner
assert "'observe'" not in runner and 'Invoke-ReadonlyObservation -' not in runner
print('Six offline cache subprocess fixtures passed; preflight-only dispatch verified.')
