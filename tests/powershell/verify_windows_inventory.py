"""Inventory-only controlled Windows checks; never launch a Ross runtime."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.certification import pr1090_terminal_observation_supervisor as module

real_run = subprocess.run
captured = []
def fixture_run(args, **kwargs):
    captured.append((args, kwargs))
    return subprocess.CompletedProcess(args, 0, json.dumps([{'ProcessId': os.getpid(), 'CommandLine': 'python.exe -E operator.py'}]), '')
module.subprocess.run = fixture_run
try:
    result = module.runtime_inventory(platform='nt')
    assert result['completed'] and not result['runtimes']
    args, kwargs = captured[-1]
    assert kwargs['timeout'] == 15
    assert '-Query' in args[-1] and "WHERE Name LIKE 'python%'" in args[-1]
    assert 'Where-Object' not in args[-1] and '-OperationTimeoutSec 10' in args[-1]
    assert result['elapsed_seconds'] >= 0 and result['timeout_seconds'] == 15
    def timeout(*args, **kwargs): raise subprocess.TimeoutExpired('inventory', 15)
    module.subprocess.run = timeout
    result = module.runtime_inventory(platform='nt')
    assert not result['completed'] and result['error_type'] == 'TimeoutExpired' and result['runtimes'] == []
finally:
    module.subprocess.run = real_run

if os.name == 'nt':
    # Real PowerShell parser/subprocess, synthetic CIM result; no process started.
    for case in ('healthy', 'runtime', 'unreadable', 'missing-self', 'cim-error', 'slow'):
        rows = [{'ProcessId':os.getpid(),'CommandLine':'python.exe -E operator.py'}]
        if case == 'runtime': rows.append({'ProcessId':987,'CommandLine':'python.exe -u -m src.main'})
        if case == 'unreadable': rows[0]['CommandLine'] = None
        if case == 'missing-self': rows[0]['ProcessId'] = 987
        payload = json.dumps(rows)
        # Powershell function emits objects, letting actual query pipeline/JSON run.
        prefix = "function Get-CimInstance { param($Query,$OperationTimeoutSec,$ErrorAction); "
        prefix += "if ($Query -notlike '*WHERE Name LIKE*' -or $OperationTimeoutSec -ne 10) { throw 'query contract' }; "
        if case == 'cim-error': prefix += "throw 'controlled CIM failure'; "
        if case == 'slow': prefix += 'Start-Sleep -Milliseconds 500; '
        prefix += "ConvertFrom-Json '" + payload.replace("'", "''") + "' }; "
        def controlled(args, **kwargs):
            assert kwargs['timeout'] == 15
            return real_run(args[:-1]+[prefix+args[-1]], **kwargs)
        module.subprocess.run = controlled
        started = time.monotonic()
        result = module.runtime_inventory(platform='nt')
        assert time.monotonic()-started < 18, case
        assert result['completed'] == (case in ('healthy','runtime','slow')), (case,result)
        if case == 'runtime': assert result['runtimes'][0]['pid'] == 987
        if case == 'slow': assert result['elapsed_seconds'] >= .5
    # Exercise the actual15s outer bound with a controlled sleeping PS child.
    def sleeping(args, **kwargs):
        return real_run(args[:-1]+['Start-Sleep -Seconds 30'], **kwargs)
    module.subprocess.run = sleeping
    result = module.runtime_inventory(platform='nt')
    assert not result['completed'] and result['error_type'] == 'TimeoutExpired'
    assert 15 <= result['elapsed_seconds'] < 18, result
    module.subprocess.run = real_run
    # Local read-only OS metadata only, measured separately; cold failure is not
    # converted into success by a subsequent empty result.
    actual = module.runtime_inventory(platform='nt')
    print('ACTUAL_WINDOWS_INVENTORY', json.dumps({k:v for k,v in actual.items() if k!='runtimes'}))
    assert actual['completed'], actual
print('INVENTORY_CHECKS_PASS: fail-closed timeout/query/correlation; no runtime/acquisition')
