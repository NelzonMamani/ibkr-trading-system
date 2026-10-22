"""Filesystem/cache-configuration probe only; never fetches provider data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def run_cache_probe(python, repo, evidence, env, *, timeout=30, cleanup=5):
    evidence = Path(evidence)
    trace = evidence / 'child-cache-stages.jsonl'
    child_env = dict(env, PR1108_CACHE_PROBE_TRACE=str(trace))
    body = (
        "import sitecustomize as s; s.probe_stage('probe_body_enter'); "
        "import os, pathlib, yfinance.cache as c; "
        "assert getattr(c, '_readonly_cache_isolated', False); "
        "assert pathlib.Path(os.environ['PR1108_YFINANCE_CACHE']).is_absolute(); "
        "print('CHILD_CACHE_ISOLATION_VERIFIED', c._readonly_cache_locations, flush=True); "
        "s.probe_stage('probe_body_complete')"
    )
    flags = ['-u', '-X', 'importtime', '-c']
    receipt = {'child_flags': flags, 'parent_ignore_environment': bool(sys.flags.ignore_environment),
               'timeout_seconds': timeout, 'cleanup_seconds': cleanup, 'timed_out': False,
               'child_exited': None, 'exit_code': None, 'pid': None,
               'stdout_path': 'child-cache.stdout.log', 'stderr_path': 'child-cache.stderr.log',
               'trace_path': trace.name, 'started_utc_epoch_ns': time.time_ns()}
    started = time.monotonic()
    process = None
    try:
        # Direct files retain partial output even if startup never reaches -c.
        # No pipe readers or unbounded communicate() after timeout.
        with (evidence / receipt['stdout_path']).open('xb') as out, (evidence / receipt['stderr_path']).open('xb') as err:
            process = subprocess.Popen([python, *flags, body], cwd=repo, env=child_env, stdout=out, stderr=err)
            receipt['pid'] = process.pid
            try:
                process.wait(timeout=max(0, timeout - (time.monotonic() - started)))
                # A late observed exit never becomes timely success.
                receipt['timed_out'] = time.monotonic() - started > timeout
            except subprocess.TimeoutExpired:
                receipt['timed_out'] = True
            finally:
                if process.poll() is None:
                    receipt['kill_requested'] = True
                    process.kill()  # only our exact child; no broad runtime kill
                    try:
                        process.wait(timeout=cleanup)
                    except subprocess.TimeoutExpired:
                        receipt['cleanup_timed_out'] = True
                receipt['exit_code'] = process.poll()
                receipt['child_exited'] = receipt['exit_code'] is not None
    except BaseException as exc:
        receipt['error_type'] = type(exc).__name__
        raise
    finally:
        if process is not None:
            receipt['exit_code'] = process.poll()
            receipt['child_exited'] = receipt['exit_code'] is not None
        receipt['elapsed_seconds'] = time.monotonic() - started
        # Files are authoritative; bounded tails keep JSON small on noisy failures.
        for stream in ('stdout', 'stderr'):
            path = evidence / receipt[stream + '_path']
            if path.exists():
                with path.open('rb') as handle:
                    handle.seek(max(0, path.stat().st_size - 16384))
                    receipt[stream] = handle.read(16384).decode('utf-8', errors='replace')
        target = evidence / 'child-cache-probe.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        temporary.replace(target)
    if receipt['timed_out']:
        raise subprocess.TimeoutExpired([python, *flags, '<cache-isolation-probe>'], timeout)
    if not receipt['child_exited'] or receipt['exit_code'] != 0 or 'CHILD_CACHE_ISOLATION_VERIFIED' not in receipt.get('stdout', ''):
        raise RuntimeError('Child startup/cache isolation failed; no runtime launch.')
    return receipt
